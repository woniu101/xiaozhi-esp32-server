import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const timbreApiSource = await readFile(
  new URL('../src/apis/module/timbre.js', import.meta.url),
  'utf8',
);
const ttsModelSource = await readFile(
  new URL('../src/components/TtsModel.vue', import.meta.url),
  'utf8',
);

test('timbre update sends the current sort value to the backend', () => {
  const updateStart = timbreApiSource.indexOf('updateVoice(params, callback)');

  assert.notEqual(updateStart, -1);
  const updateSource = timbreApiSource.slice(updateStart);
  assert.match(updateSource, /\.method\('PUT'\)/);
  assert.match(updateSource, /sort:\s*params\.sort/);
});

test('IndexTTS2.5 voice manager exposes remote lifecycle APIs', () => {
  assert.match(timbreApiSource, /getIndexRemoteVoices\(ttsModelId/);
  assert.match(timbreApiSource, /syncIndexRemoteVoices\(ttsModelId/);
  assert.match(timbreApiSource, /registerIndexVoice\(ttsModelId, formData/);
  assert.match(timbreApiSource, /deleteIndexVoice\(ttsModelId, voiceId/);
  assert.match(timbreApiSource, /previewIndexVoice\(ttsModelId, params/);
  assert.match(timbreApiSource, /\.type\('arraybuffer'\)/);
});

test('IndexTTS2.5 voice manager protects defaults and validates WAV uploads', () => {
  assert.match(ttsModelSource, /remote\.defaultVoice/);
  assert.match(ttsModelSource, /默认音色不能删除/);
  assert.match(ttsModelSource, /只能上传 WAV 参考音频/);
  assert.match(ttsModelSource, /20 \* 1024 \* 1024/);
  assert.match(ttsModelSource, /同步远端音色/);
  assert.match(ttsModelSource, /上传并注册音色/);
});

test('IndexTTS2.5 preview unlocks Web Audio before inference and validates WAV bytes', () => {
  assert.match(ttsModelSource, /window\.AudioContext \|\| window\.webkitAudioContext/);
  assert.match(ttsModelSource, /ensureIndexPreviewAudioContext\(\)\.then/);
  assert.match(ttsModelSource, /decodeAudioData/);
  assert.match(ttsModelSource, /=== 'RIFF'/);
  assert.match(ttsModelSource, /=== 'WAVE'/);
  assert.doesNotMatch(ttsModelSource, /new Audio\(/);
});
