/**
 * ESLint rule to validate interpolation variables in translation calls.
 * Ensures {{variable}} in translation strings match the variables passed to t() calls.
 */

import fs from 'node:fs';
import path from 'node:path';

// Cache for loaded translations
let translationCache = new Map();

/**
 * Extract {{variable}} patterns from a string
 */
const extractInterpolationVars = (str) => {
  const matches = str.match(/\{\{(\w+)\}\}/g) || [];
  return matches.map((m) => m.slice(2, -2));
};

/**
 * Load all translations from locale directory
 */
const loadTranslations = (localeDir) => {
  if (translationCache.has(localeDir)) {
    return translationCache.get(localeDir);
  }

  const translations = {};

  try {
    const files = fs.readdirSync(localeDir);
    for (const file of files) {
      if (file.endsWith('.json')) {
        const namespace = file.replace('.json', '');
        const filePath = path.join(localeDir, file);
        const content = JSON.parse(fs.readFileSync(filePath, 'utf-8'));
        translations[namespace] = content;
      }
    }
  } catch {
    // Directory doesn't exist or other error
  }

  translationCache.set(localeDir, translations);
  return translations;
};

/**
 * Get value from nested object using dot notation key
 */
const getNestedValue = (obj, keyPath) => {
  const keys = keyPath.split('.');
  let current = obj;

  for (const key of keys) {
    if (current === null || current === undefined || typeof current !== 'object') {
      return undefined;
    }
    current = current[key];
  }

  return current;
};

/**
 * Get translation string for a given namespace and key
 */
const getTranslationString = (translations, namespace, key) => {
  const ns = translations[namespace];
  if (!ns) return null;

  const value = getNestedValue(ns, key);
  return typeof value === 'string' ? value : null;
};

/**
 * Parse translation key to extract namespace and key
 * Handles formats: "namespace:key.path" or "key.path" (uses default namespace)
 */
const parseTranslationKey = (fullKey, defaultNamespace = 'common') => {
  if (fullKey.includes(':')) {
    const [namespace, key] = fullKey.split(':');
    return { namespace, key };
  }
  return { namespace: defaultNamespace, key: fullKey };
};

/** @type {import('eslint').Rule.RuleModule} */
export const interpolationMatch = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Ensure interpolation variables in translations match t() call arguments',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          localeDir: {
            type: 'string',
            description: 'Path to the English locale directory',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      missingVariable: 'Translation "{{key}}" expects variable "{{variable}}" but it was not provided in the t() call.',
      extraVariable: 'Variable "{{variable}}" provided to t("{{key}}") but not used in the translation string.',
      unknownKey: 'Translation key "{{key}}" not found in namespace "{{namespace}}".',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const localeDir = options.localeDir || 'packages/web/src/i18n/locales/en';

    // Resolve relative to project root
    const projectRoot = process.cwd();
    const absoluteLocaleDir = path.isAbsolute(localeDir)
      ? localeDir
      : path.join(projectRoot, localeDir);

    const translations = loadTranslations(absoluteLocaleDir);

    /**
     * Parse useTranslation hook to get the namespace
     */
    const getNamespaceFromScope = (scope) => {
      // Look for useTranslation call in the component
      let currentScope = scope;
      while (currentScope) {
        for (const variable of currentScope.variables) {
          if (variable.name === 't') {
            for (const def of variable.defs) {
              // Check if it's destructured from useTranslation
              if (def.node?.init?.callee?.name === 'useTranslation') {
                const args = def.node.init.arguments;
                if (args && args.length > 0 && args[0].type === 'Literal') {
                  return args[0].value;
                }
              }
            }
          }
        }
        currentScope = currentScope.upper;
      }
      return 'common'; // Default namespace
    };

    return {
      CallExpression(node) {
        // Check if this is a t() call
        if (node.callee.type !== 'Identifier' || node.callee.name !== 't') {
          return;
        }

        // Get the first argument (translation key)
        const keyArg = node.arguments[0];
        if (!keyArg || keyArg.type !== 'Literal' || typeof keyArg.value !== 'string') {
          return; // Skip dynamic keys
        }

        const fullKey = keyArg.value;

        // Get default namespace from useTranslation hook
        const defaultNamespace = getNamespaceFromScope(context.sourceCode.getScope(node));

        // Parse the key to extract namespace and key path
        const { namespace, key: translationKey } = parseTranslationKey(fullKey, defaultNamespace);

        // Get the translation string
        const translationString = getTranslationString(translations, namespace, translationKey);

        if (translationString === null) {
          // Key not found - this is handled by require-translation rule
          return;
        }

        // Extract expected variables from translation string
        const expectedVars = extractInterpolationVars(translationString);

        // Extract provided variables from t() call
        const providedVars = new Set();
        const optionsArg = node.arguments[1];

        if (optionsArg && optionsArg.type === 'ObjectExpression') {
          for (const prop of optionsArg.properties) {
            if (prop.type === 'Property' && prop.key.type === 'Identifier') {
              providedVars.add(prop.key.name);
            } else if (prop.type === 'Property' && prop.key.type === 'Literal') {
              providedVars.add(String(prop.key.value));
            }
          }
        }

        // Check for missing variables
        for (const expectedVar of expectedVars) {
          if (!providedVars.has(expectedVar)) {
            context.report({
              node: optionsArg || keyArg,
              messageId: 'missingVariable',
              data: {
                key: fullKey,
                variable: expectedVar,
              },
            });
          }
        }

        // Check for extra variables (warning level - could be intentional)
        const expectedSet = new Set(expectedVars);
        for (const providedVar of providedVars) {
          // Skip common special keys like 'count' for pluralization
          if (providedVar === 'count' || providedVar === 'context' || providedVar === 'defaultValue') {
            continue;
          }
          if (!expectedSet.has(providedVar)) {
            context.report({
              node: optionsArg,
              messageId: 'extraVariable',
              data: {
                key: fullKey,
                variable: providedVar,
              },
            });
          }
        }
      },
    };
  },
};

export default interpolationMatch;
