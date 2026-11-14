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

/** Every [messageId, key] difference between the source locale's keys and another locale's. */
const keySetFindings = (englishKeys, langKeys) => [
  ...[...englishKeys].filter((key) => !langKeys.has(key)).map((key) => ['missingInLanguage', key]),
  // Same leaf, different shape: a plural group on one side, a plain string on the other.
  ...[...englishKeys]
    .filter((key) => langKeys.has(key) && isGroup(englishKeys, key) !== isGroup(langKeys, key))
    .map((key) => ['shapeMismatch', key]),
  ...[...langKeys].filter((key) => !englishKeys.has(key)).map((key) => ['extraInLanguage', key]),
];

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
    const reportKeySetDiff = (node, lang, englishKeys, langKeys) => {
      const data = (key) => ({ key, source: sourceLanguage, language: lang });
      const report = (messageId, key) => context.report({ node, messageId, data: data(key) });
      for (const [messageId, key] of keySetFindings(englishKeys, langKeys)) report(messageId, key);
    };

    return {
      Document(node) {
        if (node.body?.type !== 'Object') return;

        // Get English keys from current file
        const englishFilePath = path.join(absoluteLocalesDir, sourceLanguage, `${namespace}.json`);
        const englishKeys = loadLocaleKeys(englishFilePath);

        // Check each language
        for (const lang of languages) {
          const langFilePath = path.join(absoluteLocalesDir, lang, `${namespace}.json`);

          // Skip if language file doesn't exist
          if (!fs.existsSync(langFilePath)) {
            continue;
          }

          reportKeySetDiff(node, lang, englishKeys, loadLocaleKeys(langFilePath));
        }
      },
    };
  },
};

export default crossLanguageConsistency;
