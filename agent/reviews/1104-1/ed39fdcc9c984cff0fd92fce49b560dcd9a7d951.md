# Review ed39fdcc: test(ci): the licence-expiry drill's rerun catches a second owner mail

Commit: ed39fdcc9c984cff0fd92fce49b560dcd9a7d951
Repo: console
Branch: 1104-1
Parent: d956907d706bb924a6cf30bf79c60ce03caac1e9
Patch-Id: f40e2063c93d68bb678dada09263e6c57562ff6a
Reviewed-At: 2026-11-12T23:26:13Z
Model: claude-haiku-5-5
Cost: $0.0047 USD, 1 call(s), 24.3s
Diff: 3308 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only change in the CI drill's fake; no user-facing behaviour changes.
Dropped: 0
Body-Sig: f93da0f6345bbdf3

## Findings

### ed39fdcc.1 [low] .ci/rediacc_ci/tests/test_ops_licence_expiry_drill.py:258
Anchor: in-diff
Claim: The new test asserts only that 'STEP 10 rerun rc=1' appears, not the owner-mail recount's own failure text (the sibling test checks 'want 0'), so it would still pass if the rerun failed for an unrelated reason in the same step.
Class: missing-control-test
Resolution: fixed 2bd4e4002b293420dff5019d2c00321d472406a3 | d778be9d 2026-11-12T23:27:37Z
