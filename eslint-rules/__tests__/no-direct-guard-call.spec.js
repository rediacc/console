/**
 * custom/no-direct-guard-call (agent/plans/PLAN-rmcp-decide.md D5).
 *
 * The positive fixtures are the three shapes that reopen a second decision path: a retired guard
 * imported, the policy evaluator called beside decide(), and enforce() called from a command file.
 * The negative fixtures are the files allowed to do each, plus look-alikes the rule must leave
 * alone (an unrelated `enforce` by name, by namespace or by a relative path outside
 * services/policy/, a retired import on the allowGuardImports list).
 */

export const ruleId = 'custom/no-direct-guard-call';

const COMMAND_FILE = 'packages/cli/src/commands/repo.ts';

export default async ({ sourceRuleTester, runCases }) => {
  const { noDirectGuardCall } = await import('../no-direct-guard-call.js');

  return [
    runCases(sourceRuleTester(), ruleId, noDirectGuardCall, {
      valid: [
        // The decision function and the evaluator's composer call the evaluator.
        {
          code: "import { evaluateEffectivePolicy } from './merge.js';\nexport const d = (p, c) => evaluateEffectivePolicy(p, c);\n",
          filename: 'packages/shared/src/policy/decide.ts',
        },
        {
          code: "import { evaluatePolicy } from './evaluate.js';\nexport const e = (p, c) => evaluatePolicy(p.org, c);\n",
          filename: 'packages/shared/src/policy/merge.ts',
        },
        // The CLI enforcement point calls enforce().
        {
          code: "import { enforce } from '../services/policy/enforce.js';\nexport const f = (a) => enforce(a);\n",
          filename: 'packages/cli/src/utils/command-policy.ts',
        },
        // An allowEnforce entry admits a named exception.
        {
          code: "import { enforce } from '../services/policy/enforce.js';\nexport const f = (a) => enforce(a);\n",
          filename: 'packages/cli/src/commands/repo-admin-orphan.ts',
          options: [{ allowEnforce: ['src/commands/repo-admin-orphan.ts'] }],
        },
        // An `enforce` from another module is not the enforcement step.
        {
          code: "import { enforce } from '../utils/limits.js';\nexport const f = (a) => enforce(a);\n",
          filename: COMMAND_FILE,
        },
        // Importing DecisionError from the enforcement module is fine; only the call is gated.
        {
          code: "import { DecisionError } from '../services/policy/enforce.js';\nexport const isDecision = (e) => e instanceof DecisionError;\n",
          filename: COMMAND_FILE,
        },
        // allowGuardImports admits a retired guard's import in a listed file.
        {
          code: "import { assertCommandPolicy } from '../command-policy.js';\n",
          filename: 'packages/cli/src/utils/__tests__/legacy.test.ts',
          options: [{ allowGuardImports: ['src/utils/__tests__/legacy.test.ts'] }],
        },
        // A namespace import of another module named like the step is not the enforcement step.
        {
          code: "import * as limits from '../utils/limits.js';\nexport const f = (a) => limits.enforce(a);\n",
          filename: COMMAND_FILE,
        },
        // A computed variable member and another name destructured from the namespace are not enforce().
        {
          code: "import * as enforcement from '../services/policy/enforce.js';\nconst { DecisionError: D } = enforcement;\nexport const f = (a, enforce) => [D, enforcement[enforce](a)];\n",
          filename: COMMAND_FILE,
        },
        // A relative `./enforce.js` outside services/policy/ is some other module.
        {
          code: "import { enforce } from './enforce.js';\nexport const f = (a) => enforce(a);\n",
          filename: 'packages/cli/src/services/limits/check.ts',
        },
        // A guard the plan keeps (repo create) is not retired.
        {
          code: "import { assertAgentRepoCreate } from '../utils/agent-guard.js';\nexport const g = (n) => assertAgentRepoCreate(n, undefined);\n",
          filename: COMMAND_FILE,
        },
      ],
      invalid: [
        {
          code: "import { assertCommandPolicy, CMD } from '../utils/command-policy.js';\nexport const g = (n) => assertCommandPolicy(CMD.REPO_UP, n);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'retiredGuard' }],
        },
        {
          code: "import { assertOrphanDeletePolicy } from '../utils/command-policy.js';\n",
          filename: 'packages/cli/src/commands/repo-admin-orphan.ts',
          errors: [{ messageId: 'retiredGuard' }],
        },
        {
          code: "import { resolveGrandRepoMutation as r } from './policy.js';\n",
          filename: 'packages/cli/src/services/serve/server.ts',
          errors: [{ messageId: 'retiredGuard' }],
        },
        {
          code: "import { evaluateEffectivePolicy } from '@rediacc/shared/policy';\nexport const a = (p, c) => evaluateEffectivePolicy(p, c);\n",
          filename: 'packages/cli/src/services/serve/policy.ts',
          errors: [{ messageId: 'directEvaluate' }],
        },
        {
          code: "import * as policy from '@rediacc/shared/policy';\nexport const a = (p, c) => policy.evaluatePolicy(p, c);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEvaluate' }],
        },
        {
          code: "import { enforce as check } from '../services/policy/enforce.js';\nexport const f = (a) => check(a);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEnforce' }],
        },
        // A namespace import of the enforcement module, called as a member.
        {
          code: "import * as enforcement from '../services/policy/enforce.js';\nexport const f = (a) => enforcement.enforce(a);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEnforce' }],
        },
        // A computed string member and a destructured binding of the namespace are the same call.
        {
          code: "import * as enforcement from '../services/policy/enforce.js';\nexport const f = (a) => enforcement['enforce'](a);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEnforce' }],
        },
        // A no-substitution template member, called or destructured, spells the same name.
        {
          code: "import * as enforcement from '../services/policy/enforce.js';\nexport const f = (a) => enforcement[`enforce`](a);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEnforce' }],
        },
        {
          code: "import * as enforcement from '../services/policy/enforce.js';\nconst { [`enforce`]: run } = enforcement;\nexport const f = (a) => run(a);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEnforce' }],
        },
        // A computed string-literal key in a destructuring spells the same name (a055cc86.1).
        {
          code: "import * as enforcement from '../services/policy/enforce.js';\nconst { ['enforce']: run } = enforcement;\nexport const f = (a) => run(a);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEnforce' }],
        },
        {
          code: "import * as enforcement from '../services/policy/enforce.js';\nconst { enforce: run } = enforcement;\nexport const f = (a) => run(a);\n",
          filename: COMMAND_FILE,
          errors: [{ messageId: 'directEnforce' }],
        },
        // A sibling's relative import inside services/policy/ is the enforcement module.
        {
          code: "import { enforce } from './enforce.js';\nexport const f = (a) => enforce(a);\n",
          filename: 'packages/cli/src/services/policy/target-check.ts',
          errors: [{ messageId: 'directEnforce' }],
        },
        // Without the option, the same retired import is refused.
        {
          code: "import { assertCommandPolicy } from '../command-policy.js';\n",
          filename: 'packages/cli/src/utils/__tests__/legacy.test.ts',
          errors: [{ messageId: 'retiredGuard' }],
        },
      ],
    }),
  ];
};
