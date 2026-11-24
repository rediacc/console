# PLAN: Stripe disable flag -- one server-enforced switch turns off checkout, the customer portal, plan switching, the Stripe webhook and the admin Stripe pages, with admin-edited plans as the only path
Status: approved -- operator /ask 2026-11-23 in session 9b22c347, worklist #0831560e ("make a new plan to disable stripe integration/buttons etc. and we must disable immediately when plan is implemented")
Owner: 9b22c347
First-Seen: 2026-11-23
Depends-On: no-dep -- every box builds on the 1121-1 tip; SD5 edits .github/workflows/ci.yml, which PLAN-tooling-code-reduction.md CR2 also rewrites, so SD5 waits on PLAN-tooling-code-reduction.md#CR2 as a box dependency rather than a plan edge
Priority: P1 -- Stripe is planned for removal and the operator wants it off as soon as this lands; the edge secrets push already sends an empty Stripe key (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:504), so a public portal can show Start trial and Manage billing over routes that answer 503
Concurrency: parallel -- wave 1: SD1 (server) and SD4 (www) are file-disjoint; wave 2 after SD1: SD2 (web) and SD7 (CLI hint); wave 3: SD3 (translations), SD5 (e2e and CI, after CR2), SD6 (lead correction lines); LP-bench last
Owns: agent/plans/PLAN-stripe-disable.md, private/account/src/types/env.ts, private/account/src/app.ts, private/account/src/container.ts, private/account/src/utils/stripe.ts, private/account/src/middleware/stripe.ts, private/account/src/middleware/require-stripe.ts, private/account/src/routes/portal.ts, private/account/src/routes/webhook.ts, private/account/src/routes/root-stripe.ts, private/account/src/routes/index.ts, private/account/tests/integration/stripe-disabled*.test.ts, private/account/web/src/pages/Subscription.tsx, private/account/web/src/router.tsx, private/account/web/src/pages/console/ConsoleGate.tsx, private/account/web/src/lib/nav-config.ts, private/account/web/src/api/types.ts, private/account/web/src/pages/__tests__/subscription-billing-disabled.test.tsx, private/account/web/src/i18n/locales/*/subscription.json, private/account/web/src/i18n/locales/.translation-hashes.json, packages/www/src/pages/[lang]/pricing.astro, packages/www/src/components/CfPricingCard.astro, packages/www/src/components/__tests__/pricing-no-checkout.test.ts, packages/shared/src/subscription/constants.ts, packages/cli/src/commands/doctor-subscription.ts, packages/cli/src/i18n/locales/*/cli.json, private/account/e2e/tests/**, private/account/e2e/run-stripe-e2e.sh, .github/workflows/ci.yml, private/account (gitlink bump only)
Live-Proof: bench -- the account Worker routes, the portal bundle and the www pricing page change; LP-bench runs account-smoke after deploy_bench and probes the refused routes

## Ask

The operator plans to remove the Stripe integration and asked for one disable flag that turns off the integration and its buttons, effective as soon as the plan is implemented. Self-serve purchase goes away: plans change by admin action (and, for the forensics quota of the breach-forensics work, by plan upgrade or an admin-set enterprise override).

## Context

1. There is no single switch: each Stripe route refuses only when its own key is missing. `POST /portal/checkout`, `POST /portal/billing` and `POST /portal/subscription/change` check the key separately (private/account/src/routes/portal.ts:768, private/account/src/routes/portal.ts:823, private/account/src/routes/portal.ts:884); the webhook answers 404 without a secret (middleware since deleted by the Stripe removal); `/admin/stripe/*` has its own routes ending with `reconcile` (file since deleted by the Stripe removal); tax rates load at startup when a key exists (private/account/src/app.ts:371).
2. The edge secrets push sends an empty Stripe key on every channel except stable (.ci/rediacc_ci/deploy/set_account_worker_secrets.py:504), so a public portal may already show Start trial, Switch plan and Manage billing (the Subscription page, since rewritten by the Stripe removal) over routes that answer 503. Not confirmed against `wrangler secret list`.
3. Plans change without Stripe today through `PUT /admin/subscriptions/:id` and `POST /admin/subscriptions`, root and partner grants, the COMMUNITY row new signups receive, and the on-premise entry, which builds without Stripe. Past invoices are read from D1 and keep working.
4. Booleans come from `boolFromEnv` (private/account/src/types/env.ts:16); the web learns server state from `GET /portal/me` (private/account/src/routes/portal.ts:308). No feature-flag helper exists.
5. The www pricing cards render a Start trial button that sends the visitor to `/account/?checkout=<plan>` (packages/www/src/pages/[lang]/pricing.astro:84, and the CfPricingCard component, since rewritten by the Stripe removal). The console gate links to the subscription page as an upgrade path (private/account/web/src/pages/console/ConsoleGate.tsx:72).
6. The CLI opens no checkout; only a "check billing" hint mentions it (packages/cli/src/commands/doctor-subscription.ts:19).
7. agent/plans/PLAN-root-grants.md:86 (R5) skips a subscription with a Stripe customer as billing-managed; with Stripe off that becomes a report, not a block.

## Design

D1. **The flag is `BILLING_STRIPE`, read with `boolFromEnv(false)`, default off.** The plain code change disables Stripe on deploy with no wrangler edit, which is what "disable immediately when implemented" requires. A Stripe key without the flag is ignored, so a stray secret cannot turn checkout back on. It is carried as `envConfig.stripeEnabled`.

D2. **Server enforcement, not only hidden buttons.** One middleware, `requireStripe()`, guards `/portal/checkout`, `/portal/billing`, `/portal/subscription/change` and all of `/admin/stripe/*`, answering 410 with code `BILLING_DISABLED`; the webhook answers 404. With the flag off the startup tax-rate load is skipped and `getStripe` throws as a backstop. Admin plan editing, grants, signup and invoice reads stay untouched.

D3. **The web reads `billing: { selfServe: boolean }` from `GET /portal/me`.** With it false the subscription page shows the current plan, no plan picker, no period toggle, no trial, switch or manage buttons, and the `?checkout=` redirect is a no-op. An org owner sees a note that plan changes are made by Rediacc, with the existing contact-sales link; other members see a note to contact their org owner. The console gate's upgrade link points at the same contact copy. The admin Stripe nav item and pages are hidden.

D4. **www drops checkout.** Pricing cards take the existing contact or account-link branch; `selfServe` becomes false for every plan in packages/shared/src/subscription/constants.ts.

D5. **Tests move, they are not deleted.** The Stripe e2e suites run only when `BILLING_STRIPE=1`, and the CI `stripe-sandbox` job runs under the same condition; a new e2e proves the replacement path (an admin edits the plan, the customer page shows it). The repo rule against skipping tests is kept by gating on the flag, not by `skip`.

D6. **Errors carry an origin.** `BILLING_DISABLED` is a `user` origin row in the error-origin table of agent/plans/PLAN-console-contract-semantics.md when that table exists; until then the code is documented in the route test.

## Ordering against other live plans

- agent/plans/PLAN-terms-region-notice.md (Stripe consent rows), agent/plans/PLAN-portal-analytics.md (`trial_start`/`purchase` events) and agent/plans/PLAN-www-funnel-truthfulness.md ("Start free trial" copy) are proposed and build on Stripe surfaces; this plan lands first and SD6 writes correction lines on their affected boxes.
- agent/plans/PLAN-account-sidebar-redesign.md lists Stripe in the Billing group; SD2 hides the item and SD6 records it there.
- agent/plans/PLAN-root-grants.md R5 becomes report-only for Stripe customers (SD6 correction line).
- SD5 waits on PLAN-tooling-code-reduction.md#CR2, which rewrites .github/workflows/ci.yml.

## Tasks

- [x] SD1 [writer] Server flag and enforcement (D1, D2, D6): `BILLING_STRIPE` via `boolFromEnv(false)` carried as `envConfig.stripeEnabled`, a `requireStripe()` middleware answering 410 `BILLING_DISABLED` on the three portal billing routes and every `/admin/stripe/*` route and 404 on the webhook, the startup tax-rate load and `getStripe` gated on the flag, and `billing.selfServe` on `GET /portal/me`.
  Owns: private/account/src/types/env.ts, private/account/src/app.ts, private/account/src/container.ts, private/account/src/utils/stripe.ts, private/account/src/middleware/stripe.ts, private/account/src/middleware/require-stripe.ts, private/account/src/routes/portal.ts, private/account/src/routes/webhook.ts, private/account/src/routes/root-stripe.ts, private/account/src/routes/index.ts, private/account/tests/integration/stripe-disabled*.test.ts
  Depends on: none.
  Accept: `(cd private/account && npx vitest run tests/integration/stripe-disabled.test.ts)` rc 0 with cases: each guarded route returns 410 `BILLING_DISABLED` with the flag off even when `STRIPE_SECRET_KEY` is set, a signed webhook returns 404, `PUT /admin/subscriptions/:id` still changes `planCode`, `GET /portal/me` reports `billing.selfServe: false`, and with `BILLING_STRIPE=1` plus a key the checkout route reaches the Stripe client again; `(cd private/account && npm test)` rc 0.
    (ticked) 2026-11-23T18:17:48Z by ace763dd: commit:33a8cd381a landed; writer accept rc=0, lead re-verified on the landed tree
- [x] SD2 [writer] Portal without self-serve billing (D3): the subscription page, the `?checkout=` route, the console gate link and the admin Stripe nav item read `billing.selfServe`, with the owner and member copy in English and a component test.
  Owns: private/account/web/src/pages/Subscription.tsx, private/account/web/src/router.tsx, private/account/web/src/pages/console/ConsoleGate.tsx, private/account/web/src/lib/nav-config.ts, private/account/web/src/api/types.ts, private/account/web/src/pages/__tests__/subscription-billing-disabled.test.tsx, private/account/web/src/i18n/locales/en/subscription.json
  Depends on: SD1.
  Accept: `(cd private/account/web && npx vitest run src/pages/__tests__/subscription-billing-disabled.test.tsx)` rc 0 asserting no `manage-billing`, `manage-trial`, start-trial or switch-plan control renders and the contact copy does when `selfServe` is false, and `?checkout=PROFESSIONAL` does not redirect; `(cd private/account/web && npm test)` and `(cd private/account/web && npm run build)` rc 0.
    (ticked) 2026-11-23T18:19:41Z by ace763dd: commit:b41f60733b landed; private/account/web tsc rc=0, web vitest 418 passed
- [x] SD3 [writer] Translate the new subscription strings into the 12 other locales, naturalized per docs/i18n/CONVENTIONS.md, by a sonnet writer.
  Owns: private/account/web/src/i18n/locales/*/subscription.json, private/account/web/src/i18n/locales/.translation-hashes.json
  Depends on: SD2.
  Accept: `npm run check:ci-i18n-account-key-usage` rc 0 and `npm run check:i18n` rc 0.
    (ticked) 2026-11-23T18:19:43Z by ace763dd: commit:b41f60733b landed; private/account/web tsc rc=0, web vitest 418 passed
- [x] SD4 [writer] www without checkout (D4): pricing cards render the contact or account-link branch, `selfServe` is false for every plan, and a test proves no checkout element renders.
  Owns: packages/www/src/pages/[lang]/pricing.astro, packages/www/src/components/CfPricingCard.astro, packages/www/src/components/__tests__/pricing-no-checkout.test.ts, packages/shared/src/subscription/constants.ts
  Depends on: none.
  Accept: `(cd packages/www && npx vitest run src/components/__tests__/pricing-no-checkout.test.ts)` rc 0 asserting no `[data-checkout]` element and no `?checkout=` link; `(cd packages/shared && npx vitest run)` rc 0; `(cd packages/www && npm run build)` rc 0.
    (ticked) 2026-11-23T18:17:49Z by ace763dd: commit:3aa7a75670 landed; writer accept rc=0, lead re-verified on the landed tree
- [ ] SD5 [writer] Tests follow the flag (D5): the Stripe e2e suites (10-stripe, 12-stripe-e2e, 15-02 checkout intent, the checkout steps of 03-01, 11-04 and 11-07) and run-stripe-e2e.sh run only with `BILLING_STRIPE=1`, the CI `stripe-sandbox` job runs only under the same condition, the sidebar specs expect no Stripe item, and a new spec proves an admin plan edit shows on the customer page.
  Owns: private/account/e2e/tests/**, private/account/e2e/run-stripe-e2e.sh, .github/workflows/ci.yml
  Depends on: SD1, SD2, PLAN-tooling-code-reduction.md#CR2.
  Accept: `(cd private/account/e2e && npx playwright test tests/03-subscription --project=chromium)` rc 0 with the new admin-edit spec green; the Stripe suites report as not selected (never `skip`) without the flag; `npm run check:ci-workflows` rc 0.
- [ ] SD6 [lead] Correction lines on the neighbouring plans named under Ordering: PLAN-terms-region-notice.md, PLAN-portal-analytics.md, PLAN-www-funnel-truthfulness.md, PLAN-account-sidebar-redesign.md and PLAN-root-grants.md R5, each dated and citing this plan, box lines unchanged; then `npm run check:ci-plan-boxes -- --update` and `npm run check:ci-plan-record -- --update`.
  Depends on: none.
  Accept: both checks rc 0 after the regeneration; `git grep -n "PLAN-stripe-disable.md" -- agent/plans` lists the five plans.
- [ ] SD7 [writer] The CLI hint stops pointing at self-serve billing: doctor-subscription's "check billing" text names the account owner or Rediacc instead, in all 13 CLI locales by a sonnet writer.
  Owns: packages/cli/src/commands/doctor-subscription.ts, packages/cli/src/i18n/locales/*/cli.json
  Depends on: SD1.
  Accept: `(cd packages/cli && npm test)` rc 0; `npm run check:ci-i18n-cli-key-usage` rc 0.
- [ ] LP-bench [live] Deploy the branch to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) and run the console smoke; additional verification: `POST /portal/checkout`, `/portal/billing` and `/portal/subscription/change` return 410 `BILLING_DISABLED`, the subscription page shows the contact copy, and an admin plan edit appears on the customer page.
  Accept: live-proof bench account-smoke

## Risks

- **A stable-channel company that still pays through Stripe.** Default-off disables its renewals too; such a deployment sets `BILLING_STRIPE=1` until its customers move to admin-managed plans, and the 410 makes any missed one loud rather than silent.
- **Existing Stripe subscriptions keep their `cus_` ids.** Nothing deletes them; webhook-driven status sync stops, so admin edits become the source of truth (root-grants R5 turns report-only).
- **Removal is a later step.** This plan disables; deleting the Stripe code, secrets and bws entries is a separate plan once the operator confirms no deployment needs the flag.
