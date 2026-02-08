/**
 * ESLint rule to ensure translations have the same interpolation placeholders as English.
 * Reports when {{variable}} placeholders in translations don't match English.
 */

import fs from 'node:fs';
import path from 'node:path';

// Cache for English translations
let englishCache = new Map();

/**
 * Extract all {{variable}} placeholders from a string
 */
const extractPlaceholders = (str) => {
  const matches = str.match(/\{\{[^}]+\}\}/g) || [];
  return new Set(matches.map(m => m.trim()));
};

/**
 * Flatten a JSON object to get key-value pairs
 */
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

/**
 * Load English translations for a namespace
 */
const loadEnglishTranslations = (localesDir, namespace) => {
  const cacheKey = `${localesDir}:${namespace}`;
  if (englishCache.has(cacheKey)) {
    return englishCache.get(cacheKey);
  }

  const englishFile = path.join(localesDir, 'en', `${namespace}.json`);
  try {
    const content = JSON.parse(fs.readFileSync(englishFile, 'utf-8'));
    const translations = new Map();

    for (const { key, value } of flattenToKeyValues(content)) {
      translations.set(key, value);
    }

    englishCache.set(cacheKey, translations);
    return translations;
  } catch {
    return new Map();
  }
};

/** @type {import('eslint').Rule.RuleModule} */
export const interpolationConsistency = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Ensure translations have the same interpolation placeholders as English',
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
      missingPlaceholder: 'Translation for "{{key}}" is missing placeholder: {{placeholder}}. English has: {{englishPlaceholders}}',
      extraPlaceholder: 'Translation for "{{key}}" has extra placeholder: {{placeholder}}. English has: {{englishPlaceholders}}',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const localesDir = options.localesDir || 'packages/web/src/i18n/locales';

    // Resolve paths
    const projectRoot = process.cwd();
    const absoluteLocalesDir = path.isAbsolute(localesDir)
      ? localesDir
      : path.join(projectRoot, localesDir);

    // Get current file info
    const filename = context.filename;
    const namespace = path.basename(filename, '.json');
    const currentLang = path.basename(path.dirname(filename));

    // Only run on non-English files
    if (currentLang === 'en') {
      return {};
    }

    // Load English translations
    const englishTranslations = loadEnglishTranslations(absoluteLocalesDir, namespace);

    /**
     * Recursively check all values in a JSON object
     */
    const checkObject = (node, prefix = '') => {
      if (!node || node.type !== 'Object') return;

      const members = node.members || [];

      for (const member of members) {
        if (member.type !== 'Member') continue;

        const key = member.name?.type === 'String'
          ? member.name.value
          : member.name?.name;

        if (!key) continue;

        const fullPath = prefix ? `${prefix}.${key}` : key;
        const value = member.value;

        if (value?.type === 'Object') {
          // Recursively check nested objects
          checkObject(value, fullPath);
        } else if (value?.type === 'String') {
          const strValue = value.value;
          const englishValue = englishTranslations.get(fullPath);

          if (!englishValue) continue;

          const englishPlaceholders = extractPlaceholders(englishValue);
          const translationPlaceholders = extractPlaceholders(strValue);

          // Skip if English has no placeholders
          if (englishPlaceholders.size === 0) continue;

          const englishArray = Array.from(englishPlaceholders);
          const englishStr = englishArray.join(', ');

          // Check for missing placeholders
          for (const placeholder of englishPlaceholders) {
            if (!translationPlaceholders.has(placeholder)) {
              context.report({
                node: value,
                messageId: 'missingPlaceholder',
                data: {
                  key: fullPath,
                  placeholder,
                  englishPlaceholders: englishStr,
                },
              });
            }
          }

          // Check for extra placeholders
          for (const placeholder of translationPlaceholders) {
            if (!englishPlaceholders.has(placeholder)) {
              context.report({
                node: value,
                messageId: 'extraPlaceholder',
                data: {
                  key: fullPath,
                  placeholder,
                  englishPlaceholders: englishStr,
                },
              });
            }
          }
        }
      }
    };

    return {
      Document(node) {
        if (node.body?.type === 'Object') {
          checkObject(node.body);
        }
      },
    };
  },
};

export default interpolationConsistency;
