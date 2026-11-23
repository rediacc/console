# PLAN: Stripe removal -- delete the dormant Stripe checkout, plan-change and webhook code that BILLING_STRIPE keeps off
Status: active -- removal is the executed DEFAULT of #c3383490 (2026-11-23, operator away; clean-break rule); SR2 landed as account 2c9d41a in gitlink 0f119d6430, leftovers tracked as #55882829
Depends-On: PLAN-stripe-disable.md -- removal follows the default-off switch and its portal copy
Priority: P3 -- nothing runs this code today: BILLING_STRIPE defaults off (SD1) and every plan's selfServe is false (SD4)
Concurrency: parallel -- account and web files only
Owns: agent/plans/PLAN-stripe-removal.md, private/account/src/**, private/account/tests/**, private/account/web/src/**, packages/shared/src/subscription/**
Live-Proof: bench -- the account Worker deployed to bench answers 404 on every removed Stripe route and still serves the operator plan change
Owner: ace763dd
First-Seen: 2026-11-23

## Ask

Decide between keeping the dormant Stripe path behind BILLING_STRIPE (the parked default) and deleting it. This draft lists what deletion would touch so the choice is concrete.

## Context (read 2026-11-23 against the tree)

1. `private/account/src/services/billing.service.ts:393` and `:513` refuse checkout and plan change for every plan because `getPlanMetadata(plan).selfServe` is false (SD4, 68e1565f6b).
2. `private/account/src/middleware/require-stripe.ts` (SD1) answers 410 BILLING_DISABLED on `/portal/checkout`, `/portal/billing`, `/portal/subscription/change` and every `/admin/stripe/*` route; `routes/webhook.ts` 404s with the flag off.
3. `private/account/src/routes/portal.ts:231,310` report `billing.selfServe` from the flag; the web (SD2, 55f19366e6) hides checkout and the admin Stripe routes when it is false.
4. `getStripe` throws on an empty key, and every Stripe secret reads empty with the flag off.

## Design (only if removal is chosen)

- Delete the checkout, plan-change, billing-portal and Stripe webhook routes, `utils/stripe.ts`, `middleware/stripe.ts`, the admin Stripe routes and their web pages, and the Stripe secrets in env.ts; no BILLING_STRIPE flag remains.
- Keep subscription plans, quotas and the admin `PUT /admin/subscriptions/:id` plan change (operator-driven, not Stripe).
- Delete the Stripe-dependent tests (terms-stripe, the stripe-disabled control group) and the tax-rate startup load.

## Boxes

- [ ] SR1 [operator] Choose removal over the parked DEFAULT (#c3383490). Accept: the operator's answer quoted here.
- [ ] SR2 [writer] Delete the code listed in Design. Accept: `cd private/account && npx tsc --noEmit && npx vitest run` rc 0, `cd private/account/web && npx tsc --noEmit` rc 0, `grep -rni "stripe" private/account/src --include=*.ts` lists only historical comments.
- [ ] LP-bench [live] Deploy the account Worker to bench and confirm the removed routes answer 404 and the admin plan change still works.
  Accept: live-proof bench account-smoke

## Outcome
