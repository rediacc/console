# PLAN: Console confirm and step-up -- severity-tiered dialogs, server-enforced step-up at /console/exec, passkey and password elevation, the org minimum, production popups and audited reveal
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #b785e9ff (agent/programs/console-rework/02-decisions.md)
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: PLAN-console-contract-semantics.md -- the dialogs and the server check read that plan's `severity` and `preview` contract fields; CF7 names PLAN-rmcp-policy-record.md#A1 and #W1 as box edges, so the policy-record plan does not join this PR's plan set
Priority: P1 -- the executor forces `--yes` (packages/cli/src/services/serve/command-dispatch.ts:303), so the browser dialog is the only confirmation, it runs only in the client, and `repo prune --apply` deletes with none at all
Concurrency: parallel -- wave 1: CF1, CF4; wave 2: CF2, CF6; wave 3: CF3, CF5; wave 4: CF8, then CF7, CF9, CF10. private/account/src/routes/console.ts is edited by CF3 then CF8; en/console.json by CF4, CF8, CF7 in that order; useReauth.tsx by CF6 only
Owns: agent/plans/PLAN-console-confirm-stepup.md, packages/shared/src/auth/**, packages/shared/src/index.ts, private/account/src/db/schema.ts, private/account/src/db/config-schema.ts, private/account/drizzle/**, private/account/src/services/auth.service.ts, private/account/src/services/console-stepup.ts, private/account/src/services/config-policy.service.ts, private/account/src/routes/auth.ts, private/account/src/routes/configs.ts, private/account/src/routes/config-policy.ts, private/account/src/routes/console.ts, private/account/src/routes/test.ts, private/account/src/dto/auth.dto.ts, private/account/src/dto/config.dto.ts, private/account/src/dto/config-policy.dto.ts, private/account/src/dto/console.dto.ts, private/account/tests/integration/reauth-methods.test.ts, private/account/tests/integration/console-stepup.test.ts, private/account/tests/integration/console-reveal.test.ts, private/account/tests/integration/config-policy-stepup.test.ts, private/account/web/src/lib/confirm-policy.ts, private/account/web/src/lib/__tests__/confirm-policy.test.ts, private/account/web/src/components/console/ConfirmRun.tsx, private/account/web/src/components/console/DestructiveConfirm.tsx, private/account/web/src/components/console/RevealRiskDialog.tsx, private/account/web/src/components/console/CommandForm.tsx, private/account/web/src/components/console/__tests__/**, private/account/web/src/hooks/useCommand.ts, private/account/web/src/hooks/useReauth.tsx, private/account/web/src/components/ReauthStep.tsx, private/account/web/src/components/__tests__/reauth-step.test.tsx, private/account/web/src/api/endpoints.ts, private/account/web/src/api/console.ts, private/account/web/src/pages/console/ConfigEditor.tsx, private/account/web/src/pages/console/Permissions.tsx, private/account/web/src/pages/__tests__/permissions-stepup.test.tsx, private/account/web/src/i18n/locales/*/console.json, private/account/web/src/i18n/locales/*/auth.json, private/account/e2e/tests/27-console/27-01-console.test.ts
Live-Proof: bench -- the account Worker routes /console/exec, /auth/reauth/* and /console/reveal plus the web dialogs reach the eu bench through deploy_bench

## Ask

The console confirms by severity (C11): `caution` gets an amber one-click dialog, `destructive` a red dialog with the target name typed and step-up re-verification, a preview skips both. Step-up runs passkey, then TOTP, then email link, then account password, the strongest held offered first, with an org minimum for destructive runs, enforced on the server at `/console/exec` (C12). A grand repo target always gets an explicit popup (C13). Reveal of secrets is off by default and open only to owners and admins for a short window after step-up and a red risk popup, audited (C14).

## Context

1. `/console/exec` resolves the contract entry at private/account/src/routes/console.ts:453 and answers the mock stream at :470 before any executor leg; nothing on the route checks elevation.
2. `requireElevated()` (private/account/src/middleware/elevated.ts:14) asks `authService.isElevated` (private/account/src/services/auth.service.ts:860); `elevate(userId)` (:841) records no method, and `elevated_sessions` holds only user, expiry and creation (private/account/src/db/schema.ts:268). The window is 10 minutes (private/account/src/constants.ts:29).
3. Elevation today: TOTP at private/account/src/routes/auth.ts:657, the emailed link at /reauth/verify, and every magic-link login at private/account/src/routes/auth.ts:459. `/passkey/auth-verify` (private/account/src/routes/configs.ts:1932) verifies an assertion and does not elevate. No password elevation route exists.
4. Session ace763dd landed the magic-link step-up in commit:b7323f250a: page private/account/web/src/pages/MagicLinkStepUp.tsx with passkey, TOTP, password and confirm challenges, and `chooseStepUpMethod` (private/account/src/routes/auth.ts:475) ranking TOTP above passkey for that sign-in flow. Its password check with lockout (private/account/src/routes/auth.ts:599) is the pattern for a password elevation.
5. The only typed-name dialog is private/account/web/src/components/console/DestructiveConfirm.tsx, opened when `entry.destructive` is set (private/account/web/src/components/console/CommandForm.tsx:119).
6. `useReauth().execute` retries only on an `ApiError` 403 with `reauthRequired` (private/account/web/src/hooks/useReauth.tsx:41); console runs throw `ConsoleStreamError` (private/account/web/src/api/console.ts:58), which it does not recognise.
7. The resource list marks the grand tag (private/account/web/src/lib/resource-options.ts:41) from the config's `grand` field (packages/shared/src/config-schema/schemas.ts:170). Contract `grandGuard` (packages/shared/src/cli-contract/types.ts:300) is agent-only.
8. ConfigEditor lets any member unmask a secret leaf with a local toggle (private/account/web/src/pages/console/ConfigEditor.tsx:109). The web knows owner and admin through `useAuth().isOrgAdmin` (private/account/web/src/pages/DelegationCerts.tsx:60); the server through `requireOrgRole` (private/account/src/middleware/org-role.ts:23).
9. The policy is moving to an encrypted record written by `PUT /configs/:id/policy` under 2FA and elevation (agent/plans/PLAN-rmcp-policy-record.md Design 3, reusing remote-mcp D28 at agent/programs/remote-mcp/02-decisions.md:43). The Worker cannot read inside that ciphertext.
10. The e2e destructive test (private/account/e2e/tests/27-console/27-01-console.test.ts:194) drives the mock stream through the typed-name gate; `/test/elevate` (private/account/src/routes/test.ts:35) seeds an elevation.
11. Plan 1 adds `severity` (`none`, `caution`, `destructive`) and `preview: {flag, polarity}` to `ContractCommand`, polarity `opt-in` (`--dry-run`) or `default` (previews unless `--apply`) (agent/plans/PLAN-console-contract-semantics.md D1).

## Design

D1. **One step-up vocabulary.** `packages/shared/src/auth/step-up.ts` defines `StepUpMethod` (`passkey`, `totp`, `email`, `password`) with the C12 rank, `strongestHeld()` and `meetsMinimum()`. The server and the web import it; nothing else ranks methods. The magic-link sign-in ranking (Context 4) is a different flow and stays session ace763dd's; CF2 tells that session the rank exists.

D2. **Elevation records its method.** `elevated_sessions.method` (nullable; a null row reads as `email`, the weakest method written before this plan) is set by every `elevate(userId, method)` caller. `GET /auth/reauth/status` adds `method` and `methods` (held methods, strongest first). New `POST /auth/reauth/password` uses the lockout pattern of Context 4.
`/passkey/auth-verify` takes `elevate: true` and elevates with `passkey` only when the assertion verifies; without the flag it behaves as today, so config unlock does not elevate silently.

D3. **Every elevation is an audit event**: `console.stepup` with method and org id through `eventLogService.log`. PLAN-console-audit-r2.md routes `console.*` to R2; until it lands the rows stay in

D1.

D4. **The server decides from the contract.** `services/console-stepup.ts` answers `stepUpFor(entry, request, minimum)`: required when `severity` is `destructive` and the request is not a preview (polarity `opt-in` with the flag set, or `default` with the flag absent).
`/console/exec` refuses before the mock and executor legs with 403 `{reauthRequired: true, code: 'CONSOLE_STEPUP_REQUIRED', minimum}`. Caution and preview runs pass.

D5. **The org minimum rides beside the ciphertext.** The minimum is not secret, and an encrypted field cannot be enforced by the Worker (Context 9), so `config_policies` gains a plaintext `stepup_minimum` column on the org row, written in the same `PUT /configs/:id/policy` body under its D28 checks and shown on the Permissions page with the org policy only. Team policies cannot lower it. Chosen over a field inside the encrypted document, which only the executor could read and which `rdc --proxy` reaches without the Worker (packages/cli/src/services/executor/proxy-client.ts:284).

D6. **One dialog, three tones.** `ConfirmRun.tsx` replaces DestructiveConfirm: `caution` amber with one click and focus on Cancel; `destructive` red with the typed target, the parsed ref breakdown kept, focus in the input. `lib/confirm-policy.ts` maps (entry, params, target, isGrand) to `{tone, production, skip}`; a preview returns `skip`. `role="alertdialog"`, `aria-describedby` on the risk text, Enter submits only when enabled, Esc cancels, RTL-safe layout.

D7. **Production popup (C13).** A grand target on any command whose severity is not `none` sets `production`: the dialog carries a production banner naming the grand tag and cannot be bypassed by a remembered choice. A preview still skips (C11: a preview is not an action).

D8. **Strongest method first.** ReauthStep reads `methods`, offers the strongest held first and the others behind "use another method"; a `minimum` from the 403 hides weaker ones. The passkey and password challenges reuse ace763dd's MagicLinkStepUp components rather than copying them.

D9. **Reveal (C14).** `POST /console/reveal` (session, owner or admin, elevated) answers `{revealUntil}` two minutes ahead and logs `console.reveal` (config id, leaf count, never values). ConfigEditor masks secret leaves for everyone; owners and admins get one reveal control that opens RevealRiskDialog (red, the risks listed), then `useReauth().execute(reveal)`, then unmasks with a countdown and re-masks at expiry. Members see no control.
The browser already holds plaintext, so the gate is an accountability gate, stated in the dialog text.

D10. **Strings.** Code boxes add English keys only; CF9 translates the delta into the 12 other locales through the naturalization pipeline, writers on sonnet.

## Ordering against other live plans

- PLAN-console-contract-semantics.md lands first: CS5 exports the fields, CS11 moves the web console onto the lazy contract, so CF4 and CF5 rebase onto CS11's imports.
- PLAN-rmcp-policy-record.md: CF7 waits for A1 (table, route) and W1 (Permissions page); it also owns ConfigEditor.tsx, so CF8 rebases onto W1's hunk if W1 lands first. Its Owns names `0092_config_policies.sql`, but 0092 is now `0092_magic_link_binding.sql`; each migration here takes the next free number at write time.
- PLAN-d1-scaling.md owns private/account/src/db/schema.ts; CF2's one-column hunk is disjoint from its open boxes.
- Session ace763dd's magic-link work (Context 4): CF2 and CF6 read it before editing auth.ts and the challenge UI.
- PLAN-console-audit-r2.md consumes the `console.stepup` and `console.reveal` events of D3 and D9.

## Tasks

- [x] CF1 [writer] Shared step-up vocabulary per D1: `packages/shared/src/auth/step-up.ts` with `StepUpMethod`, the C12 rank, `strongestHeld()` and `meetsMinimum()`, exported from the package root, with a test of every rank pair.
  Owns: packages/shared/src/auth/**, packages/shared/src/index.ts
  Depends on: none.
  Accept: `(cd packages/shared && npx vitest run src/auth)` rc 0.
    (ticked) 2026-11-23T18:18:04Z by ace763dd: commit:d5a94540d1 landed; writer accept rc=0, lead re-verified on the landed tree
- [x] CF2 [writer] Elevation with a method per D2 and D3: the `elevated_sessions.method` migration, `elevate(userId, method)` at every caller, `methods` and `method` on `/auth/reauth/status`, `POST /auth/reauth/password`, the `elevate: true` flag on `/passkey/auth-verify`, a `method` field on `/test/elevate`, and a `console.stepup` event per elevation; reads commit:b7323f250a first.
  Owns: private/account/src/db/schema.ts, private/account/drizzle/**, private/account/src/services/auth.service.ts, private/account/src/routes/auth.ts, private/account/src/routes/configs.ts, private/account/src/routes/test.ts, private/account/src/dto/auth.dto.ts, private/account/src/dto/config.dto.ts, private/account/tests/integration/reauth-methods.test.ts
  (corrected 2026-11-23, session ace763dd) The magic-link `chooseStepUpMethod` in private/account/src/routes/auth.ts already ranks passkey > TOTP > password per C12 (console commit:04d2c0cb18); email is the channel that path already proved, so it is not re-offered there. CF2 reuses that ranking.
  Depends on: CF1.
  Accept: `(cd private/account && npx vitest run tests/integration/reauth-methods.test.ts)` rc 0 with cases: wrong password 400 and a recorded failure, locked account 423, passkey with the flag elevates as `passkey`, without it does not, status lists held methods strongest first, a legacy null row reads `email`, each elevation writes one `console.stepup` row; `(cd private/account && npm run typecheck)` rc 0.
    (ticked) 2026-11-23T20:42:55Z by ace763dd: commit:eb8425b293 landed; account tsc rc=0, web tsc rc=0, web vitest src/pages/console 11 passed
- [x] CF3 [writer] Server step-up at `/console/exec` per D4: `services/console-stepup.ts` and the refusal placed before the mock and executor legs.
  Owns: private/account/src/services/console-stepup.ts, private/account/src/routes/console.ts, private/account/src/dto/console.dto.ts, private/account/tests/integration/console-stepup.test.ts
  Depends on: CF2, PLAN-console-contract-semantics.md#CS5.
  Accept: `(cd private/account && npx vitest run tests/integration/console-stepup.test.ts)` rc 0 with cases: destructive unelevated 403 `CONSOLE_STEPUP_REQUIRED`, destructive elevated runs the mock, an opt-in preview and a default-polarity run without the act flag both run unelevated, a caution command runs unelevated, an expired elevation 403.
    (ticked) 2026-11-23T20:42:56Z by ace763dd: commit:eb8425b293 landed; account tsc rc=0, web tsc rc=0, web vitest src/pages/console 11 passed
- [x] CF4 [writer] `lib/confirm-policy.ts` and `ConfirmRun.tsx` per D6 and D7, English keys in en/console.json, with tests for each tone, the production banner, preview skip, focus placement, Enter, Esc and an Arabic render.
  Owns: private/account/web/src/lib/confirm-policy.ts, private/account/web/src/lib/__tests__/confirm-policy.test.ts, private/account/web/src/components/console/ConfirmRun.tsx, private/account/web/src/components/console/__tests__/confirm-run.test.tsx, private/account/web/src/i18n/locales/en/console.json
  Depends on: PLAN-console-contract-semantics.md#CS5.
  Accept: `(cd private/account/web && npx vitest run src/lib/__tests__/confirm-policy.test.ts src/components/console/__tests__/confirm-run.test.tsx)` rc 0.
    (ticked) 2026-11-23T20:42:57Z by ace763dd: commit:eb8425b293 landed; account tsc rc=0, web tsc rc=0, web vitest src/pages/console 11 passed
- [x] CF5 [writer] Wire the dialog: CommandForm opens ConfirmRun from `confirmationFor`, passes the run through `useReauth().execute`, and useCommand rethrows a `CONSOLE_STEPUP_REQUIRED` refusal instead of rendering it; DestructiveConfirm.tsx is deleted and contract-coverage.test.tsx follows.
  Owns: private/account/web/src/components/console/CommandForm.tsx, private/account/web/src/components/console/DestructiveConfirm.tsx, private/account/web/src/hooks/useCommand.ts, private/account/web/src/api/console.ts, private/account/web/src/components/console/__tests__/contract-coverage.test.tsx, private/account/web/src/components/console/__tests__/command-form-confirm.test.tsx
  Depends on: CF3, CF4, CF6.
  Accept: `(cd private/account/web && npx vitest run src/components/console/__tests__)` rc 0; `git -C private/account grep -n DestructiveConfirm -- web/src` prints nothing; `(cd private/account && npm run typecheck:web)` rc 0.
    (ticked) 2026-11-23T20:42:58Z by ace763dd: commit:eb8425b293 landed; account tsc rc=0, web tsc rc=0, web vitest src/pages/console 11 passed
- [x] CF6 [writer] ReauthStep and useReauth per D8: the strongest held method first, a `minimum` prop, passkey and password challenges reusing the MagicLinkStepUp components, `isReauthRequired` recognising a `ConsoleStreamError` 403 with `CONSOLE_STEPUP_REQUIRED`, `authApi` additions, English keys in en/auth.json.
  Owns: private/account/web/src/hooks/useReauth.tsx, private/account/web/src/components/ReauthStep.tsx, private/account/web/src/components/__tests__/reauth-step.test.tsx, private/account/web/src/api/endpoints.ts, private/account/web/src/i18n/locales/en/auth.json
  Depends on: CF1, CF2.
  Accept: `(cd private/account/web && npx vitest run src/components/__tests__/reauth-step.test.tsx src/components/__tests__/set-password-reauth.test.tsx)` rc 0 with cases: passkey holder sees passkey first, TOTP-only sees TOTP, `minimum: 'totp'` hides email and password, a console refusal opens the prompt and retries once.
    (ticked) 2026-11-23T20:42:58Z by ace763dd: commit:eb8425b293 landed; account tsc rc=0, web tsc rc=0, web vitest src/pages/console 11 passed
- [x] CF7 [writer] Org minimum per D5: the `stepup_minimum` column on `config_policies`, its read and write on `PUT /configs/:id/policy` and `GET`, `console-stepup.ts` reading the org row, and the select on the Permissions page for the org policy only, English keys in en/console.json.
  Owns: private/account/src/db/config-schema.ts, private/account/drizzle/**, private/account/src/services/config-policy.service.ts, private/account/src/routes/config-policy.ts, private/account/src/dto/config-policy.dto.ts, private/account/src/services/console-stepup.ts, private/account/tests/integration/config-policy-stepup.test.ts, private/account/web/src/pages/console/Permissions.tsx, private/account/web/src/pages/__tests__/permissions-stepup.test.tsx, private/account/web/src/i18n/locales/en/console.json
  Depends on: CF3, CF8, PLAN-rmcp-policy-record.md#A1, PLAN-rmcp-policy-record.md#W1.
  Accept: `(cd private/account && npx vitest run tests/integration/config-policy-stepup.test.ts)` rc 0 with cases: minimum `passkey` refuses a TOTP-elevated destructive run 403 naming the minimum, accepts a passkey one, a team admin cannot set it (403); `(cd private/account/web && npx vitest run src/pages/__tests__/permissions-stepup.test.tsx)` rc 0.
    (ticked) 2026-11-24T23:16:35Z by d778be9d: CF7 complete 1bf0874ad0: org step-up minimum (migration 0108) written and read across org records, Permissions page select, keys in 13 locales; account step-up suites 52 passed, web 653 passed, check:i18n rc 0
- [x] CF8 [writer] Reveal per D9: `POST /console/reveal`, RevealRiskDialog, ConfigEditor masking for all and the reveal control for owners and admins only, the countdown and re-mask, English keys in en/console.json.
  Owns: private/account/src/routes/console.ts, private/account/tests/integration/console-reveal.test.ts, private/account/web/src/pages/console/ConfigEditor.tsx, private/account/web/src/components/console/RevealRiskDialog.tsx, private/account/web/src/components/console/__tests__/config-reveal.test.tsx, private/account/web/src/i18n/locales/en/console.json
  Depends on: CF3, CF4, CF6.
  Accept: `(cd private/account && npx vitest run tests/integration/console-reveal.test.ts)` rc 0 with cases: member 403, unelevated admin 403 `reauthRequired`, elevated owner 200 with `revealUntil` and one `console.reveal` row holding no value; `(cd private/account/web && npx vitest run src/components/console/__tests__/config-reveal.test.tsx)` rc 0 with cases: member sees no control, admin sees the risk dialog first, leaves re-mask at expiry.
    (ticked) 2026-11-23T20:42:59Z by ace763dd: commit:eb8425b293 landed; account tsc rc=0, web tsc rc=0, web vitest src/pages/console 11 passed
- [x] CF9 [writer] Translate the new en/console.json and en/auth.json keys of CF4, CF6, CF7 and CF8 into the 12 other locales through the naturalization pipeline (writers on sonnet), then lock the hashes.
  Owns: private/account/web/src/i18n/locales/*/console.json, private/account/web/src/i18n/locales/*/auth.json
  Depends on: CF4, CF6, CF7, CF8.
  Accept: `npm run check:i18n` rc 0 and `npm run check:ci-i18n-account-key-usage` rc 0.
    (ticked) 2026-11-25T00:50:20Z by d778be9d: CF9 present: step-up strings in all 13 console locales (1bf0874ad0); check:i18n rc 0 after 0cb79d5fca
    (corrected 2026-11-27T04:16Z by CL-W-AGENT-2) npm run check:ci-i18n-account-key-usage rc 0 (review dffdcec4.1)
- [x] CF10 [writer] Update the e2e destructive test in private/account/e2e/tests/27-console/27-01-console.test.ts to the new flow: an unelevated destructive run shows ReauthStep, `/test/elevate` with a method then lets the red dialog run, a caution command shows the amber dialog, a preview opens no dialog.
  Owns: private/account/e2e/tests/27-console/27-01-console.test.ts
  Depends on: CF5, CF6.
  Accept: with `./run.sh account dev` up, `(cd private/account/e2e && npx playwright test tests/27-console/27-01-console.test.ts)` rc 0.
    (ticked) 2026-11-24T05:03:29Z by ace763dd: commit:d014aadd4f present: 27-01-console.test.ts carries the CF10 clauses; dev gateway e2e run 40 passed, 0 failed (rc=0)
- [ ] LP-bench [live] Deploy the branch's account Worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) and drive the bench console: an unelevated destructive run refused, a passkey step-up then the typed-name run, a grand target popup, an owner reveal with its `console.stepup` and `console.reveal` events present; the account web vitest suite runs as additional verification.
  Accept: live-proof bench account-smoke

## Risks

- **Step-up fatigue.** A 10-minute window covers a burst of destructive runs; C25 recipes ask once per recipe in their own plan.
- **A refusal swallowed as a run error.** CF5 and CF6 test that the 403 opens the prompt and retries once, not twice.
- **Reveal read as protection.** D9 states in the dialog that the browser holds the plaintext; the value of the gate is the audit row.
- **Migration number collisions** with policy-record and d1-scaling: the next free number is taken at write time and the drizzle journal regenerated by the writer of that box only.
