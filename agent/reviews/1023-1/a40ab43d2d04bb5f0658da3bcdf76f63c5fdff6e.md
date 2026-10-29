# Review a40ab43d: fix(backup): a supersede that loses to a renewal logs supersede_ignored (renewed), not a release (a217a036 review)

Commit: a40ab43d2d04bb5f0658da3bcdf76f63c5fdff6e
Repo: private/account
Branch: 1023-1
Parent: a217a0364c5e0f6158332eca0ad9c3228bf73ea7
Patch-Id: 75b3445c8d502df33378e0eb346d1db1ceb0a812
Reviewed-At: 2026-10-29T10:31:45Z
Model: claude-haiku-5-5
Cost: $0.0018 USD, 1 call(s), 14.4s
Diff: 4807 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Corrects the audit event recorded when a supersede loses to a renewal; no new capability, internal behaviour fix with test.
Dropped: 0
Body-Sig: 2eb27b844cbfb294

## Findings

### a40ab43d.1 [medium] src/services/backup-storage.service.ts:874
Anchor: in-diff
Claim: A zero-row delete is logged as reason 'renewed' whenever removed.length === 0, but it also happens when a concurrent supersede or GC already deleted the same lease, so the audit records a renewal that never occurred.
Resolution: fixed d124c0d68d53dd19a009e357baba73e7fef97f79 | d778be9d 2026-10-29T10:34:21Z

### a40ab43d.2 [low] src/services/backup-storage.service.ts:867
Anchor: in-diff
Claim: markReconcileDue still runs before the delete, so on the renewal-wins path the lineage is flagged reconcile-due even though no lease was released and the early return skips any follow-up.
Resolution: not-a-bug | src/services/backup-storage.service.ts:867 marks before the delete on purpose (a crash between the two keeps the evidence); a due mark with a live lease is harmless: the inline and nightly re-bills skip a lineage with a live lease and the next applied swap clears the mark | d778be9d 2026-10-29T10:34:22Z
