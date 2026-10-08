# Review a18deccd: fix(gates): requireSubmodule treats any set, non-false CI value as CI

Commit: a18deccd3cfd9be4dcd048b27ca3a57cb5cbe290
Repo: console
Branch: 1008-1
Parent: 92b1e7f1ae7e4e763a034d10bd2c669940826921
Patch-Id: 06e6ab3403735a49e171b46b8247aed48ad42d44
Reviewed-At: 2026-10-08T06:15:58Z
Model: claude-haiku-5-5
Cost: $0.0017 USD, 1 call(s), 13.0s
Diff: 1488 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Internal CI gate helper in scripts/; no user-facing product change.
Dropped: 0
Body-Sig: 1e7b29cdd330da9e

## Findings

### a18deccd.1 [medium] scripts/lib/submodule-presence.ts:56
Anchor: in-diff
Claim: The old doc line `/** True on a CI runner: CI=true or GITHUB_ACTIONS=true, the literal string. */` is kept above the new JSDoc, and it now states the wrong behaviour because inCi no longer requires the literal 'true'.
Resolution: open

### a18deccd.2 [medium] scripts/lib/submodule-presence.ts:61
Anchor: in-diff
Claim: The changed inCi semantics (CI=1, any non-off value, GITHUB_ACTIONS widened the same way) are not covered by any test in this diff, so a regression back to literal-'true' matching would pass the gate unnoticed; the verification was manual shell runs only.
Resolution: open

### a18deccd.3 [low] scripts/lib/submodule-presence.ts:63
Anchor: in-diff
Claim: The off-list regex is anchored with no trimming, so a value such as ' false' or '0\n' with surrounding whitespace is treated as CI-on, which is a surprising edge but fails closed.
Resolution: open
