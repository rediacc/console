import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WWW_ROOT = path.resolve(__dirname, '../..');
const TRANSLATIONS_DIR = path.join(WWW_ROOT, 'src', 'i18n', 'translations');
const INDEX_PAGE_PATH = path.join(WWW_ROOT, 'src', 'pages', '[lang]', 'index.astro');

const LANGUAGES = ['en', 'de', 'es', 'fr', 'ja', 'ar', 'ru', 'tr', 'zh'];

function normalizeCommandText(text) {
  return String(text || '')
    .trim()
    .replace(/\s+/g, ' ');
}

function getCommandFromLine(line) {
  if (!line || line.type !== 'command') return null;

  const assembled = [line.cmd, line.flag, line.value]
    .filter((value) => typeof value === 'string' && value.trim().length > 0)
    .join(' ')
    .trim();

  if (assembled) return normalizeCommandText(assembled);

  if (typeof line.text === 'string' && line.text.trim()) {
    return normalizeCommandText(line.text);
  }

  return null;
}

function visitTerminals(node, pathParts, out) {
  if (!node || typeof node !== 'object') return;

  if (Array.isArray(node)) {
    for (let i = 0; i < node.length; i += 1) {
      visitTerminals(node[i], [...pathParts, `[${i}]`], out);
    }
    return;
  }

  for (const [key, value] of Object.entries(node)) {
    const nextPath = [...pathParts, key];

    if (key === 'terminal' && value && Array.isArray(value.lines)) {
      out.push({ path: nextPath.join('.'), lines: value.lines });
    }

    visitTerminals(value, nextPath, out);
  }
}

function sourceIdFromTerminalPath(terminalPath, lineIndex) {
  const match = terminalPath.match(/^pages\.(solutionPages|personaPages)\.([^.]+)\.terminal$/);
  if (!match) return `unknown:${terminalPath}:line:${lineIndex}`;

  const [, group, key] = match;
  const section = group === 'solutionPages' ? 'solution' : 'persona';
  return `${section}:${key}:line:${lineIndex}`;
}

function loadTranslationJson(lang) {
  const filePath = path.join(TRANSLATIONS_DIR, `${lang}.json`);
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

export function getTranslationTerminalCommands(lang) {
  const json = loadTranslationJson(lang);
  const terminals = [];
  visitTerminals(json, [], terminals);

  const results = [];
  for (const terminal of terminals) {
    for (let i = 0; i < terminal.lines.length; i += 1) {
      const line = terminal.lines[i];
      if (!line || line.type !== 'command') continue;

      const commandText = getCommandFromLine(line);
      results.push({
        lang,
        source: 'translation',
        sourcePath: `${terminal.path}.lines[${i}]`,
        sourceId: sourceIdFromTerminalPath(terminal.path, i),
        lineIndex: i,
        rawLine: line,
        commandText,
        isRdcCommand: typeof commandText === 'string' && commandText.startsWith('rdc '),
      });
    }
  }

  return results;
}

function extractField(objText, key) {
  const match = objText.match(new RegExp(`${key}\\s*:\\s*'([^']*)'`));
  return match ? match[1] : '';
}

export function getHomepageTerminalCommands() {
  const src = fs.readFileSync(INDEX_PAGE_PATH, 'utf-8');
  const arrayMatch = src.match(/const\s+heroTerminalLines\s*=\s*\[(.*?)\];/s);
  if (!arrayMatch) return [];

  const body = arrayMatch[1];
  const objectMatches = [...body.matchAll(/\{[^{}]*type:\s*'command'[^{}]*\}/g)];

  return objectMatches.map((m, index) => {
    const objectText = m[0];
    const cmd = extractField(objectText, 'cmd');
    const flag = extractField(objectText, 'flag');
    const value = extractField(objectText, 'value');
    const text = extractField(objectText, 'text');

    const assembled = [cmd, flag, value].filter(Boolean).join(' ').trim();
    const commandText = normalizeCommandText(assembled || text);

    return {
      lang: 'all',
      source: 'homepage',
      sourcePath: `index.heroTerminalLines[${index}]`,
      sourceId: `homepage:hero:line:${index}`,
      lineIndex: index,
      rawLine: { type: 'command', cmd, flag, value, text },
      commandText: commandText || null,
      isRdcCommand: typeof commandText === 'string' && commandText.startsWith('rdc '),
    };
  });
}

export function getAllLandingTerminalCommandsForLanguage(lang) {
  const fromTranslations = getTranslationTerminalCommands(lang);
  if (lang !== 'en') return fromTranslations;
  return [...fromTranslations, ...getHomepageTerminalCommands()];
}

export function getAllLanguages() {
  return [...LANGUAGES];
}
