import { memberKey, objectMembers, joinPath } from './shared/json-ast.js';

/**
 * ESLint rule to enforce SEO-friendly meta description lengths in translation JSON files.
 * Descriptions (keys matching *.meta.description) must be 50-160 characters.
 */

// Rule-option defaults: the SERP snippet window for a meta description.
// Below the minimum the snippet reads thin; above the maximum Google truncates.
const DEFAULT_MIN_LENGTH = 50;
const DEFAULT_MAX_LENGTH = 160;

function isMetaDescriptionKey(path) {
  return path.endsWith('.meta.description');
}

function isExempt(exemptKeys, path) {
  return exemptKeys.some((exempt) => path.includes(exempt));
}

function checkValue(env, value, fullPath) {
  const { context, minLength, maxLength, exemptKeys } = env;
  if (value.type === 'Object') {
    checkObject(env, value, fullPath);
    return;
  }
  if (value.type !== 'String') return;
  if (!isMetaDescriptionKey(fullPath) || isExempt(exemptKeys, fullPath)) return;

  const str = value.value;
  const rendered = str.replaceAll(/\{\{[^}]+\}\}/g, 'placeholder');
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

function checkObject(env, node, path = '') {
  for (const member of objectMembers(node)) {
    if (member.type !== 'Member') continue;

    const key = memberKey(member);
    const value = member.value;
    if (!key || !value) continue;

    checkValue(env, value, joinPath(path, key));
  }
}

/** @type {import('eslint').Rule.RuleModule} */
export const seoDescriptionLength = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Enforce SEO-friendly meta description lengths (50-160 chars) in translation files',
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
        'Description for key "{{key}}" is {{length}} chars (min {{min}}). Add more detail for search result snippets. See docs/i18n/CONVENTIONS.md.',
      tooLong:
        'Description for key "{{key}}" is {{length}} chars (max {{max}}). Shorten to avoid truncation in search results. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const minLength = options.minLength ?? DEFAULT_MIN_LENGTH;
    const maxLength = options.maxLength ?? DEFAULT_MAX_LENGTH;
    const exemptKeys = options.exemptKeys || [];

    const env = { context, minLength, maxLength, exemptKeys };

    return {
      Document(node) {
        if (node.body?.type === 'Object') {
          checkObject(env, node.body);
        }
      },
    };
  },
};

export default seoDescriptionLength;
