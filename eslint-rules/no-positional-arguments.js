/**
 * ESLint rule to ban positional arguments in Commander.js commands.
 * Enforces named options (.requiredOption / .option) instead of positional args
 * (.command('<arg>') or .argument()).
 *
 * Detects two patterns:
 * 1. .command('name <arg>') or .command('name [arg]') -- positional in command string
 * 2. .argument('<arg>') or .argument('[arg]') -- direct argument registration
 *
 * @example
 * // Bad -- positional argument
 * cmd.command('create <name>')
 * cmd.argument('<machine>')
 *
 * // Good -- named option
 * cmd.command('create').requiredOption('--name <name>', '...')
 * cmd.option('-m, --machine <name>', '...')
 */

import { resolve, relative } from 'node:path';

/** @type {import('eslint').Rule.RuleModule} */
export const noPositionalArguments = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow positional arguments in Commander.js commands. Use named options instead.',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          exemptFiles: {
            type: 'array',
            items: { type: 'string' },
            description:
              'File paths (relative to project root) exempt from this rule, e.g. experimental/cloud-only command files.',
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      noPositionalInCommand:
        'Positional argument in .command("{{value}}"). Use .requiredOption() or .option() instead.',
      noArgumentCall:
        '.argument() call detected. Use .option() or .requiredOption() instead.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const exemptFiles = options.exemptFiles || [];

    const cwd = context.cwd ?? process.cwd();
    const filename = context.filename ?? context.getFilename();
    const relPath = relative(cwd, resolve(filename)).replace(/\\/g, '/');

    const isExempt = exemptFiles.some((pattern) => {
      if (pattern.endsWith('/**')) {
        return relPath.startsWith(pattern.slice(0, -3));
      }
      return relPath === pattern;
    });

    if (isExempt) return {};

    return {
      CallExpression(node) {
        if (node.callee.type !== 'MemberExpression') return;

        const methodName = node.callee.property?.name;

        // Pattern 1: .command('name <arg>') or .command('name [arg]')
        if (methodName === 'command') {
          const arg = node.arguments[0];
          if (arg?.type === 'Literal' && typeof arg.value === 'string') {
            // Match <...> or [...] after the first word (command name itself)
            const afterName = arg.value.replace(/^\S+/, '');
            if (/<[^>]+>/.test(afterName) || /\[[^\]]+\]/.test(afterName)) {
              context.report({
                node,
                messageId: 'noPositionalInCommand',
                data: { value: arg.value },
              });
            }
          }
        }

        // Pattern 2: .argument(...)
        if (methodName === 'argument') {
          context.report({
            node,
            messageId: 'noArgumentCall',
          });
        }
      },
    };
  },
};
