# PLAN: free Professional for eligible organizations: self-attested eligibility with instant activation and later audit, the startup programme, upgrade popups, and the COMMUNITY migration

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), rulings under ## Rulings
Depends-On: PLAN-pricing-plan-model.md, PLAN-pricing-seat-repo-caps.md -- the free limits come from PM1 and PM2, and the 10-user / 25-repository caps must be enforced (SR1, SR2) before the free tier opens
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- the registration incentive of the whole redesign
Concurrency: parallel -- packages/www/src/i18n/translations/en.json (the legal keys only) is also edited by PLAN-pricing-public-calculator.md and PLAN-pricing-coupons.md (other keys); private/account/web/src/pages/Subscription.tsx is shared with PLAN-pricing-billing-upgrade.md and PLAN-pricing-coupons.md; block_plan_concurrency serializes writers on both
Owns: agent/plans/PLAN-pricing-free-professional.md, private/account (gitlink bump only), private/account/src/services/eligibility.service.ts (new), private/account/src/routes/eligibility.ts (new), private/account/src/routes/root-eligibility.ts (new), private/account/drizzle/*_org_eligibility.sql (new), private/account/src/db/schema.ts (the new tables only), private/account/src/email/templates/eligibility.ts (new), private/account/web/src/components/UpgradePrompt.tsx (new), private/account/web/src/pages/Subscription.tsx (the eligibility card only), private/account/web/src/pages/admin/Eligibility.tsx (new), private/account/web/src/router.tsx (two route lines only), private/account/web/src/i18n/locales/*/eligibility.json (new), private/account/tests/integration/eligibility.test.ts (new), packages/www/src/i18n/translations/en.json (the terms-of-service and privacy-policy keys only)
Live-Proof: bench -- the attestation, activation and admin routes run on the account worker; the receipt is taken on the eu bench after deploy_bench

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. Eligible: an organization that is not a government body and, with its affiliates, has fewer than 50 staff (full-time equivalent, contractors included) and less than USD 500,000 of revenue plus outside funding raised in the last 12 months. Individuals, non-commercial use, education and open-source projects are always eligible.
- R2. Self-attested with checkboxes; activation is INSTANT, audited later (the PostHog model). Re-attestation every 12 months.
- R3. Startup programme: 50% off paid Professional or Business for 24 months, for companies under 5 years old with at most USD 5M raised in total.
- R4. Upgrade popups: on first login and whenever a limit is hit, plus a permanent place to enter a new code (the code field is PLAN-pricing-coupons.md's; this plan leaves its slot).
- R5. Existing COMMUNITY accounts: near-zero users, so a 30-day notice under the existing ToS change section, then they stay on the COMMUNITY floor until they attest.
- R6. Legal wording (agent research 2026-11-27, not legal advice): the free tier is a conditional price (list price waived while eligible); audit at most once in 12 months on 15 days' notice with a chance to respond; back-billing at list price only, at most 24 months back, plus statutory interest; no burden-of-proof shift (VÕS §42(3) item 11 via §44); audit and back-billing apply to organizations, never consumers; affiliates aggregated; one free Professional per organization and its affiliates.

## Finding (verified 2026-11-27)

- Every signup gets a COMMUNITY row: private/account/src/services/initial-subscription.ts:36.
- Plan changes today are operator-only: the portal says so at private/account/web/src/pages/Subscription.tsx:215, and the operator route is `PUT /admin/subscriptions/:id`.
- No eligibility, employee, revenue, funding or startup logic exists anywhere.
- The organization record holds no company size or billing data (private/account/src/db/schema.ts:512, `organizations`); the user row has only `companyName` (:27).
- The Terms of Service text the site renders lives under the legal keys of packages/www/src/i18n/translations/en.json; the legal research found it calls Professional "paid" and that its "changed without notice" clause conflicts with VÕS §62¹⁹ for consumers on free plans.

## Design

1. **Attestation.** `org_eligibility` (org_id, kind individual|noncommercial|education|oss|organization, staff_band, revenue_plus_funding_band, government false, attested_by, attested_at, expires_at = +12 months, ip_hash, terms_version, status active|expired|revoked|under_audit). `POST /eligibility` writes it and, in the same batch, switches the org's subscription to PROFESSIONAL with pricingBasis free-eligible (PM1). One free Professional per organization: a second org sharing the company marker or a verified company domain is refused.
2. **Expiry.** A daily job emails at expiry minus 30 and minus 7 days; on expiry the subscription returns to COMMUNITY (running work unaffected, the 30-day restore-only R2 window of PLAN-pricing-billing-upgrade.md BU6 applies).
3. **Audit.** Root routes list attestations, open an audit (status under_audit, an email requesting documents, a 15-day clock), record a finding, revoke or clear; usable from the admin UI and with root API tokens.
4. **Startup programme.** `startup_applications` (org_id, founded_on, total_raised_band, website, status pending|approved|rejected, decided_by, discount_until = approval + 24 months). Approval stores a 50% price adjustment the invoice path of PLAN-pricing-billing-upgrade.md applies.
5. **Popups.** UpgradePrompt shows on first login and on every limit error the portal receives: "Small team? Get Professional free" (opens the attestation form), a code slot (hidden until PLAN-pricing-coupons.md lands), "Request upgrade" (PLAN-pricing-billing-upgrade.md; until then the support page).
6. **Legal text.** The R6 eligibility and audit clauses added to the Terms, the "Professional is paid" sentence corrected, a consumer carve-out to the "without notice" change clause, English first.
7. **Migration.** A one-off root route sends the R5 notice to every COMMUNITY org created before the release and records the send in the event log.

## Tasks

- [ ] FP1 [writer] account: migration, eligibility.service.ts and the public and root routes per Design 1-4; integration tests, controls first (an ineligible answer never switches the plan; a government body is refused; a second org on the same company marker is refused; expiry returns to COMMUNITY).
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/integration/eligibility.test.ts` rc 0
- [ ] FP2 [writer] portal: the attestation form, UpgradePrompt per Design 5, the admin Eligibility page, English then the locale pipeline.
  Accept: `cd private/account/web && npx tsc --noEmit && npx vitest run` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] FP3 [writer] legal and emails: Design 6 text in en.json, the expiry and audit email templates, the Design 7 notice.
  Accept: `npm run check:ci-i18n-account-email-templates` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] LP-bench [live] Deploy the branch's account worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after FP1 and FP2 land.
  Accept: live-proof bench account-smoke
- [ ] FP-L1 [live] eu bench: a fresh signup attests as a 3-person company and is on free Professional within the same request; an attestation answering 60 staff stays on COMMUNITY; an audit opened and cleared from a root API token.
  Accept: the transcripts recorded under `## Outcome`

## Outcome
