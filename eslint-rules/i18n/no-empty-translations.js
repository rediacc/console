/**
 * ESLint rule to prevent empty translation values in locale JSON files.
 * Detects: "", "   ", null values
 */

import { memberKey, objectMembers, joinPath } from './shared/json-ast.js';

/**
 * Report one leaf value, recursing through nested objects.
 */
const checkValue = (context, value, fullPath) => {
  if (value.type === 'Object') {
    checkObject(context, value, fullPath);
    return;
  }

  if (value.type === 'Null') {
    context.report({ node: value, messageId: 'nullValue', data: { key: fullPath } });
    return;
  }

  if (value.type !== 'String') return;

  if (value.value === '') {
    context.report({ node: value, messageId: 'emptyValue', data: { key: fullPath } });
  } else if (value.value.trim() === '') {
    context.report({ node: value, messageId: 'whitespaceOnly', data: { key: fullPath } });
  }
};

/**
 * Recursively check all values in a JSON object
 */
const checkObject = (context, node, path = '') => {
  for (const member of objectMembers(node)) {
    if (member.type !== 'Member') continue;

    const key = memberKey(member);
    const value = member.value;
    if (!key || !value) continue;

    checkValue(context, value, joinPath(path, key));
  }
};

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
      emptyValue:
        'Empty translation value for key "{{key}}". All translations must have content. See docs/i18n/CONVENTIONS.md.',
      whitespaceOnly:
        'Translation for key "{{key}}" contains only whitespace. See docs/i18n/CONVENTIONS.md.',
      nullValue:
        'Null translation value for key "{{key}}". Use a string value instead. See docs/i18n/CONVENTIONS.md.',
    },
  },

  create(context) {
    return {
      Document(node) {
        if (node.body?.type === 'Object') {
          checkObject(context, node.body);
        }
      },
    };
  },
};

export default noEmptyTranslations;
