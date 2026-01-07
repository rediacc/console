/**
 * ESLint rule to enforce `as const` on UPPER_SNAKE_CASE constant arrays
 *
 * This rule detects constant arrays with UPPER_SNAKE_CASE names that
 * don't use `as const`, which loses narrow literal type information.
 *
 * Example of violation:
 *   const TRACKED_ACTIONS = ['auth/login', 'auth/logout'];  // ❌
 *
 * Correct pattern:
 *   const TRACKED_ACTIONS = ['auth/login', 'auth/logout'] as const;  // ✅
 *
 * The rule provides auto-fix support via --fix.
 */

/** @type {import('eslint').Rule.RuleModule} */
export const preferConstArrays = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Require `as const` on UPPER_SNAKE_CASE constant arrays for type safety',
      recommended: true,
    },
    fixable: 'code',
    messages: {
      missingAsConst:
        'Constant array "{{name}}" should use `as const` for narrow literal type safety.',
    },
    schema: [],
  },

  create(context) {
    /**
     * Check if name follows UPPER_SNAKE_CASE pattern
     */
    function isUpperSnakeCase(name) {
      return /^[A-Z][A-Z0-9_]*$/.test(name);
    }

    /**
     * Check if node is an array of literal values only
     */
    function isLiteralArray(node) {
      if (node.type !== 'ArrayExpression') return false;
      if (node.elements.length === 0) return false;

      return node.elements.every(
        (el) =>
          el &&
          (el.type === 'Literal' ||
            el.type === 'TemplateLiteral' ||
            // Handle negative numbers like -1
            (el.type === 'UnaryExpression' && el.argument?.type === 'Literal'))
      );
    }

    /**
     * Check if array already has `as const` assertion
     */
    function hasAsConst(node) {
      const parent = node.parent;
      if (parent?.type === 'TSAsExpression') {
        const typeAnnotation = parent.typeAnnotation;
        // Check for `as const`
        if (typeAnnotation?.type === 'TSTypeReference') {
          return typeAnnotation.typeName?.name === 'const';
        }
      }
      return false;
    }

    return {
      VariableDeclarator(node) {
        // Must be const declaration
        if (node.parent?.kind !== 'const') return;

        // Must have identifier name
        const name = node.id?.name;
        if (!name) return;

        // Must be UPPER_SNAKE_CASE
        if (!isUpperSnakeCase(name)) return;

        // Must be initialized with array literal of literals
        const init = node.init;
        if (!init) return;

        // Handle TSAsExpression wrapper (when already has type assertion)
        const arrayNode = init.type === 'TSAsExpression' ? init.expression : init;
        if (!isLiteralArray(arrayNode)) return;

        // Skip if already has `as const`
        if (hasAsConst(arrayNode)) return;

        context.report({
          node: arrayNode,
          messageId: 'missingAsConst',
          data: { name },
          fix(fixer) {
            return fixer.insertTextAfter(arrayNode, ' as const');
          },
        });
      },
    };
  },
};

export default preferConstArrays;
