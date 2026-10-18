# Review 7ed6dfe6: fix(migration): --delete-old refuses its sweep while a row still names an unscoped key

Commit: 7ed6dfe63242ced4fbbefe7e77c72ff7a82172ad
Repo: private/account
Branch: 1008-1
Parent: d2728c8edc94fa3a2202a45716e72fbd1258cc2b
Patch-Id: 0ce8350adb3b87a1b67744c9258b07f3c619a03c
Reviewed-At: 2026-10-18T15:32:31Z
Model: claude-haiku-5-5
Cost: $0.0044 USD, 1 call(s), 30.5s
Diff: 8388 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Internal migration script fix that adds a guard against deleting blobs during an active old-layout write; no user-facing capability added.
Dropped: 0
Body-Sig: 3da6fe785bc0c883

## Findings

### 7ed6dfe6.1 [medium] scripts/lib/config-blob-migration.ts:407
Anchor: in-diff
Claim: The guard only detects an old-layout writer whose row already exists at the second read. A writer that puts its blob before listKeys() and inserts its row after the second read still has that blob deleted at line 418, so the commit's claim that the guard backs the precondition is overstated.
Resolution: open

### 7ed6dfe6.2 [low] scripts/lib/config-blob-migration.ts:407
Anchor: in-diff
Claim: The refusal assumes that after a clean pass every row is store-scoped, which the diff does not establish. If any unscoped row legitimately persists after a clean pass, the sweep is refused on every run and the report blames an old-layout worker that may not exist.
Resolution: open

### 7ed6dfe6.3 [low] scripts/lib/config-blob-migration.ts:459
Anchor: in-diff
Claim: legacyWriterRows is computed on every clean pass, but the REFUSED line is printed only when options.deleteOld is set. Without --delete-old a non-zero count is silent in the text report.
Resolution: open

### 7ed6dfe6.4 [low] tests/integration/config-blob-migration.test.ts:582
Anchor: in-diff
Claim: The shared-key test no longer asserts that store A's archived legacy key is swept (the old unreferencedLegacyDeleted === 1 expectation was removed), so the positive sweep path is no longer covered in that scenario.
Resolution: open
