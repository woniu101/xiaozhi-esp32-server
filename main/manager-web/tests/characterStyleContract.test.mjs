import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const roleConfig = await readFile(
  new URL('../src/views/roleConfig.vue', import.meta.url),
  'utf8',
);
const stylePanel = await readFile(
  new URL('../src/components/CharacterStylePanel.vue', import.meta.url),
  'utf8',
);
const indexTest = await readFile(
  new URL('../src/components/IndexTtsConnectionTest.vue', import.meta.url),
  'utf8',
);
const modelApi = await readFile(
  new URL('../src/apis/module/model.js', import.meta.url),
  'utf8',
);
const addModelDialog = await readFile(
  new URL('../src/components/AddModelDialog.vue', import.meta.url),
  'utf8',
);
const editModelDialog = await readFile(
  new URL('../src/components/ModelEditDialog.vue', import.meta.url),
  'utf8',
);
const characterStyleApi = await readFile(
  new URL('../src/apis/module/characterStyle.js', import.meta.url),
  'utf8',
);

test('bound dot-skill preserves and disables the original role introduction', () => {
  assert.match(roleConfig, /:disabled="hasCharacterStyle"/);
  assert.match(roleConfig, /characterStyle\.rolePromptPreserved/);
  assert.match(roleConfig, /const preservedSystemPrompt = characterStyleId \? this\.form\.systemPrompt : ""/);
  assert.match(roleConfig, /if \(this\.hasCharacterStyle\) \{\s*this\.\$message\.warning/);
});

test('signature audio remains optional at both global and item level', () => {
  assert.match(stylePanel, /v-model="signatureConfig\.enabled"/);
  assert.match(stylePanel, /v-model="item\.enabled"/);
  assert.match(stylePanel, /characterStyle\.recordingUploadedDisabled/);
  assert.match(stylePanel, /characterStyle\.useCurrentTts/);
  assert.match(stylePanel, /item\.audio_path && !item\.enabled/);
  assert.match(stylePanel, /characterStyle\.signatureOwner/);
  assert.match(stylePanel, /v-model="selectedId"[^>]+@change="handleSignatureOwnerChange"/);
  assert.match(stylePanel, /updateSignatures\(\s*this\.detail\.id/);
  assert.match(stylePanel, /suggestSignaturesFromSkill/);
  assert.match(stylePanel, /characterStyle\.notUserTriggerHelp/);
  assert.match(stylePanel, /trialSignatureContext/);
  assert.match(characterStyleApi, /\/signatures\/trial/);
  assert.match(stylePanel, /items: \[\]/);
});

test('dot-skill import and update are explicit mutually exclusive modes', () => {
  assert.match(stylePanel, /v-model="importMode"/);
  assert.match(stylePanel, /label="create"/);
  assert.match(stylePanel, /label="update"/);
  assert.match(stylePanel, /v-if="importMode === 'update'"/);
  assert.match(stylePanel, /const styleId = this\.importMode === 'update'/);
  assert.match(stylePanel, /el-form-item__label \{ white-space: nowrap; \}/);
});

test('IndexTTS connection diagnostic reports all three independent endpoints', () => {
  assert.match(indexTest, /key: 'health'/);
  assert.match(indexTest, /key: 'wav'/);
  assert.match(indexTest, /key: 'stream'/);
  assert.match(modelApi, /\/models\/index-tts-v2-5\/test/);
  assert.match(modelApi, /data\(\{ configJson \}\)/);
});

test('IndexTTS streaming switch stays inline beside its label in the call-info grid', () => {
  for (const source of [addModelDialog, editModelDialog]) {
    assert.match(source, /class="index-streaming-inline"/);
    assert.match(source, /field\.prop === 'streaming'/);
    assert.match(source, /index-streaming-inline-item/);
    assert.doesNotMatch(source, /index-streaming-setting/);
    assert.ok(source.indexOf('class="index-streaming-inline"') < source.indexOf('<IndexTtsConnectionTest'));
  }
});
