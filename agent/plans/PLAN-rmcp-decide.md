# PLAN: One decide(): a single shared decision function at one enforcement point, so the CLI, local MCP, remote MCP, --proxy and the web console refuse and allow the same things

Status: approved -- operator ruling 2026-11-20 in session 6c87d631 ("approved but do not promote", agent/programs/remote-mcp/02-decisions.md D51); promoted by the operator 2026-11-23
Depends-On: PLAN-rmcp-policy-record.md
Owner: 6c87d631
Priority: P1 -- today a local agent ignores the org policy entirely and the local and executor grand-repo guards disagree on five inputs (findings 1-6); the remote MCP must not ship a third variant
Concurrency: parallel -- Wave 1: D1 (shared decide and fixture) alone. Wave 2 after D1: D2 (local adapters and CLI enforcement point) and D3 (executor enforcement point) are file-disjoint. Wave 3: D4 (call-site removal across commands/, one writer, after D2), D5 (lint rule), D6 (parity harness). D3 edits packages/cli/src/services/serve/server.ts, which PLAN-rmcp-writeback.md and PLAN-rmcp-executor-hardening.md also edit; D4 edits command files PLAN-rmcp-writeback.md touches (repo-create-delete.ts). Each writer runs block_plan_concurrency before its first edit. PLAN-rmcp-config-edit-removal.md and PLAN-rmcp-local-mcp.md wait for this plan, so commands/mcp/tools.ts and agent-guard.ts are edited here first.
Owns: agent/plans/PLAN-rmcp-decide.md, packages/shared/src/policy/decide.ts, packages/shared/src/policy/decision-codes.ts, packages/shared/src/policy/__tests__/decide.test.ts, packages/shared/src/policy/__fixtures__/decision-table.json, packages/cli/src/services/policy/**, packages/cli/src/utils/agent-guard.ts, packages/cli/src/utils/grand-env.ts, packages/cli/src/utils/cluster-env.ts, packages/cli/src/utils/command-policy.ts, packages/cli/src/utils/ops-vm.ts, packages/cli/src/utils/process-ancestry.ts, packages/cli/src/utils/__tests__/agent-guard.test.ts, packages/cli/src/utils/__tests__/command-policy*.test.ts, packages/cli/src/cli.ts, packages/cli/src/services/serve/policy.ts, packages/cli/src/services/serve/command-dispatch.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/__tests__/policy*.test.ts, packages/cli/src/commands/mcp/tools.ts, packages/cli/src/commands/**/*.ts (assertCommandPolicy call-site removal only), packages/cli/src/i18n/locales/*/cli.json (errors.agent.* decision messages), eslint-rules/no-direct-guard-call.js, eslint-rules/__tests__/no-direct-guard-call.test.js, eslint.config.js, packages/cli/src/services/policy/__tests__/parity-onprem.test.ts
Live-Proof: bench -- the executor half reaches the eu bench proxy through deploy_bench, and the decision-table fixture runs once through `./rdc.sh --config eu-bench --proxy` against it; the local half is proved by the CLI and local-MCP legs of D6, which need no deploy. On-premise (D49): the same fixture runs against the local on-premise stack of PLAN-rmcp-executor-hardening.md#EHOP* in D8 and D-OP-L1.
Updated: 2026-11-20
First-Seen: 2026-11-20

## Ask

Every path that runs an `rdc` command must reach one pure decision function and get one answer for the same inputs (D18):

- **Callers:** the CLI, the local stdio MCP server, the remote MCP Worker, `rdc --proxy` and the web console.
- **Answers:** `allow`, `deny`, or `needs_confirmation`, each with a stable code and a next-step hint (D21).
- **Agent rule:** an agent may act only when a human-set session opt-in AND the policy ceiling both allow it (D22). Locally the opt-in is the ancestry-verified env var; remotely it is the grant row (D23). Both become one overrides type.
- **Policy for everyone:** humans and agents, locally and remotely (D19). An override never exceeds the policy (D20).

## Context (read 2026-11-20 against the tree; a writer re-reads each citation before relying on it)

1. **Local paths never evaluate the policy.** `evaluatePolicy` is called only from packages/cli/src/services/serve/policy.ts (`authorize`, :108-131). A grep of packages/cli/src for `evaluatePolicy` outside services/serve finds nothing.
2. **The CLI guard is agent-only and fails open.** `assertCommandPolicy` (packages/cli/src/utils/command-policy.ts:238) returns at once when `!isAgentEnvironment()` (:243), returns when no repo name is given (:252), and returns when the repo is not in the config (:256-257). It is called at 56 sites in 26 command files (grep of `assertCommandPolicy(` outside tests).
3. **The local MCP guard is a second, different implementation.** packages/cli/src/commands/mcp/tools.ts: `getRepoInfo` lets the command proceed when config is unavailable (:66-78, comment at :77), `guardNamedRepo` (:111) and `applyGrandRepoGuard` (:132) skip any tool call with no repo argument. The child `rdc` process then runs `assertCommandPolicy` again.
4. **The executor guard fails closed.** `resolveGrandRepoMutation` treats an unparsable, unresolved or absent ref as grand (packages/cli/src/services/serve/policy.ts:185-226) and adds `MUTATES_GRAND_BY_DEFINITION = {'repo promote'}` (:173, used at :199). It has no ops-VM exemption; the CLI and MCP guards do (packages/cli/src/utils/command-policy.ts:261, packages/cli/src/commands/mcp/tools.ts:122-123, `isOpsVmPlacement` at packages/cli/src/utils/ops-vm.ts:52).
5. **Overrides come in two shapes.** Locally: `REDIACC_ALLOW_GRAND_REPO` (list or `*`) and `REDIACC_ALLOW_CLUSTER_OPS` (packages/cli/src/utils/process-ancestry.ts:26, :30), checked by `isRepoAllowedByGrandEnv` (packages/cli/src/utils/grand-env.ts:26), `isClusterAllowedByEnv` (packages/cli/src/utils/cluster-env.ts:32) and `isOverrideLegitimate` (packages/cli/src/utils/process-ancestry.ts:235). At the executor: the policy flags `allowGrandRepos` and `allowClusterOps` (packages/shared/src/policy/schema.ts:67, :69). The executor has no cluster-ops guard of its own beyond the policy's `allowClusterOps`.
6. **Team policy never matches at the executor.** `authorize` passes `teamSlug: args.teamSlug` (packages/cli/src/services/serve/policy.ts:116), and the call in packages/cli/src/services/serve/server.ts:226 does not supply it. PLAN-rmcp-executor-hardening.md owns the principal plumbing; this plan consumes the team in the decision context.
7. **Dispatch has one chokepoint per path.** The executor's `prepareCommand` (packages/cli/src/services/serve/command-dispatch.ts:365-376) runs `assertDispatchable` (:186) before policy. The CLI has one Commander `preAction` hook (packages/cli/src/cli.ts:229), which already knows the action command.
8. **Annotations and confirmation.** The local MCP server marks tools `readOnlyHint: !tool.isDestructive` (tools.ts registration block, near :170-180), which labels non-destructive writes read-only; PLAN-rmcp-local-mcp.md fixes the registry, and this plan defines the `needs_confirmation` contract both MCP servers render.

## Decisions

D18 (identical local and remote behaviour), D19 (policy enforced for everyone), D20 (overrides never exceed policy), D21 (needs_confirmation through elicitation, else a confirm argument), D22 (opt-in AND ceiling), D23 (remote opt-in on the grant row), D24 (local-file policy is a ceiling), D26 (grand-repo globs, provided by PLAN-rmcp-policy-record.md). Ops VMs (192.168.111.*) are development-only and never block (operator memory "Ops VMs are dev-only"); the exemption is kept, in one predicate, on every path. Clean break: the old guards are deleted, not wrapped.

## Design

### 1. `decide(ctx)` in packages/shared/src/policy/decide.ts

Pure, synchronous, no I/O. Input:

- `principal`: `{kind: 'human' | 'agent', userEmail, orgRole, teamSlug?}`
- `command`: the contract entry fields that matter (`pathKey`, `destructive`, `grandGuard`, `forkBlocked`, cluster class, `agentBlocked`)
- `target`: `{machine?, repo?: {name, state: 'grand' | 'fork' | 'unresolved'}, isOpsVm: boolean}`; `unresolved` counts as grand (fail closed, finding 4)
- `policy`: the effective merged document from PLAN-rmcp-policy-record.md, or `null`
- `overrides`: `{grandRepos: string[] | '*' | null, clusterOps: string[] | '*' | null, source: 'env' | 'grant' | 'none'}`
- `confirmation`: `{granted: boolean}` for the D21 retry

Rules in order: dispatchability is the caller's (prepareCommand stays first); policy (deny wins; `null` policy uses `MISSING_POLICY_DEFAULT`); for `kind: 'agent'` on a grand target or cluster op, require BOTH the policy flag AND a matching override (D22); `isOpsVm` short-circuits the grand-repo rule only; `MUTATES_GRAND_BY_DEFINITION` moves here; destructive grand operations with the opt-in present answer `needs_confirmation` unless `confirmation.granted`.

Output: `{verdict, code, reason, next?: {run?: string, confirm?: {argument: 'confirm', value: string}}}`. Codes live in `decision-codes.ts` (`POLICY_DENIED`, `GRAND_REPO_DENIED`, `CLUSTER_OPS_DENIED`, `AGENT_OPT_IN_MISSING`, `FORK_BLOCKED`, `AGENT_BLOCKED`, `CONFIRMATION_REQUIRED`), shared by every surface and by PLAN-rmcp-docs.md's json-output page.

### 2. Adapters (packages/cli/src/services/policy/)

- `overrides-env.ts`: env vars plus `isOverrideLegitimate`, returning the overrides type (`source: 'env'`); an agent whose override fails ancestry gets `null` lists.
- `overrides-grant.ts`: the grant row fields from PLAN-rmcp-agent-grants.md (`allowGrandRepos`, `allowClusterOps`) to the same type (`source: 'grant'`).
- `target.ts`: ONE repo resolver for every path (parseRef, `configService.getRepository`, fork test, `isOpsVmPlacement`), returning `unresolved` instead of `null`.
- `enforce.ts`: builds the context and calls `decide`; throws a typed `DecisionError` carrying the output.

### 3. Enforcement points

- CLI: the `preAction` hook in cli.ts calls `enforce` once per command with the action's ref positional; `assertCommandPolicy` and its 56 call sites are deleted. Commands whose target is resolved inside the action (orphan delete by GUID) call `enforce` once with the resolved target, the single named exception, listed in the lint rule's allowlist with its reason.
- Executor: `authorize` and `resolveGrandRepoMutation` in serve/policy.ts are replaced by `enforce` after `prepareCommand`; the principal is `kind: 'human'` for console and `--proxy` callers and `kind: 'agent'` for remote-MCP grants (the grant marks itself).
- Local MCP: the guards in commands/mcp/tools.ts are deleted; the child `rdc` process reaches the CLI enforcement point with `kind: 'agent'`, so there is exactly one check. A `needs_confirmation` result is returned to the MCP layer as a structured error the server renders per D21.
- Remote MCP: the Worker calls the executor, which enforces; the Worker only renders the result.

### 4. One decision table

`packages/shared/src/policy/__fixtures__/decision-table.json`: rows of (principal, command, target, policy, overrides, confirmation) and the expected (verdict, code). At least: human and agent on grand, fork, unresolved and ops-VM targets; policy null, permissive, restrictive, team-narrowed, locked; overrides none, env list, env `*`, grant list; cluster ops; fork-blocked; agent-blocked; confirmation absent and granted. The same file runs against five surfaces (D6).

## Boxes

- [x] D1 [writer] `decide.ts`, `decision-codes.ts`, the fixture with at least 60 rows, and `decide.test.ts` driving the fixture plus a control row whose expected verdict is flipped and must fail. Accept: `(cd packages/shared && npx vitest run src/policy/__tests__/decide.test.ts)` rc 0.
    (ticked) 2026-11-24T05:03:28Z by ace763dd: commit:27b472ea76 present: decide.test.ts passes on the tree (vitest rc=0); fileline packages/shared/src/policy/__tests__/decide.test.ts:1
- [x] D2 [writer] Local adapters and the CLI enforcement point: `services/policy/{overrides-env,target,enforce}.ts`, the `preAction` call in cli.ts, `assertCommandPolicy` reduced to a thin `enforce` call for the one named exception, decision messages in `errors.agent.*` for all 13 CLI locales. Tests drive the fixture through `enforce` with a mocked config. Accept: `(cd packages/cli && npx vitest run src/services/policy)` rc 0 and `npm run -s check:i18n` rc 0.
    (ticked) 2026-11-25T16:00:28Z by d778be9d: D2 landed: server half account 264c5d70, CLI half fea275835d; full CLI vitest 7258 passed, tsc rc 0. DEPS-WAIVED: used prerequisites landed
- [x] D3 [writer] Executor enforcement: serve/policy.ts `authorize` and `resolveGrandRepoMutation` replaced by `enforce`, the team from the principal (once PLAN-rmcp-executor-hardening.md has landed its teamSlug box), `overrides-grant.ts` wired for grant principals, cluster-ops refusal now on this path. Accept: `(cd packages/cli && npx vitest run src/services/serve/__tests__)` rc 0.
    (ticked) 2026-11-24T23:32:20Z by d778be9d: D3 landed b2f0bd2f7d with the proxied agent check 6bc4d0e528 landed before it; cli tsc rc 0; vitest serve, policy, mcp, utils, proxy opt-in 1388 passed. DEPS-WAIVED: D3 consumes only landed policy-record boxes S1, C1, C2, W1; open K1/SK/K-L/M boxes untouched
- [x] D4 [writer] Delete the 56 `assertCommandPolicy` call sites across the 26 command files and the MCP guards in commands/mcp/tools.ts; grep proves none remain except the named exception. Accept: `(cd packages/cli && npx vitest run)` rc 0 and `test "$(git grep -c 'assertCommandPolicy(' -- packages/cli/src ':!**/__tests__/**' | awk -F: '{s+=$2} END {print s}')" -le 2` rc 0.
    (ticked) 2026-11-26T20:09:05Z by d778be9d: D4 present: git grep assertCommandPolicy( in packages/cli/src prints 0 call sites (accept needs 2 or fewer), landed in 9189b87823 commit:9189b87823
- [x] D5 [writer] Lint rule `no-direct-guard-call` refusing imports of the removed guards and any call of `evaluatePolicy` outside packages/shared/src/policy/decide.ts, registered in eslint.config.js, with a positive and a negative fixture. Accept: `npx vitest run eslint-rules/__tests__/no-direct-guard-call.test.js` rc 0 and `npx eslint packages/cli/src` rc 0.
    (ticked) 2026-11-25T02:53:36Z by d778be9d: D5 landed f4f1784ea0: custom/no-direct-guard-call registered, check-lint-rule-units rc 0, source-rules reports no finding from it. DEPS-WAIVED: D2 landed 27b472ea76; policy-record boxes S1 C1 C2 W1 landed
- [x] D6 [writer] Parity harness: the decision table driven through (a) `decide`, (b) the built CLI as a subprocess with an agent env, (c) the local MCP server over stdio, (d) the executor in-process through `createServeApp`, each asserting the same verdict and code per row. Accept: `(cd packages/cli && npx vitest run src/services/policy/__tests__/parity.test.ts)` rc 0.
    (ticked) 2026-11-25T18:10:37Z by d778be9d: D6 landed 0cd2a1f3be; parity.test.ts 46 passed. DEPS-WAIVED: used prerequisites landed
Box D7 (the remote MCP leg of the parity harness) moved to PLAN-rmcp-remote-worker.md as RW-PAR on 2026-11-20, which removes the box-level cycle between this plan and that one.
- [ ] D8 [writer] On-premise parity leg: the decision table driven through the on-premise stack (Node account entry and `rdc serve --mode daemon`, harness from PLAN-rmcp-executor-hardening.md#EHOP*), asserting the same verdict and code per row as the in-process legs of D6. Accept: `(cd packages/cli && npx vitest run src/services/policy/__tests__/parity-onprem.test.ts)` rc 0, run in that plan's on-premise CI lane.
- [ ] D-OP-L1 [live] Cloud versus on-premise parity: the fixture's executor rows through `./rdc.sh --config eu-bench --proxy` and through the local on-premise stack, comparing verdicts and codes row by row. Evidence: the comparison script rc 0 with zero mismatches, both runs' row counts recorded.
- [ ] LP-bench [live] Deploy the branch's proxy to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) and run the fixture's executor rows through `./rdc.sh --config eu-bench --proxy`, comparing codes with the local run. Evidence: the comparison script rc 0 with zero mismatches recorded.
  Accept: live-proof bench cli-bench

## Docs touched

The AI-agent safety page and the json-output error codes (PLAN-rmcp-docs.md); `.claude/skills/rdc/execution.md` guard description (PLAN-rmcp-docs.md).
