# Review fedbe1e6: fix(ci-diagnose): quote only test failures and read cut-off test logs as infra

Commit: fedbe1e6a58d0e978a21c74e2bafd89f43ecb1d6
Repo: console
Branch: 1104-1
Parent: 5c6358b3a125ecb8e0a42fc16f4c8b4f29305613
Patch-Id: 02cdda2ae8d922bebf22ea71f92ac5510925b51a
Reviewed-At: 2026-11-16T04:15:34Z
Model: claude-haiku-5-5
Cost: $0.0039 USD, 1 call(s), 24.4s
Diff: 10602 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Narrows test-failure excerpts and reclassifies cut-off Go logs in CI diagnose tooling; a bug fix with no user-facing API change.
Dropped: 0
Body-Sig: f717652b06aeb2b9

## Findings

### fedbe1e6.1 [medium] .ci/rediacc_ci/ci/ci_diagnose.py:1282
Anchor: in-diff
Claim: render() recomputes the test verdict from the excerpt lines only (`_has_test_verdict(ex)`), not from the full log that classify() and excerpt() used, so when the log has a `--- PASS`/`FAIL`/`ok` verdict outside the excerpt, a `_test.go:<n>:` line with stall or 5xx text is treated as an infra hit and shown first in the summary.
Class: other
Resolution: fixed a6e0cf24a66e8822779daf68028187d922fd9209 | d778be9d 2026-11-16T04:34:02Z

### fedbe1e6.2 [low] .ci/rediacc_ci/ci/ci_diagnose.py:804
Anchor: in-diff
Claim: TEST_VERDICT_RE matches any body line beginning with `FAIL` or `PASS` followed by a word boundary (e.g. a gate line `FAIL: ...`), so a non-Go gate line can switch off the infra skip for a `_test.go:<n>:` line in the same step.
Class: other
Resolution: fixed a6e0cf24a66e8822779daf68028187d922fd9209 | d778be9d 2026-11-16T04:34:03Z
