package xiaozhi.modules.persona.source;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;

@Component
public class GitHubSourceDownloader {
    private static final Pattern PART = Pattern.compile("^[A-Za-z0-9_.-]{1,100}$");
    private static final Pattern COMMIT = Pattern.compile("^[a-fA-F0-9]{40}$");
    private static final Pattern ADVERTISED_REF = Pattern.compile("([a-fA-F0-9]{40}) ([^\\x00\\r\\n ]+)");
    private static final int MAX_ARTIFACT_BYTES = 10 * 1024 * 1024;
    private static final int MAX_REFS_BYTES = 2 * 1024 * 1024;
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    @Value("${companion.github-token:${PERSONA_GITHUB_TOKEN:}}")
    private String githubToken;

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
        if (COMMIT.matcher(source.ref()).matches()) {
            return source.ref().toLowerCase();
        }
        URI endpoint = URI.create("https://api.github.com/repos/" + source.owner() + "/"
                + source.repository() + "/commits/" + source.ref());
        String apiFailure;
        try {
            HttpRequest.Builder builder = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(15))
                    .header("Accept", "application/vnd.github+json")
                    .header("User-Agent", "xiaozhi-companion-persona-importer");
            if (StringUtils.isNotBlank(githubToken)) {
                builder.header("Authorization", "Bearer " + githubToken.trim());
            }
            HttpRequest request = builder.GET().build();
            HttpResponse<String> response = CLIENT.send(
                    request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            if (response.statusCode() == 200) {
                Map<String, Object> data = JsonUtils.parseMap(response.body());
                String sha = data == null ? "" : String.valueOf(data.get("sha"));
                if (COMMIT.matcher(sha).matches()) {
                    return sha.toLowerCase();
                }
                apiFailure = "GitHub 返回的 commit 不合法";
            } else {
                String remaining = response.headers().firstValue("X-RateLimit-Remaining").orElse("");
                apiFailure = response.statusCode() == 403 && "0".equals(remaining)
                        ? "GitHub API 请求额度已耗尽"
                        : "GitHub API 返回 HTTP " + response.statusCode();
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new RenException("GitHub commit 解析被中断", error);
        } catch (Exception error) {
            apiFailure = "GitHub API 请求失败";
        }

        try {
            return resolveCommitFromGitRefs(source);
        } catch (RenException fallbackError) {
            String tokenHint = StringUtils.isBlank(githubToken)
                    ? "；可配置 PERSONA_GITHUB_TOKEN 后重试"
                    : "";
            throw new RenException(apiFailure + "，公开仓库 ref 降级解析也失败" + tokenHint, fallbackError);
        }
    }

    private String resolveCommitFromGitRefs(SourceDescriptor source) {
        URI endpoint = URI.create("https://github.com/" + source.owner() + "/"
                + source.repository() + ".git/info/refs?service=git-upload-pack");
        try {
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(20))
                    .header("Accept", "application/x-git-upload-pack-advertisement")
                    .header("Git-Protocol", "version=1")
                    .header("User-Agent", "xiaozhi-companion-persona-importer")
                    .GET()
                    .build();
            HttpResponse<byte[]> response = CLIENT.send(request, HttpResponse.BodyHandlers.ofByteArray());
            if (response.statusCode() != 200) {
                throw new RenException("Git refs 返回 HTTP " + response.statusCode());
            }
            if (response.body().length == 0 || response.body().length > MAX_REFS_BYTES) {
                throw new RenException("Git refs 响应为空或过大");
            }
            String commit = parseAdvertisedRef(response.body(), source.ref());
            if (commit == null) {
                throw new RenException("Git refs 中不存在 " + source.ref());
            }
            return commit;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new RenException("Git refs 解析被中断", error);
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException("Git refs 解析失败", error);
        }
    }

    static String parseAdvertisedRef(byte[] advertisement, String requestedRef) {
        String body = new String(advertisement, StandardCharsets.ISO_8859_1);
        Matcher matcher = ADVERTISED_REF.matcher(body);
        Map<String, String> refs = new LinkedHashMap<>();
        while (matcher.find()) {
            refs.put(matcher.group(2), matcher.group(1).toLowerCase());
        }
        if ("HEAD".equals(requestedRef)) {
            return refs.get("HEAD");
        }
        String exact = refs.get(requestedRef);
        if (exact != null) return exact;
        String branch = refs.get("refs/heads/" + requestedRef);
        if (branch != null) return branch;
        String peeledTag = refs.get("refs/tags/" + requestedRef + "^{}");
        return peeledTag != null ? peeledTag : refs.get("refs/tags/" + requestedRef);
    }
}
