# Review a6fcf5c6: test: fix the four pytest reds of Console CI run 39177571049, each an environment the local run did not have

Commit: a6fcf5c69eb4876accbb79fb29f98adccbaf9bd9
Repo: console
Branch: 1008-1
Parent: ce4c69ef9839caef150e9c59904ed03b4f0beb86
Patch-Id: 753d8165a2271ed81911f5266673022cc0654f8e
Reviewed-At: 2026-10-19T00:22:59Z
Model: claude-haiku-5-5
Cost: $0.0070 USD, 1 call(s), 47.9s
Diff: 18866 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only changes that fix CI-environment reds; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 7df42a25e6cc795d

## Findings

### a6fcf5c6.1 [medium] .claude/rediacc_hooks/tests/test_bash_semantics.py:3325
Anchor: in-diff
Claim: The skip gate in _curl_takes_long_equals probes `--user-agent=probe`, not the `--user=bob` form that test_a_curl_long_equals_value_matches_real_curl runs and that the commit reproduced as refused on curl 8.5. On a curl that accepts `--user-agent=` but refuses `--user=`, the probe returns True, the test runs, and it fails on the same red CI condition the commit is meant to fix.
Resolution: fixed 4ca8852631d8d6298f67fc0d5b79061e86cbc397 | d778be9d 2026-10-19T00:36:49Z

### a6fcf5c6.2 [low] .ci/rediacc_ci/tests/gates/test_gate_plan_folders.py:540
Anchor: in-diff
Claim: The expectation is `citable_token(shas["copy"], shas["copy"][: max(len(landed), 7)])`, but the commit message states the rule as `copy[:len(landed)]`. The two agree only while len(landed) is at least 7, which the diff does not show. The unexplained floor of 7 means the test no longer mirrors the gate's stated rule exactly.
Resolution: not-a-bug | .ci/rediacc_ci/quality/plan_lifecycle.py:967 the gate spells the copy at width max(len(tok), 7), and the test mirrors that exact expression | d778be9d 2026-10-19T00:34:06Z

### a6fcf5c6.3 [low] .claude/rediacc_hooks/tests/test_bash_semantics.py:2361
Anchor: in-diff
Claim: The CDPATH `cd -` row is skipped with pytest.skip rather than run, so on a bash that fails the probe the row contributes no pass. If the CI gate counts skips as not passing, as the file header says it does for xfail, the gate can stay red on the same host.
Resolution: not-a-bug | .ci/rediacc_ci/check_pytest.py:346 a skip whose message carries CANNOT RUN ( is admitted as declared cannot-run, not counted against the gate | d778be9d 2026-10-19T00:34:07Z
