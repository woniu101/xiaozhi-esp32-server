import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const addressBookSource = await readFile(
  new URL('../src/views/AddressBookManagement.vue', import.meta.url),
  'utf8',
);
const correctWordApiSource = await readFile(
  new URL('../src/apis/module/correctWord.js', import.meta.url),
  'utf8',
);
const functionDialogSource = await readFile(
  new URL('../src/components/FunctionDialog.vue', import.meta.url),
  'utf8',
);
const personaLibrarySource = await readFile(
  new URL('../src/views/PersonaLibrary.vue', import.meta.url),
  'utf8',
);
const roleConfigSource = await readFile(
  new URL('../src/views/roleConfig.vue', import.meta.url),
  'utf8',
);
const agentApiSource = await readFile(
  new URL('../src/apis/module/agent.js', import.meta.url),
  'utf8',
);

test('address-book permission state consistently uses the target device MAC', () => {
  assert.match(
    addressBookSource,
    /:value="selectedPermissions\.includes\(device\.deviceId\)"/,
  );
  assert.match(
    addressBookSource,
    /@change="\(checked\) => handlePermissionToggle\(device\.deviceId, checked\)"/,
  );
  assert.match(
    addressBookSource,
    /this\.selectedPermissions = this\.allDevices\.map\(d => d\.deviceId\)/,
  );
  assert.match(
    addressBookSource,
    /this\.originalPermissions\.includes\(device\.deviceId\)/,
  );
  assert.doesNotMatch(
    addressBookSource,
    /selectedPermissions\.includes\(device\.id\)/,
  );
  assert.doesNotMatch(
    addressBookSource,
    /originalPermissions\.includes\(device\.id\)/,
  );
  assert.match(
    addressBookSource,
    /requestId !== this\.permissionRequestSequence/,
  );
  assert.match(
    addressBookSource,
    /this\.selectedDevice\?\.deviceId !== macAddress/,
  );
  assert.match(
    addressBookSource,
    /this\.permissionsLoading = true;\s*this\.selectedPermissions = \[\];\s*this\.originalPermissions = \[\];/,
  );
  assert.match(
    addressBookSource,
    /handleSavePermissions\(\) \{\s*if \(this\.permissionsLoading\) return;/,
  );
});

test('correct-word pagination maps the UI page size to the backend limit query', () => {
  assert.match(
    correctWordApiSource,
    /new URLSearchParams\(\{\s*page: params\.page,\s*limit: params\.pageSize\s*\}\)/,
  );
  assert.doesNotMatch(correctWordApiSource, /pageSize: params\.pageSize/);
});

test('function dialog footer stays above the expanding MCP tools section', () => {
  const mcpLayer = functionDialogSource.match(
    /\.mcp-access-point\s*\{[^}]*z-index:\s*(\d+);/s,
  );
  const footerLayer = functionDialogSource.match(
    /\.drawer-footer\s*\{[^}]*z-index:\s*(\d+);/s,
  );

  assert.ok(mcpLayer, 'MCP section should define its stacking layer');
  assert.ok(footerLayer, 'drawer footer should define its stacking layer');
  assert.ok(Number(footerLayer[1]) > Number(mcpLayer[1]));
});

test('persona library only resumes active imports and uses a compact card banner', () => {
  assert.match(
    personaLibrarySource,
    /if \(activeJobId\) this\.resumeJob\(activeJobId\)/,
  );
  assert.match(
    personaLibrarySource,
    /TERMINAL_IMPORT_STATUSES\.includes\(job\.status\)[\s\S]*removeItem\('personaImportJobId'\)/,
  );
  assert.match(
    personaLibrarySource,
    /\.card-visual\s*\{[^}]*height:\s*60px;[^}]*flex:\s*0 0 60px;/s,
  );
});

test('companion role configuration preserves scoped state and legacy data', () => {
  assert.match(roleConfigSource, /\["vadModelId", "asrModelId", "llmModelId", "slmModelId", "vllmModelId", "intentModelId"\]/);
  assert.doesNotMatch(roleConfigSource, /slmModelId:\s*templateData\.llmModelId/);
  assert.match(roleConfigSource, /if \(value !== null && value !== undefined\) target\[key\] = value/);
  assert.match(roleConfigSource, /assign\(next, "chatHistoryConf", templateData\.chatHistoryConf\)/);
  assert.match(roleConfigSource, /form\.model\.memModelId === 'Memory_mem_local_short'/);
  assert.match(roleConfigSource, /Changing provider controls future behavior only/);
  assert.match(roleConfigSource, /templateScopes:\s*\["base"\]/);
  assert.match(agentApiSource, /\/legacy-memory\?confirmAgentId=/);
  assert.match(agentApiSource, /\/companion\/memories\/\$\{memoryId\}/);
});
