# Review 741cfed5: feat(cli): rsync version probe and SSH command exported for image transfers; the local-image state file and space preflight (PLAN-backup-local-image X1, S1)

Commit: 741cfed5dcb1d400acfc41ffd11f0a34fca7faee
Repo: console
Branch: 1023-1
Parent: 46f747e57b5af31cc0acd0838183ab2b15fe8586
Patch-Id: e7019954e6985011446a808e9c39aee8827247c3
Reviewed-At: 2026-10-29T12:49:00Z
Model: claude-haiku-5-5
Cost: $0.0095 USD, 1 call(s), 51.8s
Diff: 32985 bytes, 6 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=feature why=Internal helpers only: exported rsync helpers, a state file and a preflight module with no CLI command wired to them in this diff.
Dropped: 0
Body-Sig: 71d54c779c237bc9

## Findings

### 741cfed5.1 [medium] packages/cli/src/services/backup-image/state.ts:222
Anchor: in-diff
Claim: writeImageState ignores the return value of writeSync, so a short write (for example disk full mid-write) is still fsynced and renamed over the previous state file, leaving truncated JSON that readImageState cannot parse.
Resolution: fixed 59043d4db3a8fe8f82c23e9c3ec36d65e58617bb | d778be9d 2026-10-29T18:31:50Z

### 741cfed5.2 [medium] packages/cli/src/services/backup-image/state.ts:445
Anchor: in-diff
Claim: In acquireLocalLock, two processes that both read the same dead-pid lock can both unlink: the slower unlink deletes the lock the faster process just created, so both can hold the image lock; the unguarded unlinkSync also throws a raw ENOENT if the holder already removed the file.
Resolution: fixed 59043d4db3a8fe8f82c23e9c3ec36d65e58617bb | d778be9d 2026-10-29T18:31:51Z

### 741cfed5.3 [medium] packages/cli/src/services/backup-image/state.ts:418
Anchor: in-diff
Claim: tryCreateLock creates the lock with O_EXCL before writing its JSON, so a crash or short write in between leaves an empty lock that readLock returns as null, and every later run is refused as 'unreadable' until someone deletes the file by hand.
Resolution: fixed 59043d4db3a8fe8f82c23e9c3ec36d65e58617bb | d778be9d 2026-10-29T18:31:51Z

### 741cfed5.4 [low] packages/cli/src/services/backup-image/state.ts:220
Anchor: in-diff
Claim: If writeSync or fsyncSync throws inside writeImageState, the temp file opened at line 220 is left behind, because the unlink cleanup only covers the beforeRename and rename steps below it.
Resolution: fixed 59043d4db3a8fe8f82c23e9c3ec36d65e58617bb | d778be9d 2026-10-29T18:31:51Z

### 741cfed5.5 [low] packages/cli/src/services/backup-image/preflight.ts:29
Anchor: in-diff
Claim: probeSparse is documented to return a boolean, but openSync at line 29 is outside any try, so an unwritable or missing target directory makes it throw instead; no test covers that path.
Resolution: fixed 59043d4db3a8fe8f82c23e9c3ec36d65e58617bb | d778be9d 2026-10-29T18:31:52Z
