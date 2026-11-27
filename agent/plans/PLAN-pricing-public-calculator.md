# PLAN: public pricing calculator and pricing page: a server-only estimate and non-binding quote API cut from the partner engine, lead routing to certified partners as registered deals, and a pricing page with the Custom tier, a VAT toggle and the known inconsistencies fixed

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), rulings under ## Rulings
Depends-On: PLAN-pricing-plan-model.md, PLAN-pricing-partner-directory.md -- the plan resolver reads PM1's tiers and PM2's limits; the quote's partner path routes to PD1's listed partners
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- the transparency goal: anyone, Enterprise prospects included, sees what they would get and roughly pay without talking to sales
Concurrency: parallel -- private/account/src/pricing/** is otherwise touched only by PM1 (catalog edition rates); packages/www/src/i18n/translations/en.json (the `pages.pricing`, `roiCalculator` and legal quote keys only) is shared with three pricing plans on other keys; block_plan_concurrency serializes writers on both
Owns: agent/plans/PLAN-pricing-public-calculator.md, private/account (gitlink bump only), private/account/src/pricing/public-engine.ts (new), private/account/src/pricing/plan-resolver.ts (new), private/account/src/pricing/partner-engine.ts (new), private/account/src/pricing/public-catalog.ts (new), private/account/src/pricing/engine.ts, private/account/src/pricing/types.ts, private/account/src/routes/pricing-public.ts (new), private/account/src/routes/partner-offers.ts (the proposal payload only), private/account/src/services/public-quote.service.ts (new), private/account/src/services/offer.service.ts (the proposal payload only), private/account/drizzle/*_public_quotes.sql (new), private/account/src/db/schema.ts (the new table only), private/account/tests/pricing/**, private/account/tests/integration/pricing-public.test.ts (new), packages/www/src/pages/[lang]/pricing.astro, packages/www/src/components/pricing-plans.ts, packages/www/src/components/CfPricingCard.astro, packages/www/src/components/PricingComparison.astro, packages/www/src/components/pricing/** (new), packages/www/src/components/LlmsInlineScript.astro, packages/www/src/components/solution-pages/roi-compute.ts, packages/www/src/i18n/translations/*.json (the `pages.pricing` and `roiCalculator` keys only, plus the legal quote keys in en.json)
Live-Proof: bench -- the public pricing routes run on the account worker and the page on the www worker; the receipt is taken on the eu bench after deploy_bench

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. The engine stays SERVER-ONLY in private/account ("Server-only API in private/account"); nothing pricing-related is added to the public console repo beyond the list prices already in packages/shared.
- R2. Page: four cards, Free (no signup) / Professional ($0 if eligible, else per licence) / Business / Custom ("Build your quote"); the quote panel leads with "Get a partner offer", "Buy direct at list" is the secondary link, plus "Download PDF quote"; a partner strip below.
- R3. Channel: partner first, Rediacc direct as fallback when no partner covers the customer.
- R4. Prices excluding VAT by default with an "incl. VAT" toggle.
- R5. Quote: non-binding, 30-day price hold, line items, list prices in USD excluding VAT. Wording per the legal research (VÕS §16(2)-(3), §17): an invitation to make an offer, with the 30 days as a separate price-hold promise; "Certified partners set their own prices and may offer lower ones".
- R6. Lead capture: two separate unticked boxes, "email me this quote" and "share with one certified partner serving my region"; the partner is an independent controller and is named.
- R7. Partners may sell below list; Rediacc's partner floor is unchanged (the offer builder's red below-cost warning stays); public quote leads become registered deals for the assigned partner, never conditioned on partner prices (VBER 2022/720 Art 4(a)).
- R8. Calculator inputs are floating licences provisioning at the same time, logical CPUs of the largest machine, users, repositories, setups per month, eligibility answers and term; outputs carry the tier, the price state (free, startup discount, list, custom), the limits and the reasons ("Paid licence needed: machine has 48 CPUs (Professional ceiling 32)").

## Finding (verified 2026-11-27)

- The engine prices Enterprise capacity only and is a pure `computeQuote(offer, catalog)`; its customer-price half is already a separate step, computeCapacityPricing at private/account/src/pricing/engine.ts:277, returning CapacityPricing (private/account/src/pricing/types.ts:462, commented "everything the customer sees; no partner economics").
- `GET /partner/catalog` returns the whole catalog, every tier's discount and the kicker tables, to any partner member (private/account/src/routes/partner-offers.ts:44).
- The customer proposal prints the registered-deal percentage, which only moves partner cost (private/account/src/pricing/engine.ts:1423).
- www publishes the Enterprise price despite "Contact us": structured data at packages/www/src/pages/[lang]/pricing.astro:60 and the card's data attribute at packages/www/src/components/CfPricingCard.astro:63.
- The ROI calculator assumes $100 per server per month, a third price matching nothing (packages/www/src/components/solution-pages/roi-compute.ts:179).
- Hand-typed prices sit in the llms text (packages/www/src/components/LlmsInlineScript.astro) and the refund policy copy; the 12 non-English locales carry stale tier limits.
- A Turnstile-guarded anonymous lead endpoint already exists for lead magnets (`/account/api/v1/newsletter/lead-magnet`), the pattern the quote route copies.

## Design

1. **Engine split.** public-engine.ts holds the customer-price side (capacity pricing, term and prepay, service list prices); partner-engine.ts the registered deal, the partner stack, kickers and margins; engine.ts composes them so `computeQuote` returns byte-identical results (a parity test over the existing pricing fixtures). public-catalog.ts `toPublicCatalog(catalog)` strips tiers, kickers, caps, marginHealth, tierRequirements and feature cuts.
2. **Plan resolver.** plan-resolver.ts implements R8 for Free, Professional and Business from PM1 and PM2, and hands Enterprise-sized inputs to public-engine with the public catalog.
3. **Routes.** `POST /pricing/estimate` (anonymous, rate-limited) returns the R8 outputs; `POST /pricing/quote` (Turnstile) stores a `public_quotes` row (number, catalog version, inputs, result, valid_until = +30 days, consents, lead fields) and returns a PDF rendered with the R5 disclaimer. With the partner consent, the lead is assigned to one listed partner (country, language, service, then the directory order) and opens a registered deal for it.
4. **Partner fixes.** The customer proposal drops the registered-deal percentage; the proposal view receives only proposal sections, not the full quote.
5. **Page.** R2 layout and copy, the eligibility checker, the calculator island calling the estimate and quote routes, the VAT toggle (rate by visitor country, labelled), the partner value block and free-extras block, the structured-data Enterprise price removed, the ROI calculator reading PM1's per-licence price, the llms text and refund copy derived from PLAN_PRICING, all 13 locales re-synced through the pipeline.

## Tasks

- [ ] PC1 [writer] Engine split per Design 1 with the parity test and a test that `toPublicCatalog` output contains none of the partner-only keys.
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/pricing` rc 0
- [ ] PC2 [writer] plan-resolver.ts per Design 2 with a table test covering every R8 reason (free, user cap, repo cap, CPU ceiling, not eligible, startup, Enterprise size).
  Accept: `cd private/account && npx vitest run tests/pricing` rc 0
- [ ] PC3 [writer] Routes, table, PDF and lead routing per Design 3; tests, controls first (no consent never shares a lead; the quote response carries no partner field; a quote's catalog version is pinned).
  Accept: `cd private/account && npx vitest run tests/integration/pricing-public.test.ts` rc 0
- [ ] PC4 [writer] Partner fixes per Design 4 with tests on the proposal sections and payload.
  Accept: `cd private/account && npx vitest run tests/pricing` rc 0 and `cd private/account/web && npx tsc --noEmit` rc 0
- [ ] PC5 [writer] www per Design 5, English first, then the locale pipeline; check-pricing-consistency (PM4) green on the result.
  Accept: `npm run build -w @rediacc/www` rc 0, `npx tsx scripts/gates/check-pricing-consistency.ts` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] LP-bench [live] Deploy the branch's account and www workers to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after PC1-PC5 land.
  Accept: live-proof bench account-smoke
- [ ] PC-L1 [live] eu bench: the pricing page computes a free-Professional, a Business and a 120-licence Custom estimate; the Custom quote PDF downloads with the disclaimer and a 30-day validity; with the partner consent the bench test partner receives a registered deal; the page source carries no Enterprise price in structured data.
  Accept: the transcripts, the quote number and the deal number recorded under `## Outcome`

## Outcome
