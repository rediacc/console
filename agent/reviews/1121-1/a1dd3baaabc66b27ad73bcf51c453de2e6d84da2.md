# Review a1dd3baa: fix(account): reconcile writes the refund row before crediting the ledger

Commit: a1dd3baaabc66b27ad73bcf51c453de2e6d84da2
Repo: private/account
Branch: 1121-1
Parent: 611e2015eaedfda3a65f39be09f225e474d26918
Patch-Id: 5f0e48544d559afebbf823cade502481d86f638a
Reviewed-At: 2026-11-26T03:17:11Z
Model: claude-haiku-5-5
Cost: $0.0026 USD, 1 call(s), 16.9s
Diff: 4478 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Reorders refund writes to fix a double-credit path in reconcile; no user-facing feature.
Dropped: 0
Body-Sig: 6ccde210f0dd38fe

## Findings

### a1dd3baa.1 [high] src/services/ai-reconcile.service.ts:389
Anchor: in-diff
Claim: The commit comment says a failure can only miss a refund and never credit twice, but when adjustLot throws after the ledger already applied the credit (e.g. a timeout after commit), the catch deletes the marker row, so the next nightly run credits the same reservation again.
Class: doc-contradicts-code
Resolution: fixed 37d92106a7cbba839e14850d254b6e85ec1b3d10 | d778be9d 2026-11-26T03:24:39Z

### a1dd3baa.2 [medium] src/services/ai-reconcile.service.ts:389
Anchor: in-diff
Claim: The delete in the adjustLot catch block sits outside any try, so if the delete itself fails the error escapes refund() instead of returning 'failed' as the other error paths do.
Class: other
Resolution: open

### a1dd3baa.3 [medium] src/services/ai-reconcile.service.ts:396
Anchor: in-diff
Claim: The partial-credit branch (applied > 0 and applied !== credits) rewrites the row's credits via an unguarded update, and no test exercises it, so a partial adjustLot result is untested; if this update fails after the credit applied, refund() rejects and the row keeps the full requested amount.
Class: missing-control-test
Resolution: open

### a1dd3baa.4 [low] tests/integration/ai-reconcile.test.ts:233
Anchor: in-diff
Claim: The new test only covers the success path (row present when adjustLot runs); the new delete-on-throw and delete-on-zero branches have no test asserting the row is removed.
Class: missing-control-test
Resolution: open
