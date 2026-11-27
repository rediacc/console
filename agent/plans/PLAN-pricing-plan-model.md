# PLAN: pricing plan model: per-floating-licence prices from the partner catalog, CPU ceilings, user and repository caps, a quiet COMMUNITY floor with no hosted R2, and one effective-limit resolver

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), every ruling under ## Rulings; first plan of the pricing program, every other PLAN-pricing-*.md depends on it
Depends-On: no-dep -- the plan maps and the limit wrapper exist today; this plan only changes their values and adds dimensions
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- no customer is blocked (near-zero users), but every later pricing plan reads the dimensions this plan adds
Concurrency: parallel -- packages/shared/src/subscription/** also holds PLAN-executor-account-routes.md's new executor-account-routes.ts (a different file, EA1); private/account/src/services/subscription.service.ts is shared with PLAN-pricing-seat-repo-caps.md, PLAN-pricing-cpu-ceiling.md and PLAN-pricing-billing-upgrade.md, which all depend on this plan; block_plan_concurrency serializes writers on the overlap
Owns: agent/plans/PLAN-pricing-plan-model.md, packages/shared/src/subscription/constants.ts, packages/shared/src/subscription/types.ts, packages/shared/src/subscription/__tests__/**, private/account (gitlink bump only), private/account/src/types/subscription.ts, private/account/src/services/effective-limits.ts (new), private/account/src/services/backup-store-registry.ts (the BACKUP_STORE_LIMITS table only), private/account/src/pricing/catalog.default.ts (the edition rates only), private/account/tests/unit/effective-limits.test.ts (new), scripts/gates/check-pricing-consistency.ts, packages/www/src/content/docs/en/subscription-licensing.md
Live-Proof: bench -- the account worker reads every new dimension; the receipt is taken on the eu bench after deploy_bench

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. Tiers: Unregistered (plan FREE) unchanged; COMMUNITY stays as a plan code (signup default, grace degradation target, unknown-plan fallback) but is no longer marketed; it is shown as "Registered (free)".
- R2. COMMUNITY gets NO hosted R2 backup: "No, R2 only for eligible or paying". Its users bring their own S3 store.
- R3. Paid Professional and Business are priced PER FLOATING LICENCE, and the partner catalog editions are the list price: Professional $550/yr, Business $700/yr, Enterprise edition $900/yr; monthly = annual x 1.15 / 12 (about $53 / $67 / $86).
- R4. CPU ceiling per machine by tier, counted as logical CPUs (what the OS reports, hyperthreads and VM vCPUs included): FREE and COMMUNITY 16, free Professional 16, Professional 32, Business 64, Enterprise unlimited.
- R5. Users: free Professional 10, Professional 25, Business and Enterprise unlimited. Repositories (original repos only, forks do not count): free Professional 25, Professional 100 per licence, Business 250 per licence, Enterprise per quote.
- R6. Free Professional usage: 500 setups/month and 25 GiB hosted R2. Paid Professional keeps 2,000 setups and 100 GiB per licence; Business 5,000 and 500 GiB per licence.
- R7. Floating licences: Professional 1-5 self-serve, Business 1-39 self-serve, Enterprise 40+ (the catalog machine minimum).
- R8. Large-machine add-on: +8 CPUs per pass on one named machine, $50/month or $200/year, max 4 passes per machine, max 3 machines with passes per subscription; beyond that, Enterprise. The add-on itself lands in PLAN-pricing-cpu-ceiling.md; this plan carries its constants.

## Finding (verified 2026-11-27)

- Plan tables: PLAN_LIMITS at packages/shared/src/subscription/constants.ts:19, the degraded plan at :329, PLAN_MAX_MACHINES at :358 (every self-serve plan 1, ENTERPRISE 25), PLAN_PRICING at :563 ($49/$59 monthly, $499/$599 annual, ENTERPRISE 210000 cents).
- No user, repository-count or CPU dimension exists anywhere in shared, account or renet.
- Every account getter falls back to COMMUNITY: private/account/src/types/subscription.ts:283 (getLimitsForPlan) and :309, :315.
- Backup store counts are a separate table: private/account/src/services/backup-store-registry.ts:68 (COMMUNITY 2).
- Catalog edition rates: private/account/src/pricing/catalog.default.ts (professional 550, business 700, enterprise 900 per machine per year), so R3 needs no catalog change beyond keeping it the single source.
- The pricing gate checks English copy against PLAN_LIMITS and PLAN_MAX_MACHINES only, never prices or the 12 other locales (scripts/gates/check-pricing-consistency.ts).
- The Go copy carries plan codes and the degraded plan (private/renet/pkg/subscription/types.go); renet trusts the numbers signed into each licence, so the Go side of the CPU dimension lands with PLAN-pricing-cpu-ceiling.md, not here.

## Design

1. **Dimensions.** PLAN_LIMITS gains `maxUsers`, `maxRepositories` (per licence where R5 says so), `maxCpusPerMachine` (null = unlimited), and a `pricingBasis: 'free-eligible' | 'paid'` split for PROFESSIONAL so free Professional is the PROFESSIONAL plan code with the R5/R6 free limits (no new plan code; renet already knows PROFESSIONAL).
2. **Prices.** PLAN_PRICING is derived from the catalog edition rates (annual = rate x 100 cents, monthly = round(rate x 1.15 / 12)), so www, account and the calculator read one table; the hand-typed $49/$59 disappear.
3. **Effective limits.** `private/account/src/services/effective-limits.ts` exposes `resolveEffectiveLimits(sub, now)`: plan base (by planCode and pricingBasis) x licence count where per-licence, then the existing nullable per-subscription overrides, then a hook list of boosts (empty here; PLAN-pricing-coupons.md and the large-machine passes register into it). Every caller of getLimitsForPlan in the account server moves to it.
4. **COMMUNITY floor.** storageQuotaBytes 0, backup stores 1 (`home` only, customer S3), copy says "Registered (free)".
5. **Gate.** check-pricing-consistency also checks prices against PLAN_PRICING, the new dimensions against the English pricing copy and the docs table, and that no locale's `technicalSummary.values` contradicts PLAN_LIMITS.

## Tasks

- [ ] PM1 [writer] shared: the Design 1 dimensions and the R4-R8 values in constants.ts and types.ts, PLAN_PRICING derived per Design 2, unit tests pinning every number of R3-R8 (controls first: an unknown plan still resolves to COMMUNITY).
  Accept: `npm run build -w packages/shared` rc 0 and `cd packages/shared && npx vitest run src/subscription` rc 0
- [ ] PM2 [writer] account: effective-limits.ts per Design 3 with its unit test (plan base, per-licence scaling, override precedence, an empty boost list), every getLimitsForPlan caller in private/account/src moved to it, BACKUP_STORE_LIMITS.COMMUNITY 1.
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/unit/effective-limits.test.ts` rc 0, and `grep -rn "getLimitsForPlan(" private/account/src --include=*.ts | grep -v effective-limits` prints nothing
- [ ] PM4 [writer] gate and docs: check-pricing-consistency per Design 5 with a planted control per new rule; the English docs table in subscription-licensing.md updated to R1-R8.
  Accept: `npx tsx scripts/gates/check-pricing-consistency.ts` rc 0 on the tree and rc 1 on each planted control
- [ ] LP-bench [live] Deploy the branch's account worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after PM1 and PM2 land.
  Accept: live-proof bench account-smoke

## Risks

- A COMMUNITY account with hosted backups today loses its quota at R2; the 30-day restore-only window of PLAN-pricing-billing-upgrade.md is the cure, so PM2's quota change ships no earlier than that plan's BU6, or with a one-off notice if it must.

## Outcome
