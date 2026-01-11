/**
 * ESLint rule to detect hardcoded nullish coalescing defaults
 *
 * This rule flags expressions like:
 *   value ?? 22          // number literal
 *   value ?? 'latest'    // non-empty string literal
 *
 * But allows:
 *   value ?? ''          // empty string (intentional clearing)
 *   value ?? true/false  // booleans
 *   value ?? []          // empty arrays
 *   value ?? {}          // empty objects
 *   value ?? 0           // zero (can be configured)
 *
 * @example
 * // Bad - hardcoded defaults should be centralized
 * const port = options?.port ?? 22;
 * const tag = repo.tag ?? 'latest';
 *
 * // Good - use centralized defaults
 * import { DEFAULTS } from '@rediacc/shared/config';
 * const port = options?.port ?? DEFAULTS.SSH.PORT;
 * const tag = repo.tag ?? DEFAULTS.REPOSITORY.TAG;
 */

/** @type {import('eslint').Rule.RuleModule} */
export const noHardcodedNullishDefaults = {
  meta: {
    type: 'suggestion',
    docs: {
      description:
        'Disallow hardcoded number and string literals as nullish coalescing defaults. Use centralized DEFAULTS constants instead.',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      hardcodedNumber:
        'Hardcoded number "{{value}}" in nullish coalescing. Use a constant from @rediacc/shared/config/defaults instead.',
      hardcodedString:
        'Hardcoded string "{{value}}" in nullish coalescing. Use a constant from @rediacc/shared/config/defaults instead.',
    },
    schema: [
      {
        type: 'object',
        properties: {
          allowedNumbers: {
            type: 'array',
            items: { type: 'number' },
            description: 'Numbers that are allowed as nullish defaults (e.g., 0, 1)',
          },
          allowedStrings: {
            type: 'array',
            items: { type: 'string' },
            description: 'Strings that are allowed as nullish defaults',
          },
          allowZero: {
            type: 'boolean',
            description:
              'Allow 0 as a nullish default (common for counters/accumulator initialization)',
          },
          allowNegativeOne: {
            type: 'boolean',
            description: 'Allow -1 as a nullish default (common for indexOf results)',
          },
        },
        additionalProperties: false,
      },
    ],
  },

  create(context) {
    const options = context.options[0] || {};

    // Default allowed values
    const allowedNumbers = new Set(options.allowedNumbers || []);
    const allowedStrings = new Set(options.allowedStrings || []);

    // Common patterns that are typically acceptable
    if (options.allowZero !== false) {
      allowedNumbers.add(0);
    }
    if (options.allowNegativeOne !== false) {
      allowedNumbers.add(-1);
    }

    // Always allow empty string (intentional clearing pattern)
    allowedStrings.add('');

    /**
     * Check if a node is a number literal (including negative numbers)
     */
    function getNumberValue(node) {
      if (node.type === 'Literal' && typeof node.value === 'number') {
        return node.value;
      }
      // Handle negative numbers: -1, -22, etc.
      if (
        node.type === 'UnaryExpression' &&
        node.operator === '-' &&
        node.argument?.type === 'Literal' &&
        typeof node.argument.value === 'number'
      ) {
        return -node.argument.value;
      }
      return null;
    }

    /**
     * Check if a node is a string literal
     */
    function getStringValue(node) {
      if (node.type === 'Literal' && typeof node.value === 'string') {
        return node.value;
      }
      // Handle simple template literals with no expressions
      if (
        node.type === 'TemplateLiteral' &&
        node.expressions.length === 0 &&
        node.quasis.length === 1
      ) {
        return node.quasis[0].value.cooked;
      }
      return null;
    }

    return {
      LogicalExpression(node) {
        // Only check nullish coalescing operator (??)
        if (node.operator !== '??') {
          return;
        }

        const right = node.right;

        // Check for number literals
        const numberValue = getNumberValue(right);
        if (numberValue !== null) {
          if (!allowedNumbers.has(numberValue)) {
            context.report({
              node: right,
              messageId: 'hardcodedNumber',
              data: { value: String(numberValue) },
            });
          }
          return;
        }

        // Check for string literals
        const stringValue = getStringValue(right);
        if (stringValue !== null) {
          if (!allowedStrings.has(stringValue)) {
            context.report({
              node: right,
              messageId: 'hardcodedString',
              data: { value: stringValue },
            });
          }
          return;
        }

        // Allow: booleans, arrays, objects, identifiers, member expressions, etc.
        // These are not flagged as they're either:
        // - Acceptable primitives (true/false)
        // - Already using constants (identifiers/member expressions)
        // - Structural defaults ([], {})
      },
    };
  },
};

export default noHardcodedNullishDefaults;
