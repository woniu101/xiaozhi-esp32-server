package xiaozhi.modules.persona.source;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.commons.lang3.StringUtils;
import org.springframework.stereotype.Component;

import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;

@Component
public class GitHubSourceDownloader {
    private static final Pattern PART = Pattern.compile("^[A-Za-z0-9_.-]{1,100}$");
    private static final int MAX_ARTIFACT_BYTES = 10 * 1024 * 1024;
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    public record SourceDescriptor(String owner, String repository, String ref, String sourceUrl) {
    }

    public record DownloadedSource(byte[] artifact, String sourceUrl, String sourceRef, String commit) {
    }

    public SourceDescriptor parse(String rawUrl, String requestedRef) {
        try {
            URI uri = URI.create(rawUrl.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme()) || !"github.com".equalsIgnoreCase(uri.getHost())
                    || uri.getPort() != -1 || uri.getUserInfo() != null) {
                throw new RenException("第一版只允许不带端口和凭证的 HTTPS GitHub 仓库地址");
            }
            String[] parts = uri.getPath().replaceAll("^/+|/+$", "").split("/");
            if (parts.length < 2 || !PART.matcher(parts[0]).matches()) {
                throw new RenException("GitHub 仓库地址格式不正确");
            }
            String repository = parts[1].replaceFirst("\\.git$", "");
            if (!PART.matcher(repository).matches()) {
                throw new RenException("GitHub 仓库名称不合法");
            }
            String ref = StringUtils.defaultIfBlank(requestedRef, "HEAD");
            if (parts.length >= 4 && "tree".equals(parts[2]) && StringUtils.isBlank(requestedRef)) {
                ref = parts[3];
            }
            if (!ref.matches("^[A-Za-z0-9._/-]{1,200}$") || ref.contains("..")) {
                throw new RenException("GitHub ref 不合法");
            }
            return new SourceDescriptor(
                    parts[0], repository, ref,
                    "https://github.com/" + parts[0] + "/" + repository);
        } catch (IllegalArgumentException error) {
            throw new RenException("GitHub 仓库地址格式不正确", error);
        }
    }

    public DownloadedSource download(String rawUrl, String requestedRef) {
        SourceDescriptor source = parse(rawUrl, requestedRef);
        String commit = resolveCommit(source);
        URI archive = URI.create("https://codeload.github.com/" + source.owner() + "/"
                + source.repository() + "/zip/" + commit);
        try {
            HttpRequest request = HttpRequest.newBuilder(archive)
                    .timeout(Duration.ofSeconds(45))
                    .header("Accept", "application/zip")
                    .header("User-Agent", "xiaozhi-companion-persona-importer")
                    .GET()
                    .build();
            HttpResponse<byte[]> response = CLIENT.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() != 200) {
                throw new RenException("GitHub Persona 下载失败，HTTP " + response.statusCode());
            }
            byte[] artifact = response.body();
            if (artifact.length == 0 || artifact.length > MAX_ARTIFACT_BYTES) {
                throw new RenException("GitHub Persona ZIP 为空或超过 10MB 限制");
            }
            return new DownloadedSource(artifact, source.sourceUrl(), source.ref(), commit);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new RenException("GitHub Persona 下载被中断", error);
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException("GitHub Persona 下载失败", error);
        }
    }

    private String resolveCommit(SourceDescriptor source) {
        URI endpoint = URI.create("https://api.github.com/repos/" + source.owner() + "/"
                + source.repository() + "/commits/" + source.ref());
        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(15))
                    .header("Accept", "application/vnd.github+json")
                    .header("User-Agent", "xiaozhi-companion-persona-importer")
                    .GET()
                    .build();
            HttpResponse<String> response = CLIENT.send(
                    request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() != 200) {
                throw new RenException("无法解析 GitHub commit，HTTP " + response.statusCode());
            }
            Map<String, Object> data = JsonUtils.parseMap(response.body());
            String sha = data == null ? "" : String.valueOf(data.get("sha"));
            if (!sha.matches("^[a-fA-F0-9]{40}$")) {
                throw new RenException("GitHub 返回的 commit 不合法");
            }
            return sha;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new RenException("GitHub commit 解析被中断", error);
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException("无法解析 GitHub commit", error);
        }
    }
}
