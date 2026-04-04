/**
 * ESLint rule to enforce SEO-friendly meta description lengths in translation JSON files.
 * Descriptions (keys matching *.meta.description) must be 50-160 characters.
 */

/** @type {import('eslint').Rule.RuleModule} */
export const seoDescriptionLength = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Enforce SEO-friendly meta description lengths (50-160 chars) in translation files',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          minLength: { type: 'number', default: 50 },
          maxLength: { type: 'number', default: 160 },
          exemptKeys: {
            type: 'array',
            items: { type: 'string' },
            default: [],
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      tooShort:
        'Description for key "{{key}}" is {{length}} chars (min {{min}}). Add more detail for search result snippets.',
      tooLong:
        'Description for key "{{key}}" is {{length}} chars (max {{max}}). Shorten to avoid truncation in search results.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const minLength = options.minLength ?? 50;
    const maxLength = options.maxLength ?? 160;
    const exemptKeys = options.exemptKeys || [];

    function isMetaDescriptionKey(path) {
      return path.endsWith('.meta.description');
    }

    function isExempt(path) {
      return exemptKeys.some((exempt) => path.includes(exempt));
    }

    const checkObject = (node, path = '') => {
      if (!node || node.type !== 'Object') return;

      for (const member of node.members || []) {
        if (member.type !== 'Member') continue;

        const key =
          member.name?.type === 'String' ? member.name.value : member.name?.name;
        if (!key) continue;

        const fullPath = path ? `${path}.${key}` : key;
        const value = member.value;
        if (!value) continue;

        if (value.type === 'Object') {
          checkObject(value, fullPath);
        } else if (value.type === 'String' && isMetaDescriptionKey(fullPath) && !isExempt(fullPath)) {
          const str = value.value;
          const rendered = str.replace(/\{\{[^}]+\}\}/g, 'placeholder');
          const len = rendered.length;

          if (len < minLength) {
            context.report({
              node: value,
              messageId: 'tooShort',
              data: { key: fullPath, length: String(len), min: String(minLength) },
            });
          } else if (len > maxLength) {
            context.report({
              node: value,
              messageId: 'tooLong',
              data: { key: fullPath, length: String(len), max: String(maxLength) },
            });
          }
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

export default seoDescriptionLength;
