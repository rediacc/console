/**
 * ESLint rule to enforce .summary() on Commander commands with long descriptions,
 * minimum description length for top-level commands, and maximum summary length.
 *
 * Checks:
 * 1. .description() > 100 chars must have a .summary() in the chain
 * 2. Top-level command .description() (commands.X.description) must be >= 100 chars
 * 3. .summary() text must be <= 100 chars
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

/**
 * Check if an i18n key is a top-level command description.
 * Top-level keys have the form: commands.X.description (3 parts)
 * Subcommand keys have the form: commands.X.Y.description (4+ parts)
 */
function isTopLevelCommandDescription(i18nKey) {
  const parts = i18nKey.split('.');
  return parts.length === 3 && parts[0] === 'commands' && parts[2] === 'description';
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

/** Extract the i18n key from a t('KEY') call expression argument */
function extractI18nKey(arg) {
  if (
    !arg ||
    arg.type !== 'CallExpression' ||
    arg.callee?.type !== 'Identifier' ||
    arg.callee.name !== 't'
  ) {
    return null;
  }
  const keyArg = arg.arguments[0];
  if (!keyArg || keyArg.type !== 'Literal' || typeof keyArg.value !== 'string') {
    return null;
  }
  return keyArg.value;
}

/** @type {import('eslint').Rule.RuleModule} */
export const requireCommandSummary = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Enforce .summary()/.description() length constraints on Commander commands for AI agent discovery',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          excludeFromMinDescription: {
            type: 'array',
            items: { type: 'string' },
            description: 'Command names to exclude from minimum description length check (e.g., experimental cloud-only commands)',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      missingSummary:
        "Command description ({{length}} chars) exceeds 100 characters. Add .summary(t('KEY')) with a concise one-liner for human --help output.",
      descriptionTooShort:
        'Top-level command description ({{length}} chars) is below {{min}} characters. Write a detailed description for AI agent discovery and add .summary() with the short version.',
      summaryTooLong:
        'Command summary ({{length}} chars) exceeds {{max}} characters. Keep .summary() concise for human --help output.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const excludeFromMinDescription = new Set(options.excludeFromMinDescription || []);
    const threshold = 100;
    const minDescription = 100;
    const maxSummary = 100;
    const cwd = context.cwd ?? process.cwd();
    const locale = loadLocale(cwd);

    return {
      CallExpression(node) {
        if (node.callee.type !== 'MemberExpression') return;

        const methodName = node.callee.property?.name;

        // Check .description(t('KEY')) calls
        if (methodName === 'description') {
          const i18nKey = extractI18nKey(node.arguments[0]);
          if (!i18nKey || !locale) return;

          const resolved = resolveKey(locale, i18nKey);
          if (!resolved) return;

          // Check 1: Long description must have .summary()
          if (resolved.length > threshold && !hasSummaryInChain(node)) {
            context.report({
              node,
              messageId: 'missingSummary',
              data: { length: String(resolved.length) },
            });
          }

          // Check 2: Top-level command description must be >= minDescription chars
          const cmdName = i18nKey.split('.')[1];
          if (isTopLevelCommandDescription(i18nKey) && resolved.length < minDescription && !excludeFromMinDescription.has(cmdName)) {
            context.report({
              node,
              messageId: 'descriptionTooShort',
              data: { length: String(resolved.length), min: String(minDescription) },
            });
          }
        }

        // Check .summary(t('KEY')) calls
        if (methodName === 'summary') {
          const i18nKey = extractI18nKey(node.arguments[0]);
          if (!i18nKey || !locale) return;

          const resolved = resolveKey(locale, i18nKey);
          if (!resolved) return;

          // Check 3: Summary must be <= maxSummary chars
          if (resolved.length > maxSummary) {
            context.report({
              node,
              messageId: 'summaryTooLong',
              data: { length: String(resolved.length), max: String(maxSummary) },
            });
          }
        }
      },
    };
  },
};
