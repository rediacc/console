# Review e3e12fc9: feat(ci): fail check_pytest on a test over 10 s that the slow allowlist does not list

Commit: e3e12fc949dc9efcfacad567e3b07bbc241db2c3
Repo: console
Branch: 1104-1
Parent: bab2c5c8041efe57e7a28d2fe32f7a41fbcda2c7
Patch-Id: 9fc75c10ff709f2020ba849f36c9302269dc6814
Reviewed-At: 2026-11-17T21:25:54Z
Model: claude-haiku-5-5
Cost: $0.0039 USD, 1 call(s), 23.7s
Diff: 7815 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=CI gate wiring only; no product-facing behaviour change.
Dropped: 0
Body-Sig: 80ea7dd67d8ba699

## Findings

### e3e12fc9.1 [medium] .ci/rediacc_ci/check_pytest.py:1427
Anchor: in-diff
Claim: The slow_ratchet gate on the --shard path (line 1427) has no test: the new test file only calls check_pytest.main([]), so removing or breaking this call still leaves all four tests green. The impact path call (line 1578) is also untested, though the commit message says the wiring covers both.
Class: missing-control-test
Resolution: not-a-bug | .ci/rediacc_ci/tests/test_check_pytest_slow_wired.py:1 shard=True and impact=True cases cover both paths | d778be9d 2026-11-19T03:16:55Z

### e3e12fc9.2 [low] .ci/rediacc_ci/tests/test_check_pytest_slow_wired.py:5
Anchor: in-diff
Claim: The docstring says the planted defect reds only 'the first test', but the commit's own check shows two tests go red when slow_ratchet is stubbed to 0: the 11 s case and the no-junit case.
Class: doc-contradicts-code
Resolution: not-a-bug | .ci/rediacc_ci/tests/test_check_pytest_slow_wired.py:5 the docstring lists full, shard, impact and no-junit | d778be9d 2026-11-19T03:16:55Z
