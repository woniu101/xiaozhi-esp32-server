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

test('IndexTTS2.5 voice manager exposes remote upload, sync, delete, and preview APIs', () => {
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
  assert.match(ttsModelSource, /class="index-voice-summary"/);
  assert.match(ttsModelSource, /grid-template-columns: 1fr minmax\(0, auto\) 1fr/);
  assert.match(ttsModelSource, /\.index-voice-summary \{\s*text-align: center;/);
});

test('IndexTTS2.5 preview unlocks Web Audio before inference and validates WAV bytes', () => {
  assert.match(ttsModelSource, /window\.AudioContext \|\| window\.webkitAudioContext/);
  assert.match(ttsModelSource, /ensureIndexPreviewAudioContext\(\)\.then/);
  assert.match(ttsModelSource, /decodeAudioData/);
  assert.match(ttsModelSource, /=== 'RIFF'/);
  assert.match(ttsModelSource, /=== 'WAVE'/);
});

test('IndexTTS2.5 preview action is rendered in the preview column', () => {
  const previewColumnStart = ttsModelSource.indexOf(
    '<el-table-column v-if="isIndexTts" :label="$t(\'ttsModel.preview\')"',
  );
  const regularPreviewColumnStart = ttsModelSource.indexOf(
    '<el-table-column v-else-if="!showReferenceColumns"',
    previewColumnStart,
  );
  const operationColumnStart = ttsModelSource.indexOf(
    '<el-table-column :label="$t(\'ttsModel.operation\')"',
  );
  const tableEnd = ttsModelSource.indexOf('</el-table>', operationColumnStart);

  assert.notEqual(previewColumnStart, -1);
  assert.notEqual(regularPreviewColumnStart, -1);
  assert.notEqual(operationColumnStart, -1);
  const previewColumnSource = ttsModelSource.slice(previewColumnStart, regularPreviewColumnStart);
  const operationColumnSource = ttsModelSource.slice(operationColumnStart, tableEnd);
  assert.match(previewColumnSource, /@click="previewIndexVoice\(scope\.row\)"/);
  assert.match(previewColumnSource, /播放中/);
  assert.doesNotMatch(operationColumnSource, /previewIndexVoice/);
  assert.match(operationColumnSource, /重新上传/);
});
