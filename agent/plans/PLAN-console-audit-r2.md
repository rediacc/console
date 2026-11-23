# PLAN: Console audit in R2 -- one object per console action, a nightly hash-chained day file per org, paid visibility with an admin "show from" date, and plan-based retention for R2 and D1
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-confirm-stepup.md -- the `console.stepup` and `console.reveal` events and the step-up method recorded on a run come from that plan; AU3 waits on PLAN-tooling-code-reduction.md#CR2 and AU7 on PLAN-rmcp-policy-record.md#A1 as box edges, so neither plan joins this PR's plan set
Priority: P1 -- console runs land only as `cli.*` telemetry in Analytics Engine (private/account/src/services/event-log.service.ts:35), config pushes carry no org id, and the D1 purge drops every org's audit at 90 days, so no org can see who ran what in its console
Concurrency: parallel -- wave 1: AU1, AU3, AU4, AU6; wave 2: AU2, then AU5, AU8; wave 3: AU7, AU9, AU10; wave 4: AU11, AU12. private/account/drizzle is written by AU8 then AU9; private/account/src/services/event-log.service.ts by AU2 then AU9; private/account/src/entry/cloudflare.ts by AU2, AU8, AU9 in that order
Owns: agent/plans/PLAN-console-audit-r2.md, packages/shared/src/audit/**, packages/cli/src/services/serve/audit.ts, packages/cli/src/services/serve/__tests__/audit*.test.ts, private/account/src/services/console-audit.service.ts, private/account/src/services/audit-store.ts, private/account/src/services/audit-compaction.service.ts, private/account/src/services/audit-visibility.service.ts, private/account/src/services/event-log.service.ts, private/account/src/services/config.service.ts, private/account/src/services/config-policy.service.ts, private/account/src/routes/console.ts, private/account/src/routes/console-audit.ts, private/account/src/routes/license.ts, private/account/src/routes/root.ts, private/account/src/routes/index.ts, private/account/src/dto/console-audit.dto.ts, private/account/src/db/schema.ts, private/account/drizzle/**, private/account/src/app.ts, private/account/src/container.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/src/entry/on-premise.ts, private/account/scripts/audit-verify.ts, private/account/wrangler.toml, private/account/tests/integration/console-audit*.test.ts, private/account/tests/integration/event-log-retention.test.ts, workers/account/wrangler.*.toml, regions.json, .ci/rediacc_ci/quality/region_consistency_offline.py, .ci/rediacc_ci/quality/region_consistency_controls.py, .ci/rediacc_ci/ops/bench_preflight.py, .ci/rediacc_ci/ops/reset_bench.py, .ci/rediacc_ci/tests/gates/test_gate_region_consistency*.py, agent/plans/PLAN-d1-scaling.md, private/account/web/src/pages/console/Audit.tsx, private/account/web/src/pages/console/__tests__/audit*.test.tsx, private/account/web/src/pages/admin/CustomerDetail.tsx, private/account/web/src/router.tsx, private/account/web/src/lib/nav-config.ts, private/account/web/src/api/endpoints.ts, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/i18n/locales/*/admin.json, private/account/web/src/i18n/locales/*/nav.json
Live-Proof: bench -- the account Worker writes and compacts audit objects in the bench AUDIT_BUCKET and serves the Audit page; the executor's requestId reaches the bench through deploy_bench

## Ask

Every console action is audited: command runs, config-editor saves, policy saves, step-ups, reveals, AI approvals and feedback sends, each with who, what, the target and the verification method of a destructive run, never a secret parameter (C15). Records are written for every org and shown only to PROFESSIONAL, BUSINESS and ENTERPRISE, a trial not counting; an upgrade reveals the history (C16). Support sets "show audit starting from" per org (C17). Audit lives in R2 only, one object per event, compacted at 03:00 into one `.ndjson.gz` per org and day chaining the previous day's hash (C18). Retention is 2 years paid and 90 days otherwise, licence-state events keeping 400 days (C19), with 30 days of downgrade grace (C20).

## Context

1. `TELEMETRY_TYPES` holds `cli.*` (private/account/src/services/event-log.service.ts:35); the executor's per-command event is `cli.command` (packages/cli/src/services/serve/audit.ts:53) posted to `/audit-events` (private/account/src/routes/license.ts:397), so console runs never reach the D1 `event_log`.
2. The executor event carries `commandPath` and `destructive` (packages/shared/src/audit/event-schema.ts:191) and no request id; the console request has an optional `requestId` (packages/shared/src/cli-contract/wire.ts:76).
3. `config.push` is logged without an org id (private/account/src/services/config.service.ts:866), and so is the `config.version.restore` row after it; the store row has `orgId`.
4. `purgeExpired` (private/account/src/services/event-log.service.ts:234) deletes past one window for every org, 90 days by default (:26), retained-state types at 400 days; it runs from `runRetentionSweeps` (private/account/src/entry/cloudflare.ts:369) on the `0 3 * * *` cron (:575). `event_log` has `org_id` (private/account/src/db/schema.ts:634).
5. Regional R2 bindings with EU jurisdiction exist for CONFIG_BUCKET and BACKUP_BUCKET (workers/account/wrangler.eu.toml:55). `region_consistency_offline` checks both per target (.ci/rediacc_ci/quality/region_consistency_offline.py:501) against regions.json.
6. `BlobStorageService.list` refuses any prefix but `s/<storeId>/` (private/account/src/services/blob-storage.service.ts:35); node and on-premise runtimes bind the config bucket over S3 (private/account/src/entry/node.ts:66) and run no retention sweep.
7. Plans: packages/shared/src/subscription/types.ts:11; `paid` is true for the last three in `PLAN_METADATA` (packages/shared/src/subscription/constants.ts:573); a trial is `subscriptions.type = 'trial'` (private/account/src/db/schema.ts:98). The console resolves an org's subscription through `resolvePrimarySubscription` (private/account/src/routes/console.ts:181).
8. Admin per-org pattern: an elevated root route writing an org column and logging the change (private/account/src/routes/root.ts:462), over `organizations.console_executor_blocked_at` (private/account/src/db/schema.ts:505). The admin customer page is private/account/web/src/pages/admin/CustomerDetail.tsx.
9. PLAN-d1-scaling.md (owner d778be9d) ruled audit and billing in D1 at 90 days (its Status, Q2) and owns event-log.service.ts, schema.ts, root.ts, license.ts, cloudflare.ts and the wrangler files.

## Design

D1. **C18 supersedes PLAN-d1-scaling.md's D1-at-90-days ruling for console audit.** `console.*` events never touch D1; plain `cli.*` telemetry stays in Analytics Engine; other audit stays in D1 under D9's per-plan purge. AU2's commit adds a correction line to that plan, and session d778be9d is told before it.

D2. **Event schema now, for all eight kinds.** `packages/shared/src/audit/console-events.ts`: envelope `{v: 1, id, ts, type, orgId, teamId, actor: {userId, kind: 'human' | 'agent'}, target, data}` and types `console.command.run`, `console.command.result`, `console.config.saved`, `console.policy.saved`, `console.stepup`, `console.reveal`, `console.ai.approval`, `console.feedback.sent`; the last two are emitted by later plans.
`consoleTargetOf(entry, request)` keeps positionals and options whose contract option has `kinds` and is not `sensitive`; every other param is dropped.

D3. **One object per event.** `audit-store.ts` puts `audit/<org>/<yyyy>/<mm>/<dd>/<ts>-<id>.json` with its own prefix guard, on the `AUDIT_BUCKET` binding in Workers and under the `audit/` prefix of the config S3 bucket in node and on-premise (no new env variable). `EventLogService.log` routes `CONSOLE_AUDIT_TYPES` to the writer instead of D1, so plan 2's emitters move to R2 unchanged.

D4. **Runs are recorded by the Worker, results by the ingest.** `/console/exec` mints `requestId` when absent, forwards it, and writes `console.command.run` with pathKey, severity, target and the elevation method.
The executor sets `requestId` on its event, and `/audit-events` writes `console.command.result` (exit code, success, job id) for an event carrying one, beside the existing telemetry path.

D5. **Day file with a chain.** The 03:00 cron compacts each org's previous day into `audit/<org>/days/<yyyy>-<mm>-<dd>.ndjson.gz`: line 1 `{v, org, day, prevDay, prevSha256, count}`, then events by `ts`. `prevSha256` is the SHA-256 of the previous day file's bytes, `genesis` for the first; empty days write no file and the chain names the last real day. Per-event objects are deleted only after the file is read back and its hash recorded in `audit_compaction_state(org_id, last_day, last_sha256)`. A run handles a bounded number of orgs; the hourly cron drains the rest.

D6. **Verification by a reader other than the writer.** `private/account/scripts/audit-verify.ts --org <id> --from --to` downloads the day files through the R2 S3 API with a read-scoped token from bws and checks each header against the previous file's hash; the read API also reports `chain: ok | broken` per day from the stored hashes.

D7. **Visibility (C16, C17).** Paid means `PLAN_METADATA[plan].paid` and a non-trial primary subscription. Owners and admins of a paid org see every retained record. `organizations.audit_visible_from`, when set, is the lower bound and also grants visibility to a non-paid org from that date (support revealing records for an incident); null means the plan rule.
A non-paid org sees a teaser with the last seven days' counts from the day headers and an upgrade link.

D8. **Retention (C19, C20).** A bucket lifecycle rule expires objects after 730 days. `organizations.audit_paid_seen_at` is refreshed by the 03:00 cron for paid orgs; the sweep deletes day files older than 90 days of an org whose `audit_paid_seen_at` is null or older than 30 days, so a re-upgrade inside the grace keeps them.

D9. **D1 purge per plan.** `purgeExpired` keeps 730 days for rows whose org has `audit_paid_seen_at` within 30 days, 90 days otherwise (the `AUDIT_RETENTION_DAYS` override still sets that window), and 400 days for retained-state types, through one subquery on `organizations`, so the single-bound-parameter shape holds.

D10. **Strings.** Code boxes add English keys only; AU12 translates through the naturalization pipeline, writers on sonnet.

## Ordering against other live plans

- PLAN-console-confirm-stepup.md lands first; its D3 and D9 events need no change here.
- PLAN-d1-scaling.md: same files (Context 9); its open boxes (P3, C2 and the live boxes) do not touch the purge logic. AU2 and AU9 rebase onto any landed hunk.
- PLAN-rmcp-policy-record.md#A1 logs `config.policy.updated`; AU7 mirrors it.
- PLAN-tooling-code-reduction.md#CR2 holds .ci/** and package.json; AU3 waits for it.
- PLAN-console-ia.md edits nav-config.ts; AU11 adds one item and rebases.

## Tasks

- [ ] AU1 [writer] Shared schema per D2: `packages/shared/src/audit/console-events.ts` with the envelope, the eight types and `consoleTargetOf`, plus optional `requestId` on the executor event data in event-schema.ts, exported from the audit index.
  Owns: packages/shared/src/audit/**
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/audit)` rc 0 with cases: a `sensitive` option never in `target`, a kinds-bearing option kept, each type parses, an unknown type fails.
- [ ] AU2 [writer] Store and writer per D3 and the D1 correction: `audit-store.ts` (R2, S3 under `audit/`, memory), `console-audit.service.ts`, `CONSOLE_AUDIT_TYPES` routing in `EventLogService.log`, container and entry wiring, and the correction line on PLAN-d1-scaling.md.
  Owns: private/account/src/services/audit-store.ts, private/account/src/services/console-audit.service.ts, private/account/src/services/event-log.service.ts, private/account/src/app.ts, private/account/src/container.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/node.ts, private/account/src/entry/on-premise.ts, private/account/tests/integration/console-audit-writer.test.ts, agent/plans/PLAN-d1-scaling.md
  Depends on: AU1.
  Accept: `(cd private/account && npx vitest run tests/integration/console-audit-writer.test.ts)` rc 0 with cases: one object per event at the D3 key, a `console.stepup` log writes no D1 row, a key outside `audit/<org>/` refused; `(cd private/account && npm run typecheck)` rc 0.
- [ ] AU3 [writer] `AUDIT_BUCKET` in every account wrangler file (eu with `jurisdiction = "eu"`), private/account/wrangler.toml, `auditR2` in regions.json, the region-consistency arm with a control fixture lacking the binding, and bench_preflight and reset_bench reading it.
  Owns: workers/account/wrangler.*.toml, private/account/wrangler.toml, regions.json, .ci/rediacc_ci/quality/region_consistency_offline.py, .ci/rediacc_ci/quality/region_consistency_controls.py, .ci/rediacc_ci/ops/bench_preflight.py, .ci/rediacc_ci/ops/reset_bench.py, .ci/rediacc_ci/tests/gates/test_gate_region_consistency*.py
  Depends on: PLAN-tooling-code-reduction.md#CR2.
  Accept: `npm run check:ci-region-consistency` rc 0 on the tree, and its selftest fails the control fixture with no AUDIT_BUCKET; the region-consistency gate tests under .ci/rediacc_ci/tests/gates pass under `npm run check:ci-pytest` rc 0.
- [ ] AU4 [lead] Create the audit buckets of the four targets with a 730-day expiry rule (`npx wrangler r2 bucket create <name>` with `--jurisdiction eu` for eu, then `npx wrangler r2 bucket lifecycle add`), bench first, production before the first production deploy carrying AU3.
  Owns: none -- Cloudflare resources only, no tracked file
  Depends on: none.
  Accept: `npx wrangler r2 bucket lifecycle list <name>` shows the 730-day rule for each of the four buckets, quoted in the tick.
- [ ] AU5 [writer] Account emitters per D4 and Context 3: `/console/exec` mints and forwards `requestId` and writes `console.command.run`; `/audit-events` writes `console.command.result` for an event with `requestId`; `config.push` and `config.version.restore` carry `orgId` and write `console.config.saved`.
  Owns: private/account/src/routes/console.ts, private/account/src/routes/license.ts, private/account/src/services/config.service.ts, private/account/tests/integration/console-audit-emit.test.ts
  Depends on: AU2, PLAN-console-confirm-stepup.md#CF3.
  Accept: `(cd private/account && npx vitest run tests/integration/console-audit-emit.test.ts)` rc 0 with cases: a destructive run records target and method and no `params`, a `repo secret set` value never appears in any object, a result joins its run by `requestId`, a config push row carries the org id.
- [ ] AU6 [writer] The executor sets `requestId` from the command request on its audit event in packages/cli/src/services/serve/audit.ts.
  Owns: packages/cli/src/services/serve/audit.ts, packages/cli/src/services/serve/__tests__/audit*.test.ts
  Depends on: AU1.
  Accept: `(cd packages/cli && npx vitest run src/services/serve/__tests__/audit)` rc 0.
- [ ] AU7 [writer] Mirror `config.policy.updated` as `console.policy.saved` (store, config, team, actor, version, never content) in config-policy.service.ts.
  Owns: private/account/src/services/config-policy.service.ts, private/account/tests/integration/console-audit-policy.test.ts
  Depends on: AU2, PLAN-rmcp-policy-record.md#A1.
  Accept: `(cd private/account && npx vitest run tests/integration/console-audit-policy.test.ts)` rc 0.
- [ ] AU8 [writer] Compaction per D5 and D6: `audit-compaction.service.ts`, the `audit_compaction_state` migration, the 03:00 and hourly cron hooks, and `private/account/scripts/audit-verify.ts`.
  Owns: private/account/src/services/audit-compaction.service.ts, private/account/src/db/schema.ts, private/account/drizzle/**, private/account/src/entry/cloudflare.ts, private/account/scripts/audit-verify.ts, private/account/tests/integration/console-audit-compaction.test.ts
  Depends on: AU2.
  Accept: `(cd private/account && npx vitest run tests/integration/console-audit-compaction.test.ts)` rc 0 with cases: two days chain with the first day's hash, an empty day skipped, a crash before read-back keeps the per-event objects, a byte flipped in a day file makes the verifier exit 1, a bounded run resumes on the next.
- [ ] AU9 [writer] Visibility and retention per D7 to D9: `organizations.audit_visible_from` and `audit_paid_seen_at`, `audit-visibility.service.ts`, the paid-seen refresh and the non-paid R2 sweep in the 03:00 sweeps, and `purgeExpired` per plan.
  Owns: private/account/src/services/audit-visibility.service.ts, private/account/src/services/event-log.service.ts, private/account/src/db/schema.ts, private/account/drizzle/**, private/account/src/entry/cloudflare.ts, private/account/tests/integration/event-log-retention.test.ts, private/account/tests/integration/console-audit-retention.test.ts
  Depends on: AU8.
  Accept: `(cd private/account && npx vitest run tests/integration/event-log-retention.test.ts tests/integration/console-audit-retention.test.ts)` rc 0 with cases: a trial ENTERPRISE org is not paid, a paid org keeps a 400-day D1 row, a free org loses it at 91 days, a downgrade 20 days ago keeps 100-day files, 31 days ago deletes them, a re-upgrade inside grace shows them.
- [ ] AU10 [writer] Read API and admin field: `routes/console-audit.ts` (`GET /console/audit` for paid owners and admins, `GET /console/audit/teaser`), `POST /admin/customers/:id/audit-visible-from` on the root.ts pattern, logged.
  Owns: private/account/src/routes/console-audit.ts, private/account/src/routes/index.ts, private/account/src/routes/root.ts, private/account/src/dto/console-audit.dto.ts, private/account/tests/integration/console-audit-read.test.ts
  Depends on: AU9.
  Accept: `(cd private/account && npx vitest run tests/integration/console-audit-read.test.ts)` rc 0 with cases: member 403, non-paid owner 403 on the list and 200 on the teaser, `audit_visible_from` opens a free org from that date only, a broken chain day reports `broken`, the admin route needs elevation.
- [ ] AU11 [writer] Web: `pages/console/Audit.tsx` (list, filters by type and actor, chain status), the teaser with an upgrade link for non-paid orgs, the route and one nav item, and the "show audit starting from" field on CustomerDetail; English keys in en/console.json, en/admin.json and en/nav.json.
  Owns: private/account/web/src/pages/console/Audit.tsx, private/account/web/src/pages/console/__tests__/audit-page.test.tsx, private/account/web/src/pages/admin/CustomerDetail.tsx, private/account/web/src/router.tsx, private/account/web/src/lib/nav-config.ts, private/account/web/src/api/endpoints.ts, private/account/web/src/i18n/locales/en/console.json, private/account/web/src/i18n/locales/en/admin.json, private/account/web/src/i18n/locales/en/nav.json
  Depends on: AU10.
  Accept: `(cd private/account/web && npx vitest run src/pages/console/__tests__/audit-page.test.tsx)` rc 0; `(cd private/account && npm run typecheck:web)` rc 0.
- [ ] AU12 [writer] Translate AU11's new keys into the 12 other locales through the naturalization pipeline (writers on sonnet), then lock the hashes.
  Owns: private/account/web/src/i18n/locales/*/console.json, private/account/web/src/i18n/locales/*/admin.json, private/account/web/src/i18n/locales/*/nav.json
  Depends on: AU11.
  Accept: `npm run check:i18n` rc 0 and `npm run check:ci-i18n-account-key-usage` rc 0.
- [ ] LP-bench [live] Deploy the branch to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`), run a destructive console command, a config save and a step-up, trigger the compaction through the cron path, and read the day file back with `audit-verify.ts`; a `./rdc.sh --config eu-bench --proxy` run (cli-bench) is additional verification of the executor's `requestId`.
  Accept: live-proof bench account-smoke

## Risks

- **Cron subrequest budget.** One org-day costs a list, the reads, one put, one read-back and the deletes; D5 bounds a run and the hourly cron drains, so a large backlog finishes late rather than failing.
- **Node and on-premise runtimes run no cron** (Context 6): they write and read per-event objects and do not compact or sweep, shown on the Audit page's chain status as `not compacted`.
- **A secret reaching an object through a mislabelled option.** `consoleTargetOf` keeps only `kinds`-bearing, non-`sensitive` options, and AU5 tests a `repo secret set` end to end.
- **Shared files with PLAN-d1-scaling.md.** D1's correction line and the notice to d778be9d come before AU2's commit.
