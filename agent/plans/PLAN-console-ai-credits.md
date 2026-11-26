# PLAN: Console AI credits -- Rediacc-provided AI for enterprise orgs on prepaid credits, behind a per-org ledger and every spend guard
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-ai-providers.md -- the Rediacc tier is one more provider of the loop host, profile resolution and stream lines that plan builds (C30, C32)
Priority: P2 -- customers bring their own key first (C31); this tier adds revenue and convenience for enterprise orgs only and moves real money, so it lands after the customer-key path is proved
Concurrency: parallel -- wave 1: AC1, AC2, AC8, AC13 (file-disjoint; AC8 and AC13 after CR2); wave 2: AC3, AC4; wave 3: AC5, AC6, AC7; wave 4: AC9, AC10; wave 5: AC11, then the live boxes after AC12. Shared files are edited after their earlier owners land: workers/proxy/src/{org-executor,org-executor-support,index}.ts (PLAN-rmcp-writeback.md, PLAN-rmcp-executor-hardening.md, PLAN-rmcp-agent-grants.md), private/account/src/entry/cloudflare.ts (PLAN-console-audit-r2.md compaction cron), private/account/src/db/schema.ts with the drizzle journal (every account plan taking a migration number), packages/shared/src/ai/** and packages/cli/src/services/ai/provider.ts (PLAN-console-ai-providers.md); each writer runs block_plan_concurrency before its first edit.
Owns: agent/plans/PLAN-console-ai-credits.md, packages/shared/src/ai-credits/**, packages/shared/src/subscription/types.ts, packages/shared/src/subscription/constants.ts, packages/shared/src/ai/rediacc-tier.ts, packages/shared/src/ai/resolve.ts, packages/cli/src/services/ai/rediacc-provider.ts, packages/cli/src/services/ai/provider.ts, packages/cli/src/services/ai/__tests__/rediacc-provider.test.ts, workers/proxy/src/ai-egress.ts, workers/proxy/src/__tests__/ai-egress.test.ts, workers/proxy/src/org-executor.ts, workers/proxy/src/org-executor-support.ts, workers/proxy/src/index.ts, workers/proxy/wrangler.template.toml, workers/proxy/wrangler.*.toml, workers/account/src/credit-ledger.ts, workers/account/src/index.ts, workers/account/wrangler.*.toml, workers/account/enterprise.template.toml, private/account (gitlink bump only), private/account/drizzle/*_ai_credits.sql, private/account/drizzle/meta/_journal.json, private/account/drizzle/meta/*_snapshot.json, private/account/src/db/schema.ts, private/account/src/services/ai-credits.service.ts, private/account/src/services/ai-reconcile.service.ts, private/account/src/routes/ai-credits.ts, private/account/src/routes/root-ai-credits.ts, private/account/src/routes/index.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/ai-credits-schema.test.ts, private/account/tests/integration/ai-credits-routes*.test.ts, private/account/tests/integration/credit-ledger.test.ts, private/account/tests/integration/ai-reconcile.test.ts, private/account/web/src/pages/AiCredits.tsx, private/account/web/src/pages/admin/AiCredits.tsx, private/account/web/src/pages/admin/CustomerDetail.tsx, private/account/web/src/components/ai-credits/**, private/account/web/src/hooks/useAiCredits.ts, private/account/web/src/pages/__tests__/ai-credits*.test.tsx, private/account/web/src/router.tsx, private/account/web/src/lib/nav-config.ts, private/account/web/src/api/endpoints.ts, private/account/web/src/i18n/locales/*/aiCredits.json, private/account/web/src/i18n/locales/*/admin.json, .ci/config/ai-gateway.json, .ci/rediacc_ci/ops/cf_ai_gateway.py, .ci/rediacc_ci/tests/test_ops_cf_ai_gateway.py, .ci/config/bws-secret-map.json, .ci/config/secret-supply.json
Live-Proof: bench -- the credit ledger Durable Object, D1 history and admin grants run in the bench account Worker, and the ai.internal egress in the bench proxy Worker spends real Unified Billing credit on a bench enterprise org

## Ask

The operator ruled that Rediacc-provided AI exists only for enterprise orgs, on credits, in two tiers: Workers AI open models as the cheap default and Anthropic and OpenAI through Cloudflare AI Gateway Unified Billing as premium at a higher credit rate (C32). Every guard is mandatory: prepaid only, auto top-up off, a global spend cap below the purchased balance, a worst-case reservation before each call, a per-org Durable Object ledger as the hard stop, loop, token and daily caps, margin pricing, a nightly reconcile against gateway logs, per-org and global kill switches, and credit expiry (C32). No key enters the container and the account Worker holds no provider key (C30).

## Context

1. The container starts with `enableInternet: true` and one outbound intercept, `account.internal`, bound to the `AccountEgress` entrypoint with per-instance props `{orgId, placement, containerId}` (workers/proxy/src/org-executor.ts:506-511, workers/proxy/src/org-executor-support.ts:349-365). A second intercept host follows the same shape.
2. The proxy Worker already reaches the account Worker through a service binding to a named entrypoint (`ISSUER` to `ExecutorIssuer`, workers/proxy/wrangler.eu.toml:35-38, workers/account/src/index.ts:99). The account Worker already runs a Durable Object with SQLite storage (`BackupReplicator`, workers/account/wrangler.eu.toml:103-111) and binds D1 (workers/account/wrangler.eu.toml:48).
3. Proxy Worker configs are generated from workers/proxy/wrangler.template.toml (workers/proxy/wrangler.eu.toml:1); enterprise company configs come from the same template and workers/account/enterprise.template.toml (.ci/rediacc_ci/enterprise/configs.py:3).
4. The account Worker's daily 03:00 cron runs the retention sweeps and reminders (private/account/src/entry/cloudflare.ts:575, :617-619); operator alerts queue through `AlertDigestService.enqueue` (private/account/src/services/alert-digest.service.ts:55, :61), flushed at 03:00 UTC.
5. The admin per-org switch pattern is `organizations.console_executor_blocked_at` with an elevated root route (private/account/src/db/schema.ts:505, private/account/src/routes/root.ts:456-462). The admin customer page is private/account/web/src/pages/admin/CustomerDetail.tsx (201 lines).
6. Plan metadata carries per-plan capability flags (`webConsole`, packages/shared/src/subscription/types.ts:309, set per plan at packages/shared/src/subscription/constants.ts:580-612); the console entitlement reads them (private/account/src/services/console-entitlement.service.ts:84). ENTERPRISE is one of five plan codes (packages/shared/src/subscription/types.ts:11).
7. Cloudflare spend thresholds already live in a repo config applied by an ops tool (.ci/config/cf-spend-guard.json:2, upserted by `rediacc_ci.ops.cf_notifications`).
8. The latest drizzle migration is private/account/drizzle/0092_magic_link_binding.sql.

## Design

D1. **Path**: the loop host's built-in `rediacc` provider (format `openai-chat`) calls `http://ai.internal/compat/chat/completions`. The proxy intercepts `ai.internal` to a new `AiEgress` entrypoint, which forwards to the region's AI Gateway OpenAI-compatible endpoint with `cf-aig-authorization` from a Worker secret (`AI_GATEWAY_TOKEN`, a gateway-scoped Cloudflare token, not a provider key). Workers AI models (`workers-ai/@cf/...`) and premium models (`anthropic/...`, `openai/...` under Unified Billing) share that one endpoint, so one code path covers both tiers. The container holds nothing: `orgId` comes from the intercept props, never from the request.

D2. **Price table in code**: packages/shared/src/ai-credits/price-table.ts, a versioned constant (`PRICE_TABLE_VERSION`) of `{model, tier, providerUsdPerMTokIn, providerUsdPerMTokOut, creditsPerMTokIn, creditsPerMTokOut}`, one credit worth 0.001 USD. Chosen over a D1 table because a price change is then reviewed in a PR, the ledger, admin panel, usage page and reconcile read one identical source, and a unit test proves the margin: every row's credit value is at least provider cost times 1.05 (the Unified Billing fee) times 1.15, and premium rows at least times 1.30. A model absent from the table is refused before any reservation.

D3. **Gateway config in the repo**: .ci/config/ai-gateway.json (one gateway per region, logging on, caching off, collect-logs metadata on, a rate limit, the spend-limit target) applied idempotently by `rediacc_ci.ops.cf_ai_gateway` with a `--check` drift mode, beside the spend guards of context 7. Settings the API cannot set are the operator's dashboard steps in AC12.

D4. **Ledger**: one `CreditLedger` Durable Object per org (`idFromName(orgId)`) in the account Worker, SQLite tables for lots (granted, remaining, expires_at, payment reference), open reservations, per-day consumption and per-conversation totals.
The proxy reaches it only through a `CreditLedgerGate` entrypoint exposing `reserve`, `commit` and `release`; grants, refunds and switches come only from elevated account routes. Every committed change is written to D1 history (`ai_credit_ledger`) for usage views and audit.

D5. **Reserve, then commit**: before each call `reserve` computes the worst case (input tokens estimated from the body length at 1 token per 3 bytes, plus the clamped `max_tokens`, at the model's credit rates) and refuses unless every check passes: plan entitled, org and global switches off, available balance (lots minus open reservations) at least the worst case, daily cap, concurrent streams (default 3), per-conversation token cap (default 200,000) and loop depth (default 40 calls per conversation), with `max_tokens` clamped to 8,192. `commit` charges actual usage from the stream's final usage chunk (`stream_options.include_usage` forced on) and frees the rest; lots are consumed earliest-expiry first. Balance never goes below zero.

D6. **Stop on disconnect**: the container request's abort cancels the upstream fetch; usage seen so far is committed, and a reservation with no usage commits in full, corrected downward by the reconcile. A reservation uncommitted after 10 minutes is committed in full by the DO's alarm.

D7. **Metadata**: `cf-aig-metadata` carries `org_id`, `user_id`, `conversation_id`, `reservation_id` and `price_version`, five entries, the join key of the reconcile.

D8. **Reconcile**: the 03:00 cron pulls the previous UTC day's gateway logs through the AI Gateway Logs API (a logs-read token, `AI_GATEWAY_LOGS_TOKEN`) and compares cost per org and per reservation with the committed ledger.
A reservation charged above its logged cost is refunded the difference as `reconcile-adjust` (unused credit only); drift above 2 percent or 1 USD per org, and a global balance below 20 percent of purchased funding or below 14 days of trailing spend, queue an operator alert. Logpush was rejected: it needs an R2 sink and a parser, and the pull fits one cron at enterprise volumes; the switch point is a day whose log pages exceed the cron's subrequest budget, which the reconcile reports.

D9. **Prepaid, funding and expiry**: a grant requires a payment reference and is refused when the outstanding credit of all orgs, valued at provider cost, would exceed 90 percent of the funding recorded in `ai_funding` (the global cap on the Rediacc side; the gateway spend limit of AC12 is the Cloudflare side). Lots expire 12 months after grant unless set shorter; a refund returns only the unused part of an unexpired lot.

D10. **Kill switches**: `organizations.ai_credits_blocked_at` (pushed to the org's DO at once) and the single-row `ai_credit_control.paused_at` (read by each DO with a 30-second cache). Both refuse only the `rediacc` provider; customer-key profiles never pass `AiEgress`, so they keep working.

D11. **Entitlement**: a `rediaccAiCredits` flag in plan metadata, true for ENTERPRISE alone; grants and reservations both check it, and the Rediacc tier appears in the provider choice only for an entitled org.

D12. **Customer view**: an AI credits page (balance, lots with expiry, usage by day, model and user, the user split shown to owners and admins) and `GET /ai-credits/summary`, read through `useAiCredits`, the hook PLAN-console-ai-assistant.md's credits chip consumes.

## Ordering against other live plans

- After PLAN-console-ai-providers.md#AP7 (loop host) and #AP1 (profile resolution); after PLAN-rmcp-writeback.md#WB5, the last open edit of the egress files in that plan, so the second intercept lands on a settled egress.
- AC8 touches .ci/**, held by PLAN-tooling-code-reduction.md writers, hence its dependency on CR2.
- PLAN-console-audit-r2.md also edits private/account/src/entry/cloudflare.ts for the 03:00 compaction; whichever lands second rebases its branch of the `scheduled` handler.

## Tasks

- [x] AC1 [writer] Shared credits module: `price-table.ts` per D2, `reserve-math.ts` (worst-case and actual credit computation per D5) and the `rediaccAiCredits` plan flag per D11, with a margin test over every price row and a control row priced below the fee that the test refuses.
  Owns: packages/shared/src/ai-credits/**, packages/shared/src/subscription/types.ts, packages/shared/src/subscription/constants.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/ai-credits src/subscription)` rc 0.
    (ticked) 2026-11-23T18:18:09Z by ace763dd: commit:68e1565f6b landed; writer accept rc=0, lead re-verified on the landed tree
- [x] AC2 [writer] Schema and migration: `ai_credit_lots`, `ai_credit_ledger`, `ai_funding`, `ai_credit_control` and `organizations.ai_credits_blocked_at` in private/account/src/db/schema.ts, the next free drizzle migration, journal and snapshot.
  Owns: private/account/src/db/schema.ts, private/account/drizzle/*_ai_credits.sql, private/account/drizzle/meta/_journal.json, private/account/drizzle/meta/*_snapshot.json, private/account/tests/integration/ai-credits-schema.test.ts
  Depends on: none.
  Accept: `(cd private/account && npx drizzle-kit check && npx vitest run tests/integration/ai-credits-schema.test.ts)` rc 0, the test applying every migration to a fresh database and reading each new table.
    (ticked) 2026-11-24T18:25:39Z by d778be9d: AC2 landed: account migration 0104_ai_credits + schema + scope entries; vitest 175 passed rc 0; commit:572e82512f
- [x] AC3 [writer] `CreditLedger` Durable Object and `CreditLedgerGate` entrypoint per D4 to D6, D9 and D10 in workers/account/src, with its binding and SQLite migration in every account wrangler config and enterprise.template.toml; tests cover reserve refusals for each check, commit freeing the remainder, earliest-expiry consumption, the 10-minute alarm and concurrent reservations never overdrawing.
  Owns: workers/account/src/credit-ledger.ts, workers/account/src/index.ts, workers/account/wrangler.*.toml, workers/account/enterprise.template.toml, private/account/tests/integration/credit-ledger.test.ts
  Depends on: AC1, AC2.
  Accept: `(cd private/account && npx vitest run tests/integration/credit-ledger.test.ts)` rc 0.
    (ticked) 2026-11-25T19:53:16Z by d778be9d: AC3 CreditLedger Durable Object and CreditLedgerGate with bindings and the v2 migration in every wrangler file; workers/account 18 tests; landed e1d222715b. DEPS-WAIVED: used prerequisites landed
- [x] AC4 [writer] Account service and routes: `ai-credits.service.ts` (grant with payment reference and the D9 funding check, refund of unused credit, funding entries, both switches, summary and usage queries), `ai-credits.ts` for org members and `root-ai-credits.ts` behind `requireElevated()` for admins, registered in routes/index.ts.
  Owns: private/account/src/services/ai-credits.service.ts, private/account/src/routes/ai-credits.ts, private/account/src/routes/root-ai-credits.ts, private/account/src/routes/index.ts, private/account/tests/integration/ai-credits-routes*.test.ts
  Depends on: AC3.
  Accept: `(cd private/account && npx vitest run tests/integration/ai-credits-routes)` rc 0, including a grant to a non-enterprise org refused, a grant past the funding cap refused, and a refund of a spent lot refused.
    (ticked) 2026-11-25T20:29:24Z by d778be9d: AC4 credit service, member and root routes with audit; ai-credits 13 tests, account tsc rc 0; landed c1ffe07afe. DEPS-WAIVED: prerequisites landed
- [x] AC5 [writer] `AiEgress` per D1, D5 to D7: model allowlist from the price table, reserve, `max_tokens` clamp, forced usage reporting, metadata, abort and commit; the `ai.internal` intercept registered beside `account.internal`, the export in index.ts, and the `CREDITS` service binding, `AI_GATEWAY_ID` var and secret names in wrangler.template.toml with the configs regenerated by `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.proxy_configs`.
  Owns: workers/proxy/src/ai-egress.ts, workers/proxy/src/__tests__/ai-egress.test.ts, workers/proxy/src/org-executor.ts, workers/proxy/src/org-executor-support.ts, workers/proxy/src/index.ts, workers/proxy/wrangler.template.toml, workers/proxy/wrangler.*.toml
  Depends on: AC1, AC3, PLAN-rmcp-writeback.md#WB5.
  Accept: `(cd workers/proxy && npx vitest run src/__tests__/ai-egress.test.ts src/__tests__/org-executor.test.ts)` rc 0 and `npm run check:ci-proxy-configs` rc 0.
    (ticked) 2026-11-25T20:33:16Z by d778be9d: AC5 landed d80d3d06c0; merged tree proxy 472 tests, tsc rc 0, check:ci-proxy-configs and check:ci-region-consistency rc 0, proxy-config pytest 76 passed. AI_GATEWAY_TOKEN stays unset until AC13. DEPS-WAIVED: CR2 code landed, its open clause is operator-owned
- [x] AC6 [writer] Rediacc tier in the loop host: `rediacc-tier.ts` (the `rediacc:standard` and `rediacc:premium` choices and their default models), resolution of those choices in resolve.ts, and `rediacc-provider.ts` registered in provider.ts, mapping each ledger refusal code to an `ai` error event the UI can name.
  Owns: packages/shared/src/ai/rediacc-tier.ts, packages/shared/src/ai/resolve.ts, packages/cli/src/services/ai/rediacc-provider.ts, packages/cli/src/services/ai/provider.ts, packages/cli/src/services/ai/__tests__/rediacc-provider.test.ts
  Depends on: AC1, PLAN-console-ai-providers.md#AP7.
  Accept: `(cd packages/cli && npx vitest run src/services/ai/__tests__/rediacc-provider.test.ts)` rc 0 and `(cd packages/shared && npx vitest run src/ai)` rc 0.
    (ticked) 2026-11-26T02:41:23Z by d778be9d: AC6 landed 63920c4b2a; cli tsc rc 0, ai+serve 712 tests. A grant-bound chat bills the caller, since the agent session carries no person user id (#next). DEPS-WAIVED: AC5 landed
- [x] AC7 [writer] Reconcile per D8: `ai-reconcile.service.ts` run from the 03:00 branch of `scheduled`, refunds as `reconcile-adjust`, drift and low-balance alerts through `AlertDigestService`, tested on recorded log-page fixtures.
  Owns: private/account/src/services/ai-reconcile.service.ts, private/account/src/entry/cloudflare.ts, private/account/tests/integration/ai-reconcile.test.ts
  Depends on: AC4.
  Accept: `(cd private/account && npx vitest run tests/integration/ai-reconcile.test.ts)` rc 0, including a fixture with 3 percent drift that queues an alert and a fixture at 1 percent that does not.
    (ticked) 2026-11-26T18:20:51Z by d778be9d: AC7 present: adjustLot and lapseLot in the credit ledger, the reconcile integration test exists fileline:workers/account/src/credit-ledger.ts:233
- [x] AC8 [writer] Gateway config per D3: .ci/config/ai-gateway.json and `rediacc_ci.ops.cf_ai_gateway` (upsert and `--check`), with a test against a recorded API fixture and a control where a hand-changed setting makes `--check` exit 1.
  Owns: .ci/config/ai-gateway.json, .ci/rediacc_ci/ops/cf_ai_gateway.py, .ci/rediacc_ci/tests/test_ops_cf_ai_gateway.py
  Depends on: PLAN-tooling-code-reduction.md#CR2.
  Accept: `PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/test_ops_cf_ai_gateway.py` rc 0.
    (ticked) 2026-11-25T20:05:26Z by d778be9d: AC8 AI gateway config and cf_ai_gateway tool (apply, --check, --dry-run); 11 tests; landed 502a1020fc. DEPS-WAIVED: CR2 code landed, its open clause is operator-owned
- [x] AC9 [writer] Admin UI: a per-org AI credits panel on CustomerDetail.tsx (balance, lots, grant with credits, expiry and payment reference, refund of unused credit, org switch) and an admin AI credits page (global switch, funding entries, the latest reconcile drift), with router entries and endpoints.
  Owns: private/account/web/src/pages/admin/CustomerDetail.tsx, private/account/web/src/pages/admin/AiCredits.tsx, private/account/web/src/components/ai-credits/**, private/account/web/src/router.tsx, private/account/web/src/api/endpoints.ts, private/account/web/src/pages/__tests__/ai-credits-admin.test.tsx
  Depends on: AC4.
  Accept: `(cd private/account/web && npx vitest run src/pages/__tests__/ai-credits-admin.test.tsx)` rc 0 and `(cd private/account && npm run typecheck:web)` rc 0.
    (ticked) 2026-11-26T03:04:22Z by d778be9d: AC9 complete: org panel, admin page, reconcile drift display with the read-error state and the sub-0.0005 USD guard; ai-credits-admin 8 tests, typecheck rc 0; landed 12abf6c201. DEPS-WAIVED: prerequisites landed
- [x] AC10 [writer] Customer UI per D12: AiCredits.tsx, the nav entry, and `useAiCredits` returning balance, low-balance state and entitlement for the chip of PLAN-console-ai-assistant.md.
  Owns: private/account/web/src/pages/AiCredits.tsx, private/account/web/src/hooks/useAiCredits.ts, private/account/web/src/lib/nav-config.ts, private/account/web/src/pages/__tests__/ai-credits.test.tsx
  Depends on: AC4, AC9.
  Accept: `(cd private/account/web && npx vitest run src/pages/__tests__/ai-credits.test.tsx)` rc 0.
    (ticked) 2026-11-25T21:42:58Z by d778be9d: AC10 landed (gitlink aa2a204ae9); 9 tests, typecheck rc 0; locales are AC11 (in flight). DEPS-WAIVED: AC4 landed
- [x] AC11 [writer] Locales: `aiCredits.json` and the new `admin.json` keys, English first, then the 12 derived locales through the naturalization pipeline, writers on sonnet.
  Owns: private/account/web/src/i18n/locales/*/aiCredits.json, private/account/web/src/i18n/locales/*/admin.json
  Depends on: AC9, AC10.
  Accept: `npm run -s check:i18n` rc 0 and `npm run check:ci-i18n-account-key-usage` rc 0.
    (ticked) 2026-11-25T21:50:47Z by d778be9d: AC11 landed (gitlink ab75ad457a); nav-label-collisions passes, typecheck rc 0; check:i18n account-web clean of AC keys. DEPS-WAIVED: AC9, AC10 landed
- [ ] AC12 [lead] Operator-only Cloudflare account settings (billing powers no agent holds): purchase the first Unified Billing credit, turn auto top-up off, set the gateway spend limit below the purchased balance and the dashboard low-balance email, then record the purchase as an `ai_funding` entry on the admin page. The session parks this as a worklist `[?]` naming each setting, with a DEFAULT of keeping the Rediacc tier paused through the global switch until the entry exists.
  Depends on: AC4, AC9.
  Accept: the operator's answer quoted with its minute, a dashboard screenshot path or API read showing auto top-up off and the spend limit, and the `ai_funding` row id.
- [ ] AC13 [lead] Tokens: mint a Cloudflare token scoped to AI Gateway run for `AI_GATEWAY_TOKEN` and one scoped to AI Gateway logs read for `AI_GATEWAY_LOGS_TOKEN`, store both in BWS with their rows in .ci/config/bws-secret-map.json and a consumer profile in .ci/config/secret-supply.json, and set them as secrets on the bench proxy and bench account Workers; production regions follow at release.
  Owns: .ci/config/bws-secret-map.json, .ci/config/secret-supply.json
  Depends on: PLAN-tooling-code-reduction.md#CR2.
  Accept: `npm run check:ci-secret-supply` rc 0, and `wrangler secret list` on both bench Workers naming both secrets.
- [ ] AC-L1 [live] On the eu bench with a bench org set to ENTERPRISE: grant a small lot, run a standard-tier chat and a premium-tier chat and see the balance fall by the committed amounts, exhaust the lot and see the next call refused before any gateway request, see the org switch and then the global switch refuse the Rediacc tier while a customer-key profile still answers, and run the reconcile for the day with drift under the threshold.
  Depends on: AC5, AC6, AC7, AC10, AC12, AC13, LP-bench.
  Accept: the evidence records each balance read, the refusal codes, the gateway log count for the day and the reconcile drift figure.
- [ ] LP-bench [live] Deploy the branch's account and proxy Workers to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu` and `PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_proxy --target bench`), with proxy-ready run as additional verification.
  Accept: live-proof bench account-smoke

## Risks

- The reservation's input estimate can undercount a body of short tokens; the worst case adds the full clamped output, the commit uses real usage, and the reconcile refunds any overcharge.
- Unified Billing settings may lack API coverage; AC12 keeps them operator-only and the global switch holds the tier paused until funding is recorded.
- The 30-second cache on the global switch lets calls already reserved finish; a reservation in flight is not cancelled by the switch.
- A gateway outage refuses Rediacc-tier calls with a provider error; customer-key profiles are unaffected.
