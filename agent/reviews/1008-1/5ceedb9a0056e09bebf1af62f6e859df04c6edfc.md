# Review 5ceedb9a: fix(ci): gate_costs reads the checkout's branch locally, so a pre-push run judges the window the PR's CI judges

Commit: 5ceedb9a0056e09bebf1af62f6e859df04c6edfc
Repo: console
Branch: 1008-1
Parent: f7ba97db319d086301743f5840f9521af6c70596
Patch-Id: 25135f52ef68bb7b7b0ecef7a24739dcec370444
Reviewed-At: 2026-10-19T11:55:24Z
Model: claude-haiku-5-5
Cost: $0.0043 USD, 1 call(s), 30.3s
Diff: 6233 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Gate-tooling fix only: CI behaviour is unchanged (GITHUB_ACTIONS short-circuits to GITHUB_HEAD_REF), and no product code ships.
Dropped: 0
Body-Sig: 4d8d771a6ffa51bb

## Findings

### 5ceedb9a.1 [medium] .ci/rediacc_ci/ci/gate_costs.py:194
Anchor: in-diff
Claim: _local_branch() calls subprocess.run without catching OSError, so on a machine where git is not on PATH, collect_captures raises FileNotFoundError instead of returning "" as the docstring promises for 'git cannot answer' (check=False only covers a non-zero exit).
Resolution: open

### 5ceedb9a.2 [medium] .ci/rediacc_ci/tests/test_ci_gate_costs.py:812
Anchor: in-diff
Claim: The detached/no-branch case is never exercised on the local path: the stub returning "" is installed while GITHUB_ACTIONS is still true, so _head_branch returns early and never reaches _local_branch's "" result; _local_branch itself is never run against real git or a non-zero git exit, though the commit message says 'detached reads as none'.
Resolution: open
