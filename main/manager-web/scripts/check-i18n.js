const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const locales = [
  { name: 'zh_CN', file: 'src/i18n/zh_CN.js' },
  { name: 'zh_TW', file: 'src/i18n/zh_TW.js' },
  { name: 'en', file: 'src/i18n/en.js' },
  { name: 'de', file: 'src/i18n/de.js' },
  { name: 'vi', file: 'src/i18n/vi.js' },
  { name: 'pt_BR', file: 'src/i18n/pt_BR.js' },
];

function readLocale(locale, stack = new Set()) {
  const filePath = path.join(rootDir, locale.file);
  if (stack.has(filePath)) {
    throw new Error(`Circular i18n fallback import: ${filePath}`);
  }
  const nextStack = new Set(stack);
  nextStack.add(filePath);
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
  const keys = [];
  const seen = new Map();
  const duplicates = [];
  const imports = new Map();

  lines.forEach((line) => {
    const match = line.match(/^\s*import\s+([A-Za-z_$][\w$]*)\s+from\s+['"](\.\/.+?)['"];?\s*$/);
    if (match) imports.set(match[1], match[2]);
  });

  lines.forEach((line) => {
    const spread = line.match(/^\s*\.\.\.([A-Za-z_$][\w$]*)\s*,?\s*$/);
    if (!spread || !imports.has(spread[1])) return;
    const imported = imports.get(spread[1]);
    const importedFile = path.relative(rootDir, path.resolve(path.dirname(filePath), `${imported}.js`));
    const inherited = readLocale({ name: spread[1], file: importedFile }, nextStack);
    keys.push(...inherited.keys);
  });

  lines.forEach((line, index) => {
    const match = line.match(/^\s*['"]([^'"]+)['"]\s*:/);
    if (!match) {
      return;
    }

    const key = match[1];
    keys.push(key);
    if (!seen.has(key)) {
      seen.set(key, []);
    }
    seen.get(key).push(index + 1);
  });

  seen.forEach((lineNumbers, key) => {
    if (lineNumbers.length > 1) {
      duplicates.push({ key, lineNumbers });
    }
  });

  return {
    ...locale,
    filePath,
    keys,
    keySet: new Set(keys),
    duplicates,
  };
}

function diffKeys(left, right) {
  return [...left].filter((key) => !right.has(key)).sort();
}

function formatKeyList(keys) {
  return keys.length ? keys.map((key) => `    - ${key}`).join('\n') : '';
}

function main() {
  const results = locales.map((locale) => readLocale(locale));
  const base = results.find((locale) => locale.name === 'zh_CN');
  const errors = [];

  results.forEach((locale) => {
    locale.duplicates.forEach(({ key, lineNumbers }) => {
      errors.push(
        `${locale.file} has duplicate key "${key}" on lines ${lineNumbers.join(', ')}`
      );
    });
  });

  results
    .filter((locale) => locale !== base)
    .forEach((locale) => {
      const missing = diffKeys(base.keySet, locale.keySet);
      const extra = diffKeys(locale.keySet, base.keySet);

      if (missing.length) {
        errors.push(`${locale.file} is missing keys from ${base.file}:\n${formatKeyList(missing)}`);
      }

      if (extra.length) {
        errors.push(`${locale.file} has keys that do not exist in ${base.file}:\n${formatKeyList(extra)}`);
      }
    });

  if (errors.length) {
    console.error(`i18n check failed with ${errors.length} issue(s):`);
    console.error(errors.join('\n\n'));
    process.exit(1);
  }

  const keyCount = base.keySet.size;
  console.log(`i18n check passed: ${results.length} locale files, ${keyCount} keys each.`);
}

main();
