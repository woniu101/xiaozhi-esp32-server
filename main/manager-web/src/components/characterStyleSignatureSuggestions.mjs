const SIGNAL_WORDS = /(招牌|口头禅|固定问候|标志性表达|catchphrase|signature|greeting)/i;
const INLINE_CODE = /`([^`\r\n]{2,300})`/g;
const ASSISTANT_LINE = /^(?:\*\*)?(?:我|助手|assistant)(?:\*\*)?\s*[：:]\s*(.+)$/i;
const DECORATED_LATIN_PHRASE = /\b[A-Za-z][A-Za-z0-9_-]*(?:[~～][^\r\n]{1,120})/g;

function cleanCandidate(value) {
  return String(value || '')
    .replace(/<br\s*\/?>.*$/i, '')
    .replace(/^\s*["“”'‘’]+|["“”'‘’]+\s*$/g, '')
    .trim();
}

function isUsefulCandidate(value) {
  if (value.length < 2 || value.length > 300) return false;
  if (/^(?:https?:\/\/|\.\.\/|\.\/)/i.test(value)) return false;
  if (/\.(?:md|txt|json|ya?ml|wav|mp3)$/i.test(value)) return false;
  return !/[\r\n]/.test(value);
}

function stableId(value) {
  const ascii = value.match(/[A-Za-z][A-Za-z0-9_-]{1,40}/)?.[0]?.toLowerCase();
  if (ascii) return `signature_${ascii.replace(/[^a-z0-9_-]/g, '_')}`;
  let hash = 2166136261;
  for (const char of value) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `signature_${(hash >>> 0).toString(36)}`;
}

export function suggestSignaturesFromSkill(rawSkill) {
  if (typeof rawSkill !== 'string' || !rawSkill.trim()) return [];
  const lines = rawSkill.split(/\r?\n/);
  const candidates = [];
  let signalSectionLevel = null;

  const add = (rawValue, lineIndex, score) => {
    const displayText = cleanCandidate(rawValue);
    if (!isUsefulCandidate(displayText)) return;
    candidates.push({
      displayText,
      score,
      sourceExcerpt: lines[lineIndex].trim().slice(0, 260),
    });
  };

  lines.forEach((line, index) => {
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      if (SIGNAL_WORDS.test(heading[2])) signalSectionLevel = level;
      else if (signalSectionLevel !== null && level <= signalSectionLevel) signalSectionLevel = null;
    }
    const nearby = lines.slice(Math.max(0, index - 2), Math.min(lines.length, index + 3)).join('\n');
    const relevant = signalSectionLevel !== null || SIGNAL_WORDS.test(nearby);
    if (!relevant) return;

    for (const match of line.matchAll(INLINE_CODE)) {
      const decorated = /[~～★☆♡♥❤]/.test(match[1]);
      add(match[1], index, 10 + (decorated ? 5 : 0));
    }

    const assistant = line.match(ASSISTANT_LINE);
    if (assistant) {
      for (const match of assistant[1].matchAll(DECORATED_LATIN_PHRASE)) {
        add(match[0], index, 12);
      }
    }
  });

  const unique = new Map();
  for (const candidate of candidates) {
    const key = candidate.displayText.toLocaleLowerCase();
    const previous = unique.get(key);
    if (!previous || candidate.score > previous.score) unique.set(key, candidate);
  }
  const values = [...unique.values()];
  const filtered = values.filter(candidate => !values.some(other => {
    if (candidate === other || other.displayText.length <= candidate.displayText.length) return false;
    return other.displayText.toLocaleLowerCase().includes(candidate.displayText.toLocaleLowerCase())
      && other.score >= candidate.score;
  }));

  return filtered
    .sort((left, right) => right.score - left.score || right.displayText.length - left.displayText.length)
    .slice(0, 10)
    .map(candidate => ({
      id: stableId(candidate.displayText),
      displayText: candidate.displayText,
      aliases: [],
      sourceExcerpt: candidate.sourceExcerpt,
    }));
}
