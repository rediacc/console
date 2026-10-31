# Review 328cc76f: fix(ci): the 45 pytest reds after the history rewrite and the pytest 9.2.0 refresh

Commit: 328cc76f57af4a2a088adddbdef040a97eef6ff7
Repo: console
Branch: 1023-1
Parent: 43b7519975ea12e29ca761cab0b3aabca8655d57
Patch-Id: 05a3524abf543ca03568cf313277458e0fd9a9f4
Reviewed-At: 2026-10-31T12:24:49Z
Model: claude-haiku-5-5
Cost: $0.0131 USD, 1 call(s), 63.1s
Diff: 221504 bytes, 20 files, truncated: yes
Unreviewed: .ci/config/gate-costs.json, .ci/rediacc_ci/tests/fixtures/budget_drift/20261013.json
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Test, CI-config and gate changes only; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 79702fd28124f06c

## Findings

### 328cc76f.1 [medium] conftest.py:28
Anchor: in-diff
Claim: The rebind plugin and its only control test are deleted on the strength of pytest 9.2.0 binding fixtures to every collector, but this diff adds no pytest pin. If CI installs an older pytest, `gates/x.py tests/y.py gates/z.py` orders fail with "fixture 'gate' not found" and no test in the tree catches it, since the selftest at check_pytest.py:650 checks only path strings.
Resolution: open

### 328cc76f.2 [low] .ci/rediacc_ci/tests/test_ops_cf_family.py:787
Anchor: in-diff
Claim: The hint_delta mapping rewrites the port's `--config eu-bench repo create` hint back to the retired bash's `--config bench repo create` before comparing, so test_deploy_bench_matches_bash passes for any port hint that appears once; the corrected config name is never asserted directly.
Resolution: open
