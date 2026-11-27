# PLAN: partner directory and partner value pages: an opt-in public "Find a partner" listing at launch, and a /partners page that sells protected deals, growing margin, certification, trials and calculator leads without publishing a discount percentage

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), rulings under ## Rulings
Depends-On: no-dep -- the partner profiles, tiers and deal registration exist today; this plan adds public listing fields, a public read route and page copy
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- the pricing page's "Get a partner offer" path (PLAN-pricing-public-calculator.md) needs partners to route to and a directory to show at launch
Concurrency: parallel -- packages/www/src/i18n/translations/en.json (the `pages.partners` and new `pages.partnerDirectory` keys only) is also edited by three other pricing plans on other keys; block_plan_concurrency serializes writers on it
Owns: agent/plans/PLAN-pricing-partner-directory.md, private/account (gitlink bump only), private/account/src/services/partner-directory.service.ts (new), private/account/src/routes/partner-directory.ts (new), private/account/drizzle/*_partner_directory.sql (new), private/account/src/db/schema.ts (the partner_profiles listing columns only), private/account/web/src/pages/partner/Profile.tsx (new), private/account/web/src/pages/admin/PartnerDetail.tsx (the listing approval only), private/account/web/src/router.tsx (one route line only), private/account/web/src/i18n/locales/*/partner.json, packages/www/src/pages/[lang]/partners.astro, packages/www/src/pages/[lang]/partners/find.astro (new), packages/www/src/components/partners/** (new), packages/www/src/i18n/translations/en.json (the `pages.partners` and `pages.partnerDirectory` keys only), private/account/tests/integration/partner-directory.test.ts (new)
Live-Proof: bench -- the public directory route runs on the account worker and the pages on the www worker; the receipt is taken on the eu bench after deploy_bench

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. Two pages: one for customers (pricing, PLAN-pricing-public-calculator.md) and one for potential partners (/partners, this plan).
- R2. The directory ships AT LAUNCH, even with few partners listed.
- R3. Value points shown (all four chosen): customers get local support in their language, local-currency invoicing, migration help and often a price below list, and free extras that grow with the deal; partners get registered deals protected against undercutting and extra margin for multi-year, upfront and larger deals (no percentage shown), free certification, partner-issued 30-day Enterprise trials and leads routed from the public calculator.
- R4. Channel stance on the page: partner first, Rediacc direct only where no partner serves the customer.
- R5. Competition law (agent research 2026-11-27, VBER 2022/720 Art 4(a), Vertical Guidelines ¶186-188): no price floor, no minimum advertised price, and listing or lead allocation never conditioned on a partner's resale prices.

## Finding (verified 2026-11-27)

- Partner profiles exist (private/account/src/db/schema.ts:1444, `partner_profiles`: tier registered|silver|gold|platinum, contact email, website) but carry no public listing fields (regions, languages, services, description, consent to list).
- Deal registration exists (private/account/src/db/schema.ts:1795, `deal_registrations`; private/account/src/services/deal-registration.service.ts).
- The /partners page exists (packages/www/src/pages/[lang]/partners.astro) with benefits for deal protection, free certification and trials and a four-tier ladder that already avoids percentages; it has no directory and no lead or margin-growth message.
- No public partner directory route or page exists.

## Design

1. **Listing fields.** partner_profiles gains `listed` (partner opt-in), `listing_approved_at` (admin), `display_name`, `countries` json, `languages` json, `services` json (resale, migration, managed service, training), `description`, `logo_url`. A partner edits them on a new portal Profile page; an admin approves the listing.
2. **Public route.** `GET /partners/directory` (anonymous, cached) returns only listed and approved active partners with display fields, tier name and current certificate count; never discounts, contacts beyond the public website, or deal data. Filters: country, language, service.
3. **Customer page.** `/[lang]/partners/find`: filters, cards, a "Request an offer" button that opens the lead form of PLAN-pricing-public-calculator.md with the partner preselected (until that plan lands, a mailto of the partner's public contact).
4. **Partner page.** /partners gains the R3 partner points, a "leads from our pricing calculator" section, the R4 stance in one sentence ("We don't sell around our partners"), and a link to the directory.
5. **Ordering.** A stable order that never depends on price: tier, then certificate count, then name.

## Tasks

- [ ] PD1 [writer] account: migration, listing fields, partner-directory.service.ts and the public route per Design 1, 2 and 5; tests, controls first (an unlisted or unapproved partner never appears; no discount field in the response; a suspended partner disappears).
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/integration/partner-directory.test.ts` rc 0
- [ ] PD2 [writer] portal: the partner Profile page and the admin approval control, English first then the locale pipeline.
  Accept: `cd private/account/web && npx tsc --noEmit && npx vitest run` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] PD3 [writer] www: the directory page and the /partners copy per Design 3-4, English first then the locale pipeline.
  Accept: `npm run build -w @rediacc/www` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] LP-bench [live] Deploy the branch's account and www workers to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after PD1-PD3 land.
  Accept: live-proof bench account-smoke
- [ ] PD-L1 [live] eu bench: a test partner opts in, an admin approves, the directory page lists it under its country filter, and the route response carries no discount or deal field.
  Accept: the transcript and the response body recorded under `## Outcome`

## Outcome
