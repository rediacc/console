/**
 * ESLint rule to ensure translations have the same interpolation placeholders as English.
 * Reports when {{variable}} placeholders in translations don't match English.
 */

import fs from 'node:fs';
import path from 'node:path';
import { resolveRequiredDirOption } from './shared/require-path-option.js';
import { memberKey, objectMembers, joinPath } from './shared/json-ast.js';

// Cache for English translations
const englishCache = new Map();

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
      missingPlaceholder: 'Translation for "{{key}}" is missing placeholder: {{placeholder}}. English has: {{englishPlaceholders}}. Preserve all interpolation placeholders from English verbatim. See docs/i18n/CONVENTIONS.md.',
      extraPlaceholder: 'Translation for "{{key}}" has extra placeholder: {{placeholder}}. English has: {{englishPlaceholders}}. Preserve all interpolation placeholders from English verbatim. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    // Resolve paths
    const absoluteLocalesDir = resolveRequiredDirOption(
      'i18n/interpolation-consistency',
      'localesDir',
      options.localesDir,
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
     * Recursively check all values in a JSON object
     */
    /**
     * Compare one translated string's placeholder set against English.
     */
    const checkStringValue = (value, fullPath) => {
      const englishValue = englishTranslations.get(fullPath);
      if (!englishValue) return;

      const englishPlaceholders = extractPlaceholders(englishValue);
      const translationPlaceholders = extractPlaceholders(value.value);

      // Skip if English has no placeholders
      if (englishPlaceholders.size === 0) return;

      const englishStr = Array.from(englishPlaceholders).join(', ');

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

export default interpolationConsistency;
