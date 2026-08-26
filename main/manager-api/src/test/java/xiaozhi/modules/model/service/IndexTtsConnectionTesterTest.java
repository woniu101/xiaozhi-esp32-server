package xiaozhi.modules.model.service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import cn.hutool.json.JSONObject;

class IndexTtsConnectionTesterTest {

    private HttpServer server;

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void testsAllThreeEndpointsWithMinimalRequestContract() throws Exception {
        AtomicReference<String> requestBody = new AtomicReference<>();
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/health/ready", exchange -> respond(exchange, 200, "application/json",
                "{\"status\":\"ready\"}".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/v1/tts/stream", exchange -> {
            requestBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            exchange.getResponseHeaders().set("X-Audio-Format", "pcm_s16le_mono");
            exchange.getResponseHeaders().set("X-Sample-Rate", "24000");
            // A real stream is normally much larger than the diagnostic prefix.
            // Reading a valid first packet must not require buffering the whole response.
            respond(exchange, 200, "application/octet-stream", new byte[8192]);
        });
        server.createContext("/v1/tts", exchange -> {
            requestBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] wave = "RIFF\0\0\0\0WAVE".getBytes(StandardCharsets.US_ASCII);
            respond(exchange, 200, "audio/wav", wave);
        });
        server.start();

        JSONObject config = new JSONObject();
        config.set("api_url", "http://127.0.0.1:" + server.getAddress().getPort());
        config.set("voice", "test-voice");
        config.set("lang", "普通话");
        config.set("speed", 1.25);
        config.set("tts_timeout", 3);

        Map<String, Object> result = new IndexTtsConnectionTester().test(config);

        assertTrue((Boolean) result.get("allOk"));
        assertTrue(ok(result, "health"));
        assertTrue(ok(result, "wav"));
        assertTrue(ok(result, "stream"));
        assertNotNull(requestBody.get());
        assertTrue(requestBody.get().contains("\"voice_id\":\"test-voice\""));
        assertTrue(requestBody.get().contains("\"lang\":\"zh\""));
        assertFalse(requestBody.get().contains("emotion"));
    }

    @Test
    void invalidAddressReturnsIndependentFailedStates() {
        JSONObject config = new JSONObject();
        config.set("api_url", "file:///tmp/tts");

        Map<String, Object> result = new IndexTtsConnectionTester().test(config);

        assertFalse((Boolean) result.get("allOk"));
        assertFalse(ok(result, "health"));
        assertFalse(ok(result, "wav"));
        assertFalse(ok(result, "stream"));
    }

    @Test
    void normalizesServiceAndEndpointUrlsConsistently() {
        IndexTtsConnectionTester.EndpointSet endpoints = IndexTtsConnectionTester.normalizeEndpoints(
                "http://127.0.0.1:8092/v1/tts/stream/");

        assertEquals("http://127.0.0.1:8092/health/ready", endpoints.health().toString());
        assertEquals("http://127.0.0.1:8092/v1/tts", endpoints.wav().toString());
        assertEquals("http://127.0.0.1:8092/v1/tts/stream", endpoints.stream().toString());
    }

    @Test
    void doesNotTreatNotReadyTextAsAReadyHealthState() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/health/ready", exchange -> respond(exchange, 200, "application/json",
                "{\"status\":\"not ready\"}".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/v1/tts/stream", exchange -> {
            exchange.getResponseHeaders().set("X-Audio-Format", "pcm_s16le_mono");
            exchange.getResponseHeaders().set("X-Sample-Rate", "24000");
            respond(exchange, 200, "application/octet-stream", new byte[320]);
        });
        server.createContext("/v1/tts", exchange -> respond(exchange, 200, "audio/wav",
                "RIFF\0\0\0\0WAVE".getBytes(StandardCharsets.US_ASCII)));
        server.start();

        JSONObject config = new JSONObject();
        config.set("api_url", "http://127.0.0.1:" + server.getAddress().getPort());

        Map<String, Object> result = new IndexTtsConnectionTester().test(config);

        assertFalse((Boolean) result.get("allOk"));
        assertFalse(ok(result, "health"));
        assertTrue(ok(result, "wav"));
        assertTrue(ok(result, "stream"));
    }

    @SuppressWarnings("unchecked")
    private static boolean ok(Map<String, Object> result, String key) {
        return Boolean.TRUE.equals(((Map<String, Object>) result.get(key)).get("ok"));
    }

    private static void respond(HttpExchange exchange, int status, String contentType, byte[] body) throws IOException {
        exchange.getResponseHeaders().set("Content-Type", contentType);
        exchange.sendResponseHeaders(status, body.length);
        exchange.getResponseBody().write(body);
        exchange.close();
    }
}
