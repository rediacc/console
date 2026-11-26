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
 * 3. calling `enforce`, imported from the enforcement module (by name, or as a member of a
 *    namespace import), outside the enforcement points.
 *
 * Options: `{ allowGuardImports, allowEvaluate, allowEnforce }`, each a list of path suffixes. A
 * file on a list may do what that list names; the registration says why for each entry.
 */

import { posix } from 'node:path';

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

/** A path that ends at the enforcement module (`.../policy/enforce.js`, `.../policy/enforce`). */
const ENFORCE_PATH = /(^|\/)policy\/enforce(\.[cm]?[jt]s)?$/;

/**
 * Whether an import source names the enforcement module. A relative source is resolved against
 * the importing file first, so a sibling's `./enforce.js` inside services/policy/ counts too.
 */
function isEnforceModule(source, filename) {
  if (!source.startsWith('.')) return ENFORCE_PATH.test(source);
  return ENFORCE_PATH.test(posix.join(posix.dirname(filename), source));
}

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

/** The property a member callee names: `ns.enforce` or `ns['enforce']`, never a computed variable. */
function memberName(callee) {
  if (!callee.computed && callee.property.type === 'Identifier') return callee.property.name;
  if (callee.computed && callee.property.type === 'Literal') return callee.property.value;
  return undefined;
}

/** The local a destructuring property binds to `enforce` (`{ enforce }`, `{ enforce: e }`, `{ 'enforce': e }`), undefined for any other property. */
function enforceBindingOf(prop) {
  if (prop.type !== 'Property' || prop.value.type !== 'Identifier') return undefined;
  const key = prop.computed ? undefined : (prop.key.name ?? prop.key.value);
  return key === 'enforce' ? prop.value.name : undefined;
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
        'enforce() is called only at an enforcement point: the CLI decision step (packages/cli/src/utils/command-policy.ts, which the root hook calls) and the executor (packages/cli/src/services/serve/policy.ts). A command whose target is resolved inside its action calls enforceResolvedTarget and is named on ACTION_RESOLVED_TARGETS.',
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
    const enforceNamespaces = new Set();

    const checkSpecifier = (spec, fromEnforce) => {
      const name = importedName(spec);
      if (RETIRED_GUARDS.has(name) && !allowGuardImports) {
        context.report({ node: spec, messageId: 'retiredGuard', data: { name } });
      }
      if (fromEnforce && name === 'enforce') enforceLocals.add(spec.local.name);
    };

    return {
      ImportDeclaration(node) {
        const fromEnforce = isEnforceModule(String(node.source.value), filename);
        for (const spec of node.specifiers) {
          if (spec.type === 'ImportSpecifier') checkSpecifier(spec, fromEnforce);
          if (spec.type === 'ImportNamespaceSpecifier' && fromEnforce) {
            enforceNamespaces.add(spec.local.name);
          }
        }
      },
      VariableDeclarator(node) {
        // `const { enforce } = ns` on a namespace import of the enforcement module binds a local enforce.
        if (node.id.type !== 'ObjectPattern' || node.init?.type !== 'Identifier') return;
        if (!enforceNamespaces.has(node.init.name)) return;
        for (const prop of node.id.properties) {
          const local = enforceBindingOf(prop);
          if (local) enforceLocals.add(local);
        }
      },
      CallExpression(node) {
        const name = calleeName(node.callee);
        if (EVALUATORS.has(name) && !allowEvaluate) {
          context.report({ node, messageId: 'directEvaluate', data: { name } });
        }
        if (allowEnforce) return;
        const viaName = node.callee.type === 'Identifier' && enforceLocals.has(name);
        const viaNamespace =
          node.callee.type === 'MemberExpression' &&
          node.callee.object.type === 'Identifier' &&
          enforceNamespaces.has(node.callee.object.name) &&
          memberName(node.callee) === 'enforce';
        if (viaName || viaNamespace) context.report({ node, messageId: 'directEnforce' });
      },
    };
  },
};
