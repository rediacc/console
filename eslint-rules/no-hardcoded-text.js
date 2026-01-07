const DEFAULT_IGNORE_TEXT_PATTERNS = [
  // Numbers, punctuation, and whitespace only.
  '^[-\\s\\d.,:;!?/()\\[\\]{}<>%*+|_`~@#$^&=]+$',
];

const DEFAULT_IGNORE_ATTRIBUTES = [
  'className',
  'id',
  'key',
  'data-testid',
  'dataTestId',
  'to',
  'href',
  'src',
  'rel',
  'target',
  'type',
  'name',
  'role',
  'style',
  'width',
  'height',
  'size',
  'variant',
  'color',
  'icon',
  'loading',
  'disabled',
  'checked',
];

const DEFAULT_CHECK_ATTRIBUTES = [
  'title',
  'placeholder',
  'label',
  'aria-label',
  'aria-placeholder',
  'alt',
  'okText',
  'cancelText',
  'tooltip',
  'helpText',
  'description',
  'emptyText',
  'confirmText',
];

const DEFAULT_IGNORE_COMPONENTS = ['Trans', 'code', 'pre', 'kbd', 'samp'];

const hasLetters = (text) => /\p{L}/u.test(text);

const normalizeText = (text) => text.replace(/\s+/g, ' ').trim();

const getElementName = (node) => {
  if (!node) return '';
  if (node.type === 'JSXIdentifier') return node.name;
  if (node.type === 'JSXMemberExpression') {
    return `${getElementName(node.object)}.${node.property.name}`;
  }
  return '';
};

const isIgnoredText = (text, ignorePatterns) => {
  const normalized = normalizeText(text);
  if (!normalized) return true;
  if (!hasLetters(normalized)) return true;
  return ignorePatterns.some((pattern) => pattern.test(normalized));
};

const getStringLiteralValue = (node) => {
  if (!node) return null;
  if (node.type === 'Literal' && typeof node.value === 'string') {
    return node.value;
  }
  if (
    node.type === 'JSXExpressionContainer' &&
    node.expression &&
    node.expression.type === 'Literal' &&
    typeof node.expression.value === 'string'
  ) {
    return node.expression.value;
  }
  if (
    node.type === 'JSXExpressionContainer' &&
    node.expression &&
    node.expression.type === 'TemplateLiteral' &&
    node.expression.expressions.length === 0
  ) {
    return node.expression.quasis[0]?.value?.cooked ?? '';
  }
  return null;
};

/** @type {import('eslint').Rule.RuleModule} */
export const noHardcodedText = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow hardcoded text in JSX; prefer translations',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          ignoreTextPatterns: {
            type: 'array',
            items: { type: 'string' },
          },
          ignoreAttributes: {
            type: 'array',
            items: { type: 'string' },
          },
          checkAttributes: {
            type: 'array',
            items: { type: 'string' },
          },
          ignoreComponents: {
            type: 'array',
            items: { type: 'string' },
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      hardcodedText: 'Hardcoded text should use translations.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const ignorePatterns = (options.ignoreTextPatterns || DEFAULT_IGNORE_TEXT_PATTERNS).map(
      (pattern) => new RegExp(pattern, 'u')
    );
    const ignoreAttributes = new Set(options.ignoreAttributes || DEFAULT_IGNORE_ATTRIBUTES);
    const checkAttributes = new Set(options.checkAttributes || DEFAULT_CHECK_ATTRIBUTES);
    const ignoreComponents = new Set(options.ignoreComponents || DEFAULT_IGNORE_COMPONENTS);

    const isInIgnoredComponent = (node) => {
      let current = node.parent;
      while (current) {
        if (current.type === 'JSXElement') {
          const name = getElementName(current.openingElement.name);
          if (ignoreComponents.has(name)) return true;
        }
        current = current.parent;
      }
      return false;
    };

    return {
      JSXText(node) {
        if (isInIgnoredComponent(node)) return;
        if (isIgnoredText(node.value, ignorePatterns)) return;
        context.report({ node, messageId: 'hardcodedText' });
      },

      JSXExpressionContainer(node) {
        if (node.parent?.type === 'JSXAttribute') return;
        if (isInIgnoredComponent(node)) return;

        const value = getStringLiteralValue(node);
        if (!value) return;
        if (isIgnoredText(value, ignorePatterns)) return;

        context.report({ node, messageId: 'hardcodedText' });
      },

      JSXAttribute(node) {
        const attrName = node.name?.name;
        if (!attrName || typeof attrName !== 'string') return;
        if (ignoreAttributes.has(attrName)) return;
        if (attrName.startsWith('data-')) return;
        if (isInIgnoredComponent(node)) return;
        if (!checkAttributes.has(attrName)) return;

        const value = getStringLiteralValue(node.value);
        if (!value) return;
        if (isIgnoredText(value, ignorePatterns)) return;

        context.report({ node, messageId: 'hardcodedText' });
      },
    };
  },
};
