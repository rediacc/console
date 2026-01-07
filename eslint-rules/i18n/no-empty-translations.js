/**
 * ESLint rule to prevent empty translation values in locale JSON files.
 * Detects: "", "   ", null values
 */

/** @type {import('eslint').Rule.RuleModule} */
export const noEmptyTranslations = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow empty translation values in locale files',
      recommended: true,
    },
    schema: [],
    messages: {
      emptyValue: 'Empty translation value for key "{{key}}". All translations must have content.',
      whitespaceOnly: 'Translation for key "{{key}}" contains only whitespace.',
      nullValue: 'Null translation value for key "{{key}}". Use a string value instead.',
    },
  },

  create(context) {
    /**
     * Recursively check all values in a JSON object
     * @param {object} node - AST node
     * @param {string} path - Current key path
     */
    const checkObject = (node, path = '') => {
      if (!node || node.type !== 'Object') return;

      for (const member of node.body?.members || []) {
        if (member.type !== 'Member') continue;

        const key = member.name?.type === 'String'
          ? member.name.value
          : member.name?.name;

        if (!key) continue;

        const fullPath = path ? `${path}.${key}` : key;
        const value = member.value;

        if (!value) continue;

        if (value.type === 'Object') {
          // Recursively check nested objects
          checkObject(value, fullPath);
        } else if (value.type === 'String') {
          const strValue = value.value;
          if (strValue === '') {
            context.report({
              node: value,
              messageId: 'emptyValue',
              data: { key: fullPath },
            });
          } else if (strValue.trim() === '') {
            context.report({
              node: value,
              messageId: 'whitespaceOnly',
              data: { key: fullPath },
            });
          }
        } else if (value.type === 'Null') {
          context.report({
            node: value,
            messageId: 'nullValue',
            data: { key: fullPath },
          });
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

export default noEmptyTranslations;
