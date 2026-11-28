# Review f5ecc88d: fix(ci): the budget-freshness carry names the four exact gate-costs keys, not a wildcard

Commit: f5ecc88d63fa307bc2a4cdf4ff86f45c4cfa217f
Repo: console
Branch: 1121-1
Parent: 3c62df196246c2c08a8ccf5b2dced01716c2d189
Patch-Id: 27978c8dd6a7f44d8d1e9dc086deb0a61f6c727c
Reviewed-At: 2026-11-28T12:09:36Z
Model: claude-haiku-5-5
Cost: $0.0014 USD, 1 call(s), 9.0s
Diff: 2924 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only allowlist change in CI config; no user-facing behaviour.
Dropped: 0
Body-Sig: 5e8378a3cfe198a7

## Findings

### f5ecc88d.1 [low] .ci/rediacc_ci/tests/test_ci_freshness.py:655
Anchor: in-diff
Claim: The new gate-costs prefixes admit any key beginning with 'gate-costs:drift:' or 'gate-costs:unmeasured:', so the test no longer pins the four keys the commit message names; a future carried entry for an unrelated gate-costs key would pass this test.
Class: missing-control-test
Resolution: not-a-bug | .ci/rediacc_ci/tests/test_ci_freshness.py:643 | d778be9d 2026-11-28T12:09:58Z
