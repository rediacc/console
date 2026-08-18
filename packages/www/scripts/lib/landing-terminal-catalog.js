import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { SITE_LOCALES } from '@rediacc/locales';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WWW_ROOT = path.resolve(__dirname, '../..');
const TRANSLATIONS_DIR = path.join(WWW_ROOT, 'src', 'i18n', 'translations');
const INDEX_PAGE_PATH = path.join(WWW_ROOT, 'src', 'pages', '[lang]', 'index.astro');

const LANGUAGES = SITE_LOCALES;

function normalizeCommandText(text) {
  return String(text ?? '')
    .trim()
    .replaceAll(/\s+/g, ' ');
}

function getCommandFromLine(line) {
  if (line?.type !== 'command') return null;

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
      if (line?.type !== 'command') continue;

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

function getHomepageTerminalCommands() {
  const src = fs.readFileSync(INDEX_PAGE_PATH, 'utf-8');
  const arrayMatch = /const\s+heroTerminalLines\s*=\s*\[(.*?)\];/s.exec(src);
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

/**
 * How many landing TERMINAL SOURCES exist, as distinct from how many COMMANDS they yield.
 *
 * The validator refuses on a zero command count, correctly: a landing page with no rdc
 * commands usually means the collector broke, and reporting success on an empty scan is the
 * exact failure this program keeps finding. But zero has two causes and they need opposite
 * responses. If a source EXISTS and yields nothing, the collector is broken. If no source
 * exists at all, there is genuinely nothing to validate, and that is a fact about the site.
 *
 * This became real when the homepage hero was rebuilt without its terminal demo and the
 * terminal blocks left the catalogs: both sources went to zero legitimately, and the gate
 * could not tell that apart from its own collector failing.
 */
export function countLandingTerminalSources(lang) {
  const src = fs.readFileSync(INDEX_PAGE_PATH, 'utf-8');
  const homepageArray = /const\s+heroTerminalLines\s*=\s*\[/.test(src);
  const terminals = [];
  visitTerminals(loadTranslationJson(lang), [], terminals);
  return { homepageArray, terminalBlocks: terminals.length };
}

export function getAllLanguages() {
  return [...LANGUAGES];
}
