/**
 * Keep every command decision on one path (agent/plans/PLAN-rmcp-decide.md D5).
 *
 * `decide` (packages/shared/src/policy/decide.ts) is the one decision function, and `enforce`
 * (packages/cli/src/services/policy/enforce.ts) the one step that calls it. A guard of its own
 * in a command file is how the CLI, the local MCP server and the executor came to answer the same
 * question three ways. This rule refuses the three shapes that reopen that:
 *
 * 1. importing a retired guard (`assertCommandPolicy`, `assertOrphanDeletePolicy`,
 *    `resolveGrandRepoMutation`) from anywhere;
 * 2. calling the policy evaluator (`evaluatePolicy`, `evaluateEffectivePolicy`) outside the
 *    decision function and the evaluator's own composer, so no caller judges the policy beside
 *    `decide`;
 * 3. calling `enforce`, imported from the enforcement module, outside the enforcement points.
 *
 * Options: `{ allowGuardImports, allowEvaluate, allowEnforce }`, each a list of path suffixes. A
 * file on a list may do what that list names; the registration says why for each entry.
 */

const RETIRED_GUARDS = new Set([
  'assertCommandPolicy',
  'assertOrphanDeletePolicy',
  'resolveGrandRepoMutation',
]);

const EVALUATORS = new Set(['evaluatePolicy', 'evaluateEffectivePolicy']);

const DEFAULT_ALLOW_EVALUATE = [
  'packages/shared/src/policy/decide.ts',
  'packages/shared/src/policy/merge.ts',
  'packages/shared/src/policy/evaluate.ts',
];

const DEFAULT_ALLOW_ENFORCE = [
  'packages/cli/src/services/policy/enforce.ts',
  'packages/cli/src/utils/command-policy.ts',
  'packages/cli/src/services/serve/policy.ts',
];

/** An import source that names the enforcement module (`.../policy/enforce.js`, `.../enforce`). */
const isEnforceModule = (source) => /(^|\/)policy\/enforce(\.[cm]?[jt]s)?$/.test(source);

const importedName = (spec) =>
  spec.imported.type === 'Identifier' ? spec.imported.name : spec.imported.value;

/** The called name: `f` for `f()`, `m` for `x.m()`, undefined for any other callee. */
function calleeName(callee) {
  if (callee.type === 'Identifier') return callee.name;
  if (callee.type === 'MemberExpression' && callee.property.type === 'Identifier') {
    return callee.property.name;
  }
  return undefined;
}

export const noDirectGuardCall = {
  meta: {
    type: 'problem',
    docs: {
      description: 'Route every command decision through decide() and the enforce() step',
    },
    schema: [
      {
        type: 'object',
        properties: {
          allowGuardImports: { type: 'array', items: { type: 'string' } },
          allowEvaluate: { type: 'array', items: { type: 'string' } },
          allowEnforce: { type: 'array', items: { type: 'string' } },
        },
        additionalProperties: false,
      },
    ],
    messages: {
      retiredGuard:
        '"{{name}}" is a retired guard. The enforcement point judges every command through enforce() and decide() (packages/cli/src/services/policy/enforce.ts); no command file carries a guard of its own.',
      directEvaluate:
        '"{{name}}" judges the policy beside decide(). Ask decide() (packages/shared/src/policy/decide.ts), through enforce(), for the whole decision instead.',
      directEnforce:
        "enforce() is called only at an enforcement point (the CLI root hook, the executor). A command whose target is resolved inside its action goes on the rule's allowEnforce list with its reason.",
    },
  },

  create(context) {
    const options = context.options[0] ?? {};
    const filename = context.filename.replaceAll('\\', '/');
    const listed = (list) => list.some((suffix) => filename.endsWith(suffix));
    const allowGuardImports = listed(options.allowGuardImports ?? []);
    const allowEvaluate = listed(options.allowEvaluate ?? DEFAULT_ALLOW_EVALUATE);
    const allowEnforce = listed(options.allowEnforce ?? DEFAULT_ALLOW_ENFORCE);
    const enforceLocals = new Set();

    const checkSpecifier = (spec, fromEnforce) => {
      const name = importedName(spec);
      if (RETIRED_GUARDS.has(name) && !allowGuardImports) {
        context.report({ node: spec, messageId: 'retiredGuard', data: { name } });
      }
      if (fromEnforce && name === 'enforce') enforceLocals.add(spec.local.name);
    };

    return {
      ImportDeclaration(node) {
        const fromEnforce = isEnforceModule(String(node.source.value));
        for (const spec of node.specifiers) {
          if (spec.type === 'ImportSpecifier') checkSpecifier(spec, fromEnforce);
        }
      },
      CallExpression(node) {
        const name = calleeName(node.callee);
        if (EVALUATORS.has(name) && !allowEvaluate) {
          context.report({ node, messageId: 'directEvaluate', data: { name } });
        }
        if (node.callee.type === 'Identifier' && enforceLocals.has(name) && !allowEnforce) {
          context.report({ node, messageId: 'directEnforce' });
        }
      },
    };
  },
};
