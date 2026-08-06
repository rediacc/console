import { memberKey, objectMembers, joinPath } from './shared/json-ast.js';

/**
 * ESLint rule to enforce SEO-friendly title lengths in translation JSON files.
 * Titles (keys matching *.meta.title) must be 30-60 characters.
 */

// Rule-option defaults: the SERP display window for a page title.
// Below the minimum the title carries no keywords; above it Google truncates.
const DEFAULT_MIN_LENGTH = 30;
const DEFAULT_MAX_LENGTH = 60;

/** @type {import('eslint').Rule.RuleModule} */
export const seoTitleLength = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Enforce SEO-friendly title lengths (30-60 chars) in translation files',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          minLength: { type: 'number', default: 30 },
          maxLength: { type: 'number', default: 60 },
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
        'Title "{{value}}" for key "{{key}}" is {{length}} chars (min {{min}}). Expand with descriptive keywords. See docs/i18n/CONVENTIONS.md.',
      tooLong:
        'Title "{{value}}" for key "{{key}}" is {{length}} chars (max {{max}}). Shorten to fit search result display. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const minLength = options.minLength ?? DEFAULT_MIN_LENGTH;
    const maxLength = options.maxLength ?? DEFAULT_MAX_LENGTH;
    const exemptKeys = options.exemptKeys || [];

    /**
     * Check if a key path ends with "meta.title" (page title pattern)
     */
    function isMetaTitleKey(path) {
      return path.endsWith('.meta.title');
    }

    /**
     * Check if a key is exempt from validation
     */
    function isExempt(path) {
      return exemptKeys.some((exempt) => path.includes(exempt));
    }

    /**
     * Recursively walk the JSON AST checking title values
     */
    const checkValue = (value, fullPath) => {
      if (value.type === 'Object') {
        checkObject(value, fullPath);
        return;
      }
      if (value.type !== 'String') return;
      if (!isMetaTitleKey(fullPath) || isExempt(fullPath)) return;

      const str = value.value;
      // Skip interpolation-heavy titles (e.g., "{{companyName}}")
      const rendered = str.replaceAll(/\{\{[^}]+\}\}/g, 'placeholder');
      const len = rendered.length;

      if (len < minLength) {
        context.report({
          node: value,
          messageId: 'tooShort',
          data: { value: str, key: fullPath, length: String(len), min: String(minLength) },
        });
      } else if (len > maxLength) {
        context.report({
          node: value,
          messageId: 'tooLong',
          data: { value: str, key: fullPath, length: String(len), max: String(maxLength) },
        });
      }
    };

    const checkObject = (node, path = '') => {
      for (const member of objectMembers(node)) {
        if (member.type !== 'Member') continue;

        const key = memberKey(member);
        const value = member.value;
        if (!key || !value) continue;

        checkValue(value, joinPath(path, key));
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

export default seoTitleLength;
