package xiaozhi.modules.model.service;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

import org.springframework.stereotype.Service;

import cn.hutool.json.JSONObject;
import cn.hutool.json.JSONUtil;

@Service
public class IndexTtsConnectionTester {

    private static final int MAX_DIAGNOSTIC_BODY = 1024 * 1024;
    private static final int MAX_STREAM_PROBE = 4096;

    public Map<String, Object> test(JSONObject config) {
        EndpointSet endpoints;
        try {
            endpoints = normalizeEndpoints(stringValue(config, "api_url", "http://127.0.0.1:8092"));
        } catch (IllegalArgumentException error) {
            Map<String, Object> result = new LinkedHashMap<>();
            result.put("health", failed(error.getMessage()));
            result.put("wav", failed(error.getMessage()));
            result.put("stream", failed(error.getMessage()));
            result.put("allOk", false);
            return result;
        }

        double timeoutSeconds = finiteDouble(config == null ? null : config.get("tts_timeout"), 60.0, 1.0, 30.0);
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(Math.min(10, Math.max(1, (long) Math.ceil(timeoutSeconds)))))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
        String requestBody = buildRequestBody(config);

        Map<String, Object> health = probeHealth(client, endpoints.health(), Math.min(5.0, timeoutSeconds));
        Map<String, Object> wav = probeWav(client, endpoints.wav(), requestBody, timeoutSeconds);
        Map<String, Object> stream = probeStream(client, endpoints.stream(), requestBody, timeoutSeconds);

        Map<String, Object> result = new LinkedHashMap<>();
        result.put("health", health);
        result.put("wav", wav);
        result.put("stream", stream);
        result.put("allOk", isOk(health) && isOk(wav) && isOk(stream));
        return result;
    }

    static EndpointSet normalizeEndpoints(String value) {
        String raw = value == null ? "" : value.trim();
        while (raw.endsWith("/")) {
            raw = raw.substring(0, raw.length() - 1);
        }
        if (raw.endsWith("/v1/tts/stream")) {
            raw = raw.substring(0, raw.length() - "/stream".length());
        }
        String wavUrl = raw.endsWith("/v1/tts") ? raw : raw + "/v1/tts";
        URI wav = validateHttpUri(wavUrl);
        String serviceRoot = wavUrl.substring(0, wavUrl.length() - "/v1/tts".length());
        URI health = validateHttpUri(serviceRoot + "/health/ready");
        URI stream = validateHttpUri(wavUrl + "/stream");
        return new EndpointSet(health, wav, stream);
    }

    private static URI validateHttpUri(String value) {
        try {
            URI uri = URI.create(value);
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase(Locale.ROOT);
            if (!("http".equals(scheme) || "https".equals(scheme)) || uri.getHost() == null) {
                throw new IllegalArgumentException("API 地址必须是有效的 HTTP 或 HTTPS 地址");
            }
            if (uri.getUserInfo() != null || uri.getQuery() != null || uri.getFragment() != null) {
                throw new IllegalArgumentException("API 地址不得包含账号、查询参数或片段");
            }
            return uri;
        } catch (IllegalArgumentException error) {
            if (error.getMessage() != null && error.getMessage().startsWith("API 地址")) {
                throw error;
            }
            throw new IllegalArgumentException("API 地址格式无效", error);
        }
    }

    private Map<String, Object> probeHealth(HttpClient client, URI uri, double timeoutSeconds) {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(duration(timeoutSeconds))
                .header("Accept", "application/json")
                .GET()
                .build();
        return execute(client, request, MAX_DIAGNOSTIC_BODY, (status, body, _headers) -> {
            if (status < 200 || status >= 300) {
                return "健康检查返回 HTTP " + status;
            }
            String details = new String(body, StandardCharsets.UTF_8).trim();
            JSONObject payload = JSONUtil.parseObj(details);
            if (!"ready".equalsIgnoreCase(payload.getStr("status", ""))) {
                throw new IllegalStateException("健康检查未报告 ready 状态");
            }
            if (details.length() > 160) {
                details = details.substring(0, 160) + "…";
            }
            return details.isEmpty() ? null : "健康检查可用：" + details;
        });
    }

    private Map<String, Object> probeWav(HttpClient client, URI uri, String body, double timeoutSeconds) {
        HttpRequest request = postRequest(uri, body, timeoutSeconds, "audio/wav");
        return execute(client, request, MAX_DIAGNOSTIC_BODY, (status, bytes, _headers) -> {
            if (status < 200 || status >= 300) {
                return "普通合成返回 HTTP " + status;
            }
            if (bytes.length < 12 || !asciiEquals(bytes, 0, "RIFF") || !asciiEquals(bytes, 8, "WAVE")) {
                throw new IllegalStateException("普通合成未返回有效 WAV");
            }
            return "普通 WAV 可用（" + bytes.length + " 字节）";
        });
    }

    private Map<String, Object> probeStream(HttpClient client, URI uri, String body, double timeoutSeconds) {
        HttpRequest request = postRequest(uri, body, timeoutSeconds, "application/octet-stream");
        return execute(client, request, MAX_STREAM_PROBE, true, (status, bytes, headers) -> {
            if (status < 200 || status >= 300) {
                return "流式合成返回 HTTP " + status;
            }
            String format = headers.firstValue("X-Audio-Format").orElse("pcm_s16le_mono").toLowerCase(Locale.ROOT);
            if (!("pcm_s16le_mono".equals(format) || "pcm_s16le".equals(format))) {
                throw new IllegalStateException("流式音频格式不受支持：" + format);
            }
            int sampleRate;
            try {
                sampleRate = Integer.parseInt(headers.firstValue("X-Sample-Rate").orElse("22050"));
            } catch (NumberFormatException error) {
                throw new IllegalStateException("流式采样率无效", error);
            }
            if (sampleRate < 8000 || sampleRate > 192000 || bytes.length == 0) {
                throw new IllegalStateException(bytes.length == 0 ? "流式接口未返回音频首包" : "流式采样率无效");
            }
            return "流式接口可用（" + format + "，" + sampleRate + " Hz）";
        });
    }

    private Map<String, Object> execute(HttpClient client, HttpRequest request, int maxBytes, ResponseValidator validator) {
        return execute(client, request, maxBytes, false, validator);
    }

    private Map<String, Object> execute(
            HttpClient client,
            HttpRequest request,
            int maxBytes,
            boolean acceptPrefix,
            ResponseValidator validator) {
        long startedAt = System.nanoTime();
        try {
            HttpResponse<InputStream> response = client.send(request, HttpResponse.BodyHandlers.ofInputStream());
            byte[] body;
            try (InputStream input = response.body()) {
                body = input.readNBytes(maxBytes + 1);
            }
            if (body.length > maxBytes && !acceptPrefix) {
                throw new IllegalStateException("远端响应超过诊断读取上限");
            }
            if (body.length > maxBytes) {
                body = java.util.Arrays.copyOf(body, maxBytes);
            }
            String message = validator.validate(response.statusCode(), body, response.headers());
            boolean ok = response.statusCode() >= 200 && response.statusCode() < 300;
            return result(ok, response.statusCode(), elapsedMillis(startedAt), message == null ? "可用" : message);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            return result(false, null, elapsedMillis(startedAt), "连接测试已中断");
        } catch (IOException | RuntimeException error) {
            String message = error.getMessage() == null ? error.getClass().getSimpleName() : error.getMessage();
            return result(false, null, elapsedMillis(startedAt), message);
        }
    }

    private static HttpRequest postRequest(URI uri, String body, double timeoutSeconds, String accept) {
        return HttpRequest.newBuilder(uri)
                .timeout(duration(timeoutSeconds))
                .header("Content-Type", "application/json")
                .header("Accept", accept)
                .POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
                .build();
    }

    private static String buildRequestBody(JSONObject config) {
        JSONObject body = new JSONObject();
        body.set("request_id", UUID.randomUUID().toString().replace("-", ""));
        body.set("text", "你好，这是 IndexTTS2.5 连接测试。");
        body.set("voice_id", stringValue(config, "voice", "tuniang-normal"));
        body.set("lang", normalizeLanguage(stringValue(config, "lang", "zh")));
        body.set("speed", finiteDouble(config == null ? null : config.get("speed"), 1.0, 0.5, 2.0));
        body.set("text_normalization", true);
        return body.toString();
    }

    private static String normalizeLanguage(String value) {
        return switch (value.trim().toLowerCase(Locale.ROOT)) {
            case "中文", "普通话", "zh-cn" -> "zh";
            case "英语", "英文" -> "en";
            case "日语", "jp" -> "ja";
            case "韩语", "kr" -> "ko";
            default -> value.trim().toLowerCase(Locale.ROOT);
        };
    }

    private static String stringValue(JSONObject config, String key, String fallback) {
        Object value = config == null ? null : config.get(key);
        String text = value == null ? "" : String.valueOf(value).trim();
        return text.isEmpty() ? fallback : text;
    }

    private static double finiteDouble(Object value, double fallback, double minimum, double maximum) {
        try {
            double parsed = value == null ? fallback : Double.parseDouble(String.valueOf(value));
            if (!Double.isFinite(parsed)) {
                return fallback;
            }
            return Math.max(minimum, Math.min(maximum, parsed));
        } catch (NumberFormatException error) {
            return fallback;
        }
    }

    private static boolean asciiEquals(byte[] bytes, int offset, String expected) {
        if (bytes.length < offset + expected.length()) {
            return false;
        }
        for (int index = 0; index < expected.length(); index++) {
            if (bytes[offset + index] != (byte) expected.charAt(index)) {
                return false;
            }
        }
        return true;
    }

    private static Duration duration(double seconds) {
        return Duration.ofMillis(Math.max(1000L, Math.round(seconds * 1000.0)));
    }

    private static long elapsedMillis(long startedAt) {
        return Math.max(0, Math.round((System.nanoTime() - startedAt) / 1_000_000.0));
    }

    private static boolean isOk(Map<String, Object> result) {
        return Boolean.TRUE.equals(result.get("ok"));
    }

    private static Map<String, Object> failed(String message) {
        return result(false, null, 0L, message);
    }

    private static Map<String, Object> result(boolean ok, Integer statusCode, long latencyMs, String message) {
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("ok", ok);
        result.put("statusCode", statusCode);
        result.put("latencyMs", latencyMs);
        result.put("message", message);
        return result;
    }

    @FunctionalInterface
    private interface ResponseValidator {
        String validate(int status, byte[] body, java.net.http.HttpHeaders headers);
    }

    record EndpointSet(URI health, URI wav, URI stream) {
    }
}
