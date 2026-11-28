# PLAN: pricing user and repository caps: organization members capped per plan, original repositories counted and capped at licence issuance

Status: approved -- operator /ask 2026-11-27 in session e08d0be9 (pricing redesign), rulings under ## Rulings
Depends-On: PLAN-pricing-plan-model.md -- PM1 adds `maxUsers` and `maxRepositories`, PM2 the resolver this plan reads them through
Owner: e08d0be9 (author; d778be9d implements after promotion)
Updated: 2026-11-27
First-Seen: 2026-11-27
Priority: P2 -- the free Professional offer is only safe to open once its 10-user and 25-repository caps are enforced
Concurrency: parallel -- private/account/src/services/subscription.service.ts (issueRepoLicense and issueRepoLicenseBatch only) is shared with PLAN-pricing-cpu-ceiling.md and PLAN-pricing-billing-upgrade.md, and was touched today by the issuance-actor change; block_plan_concurrency serializes writers on it
Owns: agent/plans/PLAN-pricing-seat-repo-caps.md, private/account (gitlink bump only), private/account/src/services/org.service.ts (addMember, createInvitation, acceptInvitation only), private/account/src/services/subscription.service.ts (issueRepoLicense and issueRepoLicenseBatch only), private/account/src/services/repository-count.service.ts (new), private/account/drizzle/*_subscription_repositories.sql (new), private/account/src/db/schema.ts (the new table only), private/account/src/errors.ts (two new codes only), private/account/web/src/pages/Team.tsx, private/account/web/src/i18n/locales/*/team.json, private/account/tests/integration/seat-repo-caps.test.ts (new), packages/cli/src/i18n/locales/*/cli.json (the two new error hints only)
Live-Proof: bench -- org membership and licence issuance run on the account worker; the receipt is taken on the eu bench after deploy_bench

## Rulings (operator /ask, 2026-11-27, session e08d0be9)

- R1. Users: free Professional 10, paid Professional 25, Business and Enterprise unlimited; COMMUNITY and FREE 1.
- R2. Repositories count ORIGINAL repositories only (a fork, licensed 7 days, never counts): free Professional 25, Professional 100 per floating licence, Business 250 per floating licence, Enterprise per quote.
- R3. Limits are explicit everywhere; "unlimited repositories" is gone from the paid tiers.
- R4. A cap refuses only NEW work (a new member, a new original repository); existing members and running repositories are never removed or stopped.

## Finding (verified 2026-11-27)

- No user, seat or repository-count limit exists in account, shared or renet.
- Members join an org through private/account/src/services/org.service.ts:375 (addMember), :853 (createInvitation) and :931 (acceptInvitation).
- Repo licences are issued by private/account/src/services/subscription.service.ts:852 (issueRepoLicense) and :998 (issueRepoLicenseBatch); the monthly issuance slot is claimed at :1840.
- The issuance ledger (private/account/src/db/schema.ts, `issuance_ledger`) records repositoryGuid but not the grand GUID, so it cannot tell an original from a fork; the monthly slot table does carry `grandGuid`, but resets every month.

## Design

1. **Members.** createInvitation and addMember count active members plus pending invitations against `resolveEffectiveLimits(sub).maxUsers` and refuse with `ORG_MEMBER_LIMIT_REACHED` (403) naming the cap, the plan and the upgrade path. acceptInvitation re-checks, so a race of two invitations cannot pass the cap.
2. **Repositories.** A new table `subscription_repositories` (subscription_id, grand_guid, first_issued_at, last_issued_at, retired_at), upserted on every issuance whose repositoryGuid equals its grandGuid. The count is rows not retired whose last issuance is inside the licence hard-expiry window. A NEW original past the cap is refused with `REPOSITORY_LIMIT_REACHED` (403); re-issuing or renewing an existing original is never refused (R4).
3. **Messages.** The portal Team page shows `members n / cap`; the CLI prints one hint line for each new code naming the cap and `rdc subscription upgrade` (the verb lands with PLAN-pricing-billing-upgrade.md; until then the hint names the portal Subscription page).

## Tasks

- [ ] SR1 [writer] account members: Design 1 in org.service.ts with the error code; integration tests, controls first (a member below the cap joins; an existing member is never removed when the plan drops).
  Accept: `cd private/account && npx tsc --noEmit && npx vitest run tests/integration/seat-repo-caps.test.ts` rc 0
- [ ] SR2 [writer] account repositories: the migration, the table, repository-count.service.ts and the issuance check per Design 2; tests, controls first (a fork never counts; renewal of an existing original past the cap succeeds; the 26th original on free Professional is refused).
  Accept: `cd private/account && npx vitest run tests/integration/seat-repo-caps.test.ts` rc 0
- [ ] SR3 [writer] portal and CLI copy per Design 3, English first, the 12 other locales through the i18n pipeline.
  Accept: `cd private/account/web && npx tsc --noEmit` rc 0 and `npm run check:ci-i18n-completeness` rc 0
- [ ] LP-bench [live] Deploy the branch's account worker to the eu bench (`PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_bench --region eu`) after SR1 and SR2 land.
  Accept: live-proof bench account-smoke
- [ ] SR-L1 [live] eu bench: on a free-Professional test org, invite up to the cap and one more (refused), and license originals up to a temporarily lowered cap and one more (refused) while a fork still succeeds.
  Accept: the transcripts with their rc recorded under `## Outcome`

## Outcome
