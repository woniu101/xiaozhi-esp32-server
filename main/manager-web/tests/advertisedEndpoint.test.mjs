import assert from 'node:assert/strict';
import test from 'node:test';

import {
  OTA_PARAM_CODE,
  WEBSOCKET_PARAM_CODE,
  classifyAdvertisedEndpoint,
  endpointScope,
  splitAdvertisedEndpoints,
  testAdvertisedEndpoint,
} from '../src/utils/advertisedEndpoint.mjs';

test('classifies loopback, LAN, public and listener addresses', () => {
  assert.equal(classifyAdvertisedEndpoint('http://127.0.0.1:8002/xiaozhi/ota/'), 'loopback');
  assert.equal(classifyAdvertisedEndpoint('ws://192.168.18.20:8000/xiaozhi/v1/'), 'lan');
  assert.equal(classifyAdvertisedEndpoint('ws://xiaozhi-gateway.lan:8000/xiaozhi/v1/'), 'lan');
  assert.equal(classifyAdvertisedEndpoint('wss://xiaozhi.example.com/xiaozhi/v1/'), 'public');
  assert.equal(classifyAdvertisedEndpoint('ws://0.0.0.0:8000/xiaozhi/v1/'), 'unspecified');
});

test('splits websocket alternatives and reports their effective scope', () => {
  const value = 'ws://192.168.1.2:8000/xiaozhi/v1/;wss://example.com/xiaozhi/v1/';
  assert.deepEqual(splitAdvertisedEndpoints(WEBSOCKET_PARAM_CODE, value), [
    'ws://192.168.1.2:8000/xiaozhi/v1/',
    'wss://example.com/xiaozhi/v1/',
  ]);
  assert.equal(endpointScope(WEBSOCKET_PARAM_CODE, value), 'lan');
  assert.equal(endpointScope(OTA_PARAM_CODE, 'http://localhost:8002/xiaozhi/ota/'), 'loopback');
  assert.equal(endpointScope(WEBSOCKET_PARAM_CODE, 'http://gateway.lan/xiaozhi/v1/'), 'invalid');
  assert.equal(endpointScope(OTA_PARAM_CODE, 'http://gateway.lan/xiaozhi/ota'), 'invalid');
  assert.equal(endpointScope(WEBSOCKET_PARAM_CODE, 'ws://gateway.lan/a;'), 'invalid');
});

test('uses a no-cors retry when an OTA response is reachable but hidden by CORS', async () => {
  const modes = [];
  const count = await testAdvertisedEndpoint(
    OTA_PARAM_CODE,
    'http://gateway.lan:8002/xiaozhi/ota/',
    {
      fetchImpl: async (url, options) => {
        modes.push(options.mode || 'cors');
        if (!options.mode) throw new TypeError('blocked by CORS');
        return { type: 'opaque' };
      },
      AbortControllerImpl: AbortController,
    },
  );
  assert.equal(count, 1);
  assert.deepEqual(modes, ['cors', 'no-cors']);
});

test('tests OTA from the caller context and verifies its response', async () => {
  let requestedUrl;
  const count = await testAdvertisedEndpoint(
    OTA_PARAM_CODE,
    'http://192.168.1.2:8002/xiaozhi/ota/',
    {
      fetchImpl: async url => {
        requestedUrl = url;
        return { ok: true, text: async () => 'Xiaozhi OTA service' };
      },
      AbortControllerImpl: AbortController,
    },
  );
  assert.equal(count, 1);
  assert.equal(requestedUrl, 'http://192.168.1.2:8002/xiaozhi/ota/');
});

test('tests every websocket alternative', async () => {
  const opened = [];
  class FakeWebSocket {
    constructor(url) {
      this.readyState = 0;
      opened.push(url);
      queueMicrotask(() => {
        this.readyState = 1;
        this.onopen();
      });
    }
    close() {
      this.readyState = 3;
    }
  }

  const count = await testAdvertisedEndpoint(
    WEBSOCKET_PARAM_CODE,
    'ws://gateway.lan:8000/a;ws://192.168.1.2:8000/b',
    { WebSocketImpl: FakeWebSocket },
  );
  assert.equal(count, 2);
  assert.equal(opened.length, 2);
});
