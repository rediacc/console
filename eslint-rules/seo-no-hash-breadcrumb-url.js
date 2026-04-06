/**
 * ESLint rule to prevent hash-fragment URLs in breadcrumb items.
 *
 * Google Search Console rejects breadcrumb structured data where
 * itemListElement.item contains a URL with a hash fragment (e.g., /#solutions).
 * Breadcrumb URLs must be valid, crawlable standalone pages.
 *
 * Catches patterns like:
 *   { name: 'Solutions', url: `/${lang}/#solutions` }
 * in arrays assigned to variables matching *breadcrumb*.
 */

/** @type {import('eslint').Rule.RuleModule} */
export const seoNoHashBreadcrumbUrl = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow hash-fragment URLs in breadcrumb items (invalid for structured data)',
      recommended: true,
    },
    messages: {
      hashUrl:
        'Breadcrumb URL contains a hash fragment ("{{value}}"). Google rejects hash-fragment URLs in BreadcrumbList structured data. Use a real, crawlable page URL instead.',
    },
    schema: [],
  },

  create(context) {
    function isBreadcrumbArray(node) {
      // Check if this array is assigned to a variable containing "breadcrumb" (case-insensitive)
      const parent = node.parent;
      if (!parent) return false;

      // const breadcrumbItems = [...]
      if (parent.type === 'VariableDeclarator' && parent.id?.type === 'Identifier') {
        return /breadcrumb/i.test(parent.id.name);
      }

      return false;
    }

    function checkUrlProperty(prop) {
      if (!prop.key) return;
      const keyName = prop.key.type === 'Identifier' ? prop.key.name : prop.key.value;
      if (keyName !== 'url') return;

      const value = prop.value;

      // Check string literals: url: '/#solutions'
      if (value?.type === 'Literal' && typeof value.value === 'string' && value.value.includes('#')) {
        context.report({ node: value, messageId: 'hashUrl', data: { value: value.value } });
        return;
      }

      // Check template literals: url: `/${lang}/#solutions`
      if (value?.type === 'TemplateLiteral') {
        const raw = value.quasis.map((q) => q.value.raw).join('');
        if (raw.includes('#')) {
          context.report({ node: value, messageId: 'hashUrl', data: { value: raw } });
        }
      }
    }

    return {
      ArrayExpression(node) {
        if (!isBreadcrumbArray(node)) return;

        for (const element of node.elements) {
          if (element?.type !== 'ObjectExpression') continue;
          for (const prop of element.properties) {
            if (prop.type === 'Property') {
              checkUrlProperty(prop);
            }
          }
        }
      },
    };
  },
};
