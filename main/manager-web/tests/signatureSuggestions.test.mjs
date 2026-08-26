import assert from 'node:assert/strict';
import test from 'node:test';

import { suggestSignaturesFromSkill } from '../src/components/characterStyleSignatureSuggestions.mjs';

test('extracts the canonical rabbit greeting instead of a user trigger phrase', () => {
  const source = [
    '# 兔娘',
    '- 招牌点单：用户直接点名 `Ciallo`，或说“想听那个了”，可以回 `Ciallo～(∠・ω< )⌒★`。',
    '### 招牌点单',
    '**用户**：兔娘，想听那个了。',
    '**我**：哪个啊？你不说我怎么知——Ciallo～(∠・ω< )⌒★',
  ].join('\n');

  const suggestions = suggestSignaturesFromSkill(source);

  assert.equal(suggestions.length, 1);
  assert.equal(suggestions[0].displayText, 'Ciallo～(∠・ω< )⌒★');
  assert.equal(suggestions[0].id, 'signature_ciallo');
  assert.doesNotMatch(suggestions[0].displayText, /想听那个了/);
});

test('does not invent suggestions when the Skill has no signature evidence', () => {
  assert.deepEqual(
    suggestSignaturesFromSkill('# 日常交流\n请根据上下文自然回答。'),
    [],
  );
});
