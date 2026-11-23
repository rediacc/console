# PLAN: Console AI feedback offers -- an rdc feedback report offered only for Rediacc-origin failures, drafted from the server run record, previewed exactly and sent by the account worker on the user's click
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-contract-semantics.md, PLAN-console-ai-assistant.md -- the offer reads the error origin plan 1 adds to every error code (C8), and the card lives in plan 9's timeline and executor loop
Priority: P2 -- the feedback intake exists (private/account/src/routes/feedback.ts:77) but a browser session cannot post to it, so console failures reach triage only when a user retypes them in a terminal
Concurrency: parallel -- Wave 1: AF1 (shared schema). Wave 2: AF2 (account data), AF4 (executor offer), AF5 (preview card). Wave 3: AF3 (routes, after AF2), then AF6 (settings UI). Wave 4: AF7 (translations), AF8 (e2e). AF6 edits Settings.tsx and Team.tsx, which no other plan of the program owns; AF4 adds one `AiEventSchema` member to packages/shared/src/cli-contract/wire.ts after PLAN-console-ai-assistant.md#AI3; AF3 adds one type to packages/shared/src/audit/console-events.ts after PLAN-console-audit-r2.md#AU1
Owns: agent/plans/PLAN-console-ai-feedback.md, packages/shared/src/feedback/schema.ts, packages/shared/src/feedback/__tests__/schema.test.ts, packages/shared/src/cli-contract/wire.ts (the feedback_offer AiEventSchema member only), packages/shared/src/audit/console-events.ts (the console.feedback.declined type only), private/account/drizzle/*_ai_feedback.sql, private/account/src/db/schema.ts (feedback_settings, feedback_reports and organizations columns only), private/account/src/services/feedback.service.ts, private/account/src/routes/feedback.ts, private/account/src/routes/organization.ts (the AI feedback override route only), private/account/tests/integration/feedback-console.test.ts, packages/cli/src/services/ai/feedback-offer.ts, packages/cli/src/services/ai/__tests__/feedback-offer.test.ts, private/account/web/src/components/ai/feedback/**, private/account/web/src/pages/Settings.tsx, private/account/web/src/pages/Team.tsx, private/account/web/src/pages/__tests__/FeedbackSettings.test.tsx, private/account/web/src/i18n/config.ts (the aiFeedback namespace only), private/account/web/src/i18n/locales/*/aiFeedback.json, private/account/web/src/i18n/locales/*/settings.json (new feedback keys only), private/account/web/src/i18n/locales/*/team.json (new override keys only), private/account/e2e/tests/27-console/27-3*-ai-feedback.test.ts
Live-Proof: bench -- the account worker's console feedback routes, the executor's offer decision and the account web preview card on the eu bench

## Ask

The operator ruled that the AI offers an `rdc feedback` report only when a failure has Rediacc origin (C39, reading C8), writes the description itself, and lets the user send, edit or decline; a per-user setting turns the offer off and the org owner can override it for the whole org. The executor's forced `--yes` is never used for a send: the account worker posts to the feedback endpoint only on the user's click (C39). Sends and declines are audited (C15). The intake and the report shape are those of agent/plans/PLAN-rdc-feedback.md.

## Context

1. `POST /feedback` accepts an API token or a FREE licence blob and nothing else (private/account/src/routes/feedback.ts:77-118); a browser session is refused with `FEEDBACK_AUTH_REQUIRED`, so the console needs its own session-authenticated route.
2. `feedbackReportSchema` carries `commandPath`, `argv`, `exitCode`, `errorCode`, `errorMessage`, `stderrTail`, `message`, `cliVersion`, `os`, `arch`, `configFingerprint`, `agent` and `ci`, with no source field (packages/shared/src/feedback/schema.ts:30-45).
3. Settings hold one flag, `shareWithOrgAdmins` (packages/shared/src/feedback/schema.ts:77), stored per owner in `feedback_settings` (private/account/src/db/schema.ts:910-921); the PUT route names only that flag in its error (private/account/src/routes/feedback.ts:168); the Settings page shows it in one card (private/account/web/src/pages/Settings.tsx:468-490).
4. The executor forces `--yes` (packages/cli/src/services/serve/command-dispatch.ts:284-305); without `--yes` an agent gets a preview and the send command only (packages/cli/src/commands/feedback.ts:126-130). `rdc feedback report --last` reads a local ring buffer (packages/cli/src/services/feedback/ring.ts), which inside a shared org container would hold other users' runs.
5. Redaction helpers exist: `scrubText` (packages/shared/src/feedback/scrub.ts:51) and `shortFingerprint` for a config (packages/cli/src/schema/fingerprint.ts:35).
6. Per-org switches are nullable timestamp columns on `organizations` (private/account/src/db/schema.ts:505), and owner-only routes use `requireOrgRole` (private/account/src/middleware/org-role.ts:23).
7. Plan 1 puts an origin (`user`, `environment`, `rediacc`) on every error code and publishes it in the contract's `errorCodes` table (agent/plans/PLAN-console-contract-semantics.md D4).
8. Plan 4's run row holds `path_key`, `machine`, `repo`, `state`, `exit_code` and `error_code`, never params, and seals the output tail under the session CEK so the account server cannot read it (agent/plans/PLAN-console-run-index.md D2, D3).
9. Plan 3 defines `console.feedback.sent` and no decline type (agent/plans/PLAN-console-audit-r2.md D2).

## Design

D1. **The offer rule is code; the AI judges only the ambiguous case.** The executor looks up the failed run's error code in the contract's `errorCodes`. `rediacc` offers; `user` and `environment` never offer; a failure with no error code or a code absent from the table (an executor crash, a non-zero exit without an envelope) is ambiguous, and one classify-only AI call over the redacted record returns `{offer: boolean, reason}`, any parse failure meaning no offer. Each run is judged once.

D2. **The draft comes from the server run record, never the conversation or the ring buffer.** The executor reads plan 4's row for the run and opens its sealed tail with the session key. The AI writes `message` (at most `FEEDBACK_LIMITS.message`) and picks the relevant tail lines as `stderrTail` (at most 4 KiB); `scrubText` runs over both before they leave the executor. The executor adds its own `cliVersion`, `os`, `arch` and the config's `shortFingerprint`. The offer travels as a typed `feedback_offer` event in plan 9's timeline.

D3. **The preview is the exact body.** `POST /feedback/console/preview {runId, message, stderrTail, env}` makes the worker take `commandPath`, `exitCode` and `errorCode` from the run row (scoped to the caller's org and user), set `argv` to `rdc <path_key>` because params are never stored, run `scrubText` over the text fields again, and return the body with a SHA-256 digest of its canonical JSON. The card shows every field verbatim with Send, Edit and Don't send; Edit changes the text and re-previews. Send posts the same inputs plus the digest; the worker rebuilds the body, refuses a digest mismatch, and calls `feedbackService.submit` with the session's user and org as owner, `agent: true`, `ci: false` and `source: 'console'`.
The daily limits and duplicate folding of agent/plans/PLAN-rdc-feedback.md R2 apply unchanged.

D4. **Never through the executor.** The send is a worker route under session auth on a click; the executor holds no feedback credential, and `rdc feedback report` stays off its dispatch.

D5. **Settings.** Per user: `offerBugReports` in `feedback_settings`, default on, a second toggle in the existing Settings card. Per org: `organizations.ai_feedback_offers_off_at`, null meaning each user decides, set by the owner through `PUT /organization/ai-feedback` on the Team page. The org switch is a worker column, not a policy field, because the worker enforces it at preview and send and the policy record is CEK-encrypted and unreadable by the worker (remote-mcp D27). The chat request carries both flags to the executor, so no offer is drafted when either is off; the worker re-checks at send.

D6. **Audit (C15).** Send emits plan 3's `console.feedback.sent`; Don't send emits a new `console.feedback.declined`. Each carries who, run id and command path, the returned fingerprint on send, and the message length and digest, never the text.

D7. **Source.** `feedbackReportSchema` gains `source: 'cli' | 'console'` with default `cli`, so CLI senders are unchanged, and `feedback_reports` stores it for triage.

## Ordering against other live plans

- AF4 waits for PLAN-console-ai-assistant.md#AI3 (the gate and wire members) and PLAN-console-contract-semantics.md#CS3 (origins).
- AF3 waits for PLAN-console-run-index.md#RI1 (the run row reader) and PLAN-console-audit-r2.md#AU2 (the audit writer) as box dependencies, so neither plan joins this PR's plan set.
- AF5 mounts in plan 9's timeline after PLAN-console-ai-assistant.md#AI7.

## Tasks

- [ ] AF1 [writer] Shared schemas: `source` on `feedbackReportSchema` with default `cli`, `offerBugReports` on `feedbackSettingsSchema`, and the console preview, send and decline request and preview response schemas, with a test that an old CLI body still parses as `cli`.
  Owns: packages/shared/src/feedback/schema.ts, packages/shared/src/feedback/__tests__/schema.test.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/feedback/__tests__/schema.test.ts)` rc 0.
- [ ] AF2 [writer] Account data: a migration adding `feedback_settings.offer_bug_reports` (default 1), `feedback_reports.source` (default `cli`) and `organizations.ai_feedback_offers_off_at`, the drizzle columns, and `feedbackService` reading and writing both settings and storing the source.
  Owns: private/account/drizzle/*_ai_feedback.sql, private/account/src/db/schema.ts, private/account/src/services/feedback.service.ts
  Depends on: AF1.
  Accept: `(cd private/account && npx vitest run tests/integration/feedback-intake.test.ts tests/integration/feedback-visibility.test.ts)` rc 0.
- [ ] AF3 [writer] Account routes: `POST /feedback/console/preview`, `/send` and `/decline` under session auth with the D3 rebuild and digest rule and both settings re-checked, the settings PUT accepting `offerBugReports`, the owner-only `PUT /organization/ai-feedback`, and the D6 audit events with the new `console.feedback.declined` type.
  Owns: private/account/src/routes/feedback.ts, private/account/src/routes/organization.ts, packages/shared/src/audit/console-events.ts, private/account/tests/integration/feedback-console.test.ts
  Depends on: AF2, PLAN-console-run-index.md#RI1, PLAN-console-audit-r2.md#AU2.
  Accept: `(cd private/account && npx vitest run tests/integration/feedback-console.test.ts)` rc 0, covering a digest mismatch refused, a send with the org override on refused, a member calling the owner route refused, a run row of another user refused and `source: 'console'` stored; `npm run check:ci-account-scope-audit` and `npm run check:ci-audit-coverage` rc 0.
- [ ] AF4 [writer] Executor offer: the D1 origin rule with the classify-only call for ambiguous failures, the D2 draft from the run row and the opened sealed tail with `scrubText`, both settings honoured, and the `feedback_offer` `AiEventSchema` member.
  Owns: packages/cli/src/services/ai/feedback-offer.ts, packages/cli/src/services/ai/__tests__/feedback-offer.test.ts, packages/shared/src/cli-contract/wire.ts
  Depends on: AF1, PLAN-console-ai-assistant.md#AI3, PLAN-console-contract-semantics.md#CS3.
  Accept: `(cd packages/cli && npx vitest run src/services/ai/__tests__/feedback-offer.test.ts)` rc 0, with fixtures where a `user` origin never offers, a `rediacc` origin offers without an AI call, an ambiguous failure calls the classifier once, and a control where a bearer token in the tail survives the draft turning the suite red.
- [ ] AF5 [writer] The preview card in plan 9's timeline: every body field shown verbatim, Send, Edit (re-preview) and Don't send, with English strings in `aiFeedback.json` and the namespace registered.
  Owns: private/account/web/src/components/ai/feedback/**, private/account/web/src/i18n/config.ts, private/account/web/src/i18n/locales/en/aiFeedback.json
  Depends on: AF1, PLAN-console-ai-assistant.md#AI7.
  Accept: `(cd private/account/web && npx vitest run src/components/ai/feedback)` rc 0, including a test that the rendered body equals the preview response field for field.
- [ ] AF6 [writer] Settings UI: an "Offer bug reports" toggle in the Settings feedback card and the owner's org-wide override on the Team page, hidden from non-owners, with English strings in `settings.json` and `team.json`.
  Owns: private/account/web/src/pages/Settings.tsx, private/account/web/src/pages/Team.tsx, private/account/web/src/pages/__tests__/FeedbackSettings.test.tsx, private/account/web/src/i18n/locales/en/settings.json, private/account/web/src/i18n/locales/en/team.json
  Depends on: AF3.
  Accept: `(cd private/account/web && npx vitest run src/pages/__tests__/FeedbackSettings.test.tsx)` rc 0.
- [ ] AF7 [writer] Translate the new `aiFeedback`, `settings` and `team` keys into the 12 other locales through the naturalization pipeline; translation writers run on sonnet.
  Owns: private/account/web/src/i18n/locales/*/aiFeedback.json, private/account/web/src/i18n/locales/*/settings.json, private/account/web/src/i18n/locales/*/team.json
  Depends on: AF5, AF6.
  Accept: `npm run check:i18n` and `npm run check:ci-i18n-account-key-usage` rc 0.
- [ ] AF8 [writer] Playwright spec: a Rediacc-origin failure shows the card and Send files a report, a user-origin failure shows none, Don't send records a decline, the owner override hides the card, and the card is operable by keyboard alone.
  (corrected 2026-11-23, ruling C42) This spec runs against the scripted provider of PLAN-console-ai-providers.md#AP13 under TEST_MODE; no real provider key reaches CI.
  Owns: private/account/e2e/tests/27-console/27-3*-ai-feedback.test.ts
  Depends on: AF3, AF4, AF5.
  Accept: `(cd private/account/e2e && npx playwright test tests/27-console/27-30-ai-feedback.test.ts --project=chromium)` rc 0.
- [ ] LP-bench [live] Deploy the branch's account and proxy Workers to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`), provoke one Rediacc-origin failure in an AI chat on the BWS Anthropic key (C41), send the drafted report, and find it in the bench admin feedback list with `source: console` and a `console.feedback.sent` audit object; proxy-ready runs as additional verification.
  Accept: live-proof bench account-smoke

## Risks

- **A forged body from the browser.** The fields triage keys on (command path, exit code, error code, owner) come from the caller's own run row; the browser supplies only text it was shown, scrubbed again by the worker.
- **Secrets in the drafted text.** The draft reads the redacted record, passes `scrubText` in the executor and the worker, and the user sees the exact body before anything leaves.
- **Offer fatigue.** The rule offers only for `rediacc` origin, once per run, behind two switches.
