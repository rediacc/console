# Review 3fabea62: feat(backup): POST /backups/verify level chunks rehashes a lineage's stored chunks and names missing or corrupt ones (PLAN-backup-program K11)

Commit: 3fabea6275bcf0ecec46b1871c0afe53bc2273ef
Repo: private/account
Branch: 1023-1
Parent: 8237ac0d73e984713969c54b163b35b8feac7602
Patch-Id: 2c8fe308de8aaf627c3b325d1804aa8961346c95
Reviewed-At: 2026-10-29T06:54:22Z
Model: claude-haiku-5-5
Cost: $0.0069 USD, 1 call(s), 38.1s
Diff: 26992 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds a new optional level=chunks request mode and a chunks reply to POST /backups/verify. The ledger reply shape is unchanged for existing callers, except the six totals are now typed optional.
Dropped: 0
Body-Sig: 6face9ae7bdb6b00

## Findings

### 3fabea62.1 [medium] src/services/backup-gc.service.ts:395
Anchor: in-diff
Claim: The old doc comment 'One lineage whose doomed run could not be collapsed, and why.' now sits above the new LineageChunkVerify interface, and BackupCollapseDeferral (which it described) lost it. The comment states the wrong behaviour for the type it now documents.
Resolution: fixed 247da80733f9fc629e4188eeedbd68adfb634d4e | d778be9d 2026-10-29T18:56:41Z

### 3fabea62.2 [medium] src/services/backup-gc.service.ts:2662
Anchor: in-diff
Claim: The 409 branch for an unreadable manifest in verifyLineageChunks is new behaviour, but no case in tests/integration/backup-verify-chunks.test.ts sends a lineage whose manifest cannot be read, so a regression to the 404 or 200 path would pass the suite.
Resolution: fixed 247da80733f9fc629e4188eeedbd68adfb634d4e | d778be9d 2026-10-29T18:56:42Z

### 3fabea62.3 [low] src/services/backup-gc.service.ts:2664
Anchor: in-diff
Claim: verifyLineageChunks computes `rest` by filtering and slicing `hashes` assuming they are sorted, but the diff never sorts them and the commit says 'sorted'. If lineageReferencedHashes returns another order, nextAfter can skip hashes or repeat them across pages. The sort guarantee lives outside this diff, so this is unverified here.
Resolution: not-a-bug | private/account/src/services/backup-gc.service.ts:1 lineageReferencedHashes returns [...referenced].sort(), and the existing nextAfter paging test seeds the manifest unsorted | d778be9d 2026-10-29T18:56:42Z

### 3fabea62.4 [low] src/routes/backups.ts:394
Anchor: in-diff
Claim: The chunks level makes up to BACKUP_VERIFY_CHUNKS_MAX store GETs plus SHA-256 per request under a backup:read token, and this hunk adds no rateLimit call on the route. If none is applied where the route is mounted, a read-scoped token can drive that load repeatedly.
Resolution: fixed 247da80733f9fc629e4188eeedbd68adfb634d4e | d778be9d 2026-10-29T18:56:42Z
