# PLAN: self-serve upgrade without a payment provider: billing profile with a VIES check, instant upgrade, manual invoice with a 14-day due date and 7-day grace, admin and root-token controls, and a 30-day restore-only window for hosted R2 on any drop

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), rulings under ## Rulings
Depends-On: PLAN-pricing-plan-model.md, PLAN-stripe-disable.md -- the per-licence prices come from PM1; the Stripe removal leftovers (SD6, its LP-bench) own private/account/web/src/pages/Subscription.tsx and router.tsx and must close or be serialized first
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- the pricing page's paid buttons lead to a portal that cannot upgrade anyone (the Stripe checkout was deleted 2026-11-23)
Concurrency: parallel -- private/account/web/src/pages/Subscription.tsx and private/account/web/src/router.tsx sit in PLAN-stripe-disable.md's Owns and are shared with PLAN-pricing-free-professional.md and PLAN-pricing-coupons.md; private/account/src/services/subscription.service.ts (the plan-switch helper only) is shared with three pricing plans; block_plan_concurrency serializes writers on all of them
Owns: agent/plans/PLAN-pricing-billing-upgrade.md, private/account (gitlink bump only), private/account/src/services/billing-profile.service.ts (new), private/account/src/services/vies.service.ts (new), private/account/src/services/upgrade.service.ts (new), private/account/src/services/invoice.service.ts, private/account/src/services/reminder.service.ts (the new reminder kinds only), private/account/src/services/backup-retention-on-drop.service.ts (new), private/account/src/services/subscription.service.ts (the plan-switch helper only), private/account/src/routes/billing.ts (new), private/account/src/routes/root-invoices.ts, private/account/src/routes/root-upgrades.ts (new), private/account/drizzle/*_billing_profile.sql (new), private/account/src/db/schema.ts (the new tables and the invoice column nullability only), private/account/src/email/templates/billing.ts, private/account/web/src/pages/Subscription.tsx, private/account/web/src/pages/BillingProfile.tsx (new), private/account/web/src/pages/admin/Upgrades.tsx (new), private/account/web/src/pages/admin/AdminInvoices.tsx, private/account/web/src/router.tsx (route lines only), private/account/web/src/i18n/locales/*/subscription.json, private/account/web/src/i18n/locales/*/billing.json (new), packages/cli/src/commands/subscription/upgrade.ts (new), packages/cli/src/i18n/locales/*/cli.json (the upgrade verb strings only), private/account/tests/integration/billing-upgrade.test.ts (new)
Live-Proof: bench -- every route, the reminder kinds and the revert job run on the account worker; the receipt is taken on the eu bench after deploy_bench

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. No payment provider: "Request + manual invoice. They should save their company information, VAT number, address etc. Then we wait for the payment. Admin approves manually. There is root_api key support in the system, with that an AI agent can approve in the future when there is a bank transfer which is not integrated yet."
- R2. Activation: "Instant, invoice afterwards".
- R3. Unpaid: due in 14 days, 7-day grace, then the plan reverts to the free floor; "root api key or admin ui should be able to modify" every step.
- R4. VIES: validate EU VAT numbers when saved. Tested 2026-11-27 with Rediacc's own number (EE102920091): `POST https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number` answered valid, name "Rediacc OÜ" and the registered address; with `requesterMemberStateCode`/`requesterNumber` set to Rediacc's own number it also returned a consultation number (requestIdentifier); a zero number answered `valid: false` with no error.
- R5. Hosted R2 on any drop to the floor (unpaid invoice, cancellation, coupon expiry, failed re-attestation): no new backups; existing backups restorable and downloadable for 30 days with emails on days 0, 15 and 25; then deleted. Admin and root tokens can extend the window per account.
- R6. Prices shown and invoiced excluding VAT, with the VAT treatment decided per profile: Estonian VAT for consumers and for EU businesses without a valid VIES number, reverse charge for a valid EU business outside Estonia.

## Finding (verified 2026-11-27)

- The Stripe checkout, plan-change and billing-portal code is gone (PLAN-stripe-removal.md); the portal answers "Plans are changed by Rediacc" at private/account/web/src/pages/Subscription.tsx:215.
- Invoices: the table already carries customer address, tax ids, reverse charge, Factur-X keys and status `draft|finalized|paid|void|uncollectible`, but `stripe_invoice_id` is NOT NULL (private/account/src/db/schema.ts:1305). The admin routes only list, read and regenerate (private/account/src/routes/root-invoices.ts:54, :126); nothing creates an invoice.
- No billing profile: organizations hold no address, country or VAT number (private/account/src/db/schema.ts:512).
- Root API tokens carry the `root:admin` scope, bind an IP and open a TOTP session (private/account/src/db/schema.ts, `root_api_tokens`), so every root route below is callable by the admin UI and by an agent alike.
- A reminder runner already exists with kinds run in order (private/account/src/services/reminder.service.ts:155) and the worker has hourly and daily crons (private/account/wrangler.toml:43).

## Design

1. **Billing profile.** `billing_profiles` (org_id, legal_name, address json, country, vat_number, vat_status unchecked|valid|invalid|pending, vies_consultation_id, vies_name, vies_address, vies_checked_at, billing_email). Saving an EU VAT number calls VIES with Rediacc's number as requester; VIES unavailable leaves `pending`, charges Estonian VAT and retries hourly; root can mark it valid by hand. Re-checked before each invoice.
2. **Upgrade.** `POST /billing/upgrade` (plan, floating licences, term, optional machine passes): requires a complete profile, switches the plan immediately (R2), creates an `upgrade_requests` row and a finalized invoice with line items from PM1's prices, VAT per R6 and any startup or coupon adjustment, due in 14 days. CLI `rdc subscription upgrade` opens the same flow.
3. **Invoices.** The Stripe columns become nullable (migration); `invoice.service` gains create, mark-paid (amount, date, reference), void and extend-due; root routes expose them plus approve/revert on upgrade requests.
4. **Dunning.** New reminder kinds: due minus 3 days, due day, grace start, grace end. At due + 7 days unpaid, a job reverts the plan to the floor (COMMUNITY, or free Professional when a live attestation exists), logs it, and emails. Root can extend the due date or grace per invoice.
5. **R2 on drop.** On any drop that leaves the hosted quota at 0 while hosted data exists, the stores turn read-only, `backup_retention_on_drop` records delete_after = +30 days, emails go out on days 0, 15 and 25, and the existing backup GC deletes after the date unless root extended it.

## Tasks

- [ ] BU1 [writer] Billing profile and VIES per Design 1: migration, services, routes, portal page; tests with a stubbed VIES, controls first (valid, invalid, unavailable to pending, consultation id stored, non-EU country skips VIES).
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/integration/billing-upgrade.test.ts` rc 0
- [ ] BU2 [writer] Invoices per Design 3: nullable Stripe columns, create, mark-paid, void, extend-due and their root routes; the Factur-X and PDF output of a manual invoice validated against the existing generator tests.
  Accept: `cd private/account && npx vitest run tests/integration/billing-upgrade.test.ts` rc 0 and the existing invoice PDF tests rc 0
- [ ] BU3 [writer] Upgrade per Design 2: route, instant switch, invoice creation, VAT treatment per R6; the portal Subscription page replaces the "contact support" card with the upgrade flow; the admin Upgrades page; the CLI verb.
  Accept: `cd private/account/web && npx tsc --noEmit && npx vitest run` rc 0 and `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0
- [ ] BU4 [writer] Dunning per Design 4: reminder kinds, the revert job on the existing cron, root extend and revert; tests with a fake clock, controls first (paid on day 20 never reverts; an extended due date moves the revert).
  Accept: `cd private/account && npx vitest run tests/integration/billing-upgrade.test.ts` rc 0
- [ ] BU5 [writer] Copy: emails and portal strings, English first, the locale pipeline after.
  Accept: `npm run check:ci-i18n-account-email-templates` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] BU6 [writer] R2 on drop per Design 5 with tests: writes refused after the drop, reads and restores served until delete_after, deletion after, an extension honoured.
  Accept: `cd private/account && npx vitest run tests/integration/billing-upgrade.test.ts` rc 0
- [ ] LP-bench [live] Deploy the branch's account worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after BU1-BU4 and BU6 land.
  Accept: live-proof bench account-smoke
- [ ] BU-L1 [live] eu bench: a test org saves a profile with Rediacc's VAT number (VIES valid, consultation id stored), upgrades to Professional with 2 licences and is on it immediately, the invoice PDF shows the lines, a root API token marks it paid; a second org left unpaid with a back-dated due date reverts to the floor on the next cron pass.
  Accept: the transcripts and the two invoice numbers recorded under `## Outcome`

## Outcome
