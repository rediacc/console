/**
 * ESLint rule to require non-empty alt text on img and Image elements.
 *
 * Unlike jsx-a11y/alt-text (which allows alt="" for decorative images),
 * this rule requires alt to be non-empty unless the image is explicitly
 * marked as decorative with role="presentation" or aria-hidden="true".
 */

/** JSX attribute name as written: `alt`, or `ns:name` when namespaced. */
function attributeName(attr) {
  if (attr.name.type === 'JSXIdentifier') return attr.name.name;
  if (attr.name.type === 'JSXNamespacedName') {
    return `${attr.name.namespace.name}:${attr.name.name.name}`;
  }
  return '';
}

/** role="presentation", role="none", or role={expression} (dynamic -- allowed). */
function isDecorativeRole(attr) {
  if (attr.value?.type === 'JSXExpressionContainer') return true;
  return (
    attr.value?.type === 'Literal' &&
    (attr.value.value === 'presentation' || attr.value.value === 'none')
  );
}

/** aria-hidden (shorthand), aria-hidden="true", or aria-hidden={true}. */
function isAriaHiddenTrue(attr) {
  // Shorthand: <img aria-hidden /> (value is null)
  if (attr.value === null) return true;
  if (attr.value?.type === 'Literal') return attr.value.value === 'true';
  return (
    attr.value?.type === 'JSXExpressionContainer' &&
    attr.value.expression?.type === 'Literal' &&
    attr.value.expression.value === true
  );
}

function marksImageDecorative(attr) {
  if (attr.type !== 'JSXAttribute' || !attr.name) return false;
  const name = attributeName(attr);
  if (name === 'role') return isDecorativeRole(attr);
  if (name === 'aria-hidden') return isAriaHiddenTrue(attr);
  return false;
}

function isDecorativeImage(node) {
  return (node.attributes || []).some(marksImageDecorative);
}

function isAltAttribute(attr) {
  return (
    attr.type === 'JSXAttribute' &&
    attr.name?.type === 'JSXIdentifier' &&
    attr.name.name === 'alt'
  );
}

/** alt="" or alt="   " (empty or whitespace-only string literal). */
function isEmptyLiteralAlt(value) {
  return (
    value?.type === 'Literal' &&
    typeof value.value === 'string' &&
    value.value.trim() === ''
  );
}

/** alt={""}, alt={null}, alt={undefined}. */
function isEmptyExpressionAlt(value) {
  if (value?.type !== 'JSXExpressionContainer') return false;
  const expr = value.expression;
  if (expr?.type === 'Literal') return expr.value === '' || expr.value === null;
  return expr?.type === 'Identifier' && expr.name === 'undefined';
}

/** @type {import('eslint').Rule.RuleModule} */
export const seoRequireImgAlt = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Require non-empty alt text on img/Image elements for SEO',
      recommended: true,
    },
    messages: {
      emptyAlt:
        'Images must have non-empty alt text for SEO. Add a descriptive alt, or use role="presentation" for decorative images.',
      missingAlt:
        'Images must have an alt attribute. Add a descriptive alt, or use role="presentation" for decorative images.',
    },
    schema: [],
  },

  create(context) {
    function checkElement(node) {
      if (isDecorativeImage(node)) return;

      const altAttr = node.attributes.find(isAltAttribute);

      if (!altAttr) {
        context.report({ node, messageId: 'missingAlt' });
        return;
      }

      if (isEmptyLiteralAlt(altAttr.value) || isEmptyExpressionAlt(altAttr.value)) {
        context.report({ node: altAttr, messageId: 'emptyAlt' });
      }
    }

    return {
      JSXOpeningElement(node) {
        const name =
          node.name?.type === 'JSXIdentifier' ? node.name.name : '';
        if (name === 'img' || name === 'Image') {
          checkElement(node);
        }
      },
    };
  },
};
