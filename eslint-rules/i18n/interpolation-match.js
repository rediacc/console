/**
 * ESLint rule to validate interpolation variables in translation calls.
 * Ensures {{variable}} in translation strings match the variables passed to t() calls.
 */

import fs from 'node:fs';
import path from 'node:path';
import { resolveRequiredDirOption } from './shared/require-path-option.js';

// Cache for loaded translations
const translationCache = new Map();

// i18next option keys that are never interpolation variables.
const SPECIAL_T_OPTIONS = new Set(['count', 'context', 'defaultValue']);

/**
 * The namespace literal from one `const { t } = useTranslation('ns')` binding.
 * `undefined` means "no namespace here, keep looking" -- a Literal's value can
 * be null but never undefined, so it is a safe sentinel.
 */
const namespaceFromVariable = (variable) => {
  for (const def of variable.defs) {
    // Check if it's destructured from useTranslation
    if (def.node?.init?.callee?.name !== 'useTranslation') continue;
    const args = def.node.init.arguments;
    if (args && args.length > 0 && args[0].type === 'Literal') {
      return args[0].value;
    }
  }
  return undefined;
};

/** The namespace declared by a `t` binding in this scope, or undefined. */
const namespaceFromScope = (scope) => {
  for (const variable of scope.variables) {
    if (variable.name !== 't') continue;
    const namespace = namespaceFromVariable(variable);
    if (namespace !== undefined) return namespace;
  }
  return undefined;
};

/** The variable names passed in the options object of a t() call. */
const collectProvidedVars = (optionsArg) => {
  const providedVars = new Set();
  if (!optionsArg || optionsArg.type !== 'ObjectExpression') return providedVars;

  for (const prop of optionsArg.properties) {
    if (prop.type !== 'Property') continue;
    if (prop.key.type === 'Identifier') {
      providedVars.add(prop.key.name);
    } else if (prop.key.type === 'Literal') {
      providedVars.add(String(prop.key.value));
    }
  }
  return providedVars;
};

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
      missingVariable: 'Translation "{{key}}" expects variable "{{variable}}" but it was not provided in the t() call. See docs/i18n/CONVENTIONS.md.',
      extraVariable: 'Variable "{{variable}}" provided to t("{{key}}") but not used in the translation string. See docs/i18n/CONVENTIONS.md.',
      unknownKey: 'Translation key "{{key}}" not found in namespace "{{namespace}}". See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    // Resolve relative to project root
    const absoluteLocaleDir = resolveRequiredDirOption(
      'i18n-source/interpolation-match',
      'localeDir',
      options.localeDir,
    );

    const translations = loadTranslations(absoluteLocaleDir);

    /**
     * Parse useTranslation hook to get the namespace
     */
    const getNamespaceFromScope = (scope) => {
      // Look for useTranslation call in the component
      let currentScope = scope;
      while (currentScope) {
        const namespace = namespaceFromScope(currentScope);
        if (namespace !== undefined) return namespace;
        currentScope = currentScope.upper;
      }
      return 'common'; // Default namespace
    };

    // Check for missing variables
    const reportMissingVars = (expectedVars, providedVars, fullKey, reportNode) => {
      for (const expectedVar of expectedVars) {
        if (!providedVars.has(expectedVar)) {
          context.report({
            node: reportNode,
            messageId: 'missingVariable',
            data: {
              key: fullKey,
              variable: expectedVar,
            },
          });
        }
      }
    };

    // Check for extra variables (warning level - could be intentional)
    const reportExtraVars = (expectedVars, providedVars, fullKey, optionsArg) => {
      const expectedSet = new Set(expectedVars);
      for (const providedVar of providedVars) {
        // Skip common special keys like 'count' for pluralization
        if (SPECIAL_T_OPTIONS.has(providedVar)) continue;
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
        const optionsArg = node.arguments[1];
        const providedVars = collectProvidedVars(optionsArg);

        reportMissingVars(expectedVars, providedVars, fullKey, optionsArg || keyArg);
        reportExtraVars(expectedVars, providedVars, fullKey, optionsArg);
      },
    };
  },
};

export default interpolationMatch;
