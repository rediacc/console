/**
 * ESLint rule to require non-empty alt text on img and Image elements.
 *
 * Unlike jsx-a11y/alt-text (which allows alt="" for decorative images),
 * this rule requires alt to be non-empty unless the image is explicitly
 * marked as decorative with role="presentation" or aria-hidden="true".
 */

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
    function isDecorativeImage(node) {
      const attrs = node.attributes || [];
      for (const attr of attrs) {
        if (attr.type !== 'JSXAttribute' || !attr.name) continue;
        const name =
          attr.name.type === 'JSXIdentifier'
            ? attr.name.name
            : attr.name.type === 'JSXNamespacedName'
              ? `${attr.name.namespace.name}:${attr.name.name.name}`
              : '';

        // role="presentation" or role="none"
        if (
          name === 'role' &&
          attr.value?.type === 'Literal' &&
          (attr.value.value === 'presentation' || attr.value.value === 'none')
        ) {
          return true;
        }

        // aria-hidden="true", aria-hidden={true}, or shorthand aria-hidden
        if (name === 'aria-hidden') {
          // Shorthand: <img aria-hidden /> (value is null)
          if (attr.value === null) return true;
          if (attr.value?.type === 'Literal' && attr.value.value === 'true')
            return true;
          if (
            attr.value?.type === 'JSXExpressionContainer' &&
            attr.value.expression?.type === 'Literal' &&
            attr.value.expression.value === true
          )
            return true;
        }

        // role={expression} -- allow dynamic role values
        if (name === 'role' && attr.value?.type === 'JSXExpressionContainer') {
          return true;
        }
      }
      return false;
    }

    function checkElement(node) {
      if (isDecorativeImage(node)) return;

      const altAttr = node.attributes.find(
        (attr) =>
          attr.type === 'JSXAttribute' &&
          attr.name?.type === 'JSXIdentifier' &&
          attr.name.name === 'alt',
      );

      if (!altAttr) {
        context.report({ node, messageId: 'missingAlt' });
        return;
      }

      // alt="" or alt="   " (empty or whitespace-only string literal)
      if (
        altAttr.value?.type === 'Literal' &&
        typeof altAttr.value.value === 'string' &&
        altAttr.value.value.trim() === ''
      ) {
        context.report({ node: altAttr, messageId: 'emptyAlt' });
        return;
      }

      // alt={""}, alt={null}, alt={undefined}
      if (altAttr.value?.type === 'JSXExpressionContainer') {
        const expr = altAttr.value.expression;
        if (
          expr?.type === 'Literal' &&
          (expr.value === '' || expr.value === null)
        ) {
          context.report({ node: altAttr, messageId: 'emptyAlt' });
        }
        if (expr?.type === 'Identifier' && expr.name === 'undefined') {
          context.report({ node: altAttr, messageId: 'emptyAlt' });
        }
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
