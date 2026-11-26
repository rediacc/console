# Review af26b78d: fix(gates): check:ci-terms-version check 7 holds every archive's hero line to its registry date

Commit: af26b78dcfdc5ea6fa42cfaf6958ae7e58e7242b
Repo: console
Branch: 1121-1
Parent: ddd7e99e4befddecabe9e305e9732d5074383eee
Patch-Id: ad8fcf87c22c96f9d99bba284218cac20b28d29d
Reviewed-At: 2026-11-26T17:04:59Z
Model: claude-haiku-5-5
Cost: $0.0037 USD, 1 call(s), 16.7s
Diff: 16269 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Gate script change only; no user-facing behaviour.
Dropped: 0
Body-Sig: 962b64dc12e50689

## Findings

### af26b78d.1 [medium] scripts/gates/check-terms-version.ts:24
Anchor: in-diff
Claim: The header says check 7 fails when SUPERSEDED_ARCHIVES is not 'the frozen set of the three archives', but supersededRecordFindings only enforces a count of at most 3 and a pre-CHECK7_SINCE date, so replacing one exempted archive with a different pre-2026-11-26 archive produces no finding.
Class: doc-contradicts-code
Resolution: open
