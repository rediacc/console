# PLAN: Remove REDIACC_ALLOW_CONFIG_EDIT: agents lose every path to a whole-document config edit and to skipping the knowledge gate

Status: approved -- operator ruling 2026-11-20 in session 6c87d631 ("approved but do not promote", agent/programs/remote-mcp/02-decisions.md D51); promoted by the operator 2026-11-23
Depends-On: PLAN-rmcp-decide.md, PLAN-rmcp-executor-hardening.md#EHOP2 -- the removal builds on the guard code decide() reshapes; R-OP-L1 runs on the on-premise harness and scenario runner EHOP2 ships
Owner: 6c87d631
Priority: P1 -- the override lets an agent rewrite the whole config, including the policy that limits it, delete repo entries whose LUKS credential then exists nowhere, and skip the --current proof on secrets (findings 1-4)
Concurrency: exclusive -- one writer: the removal spans edit.ts, mutation-gate.ts, agent-guard.ts, process-ancestry.ts and the CLI locale files, which must change together for the suite to stay green at each commit. It starts after PLAN-rmcp-decide.md has landed, since that plan rewrites agent-guard.ts and process-ancestry.ts first.
Owns: agent/plans/PLAN-rmcp-config-edit-removal.md, packages/cli/src/commands/config/edit.ts, packages/cli/src/commands/config/field.ts, packages/cli/src/services/core/mutation-gate.ts, packages/cli/src/utils/agent-guard.ts, packages/cli/src/utils/process-ancestry.ts, packages/cli/src/utils/__tests__/agent-guard.test.ts, packages/cli/src/utils/__tests__/process-ancestry.test.ts, packages/cli/src/services/__tests__/mutation-gate.test.ts, packages/cli/src/commands/__tests__/repo-secret.test.ts, packages/cli/src/commands/config/__tests__/edit*.test.ts, packages/cli/src/i18n/locales/*/cli.json, packages/cli/README.md, .ci/config/env-manifest.json, .ci/rediacc_ci/quality/env_manifest.py, scripts/data/doc-registry.md, scripts/gates/check-docs-render-parity.ts, .ci/scripts/quality/check_removed_env_vars.py, .ci/rediacc_ci/tests/test_check_removed_env_vars.py, .ci/config/removed-env-vars.json, .ci/rediacc_ci/testrun/onprem_suites/config_edit.py, .ci/rediacc_ci/tests/test_onprem_suite_config_edit.py
Live-Proof: bench -- the built CLI from this branch runs `./rdc.sh --config eu-bench config edit --apply` and `config field rotate` in an agent environment with the old var exported, and both refuse with the eu-bench remote config left at the same version (box LP-bench); the same refusal against an on-premise config store is proved locally in R-OP-L1
Updated: 2026-11-20
First-Seen: 2026-11-20

## Ask

`REDIACC_ALLOW_CONFIG_EDIT` goes away completely (D17), with no deprecation window (CLAUDE.md rule 2):

- An agent can no longer run `rdc config edit` in any form that writes: interactive, `--apply`, or `--reveal`.
- An agent can no longer skip the knowledge gate on a sensitive pointer.
- A whole-document edit stays possible for a human at a terminal.
- The name appears nowhere in code, config, docs or locales, and a gate keeps it that way.

## Context (read 2026-11-20 against the tree; a writer re-reads each citation before relying on it)

1. **What the override unlocks.**
   - `rdc config edit` refuses an agent unless the scope is exactly `*` (packages/cli/src/commands/config/edit.ts:541-553, `checkEditGates`). The gate applies to interactive, `--apply` and `--reveal` runs (`needsAgentGate`, packages/cli/src/commands/config/edit.ts:595-596).
   - The mutation gate lets an agent skip the `--current` digest on any sensitive pointer the scope glob matches (packages/cli/src/services/core/mutation-gate.ts:108-118, `evaluateSensitiveMutation`; scope read at :193 through `configEditOverrideScope`, packages/cli/src/utils/agent-guard.ts:124-133). The var name is `OVERRIDE_VAR_CONFIG_EDIT` (packages/cli/src/utils/process-ancestry.ts:28).
2. **Why it is dangerous.**
   - The policy lives in the config document today (until PLAN-rmcp-policy-record.md), so a whole-document edit rewrites the rules that limit the agent.
   - Deleting or changing a repo entry removes its LUKS credential (packages/cli/src/commands/repo-create-delete.ts:239 writes it into the config); the encrypted volume on the host stays and can no longer be opened.
   - Edits are recorded only in a local hash-chained file rotated at 10 MB (packages/cli/src/services/core/audit-log.ts header), never in the account audit log.
3. **The locale strings advertise the override and an agent-usable whole-document path.** `errors.agent.configEdit` and `errors.agent.configEditAncestry` tell an agent to use `rdc config edit --apply config.jsonc` and to set the var (packages/cli/src/i18n/locales/en/cli.json:3366-3367); `errors.agent.rotateRequiresTty` names the var as an override (:3372), while the code behind it (packages/cli/src/commands/config/field.ts:290-291) has no such override. Each key exists in all 13 CLI locales.
4. **A doc comment promises a check the code lacks.** packages/cli/src/services/core/mutation-gate.ts:55-57 says agents can use `rotateAcknowledged` only with the override set in ancestry, but the rotate branch (:122-125) allows it for any caller. With the override gone, rotation acknowledgement must be human-only, matching the comment's intent.
5. **Reference count.** `git grep` of `REDIACC_ALLOW_CONFIG_EDIT|OVERRIDE_VAR_CONFIG_EDIT|configEditOverrideScope` outside agent ledgers, worklists and reviews lists 86 files: 14 code, config and script files (edit.ts, mutation-gate.ts, agent-guard.ts, process-ancestry.ts, four test files, packages/cli/README.md, .ci/config/env-manifest.json, .ci/rediacc_ci/quality/env_manifest.py, docs/environment-variables.md, scripts/data/doc-registry.md, scripts/gates/check-docs-render-parity.ts), 13 CLI locale files, 13 www `ai-agents-safety.md` pages and 13 www search indexes, plus other www pages.
6. **An on-premise store is a different server.** An on-premise named config syncs to the Node account server of `private/account/src/entry/on-premise.ts`, whose store is SQLite and local object storage rather than D1 and R2; a refused edit must leave that store's version unchanged too, and the locale text an operator of an air-gapped install reads must not point to a portal page the install lacks.

## Decisions

D49 and D50 (the refusal is proved against an on-premise store as well), D17 (remove completely), D22 (the remaining env opt-ins, `REDIACC_ALLOW_GRAND_REPO` and `REDIACC_ALLOW_CLUSTER_OPS`, stay and are handled by PLAN-rmcp-decide.md), D27 (policy edits move to the policy record, so no CLI path edits the policy at all). Clean break: no warning release, no alias.

## Design

1. **edit.ts.** `checkEditGates` refuses every agent for interactive, `--apply` and `--reveal`, with no scope lookup; `--dump --redacted` stays allowed for agents (read-only). `--apply` additionally requires a TTY on stdin for humans, so a script an agent drives outside the ancestry check cannot reach it either.
2. **mutation-gate.ts.** The override branch and the `overrideScope` parameter go; `rotateAcknowledged` is honoured only when `!isAgentEnvironment()` and stdin is a TTY; the module comment is rewritten to match. Agents keep exactly two allow paths: a matching `--current` digest, or a previously empty pointer.
3. **agent-guard.ts and process-ancestry.ts.** `configEditOverrideScope`, `scopeAllows`, `templateMatches` (if unused elsewhere) and `OVERRIDE_VAR_CONFIG_EDIT` are deleted.
4. **Locales.** `errors.agent.configEdit` and `configEditAncestry` become one message with no override and no `--apply` suggestion (alternatives: `--dump --redacted` and `config field set --current`); `rotateRequiresTty` drops the override sentence. All 13 CLI locales are updated through the naturalization workflow (docs/i18n/CONVENTIONS.md), writers on sonnet.
5. **Registries.** env-manifest.json and env_manifest.py drop the var; doc-registry.md and check-docs-render-parity.ts drop their entries.
6. **Gate.** `check_removed_env_vars.py` with `.ci/config/removed-env-vars.json` (initial entry `REDIACC_ALLOW_CONFIG_EDIT`, citing D17) fails on any tracked occurrence outside `agent/ledgers`, `agent/worklist`, `agent/reviews` and `agent/programs/remote-mcp`. It is wired into `npm run ci` per the gate-author three-point rule. The www pages and search indexes are cleaned by PLAN-rmcp-docs.md; in the one PR the gate's final run follows that plan's www box.
7. **On-premise suite.** `.ci/rediacc_ci/testrun/onprem_suites/config_edit.py` runs the R5 scenarios against an on-premise config: an agent environment with the old var exported before the agent started is refused for `config edit --apply` and `config field rotate`, the store version read from the Node account server is unchanged, and the refusal text names no hosted-only page.

## Boxes

- [x] R1 [writer] edit.ts per Design 1 and its tests: an agent is refused for interactive, `--apply` and `--reveal` with the var set to `*` and verified ancestry; `--dump --redacted` passes for an agent; `--apply` without a TTY is refused for a human. Accept: `(cd packages/cli && npx vitest run src/commands/config)` rc 0.
    (ticked) 2026-11-27T07:37:42Z by d778be9d: landed commit:1a354cf896; investigation row present; the box's accept ran rc 0 in the writer's lease before landing and the landing suite ran rc 0 on the landed tree
- [x] R2 [writer] mutation-gate.ts per Design 2 and its tests: an agent with the old var set still needs `--current`; `rotateAcknowledged` is refused for an agent and for a non-TTY human; the human TTY rotate path still passes. Accept: `(cd packages/cli && npx vitest run src/services/__tests__/mutation-gate.test.ts src/commands/__tests__/repo-secret.test.ts)` rc 0.
    (ticked) 2026-11-27T07:37:43Z by d778be9d: landed commit:5b0da26b39; investigation row present; the box's accept ran rc 0 in the writer's lease before landing and the landing suite ran rc 0 on the landed tree
- [x] R3 [writer] agent-guard.ts and process-ancestry.ts deletions per Design 3, with their tests updated. Accept: `(cd packages/cli && npx vitest run src/utils/__tests__/agent-guard.test.ts src/utils/__tests__/process-ancestry.test.ts)` rc 0 and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0.
    (ticked) 2026-11-27T07:37:44Z by d778be9d: landed commit:2ea4003fc9; investigation row present; the box's accept ran rc 0 in the writer's lease before landing and the landing suite ran rc 0 on the landed tree
- [x] R4 [writer] Locales per Design 4 in all 13 CLI locales, plus env-manifest, doc-registry, docs-render-parity and packages/cli/README.md per Design 5. Accept: `npm run -s check:i18n` rc 0, `npm run -s check:ci-env-manifest` rc 0 and `npm run -s check:ci-docs-render-parity` rc 0.
    (corrected 2026-11-27T14:23Z, d778be9d) check:ci-env-manifest now at check:ci-env-registry
  (corrected 2026-11-24) the env-name gates this box names were merged into one gate by PLAN-tooling-code-reduction CR3: run `PYTHONPATH=.ci python3 -m rediacc_ci.quality.env_registry` (check:ci-env-registry), and register a new read with `npm run env:register`.
    (ticked) 2026-11-27T07:37:45Z by d778be9d: landed commit:038228c5f4; investigation row present; the box's accept ran rc 0 in the writer's lease before landing and the landing suite ran rc 0 on the landed tree
- [x] R5 [writer] Built-CLI proof: with `REDIACC_ALLOW_CONFIG_EDIT='*'` exported before an agent-marked parent process, the built `rdc config edit --apply <file>` and `rdc config field rotate` both exit non-zero with the new message on stderr and the config file unchanged (byte-compare). Accept: `(cd packages/cli && npx vitest run src/commands/config/__tests__/edit-agent-e2e.test.ts)` rc 0.
    (ticked) 2026-11-27T07:37:46Z by d778be9d: landed commit:7a15ae0943; investigation row present; the box's accept ran rc 0 in the writer's lease before landing and the landing suite ran rc 0 on the landed tree
- [ ] R6 [writer] Gate `check_removed_env_vars.py` per Design 6 with a pytest that plants an occurrence and requires rc 1, wired into `npm run ci`. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_check_removed_env_vars.py` rc 0, and `python3 .ci/scripts/quality/check_removed_env_vars.py` rc 0 once PLAN-rmcp-docs.md's www box has landed.
- [ ] R-OP1 [writer] The `config-edit` on-premise suite (Design 7) with its unit test against a recorded stack env. Accept: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_onprem_suite_config_edit.py` rc 0, including a control where an edit is admitted and the suite must fail.
- [ ] LP-bench [live] In an agent environment with the old var exported before the agent started, `./rdc.sh --config eu-bench config edit --apply <file>` and `./rdc.sh --config eu-bench config field rotate --pointer <p> --new x` both exit non-zero, and `./rdc.sh --config eu-bench config remote versions` shows the same latest version before and after. Evidence: both refusals' rc and the unchanged version recorded.
  Accept: live-proof bench cli-bench
- [ ] R-OP-L1 [live] On-premise stack: `onprem_stack up --machines container`, then the `config-edit` suite. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.testrun.onprem_scenarios --suite config-edit` rc 0, transcript recorded in this plan. Local-route: e2e-local -- the on-premise stack runs on this machine through the harness of PLAN-rmcp-executor-hardening.md

## Docs touched

docs/environment-variables.md, the www `ai-agents-safety`, `ai-agents-overview`, `ai-agents-claude-code` and `account-security` pages in 13 locales and their search indexes (all owned by PLAN-rmcp-docs.md); packages/cli/README.md (R4, here).
