/**
 * Resolution of `{{t:namespace.key}}` placeholders in docs markdown.
 *
 * WHY THIS FILE EXISTS. The resolution used to live entirely inside
 * `remark-resolve-translations.ts`, which runs in Astro's markdown pipeline. That covers
 * the rendered page and nothing else. `scripts/generate-search-index.js` reads the same
 * markdown files independently, and it had no idea the placeholders existed, so every
 * locale's search index shipped the raw pattern to readers: 2,122 of them per index,
 * identical in all 13, a docs search for "backup" returning a title reading literally
 * `{{t:cli.docs.sectionTitles.backup}}`. Built HTML carried ZERO, which is exactly why it
 * survived: the surface everyone looks at was clean and the one nobody looks at was not.
 *
 * So the resolution is now in one place and both consumers import it. `.mjs` rather than
 * `.ts` because the generator is run as `node scripts/generate-search-index.js` from
 * `astro.config.mjs`, so it cannot import TypeScript; `heading-anchors.mjs` next door
 * already established that a plain-ESM plugin module imports cleanly from both the `.js`
 * generator and a `.ts` test.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * CLI locales. The retired `packages/web` locale tree used to be probed first; it no
 * longer exists, so this is the only source.
 */
const CLI_LOCALES_PATH = path.resolve(__dirname, '../../../cli/src/i18n/locales');

/** Language assumed when a document declares none. */
export const DEFAULT_LANGUAGE = 'en';

/** The placeholder shape. Built fresh per call, never shared: see `hasTranslationKeys`. */
const pattern = () => /\{\{t:([a-zA-Z]+)\.([a-zA-Z0-9_.]+)\}\}/g;

/** namespace+lang -> parsed catalog, or null when the file does not exist. */
const translationCache = new Map();

/**
 * Load one namespace catalog for a language.
 *
 * @param {string} namespace
 * @param {string} lang
 * @returns {Record<string, unknown> | null}
 */
export function loadTranslationFile(namespace, lang) {
  const cacheKey = `${lang}/${namespace}`;
  if (translationCache.has(cacheKey)) return translationCache.get(cacheKey);

  const filePath = path.join(CLI_LOCALES_PATH, lang, `${namespace}.json`);
  if (fs.existsSync(filePath)) {
    try {
      const translations = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
      translationCache.set(cacheKey, translations);
      return translations;
    } catch {
      console.error(`Failed to load translation file: ${filePath}`);
    }
  }
  // Cache the miss too, so a docs tree full of one bad namespace does not re-stat per hit.
  translationCache.set(cacheKey, null);
  return null;
}

/**
 * Walk a dotted key path, e.g. `users.modals.createTitle`.
 *
 * @param {Record<string, unknown>} translations
 * @param {string} keyPath
 * @returns {string | null} the value only when it is a string; a branch is not a value.
 */
export function resolveKeyPath(translations, keyPath) {
  let current = translations;
  for (const key of keyPath.split('.')) {
    if (current === null || current === undefined || typeof current !== 'object') return null;
    current = current[key];
  }
  return typeof current === 'string' ? current : null;
}

/**
 * @param {string} namespace
 * @param {string} keyPath
 * @param {string} lang
 * @returns {string | null}
 */
export function getTranslation(namespace, keyPath, lang) {
  const translations = loadTranslationFile(namespace, lang);
  return translations ? resolveKeyPath(translations, keyPath) : null;
}

/**
 * Does this text contain a placeholder?
 *
 * Uses a NON-global regex on purpose. The caller-side `TRANSLATION_KEY_PATTERN.test(...)`
 * this replaces was a shared `/g` regex, so every `.test()` advanced `lastIndex` and the
 * old code had to reset it by hand at four call sites. A missed reset makes `.test()`
 * return false on a string that plainly matches, which is a silent skip, not an error.
 *
 * @param {string} text
 * @returns {boolean}
 */
export function hasTranslationKeys(text) {
  return /\{\{t:[a-zA-Z]+\.[a-zA-Z0-9_.]+\}\}/.test(text);
}

/**
 * Replace every placeholder in `text`.
 *
 * An unresolvable key is left VISIBLE rather than blanked, and warned about. Blanking
 * would turn a broken key into missing prose, which reads as intentional and is far harder
 * to notice than an ugly literal.
 *
 * @param {string} text
 * @param {string} lang
 * @param {string} [filePath] for the warning only
 * @returns {string}
 */
export function replaceTranslationKeys(text, lang, filePath) {
  return text.replace(pattern(), (match, namespace, keyPath) => {
    const resolved = getTranslation(namespace, keyPath, lang);
    if (resolved === null) {
      const location = filePath ? ` in ${filePath}` : '';
      console.warn(
        `[translation-keys] Translation key not found: ${namespace}.${keyPath} for language '${lang}'${location}`
      );
      return match;
    }
    return resolved;
  });
}

/**
 * Pull `language:` out of a frontmatter block.
 *
 * @param {string} content raw file text, frontmatter included
 * @returns {string}
 */
export function extractLanguageFromContent(content) {
  const frontmatterMatch = /^---\r?\n([\s\S]*?)\r?\n---/.exec(content);
  if (!frontmatterMatch) return DEFAULT_LANGUAGE;
  const languageMatch = /^language:\s*['"]?([a-z]{2})['"]?\s*$/m.exec(frontmatterMatch[1]);
  return languageMatch ? languageMatch[1] : DEFAULT_LANGUAGE;
}
