/**
 * ESLint rule to prevent raw apiClient.post/get/put/delete calls.
 * Forces usage of typedApi for type-safe API calls.
 *
 * @example
 * // ❌ Bad - bypasses type safety
 * await apiClient.post('/GetTeamMachines', { teamName });
 * await apiClient.get('/GetOrganizationUsers', {});
 *
 * // ✅ Good - type-safe
 * await typedApi.GetTeamMachines({ teamName });
 * await typedApi.GetOrganizationUsers({});
 *
 * // ✅ Also allowed - auth/utility methods
 * await apiClient.login(email, password);
 * await apiClient.logout();
 */

/** @type {import('eslint').Rule.RuleModule} */
export const noRawApiCalls = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Disallow raw apiClient CRUD methods. Use typedApi instead.',
      category: 'Best Practices',
      recommended: true,
    },
    messages: {
      useTypedApi:
        "Use typedApi.{{procedure}}() instead of apiClient.{{method}}('{{endpoint}}'). Raw API calls bypass type safety.",
      rawApiCall:
        'Raw apiClient.{{method}}() call detected. Use typedApi for type-safe API calls.',
    },
    schema: [
      {
        type: 'object',
        properties: {
          allowedMethods: {
            type: 'array',
            items: { type: 'string' },
            description: 'Methods allowed on apiClient (e.g., login, logout)',
          },
        },
        additionalProperties: false,
      },
    ],
  },

  create(context) {
    const options = context.options[0] || {};

    // Default allowed methods - auth and utility methods that don't take endpoint strings
    const allowedMethods = new Set(
      options.allowedMethods || [
        // Auth methods
        'login',
        'logout',
        'register',
        'activateUser',
        // URL management
        'setApiUrl',
        'getApiUrl',
        'normalizeApiUrl',
        'reinitialize',
        // Token management
        'setToken',
        'clearToken',
        'hasToken',
        // Password management
        'setMasterPasswordGetter',
      ]
    );

    // CRUD methods that should use typedApi instead
    const crudMethods = new Set(['post', 'get', 'put', 'delete']);

    return {
      CallExpression(node) {
        // Check if this is a member expression call (object.method())
        if (node.callee.type !== 'MemberExpression') {
          return;
        }

        const { object, property } = node.callee;

        // Check if it's apiClient.something()
        if (object.type !== 'Identifier' || object.name !== 'apiClient') {
          return;
        }

        // Get the method name
        if (property.type !== 'Identifier') {
          return;
        }

        const method = property.name;

        // Allow whitelisted methods
        if (allowedMethods.has(method)) {
          return;
        }

        // Report CRUD methods
        if (crudMethods.has(method)) {
          // Try to extract procedure name from first argument for better error message
          const firstArg = node.arguments[0];
          let endpoint = '';
          let procedure = '';

          if (firstArg?.type === 'Literal' && typeof firstArg.value === 'string') {
            endpoint = firstArg.value;
            // Extract procedure name (remove leading /)
            procedure = endpoint.replace(/^\//, '');
          } else if (firstArg?.type === 'TemplateLiteral' && firstArg.quasis.length === 1) {
            // Handle simple template literals like `/Procedure`
            endpoint = firstArg.quasis[0].value.cooked || '';
            procedure = endpoint.replace(/^\//, '');
          }

          context.report({
            node,
            messageId: procedure ? 'useTypedApi' : 'rawApiCall',
            data: {
              method,
              endpoint,
              procedure,
            },
          });
        }
      },
    };
  },
};

export default noRawApiCalls;
