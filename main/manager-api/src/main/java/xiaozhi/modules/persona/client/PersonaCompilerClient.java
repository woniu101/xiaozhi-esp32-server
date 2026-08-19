package xiaozhi.modules.persona.client;

import java.net.ConnectException;
import java.net.URI;
import java.net.UnknownHostException;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;
import java.util.UUID;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import lombok.RequiredArgsConstructor;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.JsonUtils;
import xiaozhi.modules.sys.service.SysParamsService;

@Component
@RequiredArgsConstructor
public class PersonaCompilerClient {
    private static final HttpClient CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

    private final SysParamsService sysParamsService;

    @Value("${companion.compiler-url:http://127.0.0.1:8003}")
    private String compilerUrl;

    public Map<String, Object> inspect(Map<String, Object> payload) {
        return post("/internal/companion/persona/inspect", payload);
    }

    public Map<String, Object> compile(Map<String, Object> payload) {
        return post("/internal/companion/persona/compile", payload);
    }

    public Map<String, Object> test(Map<String, Object> payload) {
        return post("/internal/companion/persona/test", payload);
    }

    public Map<String, Object> info() {
        return post("/internal/companion/persona/compiler-info", Map.of());
    }

    public Map<String, Object> health() {
        return post("/internal/companion/health", Map.of());
    }

    private Map<String, Object> post(String path, Map<String, Object> payload) {
        String secret = sysParamsService.getValue(Constant.SERVER_SECRET, true);
        if (StringUtils.isBlank(secret)) {
            throw new RenException("server.secret 未配置，无法调用 Persona Compiler");
        }
        String body = JsonUtils.toJsonString(payload);
        String timestamp = String.valueOf(Instant.now().getEpochSecond());
        String nonce = UUID.randomUUID().toString().replace("-", "");
        String bodyHash = sha256(body.getBytes(StandardCharsets.UTF_8));
        String canonical = String.join("\n", timestamp, nonce, "POST", path, bodyHash);
        String signature = hmacSha256(secret, canonical);
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(StringUtils.removeEnd(compilerUrl, "/") + path))
                    .timeout(Duration.ofSeconds(45))
                    .header("Content-Type", "application/json")
                    .header("X-Companion-Timestamp", timestamp)
                    .header("X-Companion-Nonce", nonce)
                    .header("X-Companion-Signature", signature)
                    .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                    .build();
            HttpResponse<String> response = CLIENT.send(
                    request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            Map<String, Object> result = parseResponse(response.body());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                Object error = result == null ? null : result.get("error");
                String detail = safeText(error == null ? response.body() : String.valueOf(error));
                throw new RenException("Persona Compiler 返回 HTTP " + response.statusCode()
                        + (detail.isBlank() ? "" : "：" + detail));
            }
            if (result == null) {
                throw new RenException("Persona Compiler 返回了无法识别的响应");
            }
            return result;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new RenException("Persona Compiler 调用被中断", error);
        } catch (RenException error) {
            throw error;
        } catch (Exception error) {
            throw new RenException(unavailableMessage(error), error);
        }
    }

    private Map<String, Object> parseResponse(String body) {
        if (StringUtils.isBlank(body) || !StringUtils.trim(body).startsWith("{")) {
            return null;
        }
        try {
            return JsonUtils.parseMap(body);
        } catch (Exception ignored) {
            return null;
        }
    }

    private String unavailableMessage(Exception error) {
        Throwable root = rootCause(error);
        String endpoint = compilerEndpoint();
        if (root instanceof UnknownHostException) {
            return "无法解析 Persona Compiler 地址 " + endpoint
                    + "；本地开发请设置 COMPANION_COMPILER_URL=http://127.0.0.1:8003";
        }
        if (root instanceof ConnectException) {
            return "无法连接 Persona Compiler " + endpoint
                    + "；请先启动 xiaozhi-server 并确认 HTTP 8003 端口可达";
        }
        if (root instanceof HttpConnectTimeoutException || root instanceof HttpTimeoutException) {
            return "连接 Persona Compiler 超时 " + endpoint
                    + "；请检查 xiaozhi-server 状态和 COMPANION_COMPILER_URL";
        }
        return "Persona Compiler 不可用 " + endpoint
                + "；请检查 xiaozhi-server 的 8003 端口和 COMPANION_COMPILER_URL";
    }

    private String compilerEndpoint() {
        try {
            URI value = URI.create(StringUtils.defaultString(compilerUrl));
            int port = value.getPort();
            return value.getScheme() + "://" + value.getHost() + (port < 0 ? "" : ":" + port);
        } catch (Exception ignored) {
            return "（配置地址无效）";
        }
    }

    private static Throwable rootCause(Throwable error) {
        Throwable current = error;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        return current;
    }

    private static String safeText(String value) {
        String plain = StringUtils.defaultString(value)
                .replaceAll("<[^>]+>", " ")
                .replaceAll("[\\r\\n\\t]+", " ")
                .replaceAll("\\s{2,}", " ")
                .trim();
        return StringUtils.abbreviate(plain, 300);
    }

    private static String sha256(byte[] value) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }

    private static String hmacSha256(String secret, String value) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception error) {
            throw new IllegalStateException(error);
        }
    }
}
