/**
 * ESLint rule: CLI `--flag` names must be identical across languages.
 *
 * Flag names are part of the command-line contract, not prose — a user copies
 * `--current` verbatim regardless of UI language. Translators must never
 * translate, decline, or compound a flag token. The common failure is
 * agglutinating language-specific morphology onto the flag:
 *
 *   en:  "Rotate a sensitive value without --current."
 *   et:  "Pööra tundlik väärtus ilma --current-ita."   ← Estonian abessive case
 *   de:  "--current-Vorbedingung überspringen"          ← German compound
 *
 * `--current-ita` / `--current-Vorbedingung` are not flags the parser accepts.
 *
 * ## Detection
 *
 * Runs on non-`en` locale files only (the `en` source is validated for
 * non-existent flags by `no-undefined-cli-flags`). A `--token` in a translation
 * is reported when BOTH:
 *   1. it does not appear as a flag token in the English value for the same key
 *      (so flags shared with `en` — including any en bug — are never reported
 *      here), AND
 *   2. it is not a real registered option of any rdc command (so a translation
 *      that legitimately references a real flag the English string happened not
 *      to mention, e.g. `--editor`, is allowed).
 *
 * That intersection isolates exactly the mangled/invented tokens.
 *
 * Mirrors the cross-locale structure of `interpolation-consistency.js` and
 * reuses the valid-flag set from `no-undefined-cli-flags.js`.
 */

import fs from 'node:fs';
import path from 'node:path';
import { loadValidFlags } from './no-undefined-cli-flags.js';

const LEADING_TOKEN_CHARS = /^[('"`[]+/;
const TRAILING_TOKEN_CHARS = /[)'"`\].,;:!?]+$/;

const englishCache = new Map();

/** Extract the set of `--flag` tokens from a string (same tokenisation as the
 *  no-undefined-cli-flags rule). */
const extractFlags = (str) => {
  const set = new Set();
  for (const token of str.split(/\s+/)) {
    const cleaned = token
      .replace(LEADING_TOKEN_CHARS, '')
      .replace(TRAILING_TOKEN_CHARS, '');
    const m = cleaned.match(/^(--[a-z][a-z0-9-]*)/);
    if (m) set.add(m[1]);
  }
  return set;
};

const flattenToKeyValues = (obj, prefix = '') => {
  const pairs = [];
  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      pairs.push(...flattenToKeyValues(value, fullPath));
    } else if (typeof value === 'string') {
      pairs.push({ key: fullPath, value });
    }
  }
  return pairs;
};

const loadEnglishTranslations = (localesDir, namespace) => {
  const cacheKey = `${localesDir}:${namespace}`;
  if (englishCache.has(cacheKey)) return englishCache.get(cacheKey);
  const englishFile = path.join(localesDir, 'en', `${namespace}.json`);
  try {
    const content = JSON.parse(fs.readFileSync(englishFile, 'utf-8'));
    const translations = new Map();
    for (const { key, value } of flattenToKeyValues(content)) translations.set(key, value);
    englishCache.set(cacheKey, translations);
    return translations;
  } catch {
    return new Map();
  }
};

/** @type {import('eslint').Rule.RuleModule} */
export const cliFlagConsistency = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Ensure CLI --flag names in translations match the English source verbatim (no agglutination/translation of flag tokens).',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          localesDir: {
            type: 'string',
            description: 'Path to the locales directory',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      mangledFlag:
        'Translation for "{{key}}" contains CLI flag token `{{flag}}`, which is not a valid flag — it looks like a translated/declined/compounded form of an English flag. Flag names are part of the CLI contract and must appear verbatim. English flags for this key: {{englishFlags}}. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const localesDir = options.localesDir || 'packages/web/src/i18n/locales';
    const projectRoot = process.cwd();
    const absoluteLocalesDir = path.isAbsolute(localesDir)
      ? localesDir
      : path.join(projectRoot, localesDir);

    const namespace = path.basename(context.filename, '.json');
    const currentLang = path.basename(path.dirname(context.filename));
    if (currentLang === 'en') return {};

    const englishTranslations = loadEnglishTranslations(absoluteLocalesDir, namespace);
    const validFlags = loadValidFlags();

    const checkObject = (node, prefix = '') => {
      if (!node || node.type !== 'Object') return;
      for (const member of node.members || []) {
        if (member.type !== 'Member') continue;
        const key =
          member.name?.type === 'String' ? member.name.value : member.name?.name;
        if (!key) continue;
        const fullPath = prefix ? `${prefix}.${key}` : key;
        const value = member.value;

        if (value?.type === 'Object') {
          checkObject(value, fullPath);
        } else if (value?.type === 'String') {
          const englishValue = englishTranslations.get(fullPath);
          if (!englishValue) continue;
          const englishFlags = extractFlags(englishValue);
          const reported = new Set();
          for (const flag of extractFlags(value.value)) {
            if (englishFlags.has(flag)) continue; // shared with en → not the translator's doing
            if (validFlags.has(flag)) continue; // a real flag → allowed
            if (reported.has(flag)) continue;
            reported.add(flag);
            context.report({
              node: value,
              messageId: 'mangledFlag',
              data: {
                key: fullPath,
                flag,
                englishFlags: [...englishFlags].join(', ') || '(none)',
              },
            });
          }
        }
      }
    };

    return {
      Document(node) {
        if (node.body?.type === 'Object') checkObject(node.body);
      },
    };
  },
};

export default cliFlagConsistency;
