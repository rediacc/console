# PLAN: FREE issuance rows carry no IP data; the keyed hash lives only in the 72-hour counter
Status: executing
Owner: d778be9d
Updated: 2026-10-30
Epic: 9f92c43e (worklist #6a9f26f8)
Priority: P1 -- the operator ruling for PLAN-free-license is "IP hash only, purged after 72 h", and every FREE issuance row keeps the hash with no end date
Depends-On: no-dep -- the column, its write site, its test and the privacy text change inside this plan
Owns: agent/plans/PLAN-drop-free-license-ip-prefix-hash.md, private/account/drizzle/0072_free_license_drop_issuance_ip_hash.sql, private/account/drizzle/meta/**, private/account/src/db/schema.ts (the freeLicenseIssuances table only), private/account/src/services/free-license.service.ts, private/account/tests/integration/free-license.test.ts, packages/www/src/i18n/translations/*.json (the freeLicenseData subsection only), packages/www/src/i18n/translations/.translation-hashes.json, packages/www/src/i18n/translations/.naturalized-hashes.json
Concurrency: parallel -- no other live plan owns these files
Live-Proof: bench -- the account worker and its D1 migration deploy to bench first

## Context (anchors checked 2026-10-30)
- `free_license_issuances.ip_prefix_hash` is `NOT NULL` (private/account/src/db/schema.ts:1770, created by private/account/drizzle/0071_free_license.sql:7). The issuance insert writes it (private/account/src/services/free-license.service.ts:250). Nothing reads it: every IP bound is enforced against `free_license_ip_window` (private/account/src/services/free-license.service.ts:254, :318).
- Only `free_license_ip_window` rows are purged after 72 hours (`purgeExpiredIpWindowIn`, private/account/src/services/free-license.service.ts:547). An issuance row and its hash live until the row is removed, which nothing schedules.
- The privacy text (packages/www/src/i18n/translations/en.json, pages.privacyPolicy...freeLicenseData) says "the licence record keeps only the hash" and gives no retention for it (review 51934069.2).
- Migration 0071 is deployed to bench (ca59a4bd), so the fix is a new migration, not an edit of 0071. No index covers the column (private/account/src/db/schema.ts:1783-1785), so SQLite's `ALTER TABLE ... DROP COLUMN` applies.

## Decision
Drop the column. The hash is needed only to count requests per address inside the 72-hour window, which the window table already does. Clean break: no backfill, no nulling step.

## Boxes
- [x] A1 Migration `0072_free_license_drop_issuance_ip_hash.sql`: `ALTER TABLE free_license_issuances DROP COLUMN ip_prefix_hash;`, with the drizzle journal entry the repo's migration tooling expects (match how 0071 was added). Accept: `cd private/account && npx vitest run tests/integration/free-license.test.ts` (the in-memory DB applies every migration)
    (ticked) 2026-10-30T23:09:40Z by d778be9d: commit:8c805c92 private/account/drizzle/0072_free_license_drop_issuance_ip_hash.sql:4; migration 0072 drops ip_prefix_hash (account d69b1a0e); free-license suites 97 passed. DEPS-WAIVED: the box's code and acceptance do not depend on the open prerequisite plans
- [x] A2 Remove `ipPrefixHash` from `freeLicenseIssuances` in private/account/src/db/schema.ts and from the issuance insert in private/account/src/services/free-license.service.ts; the window insert keeps its hash. Accept: `cd private/account && npx tsc --noEmit -p tsconfig.json`
    (ticked) 2026-10-30T23:09:43Z by d778be9d: commit:8c805c92 private/account/src/db/schema.ts:1764; column and event field removed (account d69b1a0e); account tsc rc 0. DEPS-WAIVED: the box's code and acceptance do not depend on the open prerequisite plans
- [x] T1 A test in private/account/tests/integration/free-license.test.ts: after an issuance, the `free_license_issuances` table has no column whose name contains `ip` (PRAGMA table_info), and the issued row's values contain neither the requester address nor its hash; after `purgeExpiredIpWindow` at issuedAt + 72 h + 1 s, no table holds the hash. The test fails on the tree before A1/A2. Accept: `cd private/account && npx vitest run tests/integration/free-license.test.ts tests/integration/license-renew.test.ts tests/integration/license.test.ts`
    (ticked) 2026-10-30T23:09:47Z by d778be9d: commit:8c805c92 private/account/tests/integration/free-license.test.ts:1; the no-IP-data test failed on the old schema and passes (account d69b1a0e). DEPS-WAIVED: the box's code and acceptance do not depend on the open prerequisite plans
- [x] P1 Privacy text: the freeLicenseData content says the keyed hash is kept only in the per-address counter and deleted after 72 hours, and that the licence record holds no IP data; in all 13 locales, naturalized, then `npm run i18n:generate-hashes` and the ledger stamp the earlier privacy keys used. Accept: `npm run check:i18n && npm run check:ci-i18n-ledger-growth`
    (ticked) 2026-10-30T23:09:50Z by d778be9d: commit:8c805c92 packages/www/src/i18n/translations/en.json:1; privacy text in 13 locales; check:i18n and check:ci-i18n-ledger-growth rc 0. DEPS-WAIVED: the box's code and acceptance do not depend on the open prerequisite plans
- Deploy order (review 302bff18.1): the deploy applies D1 migrations before it publishes the new worker, so between the two the old worker's FREE issuance insert names the dropped column and fails. The window is the seconds between the migration and the publish, and there are no customers yet (operator order 2026-10-28), so the plan accepts it rather than splitting the change into two releases.

- [ ] L1 [live] Bench: the account deploy applies 0072 (`deploy_bench`), and `wrangler d1 execute` (read-only `PRAGMA table_info(free_license_issuances)`) on the bench D1 shows no ip_prefix_hash. Accept: the PRAGMA output recorded here

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof, after this plan's bench-deployable boxes land.
  Accept: live-proof bench account-smoke
