/**
 * ESLint rule to enforce alphabetically sorted keys in locale JSON files.
 * Supports auto-fix to sort keys automatically.
 */

import { memberKey, objectMembers, joinPath } from './shared/json-ast.js';

/**
 * Fixer that rewrites the whole object with its members in sorted order.
 */
const sortObjectFixer = (context, members, compare) => (fixer) => {
  const sourceCode = context.sourceCode;
  const sortedTexts = [...members]
    .filter((m) => m.type === 'Member')
    .sort((a, b) => compare(memberKey(a) || '', memberKey(b) || ''))
    .map((m) => sourceCode.getText(m));

  // Replace the entire object content
  const firstMember = members[0];
  const lastMember = members[members.length - 1];
  if (!firstMember || !lastMember) return null;

  return fixer.replaceTextRange(
    [firstMember.range[0], lastMember.range[1]],
    sortedTexts.join(',\n  ')
  );
};

/**
 * Report the FIRST out-of-order key in one object and stop -- reporting every
 * pair would bury the file in noise for a single misplaced key.
 */
const reportFirstUnsorted = (context, keys, members, compare) => {
  for (let i = 1; i < keys.length; i++) {
    const prev = keys[i - 1];
    const curr = keys[i];

    if (compare(prev.key, curr.key) <= 0) continue;

    context.report({
      node: curr.node,
      messageId: 'unsorted',
      data: {
        current: curr.key,
        previous: prev.key,
      },
      fix: sortObjectFixer(context, members, compare),
    });
    return;
  }
};

/** @type {import('eslint').Rule.RuleModule} */
export const sortedKeys = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Enforce alphabetically sorted keys in locale files',
      recommended: true,
    },
    fixable: 'code',
    schema: [
      {
        type: 'object',
        properties: {
          caseSensitive: {
            type: 'boolean',
            default: false,
          },
          natural: {
            type: 'boolean',
            default: true,
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      unsorted: 'Keys should be sorted alphabetically. "{{current}}" should come before "{{previous}}". See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const caseSensitive = options.caseSensitive === true;
    const natural = options.natural !== false;

    /**
     * Natural sort comparison (handles numbers correctly)
     */
    const naturalCompare = (a, b) => {
      return a.localeCompare(b, undefined, {
        numeric: natural,
        sensitivity: caseSensitive ? 'case' : 'base',
      });
    };

    /**
     * Check if an object's keys are sorted
     * @param {object} node - AST Object node
     * @param {string} path - Current path for error messages
     */
    const checkObject = (node, path = '') => {
      const members = objectMembers(node);
      const keys = [];

      for (const member of members) {
        if (member.type !== 'Member') continue;

        const key = memberKey(member);

        if (key) {
          keys.push({
            key,
            node: member,
            fullPath: joinPath(path, key),
          });
        }

        // Recursively check nested objects
        if (member.value?.type === 'Object') {
          checkObject(member.value, joinPath(path, key));
        }
      }

      reportFirstUnsorted(context, keys, members, naturalCompare);
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

export default sortedKeys;
