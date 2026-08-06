/**
 * ESLint rule to detect untranslated values in non-English locale files.
 * Reports values that are identical to their English counterparts.
 */

import fs from 'node:fs';
import path from 'node:path';
import { resolveRequiredDirOption } from './shared/require-path-option.js';
import { memberKey, objectMembers, joinPath } from './shared/json-ast.js';

// Cache for English translations
const englishCache = new Map();

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

/**
 * Check if a value looks like it needs translation
 * (contains letters, not just symbols/numbers)
 */
const needsTranslation = (value) => {
  // Must contain at least one letter
  if (!/[a-zA-Z]/.test(value)) {
    return false;
  }

  // Skip if it's ONLY interpolation variables
  if (/^\{\{[^}]+\}\}$/.test(value.trim())) {
    return false;
  }

  // Skip URLs and paths
  if (/^(https?:\/\/|\/)/.test(value)) {
    return false;
  }

  // Skip all-caps acronyms/abbreviations
  if (/^[A-Z_]+$/.test(value.trim())) {
    return false;
  }

  return true;
};

// Rule-option default: values shorter than this are too small to judge as
// "identical to English" (product names, "OK", punctuation).
const DEFAULT_MIN_LENGTH = 3;

/** @type {import('eslint').Rule.RuleModule} */
export const noUntranslatedValues = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Detect values that are identical to English (untranslated)',
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
          allowedPatterns: {
            type: 'array',
            items: { type: 'string' },
            description: 'Regex patterns for values that can remain untranslated',
          },
          minLength: {
            type: 'number',
            default: 3,
            description: 'Minimum string length to check',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      untranslated:
        'Value for key "{{key}}" is identical to English. Translate it naturally and idiomatically (not literal/word-for-word): "{{value}}". See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const allowedPatterns = (options.allowedPatterns || []).map((p) => new RegExp(p));
    const minLength = options.minLength ?? DEFAULT_MIN_LENGTH;

    // Resolve paths
    const absoluteLocalesDir = resolveRequiredDirOption(
      'i18n/no-untranslated-values',
      'localesDir',
      options.localesDir
    );

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
     * Check if a value matches any allowed pattern
     */
    const isAllowed = (value) => {
      return allowedPatterns.some((pattern) => pattern.test(value));
    };

    /**
     * Recursively check all values in a JSON object
     */
    const checkStringValue = (value, fullPath) => {
      const strValue = value.value;

      // Skip short strings
      if (strValue.length < minLength) return;

      // Skip if it doesn't need translation
      if (!needsTranslation(strValue)) return;

      // Skip allowed patterns
      if (isAllowed(strValue)) return;

      // Check if identical to English
      const englishValue = englishTranslations.get(fullPath);
      if (englishValue && strValue === englishValue) {
        context.report({
          node: value,
          messageId: 'untranslated',
          data: {
            key: fullPath,
            value: strValue.length > 50 ? `${strValue.slice(0, 47)}...` : strValue,
          },
        });
      }
    };

    const checkObject = (node, prefix = '') => {
      for (const member of objectMembers(node)) {
        if (member.type !== 'Member') continue;

        const key = memberKey(member);
        if (!key) continue;

        const fullPath = joinPath(prefix, key);
        const value = member.value;

        if (value?.type === 'Object') {
          // Recursively check nested objects
          checkObject(value, fullPath);
        } else if (value?.type === 'String') {
          checkStringValue(value, fullPath);
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

export default noUntranslatedValues;
