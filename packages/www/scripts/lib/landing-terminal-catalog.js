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

/**
 * The CTA command block: `pages.{solutionPages,personaPages}.<key>.bottomCta.command`.
 *
 * THIS IS THE LANDING TERMINAL SURFACE TODAY. The `terminal.lines` blocks this file was
 * written for are gone from every catalog, and `heroTerminalLines` left index.astro with
 * the homepage reshape, so the collector was scanning two extinct shapes and finding
 * nothing. It reported that honestly ("no landing terminal sources exist") and exited 0,
 * which is the correct answer to the wrong question: the commands did not leave the site,
 * they MOVED. 23 of them render today, one per solution/persona page, in a copy-me code
 * block at the bottom of the page (SPBottomCta.astro:30-33).
 *
 * That is a stricter contract than the old animated terminal, not a looser one. A
 * decorative terminal demo could be abbreviated for rhythm; `bottomCta.command` is
 * presented as THE command to run, so an unrunnable one is a defect a reader hits
 * personally.
 */
function visitCtaCommands(node, pathParts, out) {
  if (!node || typeof node !== 'object') return;

  if (Array.isArray(node)) {
    for (let i = 0; i < node.length; i += 1) {
      visitCtaCommands(node[i], [...pathParts, `[${i}]`], out);
    }
    return;
  }

  for (const [key, value] of Object.entries(node)) {
    const nextPath = [...pathParts, key];
    if (key === 'bottomCta' && value && typeof value.command === 'string') {
      out.push({ path: `${nextPath.join('.')}.command`, command: value.command });
    }
    visitCtaCommands(value, nextPath, out);
  }
}

/** `solution:instantRecovery:bottomCta`, `persona:forDevops:bottomCta`, or a raw path. */
function sourceIdFromCtaPath(ctaPath) {
  const match = ctaPath.match(/^pages\.(solutionPages|personaPages)\.([^.]+)\.bottomCta\.command$/);
  if (!match) return `unknown:${ctaPath}`;
  const [, group, key] = match;
  return `${group === 'solutionPages' ? 'solution' : 'persona'}:${key}:bottomCta`;
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
  const ctas = [];
  visitCtaCommands(json, [], ctas);

  const results = [];
  for (const cta of ctas) {
    const commandText = normalizeCommandText(cta.command);
    results.push({
      lang,
      source: 'cta',
      sourcePath: cta.path,
      sourceId: sourceIdFromCtaPath(cta.path),
      lineIndex: 0,
      rawLine: { type: 'command', text: cta.command },
      commandText: commandText || null,
      isRdcCommand: commandText.startsWith('rdc '),
    });
  }

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
  const json = loadTranslationJson(lang);
  const terminals = [];
  visitTerminals(json, [], terminals);
  const ctas = [];
  visitCtaCommands(json, [], ctas);
  return { homepageArray, terminalBlocks: terminals.length, ctaCommands: ctas.length };
}

export function getAllLanguages() {
  return [...LANGUAGES];
}
