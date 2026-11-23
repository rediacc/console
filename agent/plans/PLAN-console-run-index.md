# PLAN: Console run index -- every run recorded per org on the server, the executor kept awake until a dispatch ends, and a block-stream panel on every account page
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-contract-semantics.md -- run blocks read the summary and severity that plan exports (C5, C6) through its lazy contract provider (CS11), and that plan edits Layout.tsx, CommandPalette.tsx, RunHistory.tsx, api/console.ts and the console pages first; the remote-mcp edges are box-level (RI3, RI6) so this plan does not wait for that program's promotion (C40)
Priority: P1 -- a synchronous console run whose client left loses its in-flight count when the body is cancelled (workers/proxy/src/org-executor-support.ts:311-313) and the container may stop 2 minutes later (workers/proxy/src/org-executor.ts:96) while the dispatch still runs; no run record exists on any server, and the Jobs page needs a typed machine name (private/account/web/src/pages/console/Jobs.tsx:66)
Concurrency: parallel -- three file-disjoint groups: account store and routes (RI1, RI2), executor and proxy (RI3, RI5, RI6, after RI0 and RI4 in packages/shared), web (RI7, then RI8 and RI10 in parallel, RI9 after RI8, RI11 after them, RI12 last). packages/cli/src/services/serve/server.ts and job-routes.ts are also edited by PLAN-rmcp-writeback.md, PLAN-rmcp-executor-hardening.md and PLAN-rmcp-decide.md, so RI3 waits on the named boxes and RI5 follows RI3 in one writer group; private/account/src/db/schema.ts is also edited by PLAN-rmcp-executor-hardening.md (a migration number clash is renumbered at landing); CommandPage.tsx is also edited by PLAN-console-confirm-stepup.md, and RI7 touches only its history and job-id lines
Owns: agent/plans/PLAN-console-run-index.md, packages/shared/src/cli-contract/mask.ts, packages/shared/src/cli-contract/__tests__/mask.test.ts, packages/shared/src/config-crypto/run-tail.ts, packages/shared/src/config-crypto/__tests__/run-tail.test.ts, packages/shared/src/cli-contract/wire.ts, packages/cli/src/services/feedback/redact.ts, packages/cli/src/services/serve/run-index.ts, packages/cli/src/services/serve/busy.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/job-routes.ts, packages/cli/src/services/serve/deps.ts, packages/cli/src/services/serve/sessions.ts, packages/cli/src/commands/serve.ts, packages/cli/src/services/serve/__tests__/run-index*.test.ts, packages/cli/src/services/serve/__tests__/busy*.test.ts, workers/proxy/src/org-executor.ts, workers/proxy/src/org-executor-support.ts, workers/proxy/src/egress.ts, workers/proxy/src/__tests__/org-executor-keepawake.test.ts, workers/proxy/src/__tests__/egress.test.ts, private/account (gitlink bump only), private/account/src/db/schema.ts, private/account/src/db/scope-registry.ts, private/account/src/db/shard-router.ts, private/account/drizzle/*_console_run_index.sql, private/account/drizzle/meta/**, private/account/src/services/console-run.service.ts, private/account/src/container.ts, private/account/src/routes/console-runs.ts, private/account/src/routes/console.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/tests/integration/console-run-*.test.ts, private/account/web/src/api/console.ts, private/account/web/src/hooks/useRuns.ts, private/account/web/src/hooks/useRunHistory.ts, private/account/web/src/hooks/__tests__/use-runs.test.ts, private/account/web/src/hooks/__tests__/use-run-history.test.ts, private/account/web/src/lib/run-history.ts, private/account/web/src/lib/__tests__/run-history.test.ts, private/account/web/src/components/console/RunHistory.tsx, private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/components/console/runs/**, private/account/web/src/components/Layout.tsx, private/account/web/src/pages/console/CommandPage.tsx, private/account/web/src/pages/console/Jobs.tsx, private/account/web/src/pages/console/__tests__/jobs.test.tsx, private/account/web/src/i18n/locales/*/console.json, private/account/e2e/tests/27-console/27-03-run-panel.test.ts
Live-Proof: bench -- the proxy Worker's keep-awake, the executor's run recorder and the account worker's run index routes are proved on the eu bench with a run whose browser closes mid-dispatch (RI-L1)

## Ask

C21: runs are indexed on the server per org; the executor records each run's start and end; the console reads the list across devices and teammates; the container stays awake until a run ends. C22: a docked panel on every account page holds one scrolling feed of run blocks (finished ones fold to a line, running ones stay live, filters for the viewer's own runs, the team's runs, running and failed, the prompt at the bottom), and a thin status bar shows running runs as pills while the panel is closed. C26: command history is stored on the server per user, secret values masked before saving. The prompt slot is filled by PLAN-console-command-line.md (C23); animations inside run blocks come from PLAN-console-animations.md (C29).

## Context

1. The executor dispatches inside `streamText` and keeps running when the client leaves: `safeWrite` drops the write (packages/cli/src/services/serve/server.ts:255-257); the job id is announced first (`onJobStarted`, :281-289); audit runs after the dispatch (:330-352).
2. The Durable Object counts a request in flight only until its response body closes (workers/proxy/src/org-executor.ts:312-318, :335); `trackBody` releases on cancel (workers/proxy/src/org-executor-support.ts:311-313). The alarm holds the container only while `inFlight > 0` (workers/proxy/src/org-executor.ts:359-363) and stops it after `sleepAfter = '2m'` (:96, :364-368).
3. One OrgExecutor instance serves one org and placement and retires on relocation (workers/proxy/src/org-executor.ts:8); on-premise runs a daemon executor with no Durable Object (agent/plans/PLAN-rmcp-executor-hardening.md Design 15 to 19).
4. The executor already reaches the account server through the egress with its own token: audit posts to `/account/api/v1/licenses/audit-events` (packages/cli/src/services/serve/audit.ts:125) under `audit:write`, one of the two executor scopes (private/account/src/services/executor-issuer.service.ts:30); the egress allowlist is `BEARER_ROUTES` (workers/proxy/src/egress.ts:31-36).
5. `requestId` is the run's idempotency key and the executor mints one when absent (packages/shared/src/cli-contract/wire.ts:70-79); the web mints one per run (private/account/web/src/hooks/useCommand.ts:111).
6. Detached jobs end on the machine; the executor learns the terminal state only when a poll observes it (packages/cli/src/services/serve/job-routes.ts:107), and the worker relays polls at private/account/src/routes/console.ts:517.
7. The console relays `/console/exec` as a byte passthrough (private/account/src/routes/console.ts:444-504); routes mount at `/console` (private/account/src/routes/index.ts:139).
8. Run history is localStorage today, capped at 50 entries (private/account/web/src/lib/run-history.ts:4, :21-23), with contract-driven redaction (:66-79); CommandPage loads it (private/account/web/src/pages/console/CommandPage.tsx:56) and drops the job id `useCommand` returns (:55).
9. The Jobs page asks for a machine and runs `job list` once (private/account/web/src/pages/console/Jobs.tsx:66). `useJobStream` re-attaches by line count (private/account/web/src/hooks/useJobStream.ts:1-12); `StepsCard` renders renet step events (private/account/web/src/components/console/StepTimeline.tsx:1-11).
10. The authed shell mounts one session scope and the palette for every page (private/account/web/src/components/Layout.tsx:48-62, :98-125).
11. Tenant tables register a scope and a shard class (private/account/src/db/scope-registry.ts:35, private/account/src/db/shard-router.ts:41); nightly purges run from private/account/src/entry/cloudflare.ts:238-243 and the Node timers from private/account/src/entry/node.ts:126-140.
12. CLI redaction masks contract-sensitive options and fails closed on unknown keys (packages/cli/src/services/feedback/redact.ts:80-89).

## Design

D1. **Store: a D1 table in the account worker, not the org Durable Object.** The Durable Object is per org and placement and retires on relocation (Context 3), so its storage would lose the index on every move; on-premise has no Durable Object while its Node account server shares the drizzle schema; the panel's filters (user, team, state, time) are SQL queries, and reading Durable Object storage from the account worker would add a cross-worker hop to every panel poll. Tables `console_runs` (org-scoped, tenant shard) and `console_command_history` (user and org scoped, tenant shard).

D2. **Run row.** `org_id`, `run_id` (the requestId), `team_id`, `user_id`, `path_key`, `machine`, `repo`, `job_id`, `state` (`running`, `detached`, `succeeded`, `failed`, `cancelled`), `exit_code`, `error_code`, `last_step`, `started_at`, `updated_at`, `ended_at`, `seq`, `tail` (sealed, at most 8 KiB). Params are never stored. Rows older than 30 days are purged nightly: the index is an operational view, and audit (PLAN-console-audit-r2.md, C15 to C18) stays the record.

D3. **Output tail sealed with the config key.** The executor seals the last 8 KiB of stdout and stderr with AES-GCM under an HKDF subkey of the session CEK (`info` `rediacc/run-tail/v1`, AAD `org_id|run_id`); the browser opens it only when unlocked, so the account server never reads command output. A run with no config session stores no tail. Machine and repo names stay plaintext, as the audit event already carries them (packages/cli/src/services/serve/audit.ts:73-75).

D4. **Executor recorder.** `run-index.ts` posts `start` after authorize, `progress` at most every 15 s (last step, tail), `job` on handoff and `end` with exit and error code, to `POST /account/api/v1/console/runs/events` with the executor token under `audit:write` (no new scope, no issuer edit).
Each event carries `seq`; the route keeps the highest. Delivery retries twice and never fails the command. A terminal poll in job-routes posts `end` for a `detached` row; a detached row no client polls stays `detached`, and the panel re-attaches it while open, which records the end.

D5. **Keep-awake until the dispatch ends.** The executor counts running dispatches (`busy.ts`) and answers `GET /v1/busy`. The alarm, finding `inFlight === 0`, asks the container; while dispatches run it holds the lease and re-arms, up to a literal `MAX_DISPATCH_HOLD_MS` of 60 minutes. `sleepAfter` stays `'2m'`, so the proxy cost guard (`PYTHONPATH=.ci python3 -m rediacc_ci.quality.proxy_cost_guard`) is unaffected.
The Worker's forward refuses `/v1/busy` from outside; only the alarm reaches it.

D6. **API.** Session routes in `routes/console-runs.ts`, mounted by one line in console.ts: `GET /console/runs?filter=mine|team|running|failed&cursor=` (Team is the active team; an org owner or admin may pass `team=all`), `GET /console/runs/:id`, `GET /console/history`, `POST /console/history`. Re-attach of a job-backed run uses the existing poll route (Context 6). The TEST_MODE mock exec path writes the same rows, so e2e runs without an executor.

D7. **History (C26).** The masking rule moves to `packages/shared/src/cli-contract/mask.ts` (contract `sensitive` plus the fail-closed unknown key), used by the web before sending, by the account route before insert and by redact.ts.
Cap 200 entries per user and org; the localStorage history is deleted (clean break).

D8. **Panel.** `components/console/runs/`: `RunPanel` docked at the bottom of `SidebarInset`, resizable, open state kept per browser; one feed, newest last; a finished block folds to one line (status, summary, target, duration, user); a running block shows `StepsCard`, live output and the animation slot of PLAN-console-animations.md; filter chips for the viewer's own runs, the team's runs, running and failed (labels "Own", "Team", "Running", "Failed"); a `RunPanelPromptSlot` at the bottom that PLAN-console-command-line.md fills. Polls every 5 s while open and every 30 s for the status bar. Shown only when `useConsoleAccess().allowed`.

D9. **Status bar and pages.** A thin bar under the content while the panel is closed, one pill per running run; a click opens the panel on that block. The Jobs page lists index rows with the panel's chips and links job-backed rows to job detail. CommandPage hands its requestId and job id to the panel and focuses that block when the run starts.

## Ordering against other live plans

- PLAN-console-contract-semantics.md lands first (header edge).
- PLAN-rmcp-writeback.md: RI3 waits on WB7 (job routes) and WB8 (audit and result path in server.ts); RI6 waits on WB5 (egress routes). PLAN-rmcp-executor-hardening.md: RI3 waits on EH4 (sessions.ts) and EH9 (commands/serve.ts). PLAN-rmcp-decide.md D3 also edits server.ts on different lines; whichever lands second rebases.
- PLAN-rmcp-remote-worker.md RW-T2 edits workers/proxy/src/org-executor.ts; RI5 touches only `alarm()` and the forward refusal.
- PLAN-console-command-line.md and PLAN-console-animations.md depend on this plan (RI8's slots).

## Tasks

- [ ] RI0 [writer] Shared parameter masking (D7): `maskParams(entry, params)` in packages/shared/src/cli-contract/mask.ts, masking every contract-`sensitive` option and positional and any key the contract does not know whose name `isSensitiveKey` matches, with packages/cli/src/services/feedback/redact.ts calling it for option values.
  Owns: packages/shared/src/cli-contract/mask.ts, packages/shared/src/cli-contract/__tests__/mask.test.ts, packages/cli/src/services/feedback/redact.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/cli-contract/__tests__/mask.test.ts)` rc 0 with a control where an unknown `api-token` key is masked; `(cd packages/cli && npx vitest run src/services/feedback)` rc 0 unchanged.
- [ ] RI1 [writer] Run index store (D1, D2): `console_runs` and `console_command_history` in schema.ts with a drizzle migration, scope registry and tenant shard class entries, and `ConsoleRunService` (event upsert keeping the highest `seq`, filtered cursor list, get, history append with masking and a 200-entry cap, 30-day purge) registered in container.ts.
  Owns: private/account/src/db/schema.ts, private/account/src/db/scope-registry.ts, private/account/src/db/shard-router.ts, private/account/drizzle/*_console_run_index.sql, private/account/drizzle/meta/**, private/account/src/services/console-run.service.ts, private/account/src/container.ts, private/account/tests/integration/console-run-store.test.ts
  Depends on: RI0.
  Accept: `(cd private/account && npx vitest run tests/integration/console-run-store.test.ts)` rc 0: an out-of-order `seq` keeps the newer state, org B never reads org A's rows, history keeps 200 and masks a sensitive param, a 31-day-old row is purged.
- [ ] RI2 [writer] Run index routes (D6): `routes/console-runs.ts` with the executor-bearer `POST /console/runs/events` (`apiTokenAuth('audit:write')`, org and team from the token) and the session routes for runs and history, one mount line in console.ts, the TEST_MODE mock exec path writing start and end rows, and the purge called from entry/cloudflare.ts and entry/node.ts.
  Owns: private/account/src/routes/console-runs.ts, private/account/src/routes/console.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/tests/integration/console-run-routes.test.ts
  Depends on: RI1.
  Accept: `(cd private/account && npx vitest run tests/integration/console-run-routes.test.ts)` rc 0: an executor event without `audit:write` is 403, a member's `filter=team` excludes another team, `team=all` is refused for a member and allowed for an admin, a mock exec writes a row the list returns.
- [ ] RI3 [writer] Executor run recorder (D3, D4): `run-index.ts` posting start, progress (15 s throttle), job and end events with the sealed tail; hooks in server.ts around the dispatch, an `end` on the first terminal poll in job-routes.ts, the `runIndex` field in deps.ts, a CEK accessor in sessions.ts, and the wiring in commands/serve.ts.
  Owns: packages/cli/src/services/serve/run-index.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/job-routes.ts, packages/cli/src/services/serve/deps.ts, packages/cli/src/services/serve/sessions.ts, packages/cli/src/commands/serve.ts, packages/cli/src/services/serve/__tests__/run-index*.test.ts
  Depends on: RI4, PLAN-rmcp-writeback.md#WB7, PLAN-rmcp-writeback.md#WB8, PLAN-rmcp-executor-hardening.md#EH4, PLAN-rmcp-executor-hardening.md#EH9.
  Accept: `(cd packages/cli && npx vitest run src/services/serve/__tests__/run-index.test.ts src/services/serve/__tests__/run-index-client-gone.test.ts)` rc 0: one start and one end per run with rising `seq`, a client that disconnects mid-dispatch still produces the end event, an unreachable account route leaves the command's result unchanged, the tail opens with the CEK and not without it.
- [x] RI4 [writer] Run tail sealing (D3): `sealRunTail` and `openRunTail` in packages/shared/src/config-crypto/run-tail.ts over the existing HKDF and AES helpers, usable in Node and the browser, imported through the `./config-crypto/*` subpath.
  Owns: packages/shared/src/config-crypto/run-tail.ts, packages/shared/src/config-crypto/__tests__/run-tail.test.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/config-crypto/__tests__/run-tail.test.ts)` rc 0: round trip, a changed `run_id` in the AAD fails to open, a tail over 8 KiB is cut from the front.
    (ticked) 2026-11-23T18:18:05Z by ace763dd: commit:7d41f658a6 landed; writer accept rc=0, lead re-verified on the landed tree
- [ ] RI5 [writer] Keep-awake until the dispatch ends (D5): the dispatch counter in busy.ts and `GET /v1/busy` (route constant in wire.ts `PROXY_ROUTES`, served in server.ts), the OrgExecutor alarm asking it when nothing is in flight and holding the lease up to `MAX_DISPATCH_HOLD_MS`, and the forward refusing `/v1/busy` from outside.
  Owns: packages/cli/src/services/serve/busy.ts, packages/cli/src/services/serve/server.ts, packages/cli/src/services/serve/__tests__/busy*.test.ts, packages/shared/src/cli-contract/wire.ts, workers/proxy/src/org-executor.ts, workers/proxy/src/org-executor-support.ts, workers/proxy/src/__tests__/org-executor-keepawake.test.ts
  Depends on: RI3.
  Accept: `(cd workers/proxy && npx vitest run src/__tests__/org-executor-keepawake.test.ts)` rc 0: with the body cancelled and one dispatch running the alarm re-arms instead of stopping, with none it stops at `sleepAfter`, a hold past 60 minutes stops, an outside `/v1/busy` is refused; `(cd packages/cli && npx vitest run src/services/serve/__tests__/busy.test.ts)` rc 0; `PYTHONPATH=.ci python3 -m rediacc_ci.quality.proxy_cost_guard` rc 0.
- [ ] RI6 [writer] Egress admits the run events route: `POST /account/api/v1/console/runs/events` joins `BEARER_ROUTES` with no query admitted.
  Owns: workers/proxy/src/egress.ts, workers/proxy/src/__tests__/egress.test.ts
  Depends on: PLAN-rmcp-writeback.md#WB5.
  Accept: `(cd workers/proxy && npx vitest run src/__tests__/egress.test.ts)` rc 0 with the route admitted, a query string refused, and `GET` on the same path refused.
- [ ] RI7 [writer] Web data layer and history (D7, D9): `listRuns`, `getRun` and history calls in api/console.ts, `useRuns` and `useRunHistory`, RunHistory.tsx, CommandPage.tsx and CommandPalette.tsx reading server history, lib/run-history.ts and its test deleted, and CommandPage handing its requestId and job id to the panel context.
  Owns: private/account/web/src/api/console.ts, private/account/web/src/hooks/useRuns.ts, private/account/web/src/hooks/useRunHistory.ts, private/account/web/src/hooks/__tests__/use-runs.test.ts, private/account/web/src/hooks/__tests__/use-run-history.test.ts, private/account/web/src/lib/run-history.ts, private/account/web/src/lib/__tests__/run-history.test.ts, private/account/web/src/components/console/RunHistory.tsx, private/account/web/src/components/console/CommandPalette.tsx, private/account/web/src/pages/console/CommandPage.tsx
  Depends on: RI0, RI2.
  Accept: `(cd private/account/web && npx vitest run src/hooks/__tests__/use-runs.test.ts src/hooks/__tests__/use-run-history.test.ts)` rc 0 (a sensitive param leaves the browser masked); `git grep -n "run-history" -- private/account/web/src` prints nothing; `(cd private/account/web && npm run typecheck)` rc 0.
- [ ] RI8 [writer] Block-stream panel (D8): RunPanel, RunBlock, RunFilters and the panel context with the prompt slot and the animation slot under components/console/runs/, reusing `useJobStream` for job-backed running blocks and `StepsCard` for steps, opening the sealed tail when unlocked, English strings in console.json.
  Owns: private/account/web/src/components/console/runs/**, private/account/web/src/i18n/locales/en/console.json
  Depends on: RI4, RI7.
  Accept: `(cd private/account/web && npx vitest run src/components/console/runs)` rc 0: a finished block renders one line, a running one renders steps and output, each filter narrows the feed, a locked session shows the tail as locked.
- [ ] RI9 [writer] Status bar and mount (D9): RunStatusBar with one pill per running run, mounted with RunPanel in Layout.tsx inside `ConsoleScope`, rendered only for console-allowed users.
  Owns: private/account/web/src/components/Layout.tsx, private/account/web/src/components/console/runs/RunStatusBar.tsx, private/account/web/src/components/console/runs/__tests__/run-status-bar.test.tsx
  Depends on: RI8.
  Accept: `(cd private/account/web && npx vitest run src/components/console/runs/__tests__/run-status-bar.test.tsx src/components/__tests__)` rc 0: two running runs give two pills, a click opens the panel focused on that run, a user without console access sees neither.
- [ ] RI10 [writer] Jobs page reads the index (D9): the machine input is removed, the page lists index rows with the panel's filter chips, and job-backed rows link to job detail.
  Owns: private/account/web/src/pages/console/Jobs.tsx, private/account/web/src/pages/console/__tests__/jobs.test.tsx
  Depends on: RI7.
  Accept: `(cd private/account/web && npx vitest run src/pages/console/__tests__/jobs.test.tsx)` rc 0; `git grep -n "jobs-machine" -- private/account/web/src` prints nothing.
- [ ] RI11 [writer] Translations of the panel, status bar and Jobs strings into the 12 other locales of console.json, naturalized per docs/i18n/CONVENTIONS.md, writers on sonnet.
  Owns: private/account/web/src/i18n/locales/*/console.json
  Depends on: RI8, RI9, RI10.
  Accept: `npm run check:ci-i18n-account-key-usage` rc 0 and `npm run ci -- --narrow` rc 0.
- [ ] RI12 [writer] E2e of the panel against the TEST_MODE mock: a run from a command page appears as a running block, folds to one line when done, the filters narrow the feed, and the status bar shows a pill while the panel is closed.
  Owns: private/account/e2e/tests/27-console/27-03-run-panel.test.ts
  Depends on: RI2, RI9, RI10.
  Accept: `(cd private/account/e2e && npx playwright test tests/27-console/27-03-run-panel.test.ts)` rc 0.
- [ ] LP-bench [live] Deploy the branch's proxy and account Workers to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench` and `PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) so RI-L1 runs against the keep-awake, recorder and routes this branch builds; account-smoke and cli-bench run as additional verification.
  Accept: live-proof bench proxy-ready
- [ ] RI-L1 [live] eu bench: start a synchronous run longer than 3 minutes from the console, close the browser at once, reopen after 4 minutes on a second device as a teammate, and see the row end `succeeded` with its tail; the executor log shows no idle stop during the dispatch. Local-route: deploy-proxy-bench, deploy-bench -- the branch Workers serve the eu bench and the console is driven from this machine.
  Depends on: LP-bench.
  Accept: the transcript, the row JSON from `GET /console/runs/:id` and the executor log lines recorded in this plan.

## Risks

- A dispatch that hangs holds a container for up to 60 minutes; `MAX_DISPATCH_HOLD_MS` bounds the cost, and its row stays `running` until a poll or the purge.
- Two D1 writes per run plus one per 15 s of progress; the throttle is the knob if write volume grows.
- A detached run no client ever polls never records its end; the row says `detached` rather than guessing.
