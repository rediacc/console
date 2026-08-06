/**
 * ESLint rule to enforce data-track on interactive elements in the www package.
 *
 * Ensures Plausible analytics tracking coverage by requiring data-track
 * attributes on links (<a href>) and buttons (<button onClick>).
 * The data-track attribute is picked up by tracker.js for delegated click tracking.
 */

/** @type {import('eslint').Rule.RuleModule} */
export const requireDataTrack = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Require data-track attribute on interactive elements for analytics tracking',
      recommended: false,
    },
    messages: {
      missingDataTrack:
        '<{{element}}> with {{attr}} should have a data-track attribute for analytics tracking.',
    },
    schema: [
      {
        type: 'object',
        properties: {
          // HTML elements to check (lowercase tag names)
          elements: {
            type: 'array',
            items: { type: 'string' },
            default: ['a', 'button'],
          },
          // Parent component names where tracking is handled in React code
          exemptParents: {
            type: 'array',
            items: { type: 'string' },
            default: [],
          },
        },
        additionalProperties: false,
      },
    ],
  },

  create(context) {
    const options = context.options[0] || {};
    const elements = options.elements || ['a', 'button'];
    const exemptParents = options.exemptParents || [];

    /**
     * Get the full element name (handles JSXMemberExpression like Menu.Item)
     */
    function getElementName(node) {
      if (node.type === 'JSXIdentifier') {
        return node.name;
      }
      if (node.type === 'JSXMemberExpression') {
        return `${getElementName(node.object)}.${node.property.name}`;
      }
      return '';
    }

    /**
     * Check if element has a specific attribute
     */
    function hasAttribute(attributes, name) {
      return attributes.some(
        (attr) => attr.type === 'JSXAttribute' && attr.name?.name === name,
      );
    }

    /**
     * Get the static string value of a JSX attribute, or null if dynamic/missing.
     */
    function getAttributeStringValue(attributes, name) {
      for (const attr of attributes) {
        if (attr.type !== 'JSXAttribute' || attr.name?.name !== name) continue;
        // value is a StringLiteral like href="/"
        if (attr.value?.type === 'Literal' && typeof attr.value.value === 'string') {
          return attr.value.value;
        }
        // No value means boolean attribute (e.g. disabled) — not a string
        return null;
      }
      return null;
    }

    /**
     * Check if element is passed as a prop value (e.g. icon={<button />})
     */
    function isPassedAsProp(node) {
      let parent = node.parent;
      while (parent) {
        if (parent.type === 'JSXExpressionContainer' && parent.parent?.type === 'JSXAttribute') {
          return true;
        }
        parent = parent.parent;
      }
      return false;
    }

    /**
     * Check if element is inside an exempt parent component
     */
    function isInsideExemptParent(node) {
      if (exemptParents.length === 0) return false;
      let parent = node.parent;
      while (parent) {
        if (parent.type === 'JSXElement') {
          const parentName = getElementName(parent.openingElement.name);
          if (exemptParents.includes(parentName)) {
            return true;
          }
        }
        parent = parent.parent;
      }
      return false;
    }

    /** True when the element is exempt for reasons unrelated to its tag. */
    const isExemptElement = (node, attributes) => {
      // Skip if already has data-track
      if (hasAttribute(attributes, 'data-track')) return true;

      // Skip elements passed as prop values
      if (isPassedAsProp(node)) return true;

      // Skip decorative / non-interactive elements
      if (hasAttribute(attributes, 'aria-hidden')) return true;

      // Skip inside exempt parent components
      return isInsideExemptParent(node);
    };

    // --- Element-specific checks ---

    const checkAnchor = (node, attributes) => {
      // Only check <a> with href
      if (!hasAttribute(attributes, 'href')) return;

      // Skip anchor links (href="#section")
      const href = getAttributeStringValue(attributes, 'href');
      if (href !== null && href.startsWith('#')) return;

      context.report({
        node,
        messageId: 'missingDataTrack',
        data: { element: 'a', attr: 'href' },
      });
    };

    const checkButton = (node, attributes) => {
      // Only check <button> with onClick (submit buttons tracked via form events)
      if (!hasAttribute(attributes, 'onClick')) return;

      context.report({
        node,
        messageId: 'missingDataTrack',
        data: { element: 'button', attr: 'onClick' },
      });
    };

    return {
      JSXOpeningElement(node) {
        const elementName = getElementName(node.name);
        const attributes = node.attributes;

        // Only check configured elements
        if (!elements.includes(elementName)) return;

        if (isExemptElement(node, attributes)) return;

        if (elementName === 'a') checkAnchor(node, attributes);
        if (elementName === 'button') checkButton(node, attributes);
      },
    };
  },
};

export default requireDataTrack;
