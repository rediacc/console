/**
 * ESLint rule to enforce data-testid on interactive elements
 *
 * This rule helps ensure E2E test coverage by requiring data-testid
 * attributes on buttons, inputs, modals, and other interactive components.
 */

/** @type {import('eslint').Rule.RuleModule} */
export const requireTestId = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Require data-testid attribute on interactive elements',
      recommended: true,
    },
    messages: {
      missingTestId: '{{element}} should have a data-testid attribute for E2E testing.',
      missingTestIdModal: 'Modal should have a data-testid attribute. Use data-testid="{{suggested}}".',
    },
    schema: [
      {
        type: 'object',
        properties: {
          // Elements that always require data-testid
          requiredElements: {
            type: 'array',
            items: { type: 'string' },
            default: ['Modal', 'Drawer'],
          },
          // Elements that require data-testid when they have onClick/onSubmit
          interactiveElements: {
            type: 'array',
            items: { type: 'string' },
            default: ['Button'],
          },
          // Form elements that require data-testid
          formElements: {
            type: 'array',
            items: { type: 'string' },
            default: ['Input', 'Input.Password', 'Input.Search', 'Select', 'Checkbox', 'Radio', 'Switch', 'Upload'],
          },
          // Ignore patterns for dynamic testids (template literals are OK)
          allowTemplateLiterals: {
            type: 'boolean',
            default: true,
          },
        },
        additionalProperties: false,
      },
    ],
  },

  create(context) {
    const options = context.options[0] || {};
    const requiredElements = options.requiredElements || ['Modal', 'Drawer'];
    const interactiveElements = options.interactiveElements || ['Button'];
    const formElements = options.formElements || [
      'Input', 'Input.Password', 'Input.Search', 'Input.TextArea',
      'Select', 'Checkbox', 'Radio', 'Switch', 'Upload', 'DatePicker',
      'TimePicker', 'Slider', 'Rate', 'Transfer', 'TreeSelect', 'Cascader',
    ];
    const allowTemplateLiterals = options.allowTemplateLiterals !== false;

    /**
     * Get the full element name (handles Input.Password, etc.)
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
     * Check if element has data-testid attribute
     */
    function hasTestId(attributes) {
      return attributes.some((attr) => {
        if (attr.type !== 'JSXAttribute') return false;
        const name = attr.name?.name;
        return name === 'data-testid';
      });
    }

    /**
     * Check if element has a dynamic testid (template literal)
     */
    function hasDynamicTestId(attributes) {
      return attributes.some((attr) => {
        if (attr.type !== 'JSXAttribute') return false;
        if (attr.name?.name !== 'data-testid') return false;
        // Check if value is a JSXExpressionContainer with TemplateLiteral
        if (attr.value?.type === 'JSXExpressionContainer') {
          return attr.value.expression?.type === 'TemplateLiteral';
        }
        return false;
      });
    }

    /**
     * Check if element has onClick or onSubmit handler
     */
    function hasInteractiveHandler(attributes) {
      return attributes.some((attr) => {
        if (attr.type !== 'JSXAttribute') return false;
        const name = attr.name?.name;
        return name === 'onClick' || name === 'onSubmit' || name === 'onChange';
      });
    }

    /**
     * Check if this is inside a dropdown menu (common pattern where individual items don't need testids)
     */
    function isInsideMenuOrDropdown(node) {
      let parent = node.parent;
      while (parent) {
        if (parent.type === 'JSXElement') {
          const parentName = getElementName(parent.openingElement.name);
          if (parentName === 'Menu' || parentName === 'Dropdown' || parentName === 'Menu.Item') {
            return true;
          }
        }
        parent = parent.parent;
      }
      return false;
    }

    /**
     * Check if element is passed as a prop (e.g., icon={<Button />})
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

    return {
      JSXOpeningElement(node) {
        const elementName = getElementName(node.name);
        const attributes = node.attributes;

        // Skip if already has data-testid
        if (hasTestId(attributes)) {
          return;
        }

        // Skip template literals if allowed
        if (allowTemplateLiterals && hasDynamicTestId(attributes)) {
          return;
        }

        // Skip elements inside menus/dropdowns
        if (isInsideMenuOrDropdown(node)) {
          return;
        }

        // Skip elements passed as props
        if (isPassedAsProp(node)) {
          return;
        }

        // Check required elements (Modal, Drawer)
        if (requiredElements.includes(elementName)) {
          context.report({
            node,
            messageId: 'missingTestId',
            data: { element: elementName },
          });
          return;
        }

        // Check interactive elements (Button with onClick)
        if (interactiveElements.includes(elementName)) {
          if (hasInteractiveHandler(attributes)) {
            context.report({
              node,
              messageId: 'missingTestId',
              data: { element: elementName },
            });
          }
          return;
        }

        // Check form elements
        if (formElements.some((fe) => elementName === fe || elementName.startsWith(`${fe}.`))) {
          context.report({
            node,
            messageId: 'missingTestId',
            data: { element: elementName },
          });
        }
      },
    };
  },
};

export default requireTestId;
