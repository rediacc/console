/**
 * ESLint rule to enforce naming conventions for translation keys.
 * Default: camelCase with dot notation for nesting
 */

// Regex patterns for different naming conventions
const PATTERNS = {
  camelCase: /^[a-z][a-zA-Z0-9]*$/,
  'kebab-case': /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/,
  snake_case: /^[a-z][a-z0-9]*(_[a-z0-9]+)*$/,
  PascalCase: /^[A-Z][a-zA-Z0-9]*$/,
};

/** @type {import('eslint').Rule.RuleModule} */
export const keyNamingConvention = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Enforce naming conventions for translation keys',
      recommended: true,
    },
    schema: [
      {
        type: 'object',
        properties: {
          keyFormat: {
            type: 'string',
            enum: ['camelCase', 'kebab-case', 'snake_case', 'PascalCase'],
            default: 'camelCase',
          },
          allowedPatterns: {
            type: 'array',
            items: { type: 'string' },
            default: [],
          },
          maxNestingDepth: {
            type: 'number',
            default: 6,
          },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      invalidFormat: 'Key "{{key}}" does not follow {{format}} naming convention. Full path: "{{path}}".',
      tooDeep: 'Key path "{{path}}" exceeds maximum nesting depth of {{max}}.',
    },
  },

  create(context) {
    const options = context.options[0] || {};
    const keyFormat = options.keyFormat || 'camelCase';
    const allowedPatterns = (options.allowedPatterns || []).map((p) => new RegExp(p));
    const maxNestingDepth = options.maxNestingDepth ?? 6;

    const pattern = PATTERNS[keyFormat];

    /**
     * Check if a key matches any allowed pattern
     */
    const isAllowed = (key) => {
      return allowedPatterns.some((p) => p.test(key));
    };

    /**
     * Check a key segment against the naming convention
     */
    const checkKey = (key, fullPath, node) => {
      // Skip if matches allowed patterns
      if (isAllowed(key) || isAllowed(fullPath)) {
        return;
      }

      // Check naming convention
      if (!pattern.test(key)) {
        context.report({
          node,
          messageId: 'invalidFormat',
          data: {
            key,
            format: keyFormat,
            path: fullPath,
          },
        });
      }
    };

    /**
     * Recursively check all keys in a JSON object
     */
    const checkObject = (node, path = '', depth = 0) => {
      if (!node || node.type !== 'Object') return;

      const members = node.body?.members || [];

      for (const member of members) {
        if (member.type !== 'Member') continue;

        const key = member.name?.type === 'String'
          ? member.name.value
          : member.name?.name;

        if (!key) continue;

        const fullPath = path ? `${path}.${key}` : key;
        const currentDepth = depth + 1;

        // Check nesting depth
        if (currentDepth > maxNestingDepth) {
          context.report({
            node: member.name,
            messageId: 'tooDeep',
            data: {
              path: fullPath,
              max: maxNestingDepth,
            },
          });
          continue;
        }

        // Check key naming
        checkKey(key, fullPath, member.name);

        // Recursively check nested objects
        if (member.value?.type === 'Object') {
          checkObject(member.value, fullPath, currentDepth);
        }
      }
    };

    return {
      Document(node) {
        if (node.body?.type === 'Object') {
          checkObject(node.body);
        }
      },
    };
  },
};

export default keyNamingConvention;
