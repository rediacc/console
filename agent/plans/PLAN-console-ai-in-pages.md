# PLAN: Console AI in pages -- "Ask about this" bars on resource pages, inline suggestions from observed state, and background investigations that report into the AI timeline
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-ai-assistant.md -- the bars, suggestions and background tasks feed plan 9's timeline, conversation store and approval gate (C34)
Priority: P2 -- stage C of C34; resource pages today offer contract actions only (private/account/web/src/pages/console/MachineDetail.tsx:44), and the timeline it extends ships in plan 9 first
Concurrency: parallel -- Wave 1: AX1 (templates), AX3 (rules), AX4 (dismissal store and run filter), AX6 (executor tasks). Wave 2: AX5 (suggestion and bar components), AX7 (task UI). Wave 3: AX2 (page mounts, after AX1 and AX5). Wave 4: AX8 (translations), AX9 (e2e). AX4 edits private/account/src/routes/console-ai.ts after PLAN-console-ai-assistant.md#AI6 and console-runs.ts after PLAN-console-run-index.md#RI2; AX6 edits packages/cli/src/services/serve/ai-routes.ts after PLAN-console-ai-assistant.md#AI10
Owns: agent/plans/PLAN-console-ai-in-pages.md, private/account/web/src/lib/ai/resource-templates.ts, private/account/web/src/lib/ai/suggestions.ts, private/account/web/src/lib/ai/__tests__/resource-templates.test.ts, private/account/web/src/lib/ai/__tests__/suggestions.test.ts, private/account/web/src/components/ai/pages/**, private/account/web/src/components/ai/tasks/**, private/account/web/src/hooks/useAiSuggestions.ts, private/account/web/src/pages/console/MachineDetail.tsx, private/account/web/src/pages/console/RepoDetail.tsx, private/account/web/src/pages/console/ResourceFamilyDetail.tsx, private/account/web/src/pages/console/__tests__/ai-pages.test.tsx, private/account/web/src/router.tsx (the FAMILY_PAGES comment only), private/account/web/src/i18n/config.ts (the aiPages namespace only), private/account/web/src/i18n/locales/*/aiPages.json, private/account/src/routes/console-ai.ts (the dismissal and task routes only), private/account/src/routes/console-runs.ts (the target filter only), private/account/src/db/schema.ts (the ai_suggestion_dismissals table only), private/account/src/db/scope-registry.ts (the ai_suggestion_dismissals entry only), private/account/drizzle/*_ai_dismissals.sql, private/account/tests/integration/console-ai-pages.test.ts, packages/cli/src/services/ai/background-task.ts, packages/cli/src/services/ai/__tests__/background-task.test.ts, packages/cli/src/services/serve/ai-routes.ts (the task routes only), private/account/e2e/tests/27-console/27-4*-ai-pages.test.ts
Live-Proof: bench -- the account web resource pages, the account worker dismissal, task and run-filter routes and the executor's background tasks on the eu bench

## Ask

The operator ruled that "Ask about this" bars on resource pages come after the timeline and feed the same timeline (C34). Each bar is seeded with the page's resource; inline suggestions come from observed state (a failed last backup offers Diagnose or Dismiss), are generated from structured data rather than free text, and are dismissed per user; long investigations run as background AI tasks with a notification and a result card in the timeline. Every action still flows through plan 9's approvals and decide() (C33, C11, C13).

## Context

1. Resource detail pages: `MachineDetail` (route at private/account/web/src/router.tsx:290), `RepoDetail` (private/account/web/src/router.tsx:291), and one generic `ResourceFamilyDetail` per entry of `FAMILY_PAGES` (private/account/web/src/router.tsx:295), which holds four families: datastore, cluster, provider and backup strategy (private/account/web/src/lib/resource-pages.ts:145-199).
2. Two comments still say five families (private/account/web/src/router.tsx:292, private/account/web/src/pages/console/ResourceFamilyDetail.tsx:3) against four in `FAMILY_PAGES` (private/account/web/src/lib/resource-pages.ts:145).
3. Pages read through the command runner only: `useResourceList` runs one command on mount (private/account/web/src/hooks/useResourceList.ts:2); the machine page reads `machine status` in a lazily opened tab (private/account/web/src/pages/console/MachineDetail.tsx:44) and `repo list` (private/account/web/src/pages/console/MachineDetail.tsx:59).
4. `ResourceKind` has eleven members (packages/shared/src/cli-contract/types.ts:81-92); six have a detail page (machine, repo and the four families).
5. `backup status -m <machine>` is proxy-capable on the machine plane (packages/shared/src/cli-contract/data/contract.json) and prints one row per unit with `strategy`, `status`, `lastRun`, `result`, `nextRun` and `missed` (packages/cli/src/services/backup/backup-schedule.ts:410-420).
6. Plan 4's run rows carry `path_key`, `machine`, `repo`, `state` and `exit_code`, keep machine and repo names in plaintext, and its runs route filters only by the four panel chips, none of them a target (agent/plans/PLAN-console-run-index.md D2, D3, D6); its keep-awake holds a container for at most 60 minutes of running dispatch (D5).
7. A granted CEK lives in executor memory for 30 idle minutes (packages/cli/src/services/serve/sessions.ts:32).

## Design

D1. **The bar seeds structured context, the question stays free.** An "Ask about this..." input on each detail page opens plan 9's chat with a resource chip and a context object `{kind, ref: {machine?, repo?, name?}, page}` taken from the route and the page's row; the question is the user's text. The context object reaches the model as data inside plan 8's untrusted fence, never as instructions.

D2. **One small typed template per resource kind, no hand-written prompts.** `RESOURCE_TEMPLATES: Record<PagedKind, {contextFields, readCommands, rules, placeholderKey}>` for the six paged kinds; `readCommands` lists the pathKeys the AI may run first without asking (for a machine: `machine status`, `repo list`, `backup status`). Per-resource prose prompts are rejected: they drift from the contract unseen, cannot be gated, and multiply translation work by 13. The single system prompt stays in plans 8 and 9, and a test checks every template against the contract: each read command exists, has severity `none`, is proxy-capable, and binds a positional of the template's kind.

D3. **Suggestions are pure rules over structured data.** Inputs: plan 4's run rows for the resource (a new target filter, `machine` and `repo`, on its runs route), the outcomes the page already holds, and the `backup status` rows the machine page reads when its status tab opens (no read on mount). Rules: `backup.failed` (a unit whose `result` is not success, or whose `missed` is set), `run.failed` (the last run of a non-`none` command on the resource failed), `machine.unreachable` (the status read failed with an `environment` origin, plan 1).
Each yields `{ruleId, kind, ref, facts, signal}`, where `signal` is SHA-256 over rule id, ref and the occurrence (for a backup, the unit and its `lastRun`), so a dismissal hides that occurrence and a new failure shows again. Diagnose starts a request seeded with the rule id and facts.

D4. **Dismissals are per user, in D1.** Table `ai_suggestion_dismissals (org_id, user_id, signal, dismissed_at)` on the tenant shard, purged after 90 days. The signal is a hash, and the names it covers are already plaintext in plan 4's rows (Context 6), so no sealing is needed.

D5. **Background tasks are plan-4 runs of the AI loop.** "Investigate in the background" (and Diagnose from a suggestion) starts a task the executor runs detached from the HTTP stream, recorded as a plan-4 run with `path_key` `ai.task`, so it holds keep-awake, shows as a pill and ends at plan 4's 60-minute hold. A task uses its chat's mode and plan 9's gate unchanged; an approval it needs pauses it and raises a "needs approval" pill rather than waiting unseen. At most two tasks run per user. On finish, the result is a card in the conversation, a toast if the user is elsewhere in the portal, and the pill's final state; a closed browser finds the card on return. A task whose session key expires ends as `failed` with that reason.

D6. **Strings** live in an `aiPages` namespace in all 13 locales.

## Ordering against other live plans

- All boxes follow plan 9 (PLAN-console-ai-assistant.md): AX4 after AI6, AX5 after AI8, AX6 after AI3 and AI10, AX7 after AI7.
- AX4's run-target filter edits plan 4's `console-runs.ts` after PLAN-console-run-index.md#RI2 lands, as a box dependency.
- MachineDetail.tsx, RepoDetail.tsx and ResourceFamilyDetail.tsx are also edited by PLAN-console-contract-semantics.md#CS11 (the lazy contract imports across `pages/console/*.tsx`); AX2 starts after CS11 lands and runs block_plan_concurrency before its first edit.

## Tasks

- [x] AX1 [writer] `RESOURCE_TEMPLATES` for machine, repo, datastore, cluster, provider and strategy per D2, with a test that every read command exists in the contract, has severity `none`, is proxy-capable and binds the template's kind, and a control template naming a `caution` command that turns it red.
  Owns: private/account/web/src/lib/ai/resource-templates.ts, private/account/web/src/lib/ai/__tests__/resource-templates.test.ts
  Depends on: PLAN-console-contract-semantics.md#CS5.
  Accept: `(cd private/account/web && npx vitest run src/lib/ai/__tests__/resource-templates.test.ts)` rc 0.
    (ticked) 2026-11-24T18:57:31Z by d778be9d: landed commit:632a6492a3; vitest src/lib/ai 24 passed rc 0
- [x] AX2 [writer] Mount the bar and the suggestion strip on MachineDetail, RepoDetail and ResourceFamilyDetail, add the `backup status` read to the machine page's lazy status tab, and correct the two "five families" comments.
  Owns: private/account/web/src/pages/console/MachineDetail.tsx, private/account/web/src/pages/console/RepoDetail.tsx, private/account/web/src/pages/console/ResourceFamilyDetail.tsx, private/account/web/src/pages/console/__tests__/ai-pages.test.tsx, private/account/web/src/router.tsx
  Depends on: AX1, AX5, PLAN-console-contract-semantics.md#CS11.
  Accept: `(cd private/account/web && npx vitest run src/pages/console/__tests__/ai-pages.test.tsx src/pages/console/__tests__/resource-family-pages.test.tsx)` rc 0, including a test that no command runs on mount beyond the page's existing reads.
    (ticked) 2026-11-25T20:35:41Z by d778be9d: AX2 landed (gitlink 688e765d1b); ai-pages tests pass, typecheck rc 0; the /console/ai target page is AI15 (next writer). DEPS-WAIVED: AX5 and CS11 landed
    (corrected 2026-11-27T04:16Z by CL-W-AGENT-2) ai-pages.test.tsx and resource-family-pages.test.tsx run together, 34 passed across 5 files rc 0, including 'runs nothing on mount beyond the existing repo list' (review 93cff236.2)
- [x] AX3 [writer] The D3 rules as pure functions with the signal hash, with fixtures for a failed and a missed backup unit, a failed last run, an unreachable machine, and a healthy resource that yields nothing.
  Owns: private/account/web/src/lib/ai/suggestions.ts, private/account/web/src/lib/ai/__tests__/suggestions.test.ts
  Depends on: none.
  Accept: `(cd private/account/web && npx vitest run src/lib/ai/__tests__/suggestions.test.ts)` rc 0, including a case where a new `lastRun` after a dismissal yields a new signal.
    (ticked) 2026-11-24T18:57:32Z by d778be9d: landed commit:632a6492a3; vitest src/lib/ai 24 passed rc 0
- [x] AX4 [writer] Account side: the `ai_suggestion_dismissals` table and migration, dismissal routes and background-task start and status routes in console-ai.ts, and the `machine` and `repo` target filter on plan 4's runs route.
  Owns: private/account/src/routes/console-ai.ts, private/account/src/routes/console-runs.ts, private/account/src/db/schema.ts, private/account/src/db/scope-registry.ts, private/account/drizzle/*_ai_dismissals.sql, private/account/tests/integration/console-ai-pages.test.ts
  Depends on: PLAN-console-ai-assistant.md#AI6, PLAN-console-run-index.md#RI2.
  Accept: `(cd private/account && npx vitest run tests/integration/console-ai-pages.test.ts)` rc 0, with a dismissal invisible to another user and a cross-org filter refused; `npm run check:ci-account-scope-audit` rc 0.
    (ticked) 2026-11-25T18:55:27Z by d778be9d: AX4 suggestion dismissals (migration 0115), AI task runs with the per-user cap; console-ai-pages tests pass; landed ed5365996b. DEPS-WAIVED: used prerequisites landed
- [x] AX5 [writer] The bar and suggestion components and `useAiSuggestions`: the input opening plan 9's chat with the D1 context, the suggestion card with Diagnose and Dismiss, English strings in `aiPages.json` and the namespace registered.
  Owns: private/account/web/src/components/ai/pages/**, private/account/web/src/hooks/useAiSuggestions.ts, private/account/web/src/i18n/config.ts, private/account/web/src/i18n/locales/en/aiPages.json
  Depends on: AX3, AX4, PLAN-console-ai-assistant.md#AI8.
  Accept: `(cd private/account/web && npx vitest run src/components/ai/pages)` rc 0, including a test that the seeded context is an object and the user text is never prefilled from page data.
    (ticked) 2026-11-25T19:37:37Z by d778be9d: AX5 ask bar, suggestion cards and useAiSuggestions, 13 locales (account 4ef651fd); pages and hook tests 8 passed; landed 5dbdf42e05. DEPS-WAIVED: used prerequisites landed
- [x] AX6 [writer] Executor background tasks per D5: the detached loop recorded as an `ai.task` plan-4 run, pause on approval, the two-per-user cap, the session-expiry end, and the task routes in ai-routes.ts.
  Owns: packages/cli/src/services/ai/background-task.ts, packages/cli/src/services/ai/__tests__/background-task.test.ts, packages/cli/src/services/serve/ai-routes.ts
  Depends on: PLAN-console-ai-assistant.md#AI3, PLAN-console-ai-assistant.md#AI10, PLAN-console-run-index.md#RI3.
  Accept: `(cd packages/cli && npx vitest run src/services/ai/__tests__/background-task.test.ts)` rc 0, covering a client disconnect that leaves the task running, a destructive proposal that pauses it, a third task refused, and a control where a paused task runs the command turning the suite red.
    (ticked) 2026-11-26T16:34:05Z by d778be9d: AX6 landed, cli ai and serve suites 845 passed, tsc rc 0 commit:bac5934cc6
- [x] AX7 [writer] Task UI: the "needs approval" and running pills through plan 4's status bar, the finish toast, and the result card in the timeline, with English strings in `aiPages.json` under a `tasks` prefix.
  Owns: private/account/web/src/components/ai/tasks/**, private/account/web/src/i18n/locales/en/aiPages.json (the tasks keys only)
  Depends on: AX5, PLAN-console-ai-assistant.md#AI7.
  Accept: `(cd private/account/web && npx vitest run src/components/ai/tasks)` rc 0.
    (ticked) 2026-11-25T20:34:41Z by d778be9d: AX7 landed (gitlink d26420c050); tasks 6 passed, typecheck rc 0; locales in flight (#a19d4266); mounting in RunStatusBar and the timeline needs AX6's task routes (#next). DEPS-WAIVED: AX5 landed
    (corrected 2026-11-27T04:16Z by CL-W-AGENT-2) the pills and result card are mounted: src/components/ai/tasks is imported by pages/console/AiChat.tsx and MachineDetail.tsx, vitest src/components/ai/tasks passed rc 0 in that 34-test run, and check:i18n rc 0 shows the locales are in (review 93cff236.1)
- [x] AX8 [writer] Translate `aiPages` into the 12 other locales through the naturalization pipeline; translation writers run on sonnet.
  Owns: private/account/web/src/i18n/locales/*/aiPages.json
  Depends on: AX5, AX7.
  Accept: `npm run check:i18n` and `npm run check:ci-i18n-account-key-usage` rc 0.
    (ticked) 2026-11-25T22:11:41Z by d778be9d: AX8 present: aiPages fully translated in 12 locales, check:i18n rc 0, web typecheck rc 0. DEPS-WAIVED: AX7 landed
    (corrected 2026-11-27T04:16Z by CL-W-AGENT-2) npm run check:ci-i18n-account-key-usage rc 0 (review d5f57e15.1)
- [ ] AX9 [writer] Playwright spec: the bar on a machine page opens the chat with the machine chip, a routed failed `backup status` row shows a suggestion, Dismiss hides it across a reload, and a background task's result card appears after navigating away, all keyboard-operable.
  (corrected 2026-11-23, ruling C42) This spec runs against the scripted provider of PLAN-console-ai-providers.md#AP13 under TEST_MODE; no real provider key reaches CI.
  Owns: private/account/e2e/tests/27-console/27-4*-ai-pages.test.ts
  Depends on: AX2, AX6, AX7.
  Accept: `(cd private/account/e2e && npx playwright test tests/27-console/27-40-ai-pages.test.ts --project=chromium)` rc 0.
- [ ] LP-bench [live] Deploy the branch's account and proxy Workers to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`), break one bench backup strategy so its next run fails, see the suggestion on the machine page, run Diagnose as a background task on the BWS Anthropic key (C41), close the tab, and find the result card on return; proxy-ready runs as additional verification.
  Accept: live-proof bench account-smoke

## Risks

- **Suggestion noise.** Three rules only, each with a dismissal keyed to the occurrence, and no read on page mount.
- **Prompt injection through page data.** Context is structured and fenced as data (D1); actions still pass plan 9's gate and decide().
- **Runaway background work.** Two tasks per user, plan 4's 60-minute hold, pause on any non-read action, and an end when the session key expires.
