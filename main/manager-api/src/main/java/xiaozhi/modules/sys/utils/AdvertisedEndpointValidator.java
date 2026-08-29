package xiaozhi.modules.sys.utils;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.Locale;
import java.util.Set;

import org.apache.commons.lang3.StringUtils;

/**
 * Validates endpoints that are advertised to devices.
 *
 * <p>These addresses are consumed from the device's network, so the manager API
 * must not try to connect to them while saving configuration. In particular, a
 * private address may intentionally point at a LAN gateway or SSH tunnel that
 * is unreachable from the server itself.</p>
 */
public final class AdvertisedEndpointValidator {
    private static final Set<String> HTTP_SCHEMES = Set.of("http", "https");
    private static final Set<String> WEBSOCKET_SCHEMES = Set.of("ws", "wss");

    private AdvertisedEndpointValidator() {
    }

    public static boolean isValidWebSocketList(String value) {
        if (StringUtils.isBlank(value)) {
            return false;
        }
        String[] endpoints = value.split(";", -1);
        if (endpoints.length == 0) {
            return false;
        }
        for (String endpoint : endpoints) {
            if (!isValidEndpoint(endpoint, WEBSOCKET_SCHEMES, false)) {
                return false;
            }
        }
        return true;
    }

    public static boolean isValidOtaUrl(String value) {
        if (StringUtils.isBlank(value) || "null".equalsIgnoreCase(value.trim())) {
            return true;
        }
        if (!isValidEndpoint(value, HTTP_SCHEMES, true)) {
            return false;
        }
        try {
            URI uri = new URI(value.trim());
            return uri.getRawQuery() == null
                    && uri.getRawPath() != null
                    && uri.getRawPath().endsWith("/ota/");
        } catch (URISyntaxException e) {
            return false;
        }
    }

    private static boolean isValidEndpoint(String value, Set<String> allowedSchemes, boolean requirePath) {
        if (StringUtils.isBlank(value) || !value.equals(value.trim())) {
            return false;
        }
        try {
            URI uri = new URI(value);
            String scheme = uri.getScheme();
            String host = normalizeHost(uri.getHost());
            if (scheme == null || !allowedSchemes.contains(scheme.toLowerCase(Locale.ROOT))) {
                return false;
            }
            if (StringUtils.isBlank(host) || uri.getRawAuthority() == null) {
                return false;
            }
            if (uri.getRawUserInfo() != null || uri.getRawFragment() != null) {
                return false;
            }
            int port = uri.getPort();
            if (port == 0 || port > 65535) {
                return false;
            }
            if (isUnspecifiedHost(host)) {
                return false;
            }
            return !requirePath || StringUtils.isNotBlank(uri.getRawPath());
        } catch (URISyntaxException | IllegalArgumentException e) {
            return false;
        }
    }

    private static String normalizeHost(String host) {
        if (host == null) {
            return null;
        }
        String normalized = host.toLowerCase(Locale.ROOT);
        if (normalized.startsWith("[") && normalized.endsWith("]")) {
            return normalized.substring(1, normalized.length() - 1);
        }
        return normalized;
    }

    private static boolean isUnspecifiedHost(String host) {
        return "0.0.0.0".equals(host)
                || "::".equals(host)
                || "0:0:0:0:0:0:0:0".equals(host);
    }
}
