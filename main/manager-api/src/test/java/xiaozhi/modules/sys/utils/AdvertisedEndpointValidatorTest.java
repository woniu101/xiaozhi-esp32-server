package xiaozhi.modules.sys.utils;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

class AdvertisedEndpointValidatorTest {

    @Test
    void acceptsEndpointsAdvertisedThroughALocalGateway() {
        assertTrue(AdvertisedEndpointValidator.isValidOtaUrl("http://127.0.0.1:8002/xiaozhi/ota/"));
        assertTrue(AdvertisedEndpointValidator.isValidOtaUrl("http://192.168.18.20:8002/xiaozhi/ota/"));
        assertTrue(AdvertisedEndpointValidator.isValidOtaUrl("https://xiaozhi-gateway.lan/xiaozhi/ota/"));

        assertTrue(AdvertisedEndpointValidator.isValidWebSocketList("ws://localhost:8000/xiaozhi/v1/"));
        assertTrue(AdvertisedEndpointValidator.isValidWebSocketList(
                "ws://192.168.18.20:8000/xiaozhi/v1/;wss://xiaozhi.example.com/xiaozhi/v1/"));
    }

    @Test
    void rejectsListenerAddressesThatClientsCannotDial() {
        assertFalse(AdvertisedEndpointValidator.isValidOtaUrl("http://0.0.0.0:8002/xiaozhi/ota/"));
        assertFalse(AdvertisedEndpointValidator.isValidWebSocketList("ws://[::]:8000/xiaozhi/v1/"));
    }

    @Test
    void rejectsInvalidSchemesPortsAndCredentials() {
        assertFalse(AdvertisedEndpointValidator.isValidOtaUrl("ftp://192.168.1.2/xiaozhi/ota/"));
        assertFalse(AdvertisedEndpointValidator.isValidWebSocketList("http://192.168.1.2:8000/xiaozhi/v1/"));
        assertFalse(AdvertisedEndpointValidator.isValidWebSocketList("ws://user:pass@host:8000/xiaozhi/v1/"));
        assertFalse(AdvertisedEndpointValidator.isValidWebSocketList("ws://host:70000/xiaozhi/v1/"));
    }

    @Test
    void requiresExactOtaPathAndCompleteWebSocketList() {
        assertFalse(AdvertisedEndpointValidator.isValidOtaUrl("http://host:8002/xiaozhi/ota"));
        assertFalse(AdvertisedEndpointValidator.isValidOtaUrl("http://host:8002/xiaozhi/ota/?token=x"));
        assertFalse(AdvertisedEndpointValidator.isValidWebSocketList("ws://host:8000/xiaozhi/v1/;"));
        assertFalse(AdvertisedEndpointValidator.isValidWebSocketList(""));
    }

    @Test
    void permitsAnUnconfiguredOtaEndpoint() {
        assertTrue(AdvertisedEndpointValidator.isValidOtaUrl(null));
        assertTrue(AdvertisedEndpointValidator.isValidOtaUrl("null"));
    }
}
