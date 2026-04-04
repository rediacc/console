/**
 * ESLint rule to prevent non-descriptive anchor text in JSX.
 *
 * Catches links that use vague text like "click here", "read more", "learn more",
 * "here", "link", etc. Search engines use anchor text to understand link targets,
 * and vague text provides no semantic value.
 */

const VAGUE_PATTERNS = [
  /^click\s+here$/i,
  /^here$/i,
  /^read\s+more$/i,
  /^learn\s+more$/i,
  /^more$/i,
  /^link$/i,
  /^this$/i,
  /^go$/i,
  /^see\s+more$/i,
  /^view\s+more$/i,
  /^details$/i,
  /^more\s+info$/i,
  /^more\s+details$/i,
  /^info$/i,
];

/** @type {import('eslint').Rule.RuleModule} */
export const seoNoVagueAnchorText = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Disallow non-descriptive anchor text like "click here" or "read more"',
      recommended: true,
    },
    schema: [],
    messages: {
      vagueText:
        'Anchor text "{{text}}" is non-descriptive. Use text that describes the link destination for better SEO and accessibility.',
    },
  },

  create(context) {
    /**
     * Extract static text content from JSX children (string literals only).
     * Returns null if any child is dynamic (expressions, components).
     */
    function getStaticText(node) {
      if (!node.parent || node.parent.type !== 'JSXElement') return null;
      const children = node.parent.children || [];
      const parts = [];

      for (const child of children) {
        if (child.type === 'JSXText') {
          parts.push(child.value);
        } else if (child.type === 'Literal' && typeof child.value === 'string') {
          parts.push(child.value);
        } else {
          // Dynamic content (expressions, components) - skip check
          return null;
        }
      }

      return parts.join('').trim();
    }

    return {
      JSXOpeningElement(node) {
        // Only check <a> elements
        if (node.name.type !== 'JSXIdentifier' || node.name.name !== 'a') return;

        // Must have href
        const hasHref = node.attributes.some(
          (attr) => attr.type === 'JSXAttribute' && attr.name?.name === 'href',
        );
        if (!hasHref) return;

        const text = getStaticText(node);
        if (text === null) return; // Dynamic text, can't check

        for (const pattern of VAGUE_PATTERNS) {
          if (pattern.test(text)) {
            context.report({
              node,
              messageId: 'vagueText',
              data: { text },
            });
            return;
          }
        }
      },
    };
  },
};

export default seoNoVagueAnchorText;
