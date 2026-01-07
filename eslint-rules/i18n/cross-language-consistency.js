/**
 * ESLint rule to ensure cross-language consistency in translation files.
 * Compares English (source of truth) keys with other language files.
 * Reports missing keys in each language.
 */

import fs from 'node:fs';
import path from 'node:path';

// Cache for loaded locale data
let localeCache = new Map();

/**
 * Get all supported language directories
 */
const getLanguageDirectories = (localesDir) => {
  try {
    const entries = fs.readdirSync(localesDir, { withFileTypes: true });
    return entries
      .filter((e) => e.isDirectory())
      .map((e) => e.name);
  } catch {
    return [];
  }
};

/**
 * Flatten a JSON object to get all leaf keys
 */
const flattenKeys = (obj, prefix = '') => {
  const keys = [];

  for (const [key, value] of Object.entries(obj)) {
    const fullPath = prefix ? `${prefix}.${key}` : key;

    if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
      keys.push(...flattenKeys(value, fullPath));
    } else {
      keys.push(fullPath);
    }
  }

  return keys;
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
    const keys = new Set(flattenKeys(content));
    localeCache.set(filePath, keys);
    return keys;
  } catch {
    return new Set();
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
      missingInLanguage: 'Key "{{key}}" exists in {{source}} but is missing in {{language}}.',
      extraInLanguage: 'Key "{{key}}" exists in {{language}} but not in {{source}} (source of truth).',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const localesDir = options.localesDir || 'packages/web/src/i18n/locales';
    const sourceLanguage = options.sourceLanguage || 'en';

    // Resolve paths
    const projectRoot = process.cwd();
    const absoluteLocalesDir = path.isAbsolute(localesDir)
      ? localesDir
      : path.join(projectRoot, localesDir);

    // Get current file info
    const filename = context.filename || context.getFilename();
    const namespace = path.basename(filename, '.json');
    const currentLang = path.basename(path.dirname(filename));

    // Only run on source language files (English)
    if (currentLang !== sourceLanguage) {
      return {};
    }

    // Get all language directories
    const languages = getLanguageDirectories(absoluteLocalesDir)
      .filter((lang) => lang !== sourceLanguage);

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

          const langKeys = loadLocaleKeys(langFilePath);

          // Find keys missing in this language
          for (const key of englishKeys) {
            if (!langKeys.has(key)) {
              // Report on the Document node since we can't pinpoint the exact location
              context.report({
                node,
                messageId: 'missingInLanguage',
                data: {
                  key,
                  source: sourceLanguage,
                  language: lang,
                },
              });
            }
          }

          // Find extra keys in this language (not in English)
          for (const key of langKeys) {
            if (!englishKeys.has(key)) {
              context.report({
                node,
                messageId: 'extraInLanguage',
                data: {
                  key,
                  source: sourceLanguage,
                  language: lang,
                },
              });
            }
          }
        }
      },
    };
  },
};

export default crossLanguageConsistency;
