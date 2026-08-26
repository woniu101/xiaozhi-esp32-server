package xiaozhi.modules.characterstyle.source;

import java.io.IOException;
import java.io.InputStream;
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
    private static final int MAX_API_BYTES = 1024 * 1024;
    private static final int MAX_REFS_BYTES = 2 * 1024 * 1024;
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(8))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    @Value("${character-style.github-token:${CHARACTER_STYLE_GITHUB_TOKEN:}}")
    private String githubToken;

    public record SourceDescriptor(String owner, String repository, String ref, String sourceUrl) {
    }

    public record DownloadedSource(byte[] artifact, String sourceUrl, String sourceRef, String commit) {
    }

    public SourceDescriptor parse(String rawUrl, String requestedRef) {
        try {
            URI uri = URI.create(rawUrl.trim());
            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || !"github.com".equalsIgnoreCase(uri.getHost())
                    || uri.getPort() != -1
                    || uri.getUserInfo() != null
                    || uri.getQuery() != null
                    || uri.getFragment() != null) {
                throw new RenException("只允许不带端口、凭证、查询参数的 HTTPS GitHub 仓库地址");
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
            HttpRequest.Builder builder = HttpRequest.newBuilder(archive)
                    .timeout(Duration.ofSeconds(45))
                    .header("Accept", "application/zip")
                    .header("User-Agent", "xiaozhi-character-style-importer")
                    .GET();
            if (StringUtils.isNotBlank(githubToken)) {
                builder.header("Authorization", "Bearer " + githubToken.trim());
            }
            HttpResponse<InputStream> response = CLIENT.send(
                    builder.build(), HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() != 200) {
                response.body().close();
                throw new RenException("GitHub dot-skill 下载失败，HTTP " + response.statusCode());
            }
            byte[] artifact;
            try (InputStream input = response.body()) {
                artifact = readLimited(input, MAX_ARTIFACT_BYTES, "GitHub dot-skill ZIP");
            }
            return new DownloadedSource(artifact, source.sourceUrl(), source.ref(), commit);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new RenException("GitHub dot-skill 下载被中断", error);
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException("GitHub dot-skill 下载失败", error);
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
                    .header("User-Agent", "xiaozhi-character-style-importer");
            if (StringUtils.isNotBlank(githubToken)) {
                builder.header("Authorization", "Bearer " + githubToken.trim());
            }
            HttpResponse<InputStream> response = CLIENT.send(
                    builder.GET().build(), HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream input = response.body()) {
                if (response.statusCode() == 200) {
                    byte[] content = readLimited(input, MAX_API_BYTES, "GitHub API 响应");
                    Map<String, Object> data = JsonUtils.parseMap(
                            new String(content, StandardCharsets.UTF_8));
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
                    ? "；可配置 CHARACTER_STYLE_GITHUB_TOKEN 后重试"
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
                    .header("User-Agent", "xiaozhi-character-style-importer")
                    .GET()
                    .build();
            HttpResponse<InputStream> response = CLIENT.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            if (response.statusCode() != 200) {
                response.body().close();
                throw new RenException("Git refs 返回 HTTP " + response.statusCode());
            }
            byte[] advertisement;
            try (InputStream input = response.body()) {
                advertisement = readLimited(input, MAX_REFS_BYTES, "Git refs 响应");
            }
            String commit = parseAdvertisedRef(advertisement, source.ref());
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
        if (exact != null) {
            return exact;
        }
        String branch = refs.get("refs/heads/" + requestedRef);
        if (branch != null) {
            return branch;
        }
        String peeledTag = refs.get("refs/tags/" + requestedRef + "^{}");
        return peeledTag != null ? peeledTag : refs.get("refs/tags/" + requestedRef);
    }

    private static byte[] readLimited(InputStream input, int maximum, String label) throws IOException {
        byte[] value = input.readNBytes(maximum + 1);
        if (value.length == 0 || value.length > maximum) {
            throw new RenException(label + "为空或超过大小限制");
        }
        return value;
    }
}
