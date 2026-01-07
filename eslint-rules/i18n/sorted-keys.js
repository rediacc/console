/**
 * ESLint rule to enforce alphabetically sorted keys in locale JSON files.
 * Supports auto-fix to sort keys automatically.
 */

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
      unsorted: 'Keys should be sorted alphabetically. "{{current}}" should come before "{{previous}}".',
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
      if (!node || node.type !== 'Object') return;

      const members = node.body?.members || [];
      const keys = [];

      for (const member of members) {
        if (member.type !== 'Member') continue;

        const key = member.name?.type === 'String'
          ? member.name.value
          : member.name?.name;

        if (key) {
          keys.push({
            key,
            node: member,
            fullPath: path ? `${path}.${key}` : key,
          });
        }

        // Recursively check nested objects
        if (member.value?.type === 'Object') {
          const fullPath = path ? `${path}.${key}` : key;
          checkObject(member.value, fullPath);
        }
      }

      // Check if keys are sorted
      for (let i = 1; i < keys.length; i++) {
        const prev = keys[i - 1];
        const curr = keys[i];

        if (naturalCompare(prev.key, curr.key) > 0) {
          context.report({
            node: curr.node,
            messageId: 'unsorted',
            data: {
              current: curr.key,
              previous: prev.key,
            },
            fix(fixer) {
              // Fix by sorting all keys in this object
              const sourceCode = context.sourceCode;
              const sortedMembers = [...members]
                .filter((m) => m.type === 'Member')
                .sort((a, b) => {
                  const keyA = a.name?.type === 'String' ? a.name.value : a.name?.name || '';
                  const keyB = b.name?.type === 'String' ? b.name.value : b.name?.name || '';
                  return naturalCompare(keyA, keyB);
                });

              // Get the text for each member
              const sortedTexts = sortedMembers.map((m) => sourceCode.getText(m));

              // Replace the entire object content
              const firstMember = members[0];
              const lastMember = members[members.length - 1];

              if (firstMember && lastMember) {
                return fixer.replaceTextRange(
                  [firstMember.range[0], lastMember.range[1]],
                  sortedTexts.join(',\n  ')
                );
              }
              return null;
            },
          });
          // Only report the first unsorted key to avoid noise
          break;
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

export default sortedKeys;
