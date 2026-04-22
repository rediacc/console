import path from 'node:path';
import {
  ROOT_DIR,
  getResources,
  getStringValue,
  hasPath,
  isNotTranslationKey,
  splitKey,
} from './translation-helpers.js';

/**
 * Validates that a string literal passed to a configured function (at a
 * configured argument index) exists as a key in the locale resources.
 *
 * Motivated by helpers like `errorResult(key: string)` that produce
 * translation-key-shaped strings eventually interpolated into a `t(...)`
 * template. The `require-translation` rule only matches `t()` calls, so
 * such indirect flows leak raw keys to users. This rule plugs the gap
 * by letting you declare those helpers as extra entry points.
 *
 * Config:
 *   ['error', {
 *     localeDir: 'packages/cli/src/i18n/locales/en',
 *     functions: [
 *       { name: 'errorResult', argIndex: 0 },
 *     ],
 *   }]
 */

/** @type {import('eslint').Rule.RuleModule} */
export const requireTranslationKeyArg = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Require string literals passed to configured helper functions to exist as translation keys.',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          localeDir: { type: 'string' },
          functions: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                name: { type: 'string' },
                argIndex: { type: 'integer', minimum: 0 },
              },
              required: ['name', 'argIndex'],
              additionalProperties: false,
            },
          },
        },
        required: ['localeDir', 'functions'],
        additionalProperties: false,
      },
    ],
    messages: {
      missingKey:
        'Missing translation key "{{key}}" passed to {{fn}}() — add it to the locale files or wrap the string in t().',
    },
  },

  create(context) {
    const options = context.options[0];
    if (!options) return {};

    const localeDir = path.resolve(ROOT_DIR, options.localeDir);
    const resources = getResources(localeDir);
    const targets = new Map();
    for (const fn of options.functions) {
      targets.set(fn.name, fn.argIndex);
    }

    return {
      CallExpression(node) {
        if (node.callee.type !== 'Identifier') return;
        const argIndex = targets.get(node.callee.name);
        if (argIndex === undefined) return;

        const argNode = node.arguments?.[argIndex];
        const keyValue = getStringValue(argNode);
        if (!keyValue) return;

        if (isNotTranslationKey(keyValue)) return;

        const { namespace, path: keyPath } = splitKey(keyValue);
        const segments = keyPath.split('.').filter(Boolean);
        if (segments.length === 0) return;

        const candidateNamespaces = namespace ? [namespace] : [...resources.keys()];
        const exists = candidateNamespaces.some((ns) => hasPath(resources.get(ns), segments));
        if (!exists) {
          context.report({
            node: argNode,
            messageId: 'missingKey',
            data: { key: keyValue, fn: node.callee.name },
          });
        }
      },
    };
  },
};
