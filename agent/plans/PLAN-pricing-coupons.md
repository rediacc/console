# PLAN: coupon campaigns: time-boxed codes that grant quota, users, repositories, licences, CPU, a temporary plan or a discount, permanently or until a date, redeemable once per organization and email with an IP throttle, managed from the admin UI and with root API tokens

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), rulings under ## Rulings
Depends-On: PLAN-pricing-plan-model.md, PLAN-pricing-billing-upgrade.md -- boosts register into PM2's resolver; the discount effect applies to BU2's manual invoices
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- the operator's lever for registration campaigns (videos, social, newsletters)
Concurrency: parallel -- private/account/web/src/pages/Subscription.tsx is shared with PLAN-pricing-billing-upgrade.md and PLAN-pricing-free-professional.md, and private/account/src/services/effective-limits.ts is PM2's; block_plan_concurrency serializes writers on both
Owns: agent/plans/PLAN-pricing-coupons.md, private/account (gitlink bump only), private/account/src/services/campaign.service.ts (new), private/account/src/services/effective-limits.ts (the boost registration only), private/account/src/routes/redeem.ts (new), private/account/src/routes/root-campaigns.ts (new), private/account/drizzle/*_campaigns.sql (new), private/account/src/db/schema.ts (the two new tables only), private/account/web/src/pages/Subscription.tsx (the redeem card only), private/account/web/src/components/UpgradePrompt.tsx (the code slot only), private/account/web/src/pages/admin/Campaigns.tsx (new), private/account/web/src/pages/Login.tsx (the signup `?code=` read only), private/account/web/src/router.tsx (route lines only), private/account/web/src/i18n/locales/*/campaigns.json (new), packages/cli/src/commands/subscription/redeem.ts (new), packages/cli/src/i18n/locales/*/cli.json (the redeem verb strings only), packages/www/src/i18n/translations/en.json (the privacy-policy keys only), private/account/tests/integration/campaigns.test.ts (new)
Live-Proof: bench -- redemption, the resolver boost and the root routes run on the account worker; the receipt is taken on the eu bench after deploy_bench

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. Purpose: "lead more person to register ... more quota, machine or limit. Making it flexible would be great for future campaigns ... permanently or to a certain date increase the quotas".
- R2. Effects (all four chosen): quota boosts (setups/month, hosted R2 storage, repository size); more users or repositories; floating licences, CPU ceiling or large-machine passes; a temporary plan upgrade or a percentage or fixed price discount.
- R3. Durations: permanent, until a date, or N days after redemption. Each campaign has its own redemption window.
- R4. Redemption: once per organization AND once per verified email, with a per-IP throttle (hashed IPv4 address or IPv6 /64, default 1 per campaign, configurable) and Turnstile. Who: anyone with the code.
- R5. Coupons STACK across campaigns, each campaign once per org and email, with an optional per-dimension ceiling.
- R6. Entry points: signup (`?code=`), the first-login and limit-hit popups, a permanent "Redeem a code" field ("a place for loyal ones to enter a new code ... maybe they've watched a new youtube video"), and `rdc subscription redeem <code>`.
- R7. Managed from the admin UI and with root API tokens ("Should be manageable with root api key and with admin ui").
- R8. Legal (agent research 2026-11-27): the campaign terms (window, effect, duration, what happens at expiry) are shown before redemption; "permanent" reads "for as long as the account stays active, unless the campaign terms say otherwise"; hashed IPs are kept under legitimate interest (fraud prevention) until the campaign ends plus 12 months, stated in the privacy policy.

## Finding (verified 2026-11-27)

- No coupon, promotion, voucher or campaign code exists in account, shared, CLI or www.
- Building blocks: the nullable per-subscription overrides (`maxActivations`, `maxRepositorySizeGb`, `maxRepoLicenseIssuancesPerMonth`, `storageQuotaBytes`, `features`) on the subscriptions table carry no expiry, so a boost written into them could never lapse; PM2's resolver computes limits at read time instead.
- The FREE licence service already keys per-IP limits on an HMAC of the IPv4 address or IPv6 /64 (private/account/src/services/free-license.service.ts:48).
- Root API tokens (`root:admin`, IP-bound, TOTP session) reach every root route.

## Design

1. **Tables.** `campaigns` (id, code unique case-insensitive, name, starts_at, ends_at, max_redemptions, per_ip_limit, status draft|active|paused|ended, terms_text, effects json, created_by). An effect: {dimension, op add|set, amount, duration permanent|until|days, until_at, days, ceiling}. `campaign_redemptions` (campaign_id, org_id, user_id, email_verified, ip_hash, redeemed_at, effects_snapshot json with each effect's resolved expires_at), unique on (campaign_id, org_id) and (campaign_id, user email).
2. **Resolver.** campaign.service registers a boost provider into PM2's resolver: active snapshots add or set their dimensions, stack across campaigns, respect each ceiling; expired effects drop out at read time with no cleanup job. A temporary plan effect overrides planCode for its window; a discount effect is read by BU2's invoice creation.
3. **Redeem.** `POST /redeem` (Turnstile, verified email required): window, status, total cap, per-org, per-email and per-IP checks in that order, each with its own refusal code; the campaign terms are returned before confirmation and their version stored with the redemption.
4. **Admin.** Root routes create, edit (effects locked after the first redemption; a new campaign instead), pause, end, list redemptions and export; the admin Campaigns page on top.
5. **Entry points.** Per R6; the CLI verb calls the same route with the device-auth token.

## Tasks

- [ ] CP1 [writer] account: migration, tables, campaign.service.ts with the resolver provider per Design 1-2; unit tests, controls first (an expired effect no longer applies; two campaigns stack; a ceiling caps the sum; a temporary plan ends on time).
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/integration/campaigns.test.ts` rc 0
- [ ] CP2 [writer] redeem and root routes per Design 3-4 with integration tests for every refusal (window, paused, total cap, second redemption per org, per email, per IP, missing Turnstile).
  Accept: `cd private/account && npx vitest run tests/integration/campaigns.test.ts` rc 0
- [ ] CP3 [writer] portal, signup and CLI entry points per Design 5, the admin page, the privacy-policy line, English first then the locale pipeline.
  Accept: `cd private/account/web && npx tsc --noEmit && npx vitest run` rc 0, `npx tsc --noEmit --project packages/cli/tsconfig.json` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] LP-bench [live] Deploy the branch's account worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after CP1 and CP2 land.
  Accept: live-proof bench account-smoke
- [ ] CP-L1 [live] eu bench: a root API token creates a campaign (+50 GiB hosted storage for 30 days, +10 repositories permanently), a test org redeems it from the portal and a second from the CLI, a second redemption from the same org is refused, and the effective limits show both boosts.
  Accept: the transcripts recorded under `## Outcome`

## Outcome
