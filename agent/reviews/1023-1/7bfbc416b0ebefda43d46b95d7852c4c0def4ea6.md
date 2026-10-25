# Review 7bfbc416: feat(backups): stream-scoped retention with plan limits, preview, orphan and purge, snapshot delete, chunk verification and the isolation suite (PLAN-backup-pro

Commit: 7bfbc416b0ebefda43d46b95d7852c4c0def4ea6
Repo: private/account
Branch: 1023-1
Parent: 262d97cbb41b5ef0e02d7e102f15254741f1862e
Patch-Id: 22f9deef4e119cb7daaff5841df6f56ea32e1a65
Reviewed-At: 2026-10-25T07:35:14Z
Model: claude-haiku-5-5
Cost: $0.0126 USD, 1 call(s), 49.3s
Diff: 199756 bytes, 23 files, truncated: yes
Unreviewed: src/services/backup-gc.service.ts, tests/integration/backup-policy-scope.test.ts, tests/integration/backup-server-ops.test.ts, web/src/data/study-content/mt6-backup.ts, web/src/lib/resource-options.ts
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature,docs why=Adds retention preview, snapshot delete, orphan and purge routes, stream-scoped retention with plan caps, and rate limiting on session mint; catalog and exam text also change.
Dropped: 0
Body-Sig: bd6692ccfdf2ab1f

## Findings

### 7bfbc416.1 [high] web/src/components/console/ResourceContext.tsx:62
Anchor: in-diff
Claim: The diff removes `storages` from ConsoleResources and EMPTY_RESOURCES, and the commit's own verification says tsc and the account suite are still red after it, so this commit ships a broken build until the matching change lands elsewhere.
Resolution: not-a-bug | 06ab0da0 the storages removal in ResourceContext.tsx was intended (the shared schema retired the family); the red build the finding describes came from the other storages references, which account 06ab0da0 removes: private/account tsc rc=0, account web tsc rc=0, config-sync 99 passed | d778be9d 2026-10-25T09:27:06Z

### 7bfbc416.2 [medium] src/services/backup-storage.service.ts:652
Anchor: in-diff
Claim: The comment says the quota check refuses 'before I/O is spent', but line 661 now calls estimateSubscriptionFreed before every over-quota throw, so each refused grant does store I/O first and the comment states the wrong behaviour.
Resolution: open

### 7bfbc416.3 [low] src/middleware/rate-limit.ts:157
Anchor: in-diff
Claim: The eviction runs only when the map holds 10,000 keys and deletes only expired windows, so when all 10,000 windows are still live the map grows past the cap with no eviction.
Resolution: open

### 7bfbc416.4 [low] src/routes/backups.ts:307
Anchor: in-diff
Claim: DELETE /backups/retention passes the raw `stream` query value straight to clearRetentionPolicy with no identifier check, while the S8 test claims separator refusal at every surface and never exercises this one.
Resolution: open
