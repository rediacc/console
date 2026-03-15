/**
 * ESLint rule to enforce .summary() on Commander commands with long descriptions.
 * When a .description(t('KEY')) call resolves to text longer than the threshold,
 * the same method chain must also contain a .summary(t('ANY_KEY')) call.
 */

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/** Resolve a dot-separated key path in a nested object */
function resolveKey(obj, dotPath) {
  const parts = dotPath.split('.');
  let current = obj;
  for (const part of parts) {
    if (current == null || typeof current !== 'object') return null;
    current = current[part];
  }
  return typeof current === 'string' ? current : null;
}

/** Walk the left-nested Commander method chain looking for a .summary() call */
function hasSummaryInChain(node) {
  // node is the .description(...) CallExpression
  // Walk callee.object chain to find a .summary() call
  let current = node.callee.object; // object .description was called on
  while (current) {
    if (
      current.type === 'CallExpression' &&
      current.callee?.type === 'MemberExpression' &&
      current.callee.property?.name === 'summary'
    ) {
      return true;
    }
    current = current.callee?.object;
  }
  return false;
}

// Cache: cwd -> parsed locale JSON
const localeCache = new Map();

function loadLocale(cwd) {
  if (localeCache.has(cwd)) return localeCache.get(cwd);
  try {
    const localePath = resolve(cwd, 'packages/cli/src/i18n/locales/en/cli.json');
    const raw = readFileSync(localePath, 'utf8');
    const parsed = JSON.parse(raw);
    localeCache.set(cwd, parsed);
    return parsed;
  } catch {
    localeCache.set(cwd, null);
    return null;
  }
}

/** @type {import('eslint').Rule.RuleModule} */
export const requireCommandSummary = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Require .summary() on Commander commands whose description exceeds the character threshold',
      recommended: true,
    },
    schema: [],
    messages: {
      missingSummary:
        "Command description ({{length}} chars) exceeds 100 characters. Add .summary(t('KEY')) with a concise one-liner for human --help output.",
    },
  },

  create(context) {
    const threshold = 100;
    const cwd = context.cwd ?? process.cwd();
    const locale = loadLocale(cwd);

    return {
      CallExpression(node) {
        // Must be a .description(...) call
        if (
          node.callee.type !== 'MemberExpression' ||
          node.callee.property?.name !== 'description'
        ) {
          return;
        }

        // Argument must be t('KEY') — a CallExpression with Identifier callee named 't'
        const arg = node.arguments[0];
        if (
          !arg ||
          arg.type !== 'CallExpression' ||
          arg.callee?.type !== 'Identifier' ||
          arg.callee.name !== 't'
        ) {
          return;
        }

        // First argument to t() must be a string literal
        const keyArg = arg.arguments[0];
        if (!keyArg || keyArg.type !== 'Literal' || typeof keyArg.value !== 'string') {
          return;
        }

        const i18nKey = keyArg.value;

        // Resolve the key in the English locale
        if (!locale) return;
        const resolved = resolveKey(locale, i18nKey);
        if (!resolved) return;

        // Only flag if description exceeds threshold
        if (resolved.length <= threshold) return;

        // Check the chain for a .summary() call
        if (!hasSummaryInChain(node)) {
          context.report({
            node,
            messageId: 'missingSummary',
            data: {
              length: String(resolved.length),
            },
          });
        }
      },
    };
  },
};
