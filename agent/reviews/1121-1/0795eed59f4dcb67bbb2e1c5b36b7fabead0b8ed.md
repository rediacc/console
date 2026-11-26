# Review 0795eed5: fix(account): console runs read through one visibility rule

Commit: 0795eed59f4dcb67bbb2e1c5b36b7fabead0b8ed
Repo: private/account
Branch: 1121-1
Parent: e322a2426d93ba4f18ed4078168d186ea8870dcc
Patch-Id: ceb4a068576f9f3c84057c3a89ab1ff3b0f456da
Reviewed-At: 2026-11-24T09:32:36Z
Model: claude-haiku-5-5
Cost: $0.0061 USD, 1 call(s), 31.5s
Diff: 26033 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes run visibility leak on GET /runs/:id and list filters, plus history masking and ordering bugs; no new capability.
Dropped: 0
Body-Sig: bcfe49472996aa80

## Findings

### 0795eed5.1 [low] src/services/console-run.service.ts:139
Anchor: in-diff
Claim: applyEvent now throws a RangeError for an oversized tail instead of truncating it; the route tests in console-run-routes.test.ts add no oversized-tail case, so the HTTP status the POST /runs/events caller gets for this refusal is untested.
Class: missing-control-test
Resolution: fixed 180a355b90ba5767166023ea17f4ef4e66c6a585 | d778be9d 2026-11-26T16:50:51Z
