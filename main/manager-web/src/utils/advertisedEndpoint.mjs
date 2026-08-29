export const OTA_PARAM_CODE = 'server.ota';
export const WEBSOCKET_PARAM_CODE = 'server.websocket';

export function isAdvertisedEndpointParam(paramCode) {
  return paramCode === OTA_PARAM_CODE || paramCode === WEBSOCKET_PARAM_CODE;
}

export function splitAdvertisedEndpoints(paramCode, value) {
  const raw = String(value || '').trim();
  if (!raw) return [];
  return paramCode === WEBSOCKET_PARAM_CODE
    ? raw.split(';').map(item => item.trim()).filter(Boolean)
    : [raw];
}

export function classifyAdvertisedEndpoint(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.replace(/^\[|\]$/g, '').toLowerCase();
    if (host === '0.0.0.0' || host === '::' || host === '0:0:0:0:0:0:0:0') {
      return 'unspecified';
    }
    if (host === 'localhost' || host === '::1' || host.startsWith('127.')) {
      return 'loopback';
    }
    if (isPrivateIpv4(host) || isPrivateIpv6(host) || isLanHostname(host)) {
      return 'lan';
    }
    return 'public';
  } catch (error) {
    return 'invalid';
  }
}

export function endpointScope(paramCode, value) {
  const original = String(value || '');
  const raw = original.trim();
  if (original !== raw) return 'invalid';
  if (paramCode === WEBSOCKET_PARAM_CODE
    && raw.split(';').some(item => !item.trim() || item !== item.trim())) {
    return 'invalid';
  }
  const endpoints = splitAdvertisedEndpoints(paramCode, value);
  const scopes = endpoints.map(endpoint => (
    isEndpointSyntaxValid(paramCode, endpoint) ? classifyAdvertisedEndpoint(endpoint) : 'invalid'
  ));
  if (!scopes.length) return 'empty';
  if (scopes.includes('invalid') || scopes.includes('unspecified')) {
    return scopes.includes('unspecified') ? 'unspecified' : 'invalid';
  }
  if (scopes.every(scope => scope === 'loopback')) return 'loopback';
  if (scopes.some(scope => scope === 'lan' || scope === 'loopback')) return 'lan';
  return 'public';
}

export async function testAdvertisedEndpoint(paramCode, value, dependencies = {}) {
  const endpoints = splitAdvertisedEndpoints(paramCode, value);
  if (!endpoints.length) throw new Error('empty');

  for (const endpoint of endpoints) {
    if (paramCode === OTA_PARAM_CODE) {
      await testOtaEndpoint(endpoint, dependencies);
    } else if (paramCode === WEBSOCKET_PARAM_CODE) {
      await testWebSocketEndpoint(endpoint, dependencies);
    } else {
      throw new Error('unsupported');
    }
  }
  return endpoints.length;
}

async function testOtaEndpoint(endpoint, dependencies) {
  const fetchImpl = dependencies.fetchImpl || globalThis.fetch;
  const AbortControllerImpl = dependencies.AbortControllerImpl || globalThis.AbortController;
  if (!fetchImpl || !AbortControllerImpl) throw new Error('unsupported');

  const controller = new AbortControllerImpl();
  const timeout = setTimeout(() => controller.abort(), 5000);
  try {
    let response;
    try {
      response = await fetchImpl(endpoint, {
        method: 'GET',
        cache: 'no-store',
        signal: controller.signal,
      });
    } catch (error) {
      if (controller.signal.aborted) throw error;
      // A cross-origin OTA service may be reachable without exposing its body
      // to JavaScript. A no-cors retry still verifies browser-level reachability.
      const opaqueResponse = await fetchImpl(endpoint, {
        method: 'GET',
        mode: 'no-cors',
        cache: 'no-store',
        signal: controller.signal,
      });
      if (opaqueResponse.type === 'opaque') return;
      throw error;
    }
    if (!response.ok) throw new Error('http-status');
    const body = await response.text();
    if (!body.includes('OTA')) throw new Error('unexpected-response');
  } finally {
    clearTimeout(timeout);
  }
}

function isEndpointSyntaxValid(paramCode, endpoint) {
  try {
    const url = new URL(endpoint);
    if (url.username || url.password || url.hash || url.port === '0') return false;
    if (paramCode === WEBSOCKET_PARAM_CODE) {
      return url.protocol === 'ws:' || url.protocol === 'wss:';
    }
    if (paramCode === OTA_PARAM_CODE) {
      return (url.protocol === 'http:' || url.protocol === 'https:')
        && !url.search
        && url.pathname.endsWith('/ota/');
    }
    return false;
  } catch (error) {
    return false;
  }
}

function testWebSocketEndpoint(endpoint, dependencies) {
  const WebSocketImpl = dependencies.WebSocketImpl || globalThis.WebSocket;
  if (!WebSocketImpl) return Promise.reject(new Error('unsupported'));

  return new Promise((resolve, reject) => {
    let settled = false;
    let socket;
    const finish = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeout);
      if (socket && (socket.readyState === 0 || socket.readyState === 1)) socket.close();
      if (error) reject(error);
      else resolve();
    };
    const timeout = setTimeout(() => finish(new Error('timeout')), 5000);
    try {
      socket = new WebSocketImpl(endpoint);
      socket.onopen = () => finish();
      socket.onerror = () => finish(new Error('connection'));
      socket.onclose = event => {
        if (!settled && !event.wasClean) finish(new Error('connection'));
      };
    } catch (error) {
      finish(error);
    }
  });
}

function isPrivateIpv4(host) {
  const parts = host.split('.').map(Number);
  if (parts.length !== 4 || parts.some(part => !Number.isInteger(part) || part < 0 || part > 255)) {
    return false;
  }
  return parts[0] === 10
    || (parts[0] === 172 && parts[1] >= 16 && parts[1] <= 31)
    || (parts[0] === 192 && parts[1] === 168)
    || (parts[0] === 169 && parts[1] === 254);
}

function isPrivateIpv6(host) {
  return /^f[cd][0-9a-f]{2}:/.test(host) || /^fe[89ab][0-9a-f]:/.test(host);
}

function isLanHostname(host) {
  return host.endsWith('.local') || host.endsWith('.lan') || (!host.includes('.') && !host.includes(':'));
}
