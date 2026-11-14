# Review aa5a1fb3: test(cli): a failed license-write job is a thrown error and never an issued license

Commit: aa5a1fb33f8a06b6efd0bfc830a5bdbdc6c767ec
Repo: console
Branch: 1104-1
Parent: dc641881183584a84344c58174d06d2023aa79f7
Patch-Id: 47a54436c7c77939ea5464fd19199c5aad954728
Reviewed-At: 2026-11-04T18:13:49Z
Model: claude-haiku-5-5
Cost: $0.0011 USD, 1 call(s), 9.1s
Diff: 2047 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=none why=Test-only change with no source or user-facing behaviour change; it adds coverage for an existing failure path.
Dropped: 0
Body-Sig: 036bc13df0be458d

## Findings

### aa5a1fb3.1 [low] packages/cli/src/services/__tests__/license-batch-refresh.test.ts:187
Anchor: in-diff
Claim: The test name promises that a failed awaited license-write does not report the license as issued, but the assertions only check that the call rejects with the error text and that one license-write job was sent. Nothing checks that the 'issued' license from the mocked batch response is withheld from the caller or from storage, so a regression that stores the license before the write fails would still pass.
Resolution: not-a-bug | packages/cli/src/services/__tests__/license-batch-refresh.test.ts:216 the awaited license-write failure makes refreshRepoLicensesBatch reject, and the license-write job is the only storage path (asserted at line 217) | d778be9d 2026-11-06T21:33:33Z
