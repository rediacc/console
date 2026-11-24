/**
 * ESLint rule to ensure cross-language consistency in translation files.
 * Compares English (source of truth) keys with other language files.
 * Reports missing keys in each language.
 */

import fs from 'node:fs';
import path from 'node:path';
import { isPluralGroup } from './shared/plural-group.js';
import { resolveRequiredDirOption } from './shared/require-path-option.js';

// Cache for loaded locale data
const localeCache = new Map();

const PLURAL_CATEGORIES = ['zero', 'one', 'two', 'few', 'many', 'other'];

/**
 * The CLDR categories `Intl.PluralRules` selects in `lang`, which is the set i18next asks a flat plural for (`key_<category>`). Null when the runtime has no plural data for `lang`, so the caller reports it rather than guessing a set.
 */
const requiredPluralCategories = (lang) => {
  try {
    if (Intl.PluralRules.supportedLocalesOf([lang]).length === 0) return null;
    return new Intl.PluralRules(lang).resolvedOptions().pluralCategories;
  } catch {
    return null;
  }
};

/**
 * i18next flat plurals: `key_other` with `key_one`, `key_few` and the like beside it, the bare `key` standing in for `one` (i18next falls back to it when `key_<category>` is missing). Each locale holds the categories ITS `Intl.PluralRules` selects, so the forms are not compared against the source locale key by key. A stem is a flat plural when the source locale holds `<stem>_other`.
 */
const flatPluralStems = (sourceKeys) =>
  new Set(
    [...sourceKeys]
      .filter((key) => key.endsWith('_other'))
      .map((key) => key.slice(0, -'_other'.length))
  );

/** True when `key` is `<stem>_<category>` for one of `stems`. */
const isFlatPluralForm = (stems, key) => {
  const cut = key.lastIndexOf('_');
  return cut > 0 && PLURAL_CATEGORIES.includes(key.slice(cut + 1)) && stems.has(key.slice(0, cut));
};

/** Every [stem, category, key] form `lang` requires and `keys` lacks. The bare stem satisfies `one`. */
const missingPluralForms = (stems, keys, categories) =>
  [...stems].flatMap((stem) =>
    categories
      .filter(
        (category) => !keys.has(`${stem}_${category}`) && !(category === 'one' && keys.has(stem))
      )
      .map((category) => [stem, category, `${stem}_${category}`])
  );

/**
 * Get all supported language directories
 */
const getLanguageDirectories = (localesDir) => {
  try {
    const entries = fs.readdirSync(localesDir, { withFileTypes: true });
    return entries.filter((e) => e.isDirectory()).map((e) => e.name);
  } catch {
    return [];
  }
};

/**
 * Flatten a JSON object to get all leaf keys
 */
const flattenKeys = (obj, prefix = '', groups = new Set()) => {
  const keys = [];

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (isPluralGroup(value)) {
      // One leaf per group: locales hold different CLDR category sets by design.
      keys.push(fullPath);
      groups.add(fullPath);
    } else if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...flattenKeys(value, fullPath, groups));
    } else {
      keys.push(fullPath);
    }
  }

  return keys;
};

/** True when `key` is a plural group in the loaded locale keys. */
const isGroup = (keys, key) => keys.groups?.has(key) === true;

/**
 * Every [messageId, key] difference between the source locale's keys and another locale's. The forms of a flat plural (`stems`) are left out here; `missingPluralForms` checks them against each locale's own category set.
 */
const keySetFindings = (englishKeys, langKeys, stems = new Set()) => {
  const compared = (keys) => [...keys].filter((key) => !isFlatPluralForm(stems, key));
  return [
    ...compared(englishKeys)
      .filter((key) => !langKeys.has(key))
      .map((key) => ['missingInLanguage', key]),
    // Same leaf, different shape: a plural group on one side, a plain string on the other.
    ...compared(englishKeys)
      .filter((key) => langKeys.has(key) && isGroup(englishKeys, key) !== isGroup(langKeys, key))
      .map((key) => ['shapeMismatch', key]),
    ...compared(langKeys)
      .filter((key) => !englishKeys.has(key))
      .map((key) => ['extraInLanguage', key]),
  ];
};

/**
 * Load and flatten keys from a locale file
 */
const loadLocaleKeys = (filePath) => {
  if (localeCache.has(filePath)) {
    return localeCache.get(filePath);
  }

  try {
    const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
    const groups = new Set();
    const keys = new Set(flattenKeys(content, '', groups));
    // Which leaves are plural groups: a group against a plain string is a shape mismatch.
    keys.groups = groups;
    localeCache.set(filePath, keys);
    return keys;
  } catch {
    const keys = new Set();
    keys.groups = new Set();
    return keys;
  }
};

/** @type {import('eslint').Rule.RuleModule} */
export const crossLanguageConsistency = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Ensure all languages have the same translation keys as English',
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
          sourceLanguage: {
            type: 'string',
            default: 'en',
            description: 'Source language to compare against',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      missingInLanguage:
        'Key "{{key}}" exists in {{source}} but is missing in {{language}}. See docs/i18n/CONVENTIONS.md.',
      extraInLanguage:
        'Key "{{key}}" exists in {{language}} but not in {{source}} (source of truth). See docs/i18n/CONVENTIONS.md.',
      shapeMismatch:
        'Key "{{key}}" is a plural group in one of {{source}} and {{language}} and a plain string in the other. See docs/i18n/CONVENTIONS.md.',
      missingPluralForm:
        'Flat plural "{{stem}}" in {{language}} has no "{{key}}", and Intl.PluralRules selects "{{category}}" there (i18next would fall back to the bare key). Add the form. See docs/i18n/CONVENTIONS.md.',
      unknownPluralLocale:
        'Locale directory "{{language}}" has no Intl.PluralRules data, so its flat plural forms cannot be checked. Name the directory by a BCP 47 tag the runtime knows. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const sourceLanguage = options.sourceLanguage || 'en';

    // Resolve paths
    const absoluteLocalesDir = resolveRequiredDirOption(
      'i18n/cross-language-consistency',
      'localesDir',
      options.localesDir
    );

    // Get current file info
    const filename = context.filename;
    const namespace = path.basename(filename, '.json');
    const currentLang = path.basename(path.dirname(filename));

    // Only run on source language files (English)
    if (currentLang !== sourceLanguage) {
      return {};
    }

    // Get all language directories
    const languages = getLanguageDirectories(absoluteLocalesDir).filter(
      (lang) => lang !== sourceLanguage
    );

    /**
     * Report both directions of the key-set difference for one language.
     * Reports land on the Document node -- the offending key lives in another
     * file, so there is no position in this one to point at.
     */
    const reportKeySetDiff = (node, lang, englishKeys, langKeys, stems) => {
      const data = (key) => ({ key, source: sourceLanguage, language: lang });
      const report = (messageId, key) => context.report({ node, messageId, data: data(key) });
      for (const [messageId, key] of keySetFindings(englishKeys, langKeys, stems)) {
        report(messageId, key);
      }
    };

    /** Each flat plural form `lang` requires and lacks; the source locale itself goes through this too. */
    const reportPluralForms = (node, lang, keys, stems) => {
      if (stems.size === 0) return;
      const categories = requiredPluralCategories(lang);
      if (categories === null) {
        context.report({ node, messageId: 'unknownPluralLocale', data: { language: lang } });
        return;
      }
      for (const [stem, category, key] of missingPluralForms(stems, keys, categories)) {
        context.report({
          node,
          messageId: 'missingPluralForm',
          data: { stem, category, key, language: lang },
        });
      }
    };

    return {
      Document(node) {
        if (node.body?.type !== 'Object') return;

        // Get English keys from current file
        const englishFilePath = path.join(absoluteLocalesDir, sourceLanguage, `${namespace}.json`);
        const englishKeys = loadLocaleKeys(englishFilePath);
        const stems = flatPluralStems(englishKeys);
        reportPluralForms(node, sourceLanguage, englishKeys, stems);

        // Check each language
        for (const lang of languages) {
          const langFilePath = path.join(absoluteLocalesDir, lang, `${namespace}.json`);

          // Skip if language file doesn't exist
          if (!fs.existsSync(langFilePath)) {
            continue;
          }

          const langKeys = loadLocaleKeys(langFilePath);
          reportKeySetDiff(node, lang, englishKeys, langKeys, stems);
          reportPluralForms(node, lang, langKeys, stems);
        }
      },
    };
  },
};

export default crossLanguageConsistency;
