# Review 8e9dee20: fix(cli): the restore licence sizing falls back to the floor, and a failed cleanup keeps the real error

Commit: 8e9dee204cbcaa25a33ed46a1fa4ac658eab9c5d
Repo: console
Branch: 1023-1
Parent: 3731780657a9ef22f975d4fd8a77cadf0efd5b57
Patch-Id: 29a36c57a6290292510bd07975339b9292e9eb65
Reviewed-At: 2026-11-01T07:18:25Z
Model: claude-haiku-5-5
Cost: $0.0019 USD, 1 call(s), 18.1s
Diff: 2994 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Restore no longer throws when the source cannot be sized or the rollback fails, which fixes error handling in the restore path; no new capability.
Dropped: 0
Body-Sig: 67edf0a0c152c5e8

## Findings

### 8e9dee20.1 [medium] packages/cli/src/commands/backup.ts:388
Anchor: in-diff
Claim: The rollback's `.catch(() => undefined)` discards a failed removeRepository with no warning, so the stale registration stays and the next retry hits target-exists with no hint about the leftover record.
Resolution: open

### 8e9dee20.2 [medium] packages/cli/src/commands/backup.ts:490
Anchor: in-diff
Claim: When measureRepoSizeGb throws for any reason (including unexpected errors, not only unreachable sources), the catch returns 1 GB, so a source image larger than 1 GB gets an under-sized licence and the restore can fail partway through on the datastore.
Resolution: open

### 8e9dee20.3 [medium] packages/cli/src/commands/backup.ts:474
Anchor: in-diff
Claim: The acquire catch turns any failure from machineConnections.acquire into a 1 GB request, so a connection or auth problem that the user should see is now downgraded to a warning and the licence is sized from the floor.
Resolution: open

### 8e9dee20.4 [low] packages/cli/src/commands/backup.ts:463
Anchor: in-diff
Claim: The new fallback branches in sourceImageSizeGb are not covered by any test in this diff; the cited passing suites are existing tests and do not exercise the unreachable or unmeasurable paths.
Resolution: open
