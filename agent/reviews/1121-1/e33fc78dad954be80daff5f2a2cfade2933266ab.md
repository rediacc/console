# Review e33fc78d: test(ci): the rsync release test asserts no route outside the GitHub API is asked

Commit: e33fc78dad954be80daff5f2a2cfade2933266ab
Repo: console
Branch: 1121-1
Parent: 4b7dd8db696757f5444bb7ed384474da114bcf97
Patch-Id: ae612e2c5a57b32c88171945357da6fa0371d2f5
Reviewed-At: 2026-11-22T14:30:45Z
Model: claude-haiku-5-5
Cost: $0.0015 USD, 1 call(s), 10.4s
Diff: 1662 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only change in the CI gate suite; no user-facing behaviour changed.
Dropped: 0
Body-Sig: 9da7a1e71a2083e9

## Findings

### e33fc78d.1 [low] .ci/rediacc_ci/tests/gates/test_gate_embed_asset_freshness.py:336
Anchor: in-diff
Claim: The new path check only sees requests that reach this one stub, so a rsync pin pointed at another host would never be recorded and the test would still pass, even though the unchanged docstring on line 328 says no host but api.github.com is asked.
Class: missing-control-test
Resolution: fixed ed742c5903fcb456551da272f0910952fcde2cd7 | ace763dd 2026-11-22T14:35:36Z
