# Review 4cbeb3ff: fix(backup): resolve --at inside each store a restore tries, and close review findings f9408f6b.2 and 1a0788d8

Commit: 4cbeb3ffcdc37fe0a3d7f0e5fc40d87cf201bf7b
Repo: console
Branch: 1104-1
Parent: 10eae6293b702b1a12bcaf53d6d4d8bb62891775
Patch-Id: 4031ffa5a6658fe7d41a55744e3680ccdf624d3b
Reviewed-At: 2026-11-07T16:30:14Z
Model: claude-haiku-5-5
Cost: $0.0123 USD, 1 call(s), 62.4s
Diff: 82546 bytes, 15 files, truncated: yes
Unreviewed: scripts/gates/check-backup-protocol-conformance.ts
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,ci why=Fixes restore/browse/download store fallback so the time resolves inside each store tried, plus a conformance gate and test parity; user-visible fix, no new capability.
Dropped: 0
Body-Sig: 35f48cf1f891c6a9

## Findings

### 4cbeb3ff.1 [medium] packages/cli/src/services/backup/backup-store-pick.ts:177
Anchor: in-diff
Claim: In resolveFrom, any resolve error with a numeric HTTP status (isAccountError) is thrown on the first store, so a 5xx from the first store's resolve aborts the restore without trying the next ranked store, although the same 5xx from an attempt (isStoreFailure) does fall back to the next store.
Resolution: open
