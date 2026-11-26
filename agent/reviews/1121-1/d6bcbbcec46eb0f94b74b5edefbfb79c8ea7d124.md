# Review d6bcbbce: fix(gates): scan every test module for fan-out drivers, not only tests/gates

Commit: d6bcbbcec46eb0f94b74b5edefbfb79c8ea7d124
Repo: console
Branch: 1121-1
Parent: 82db4b74ed02df611d64147c497440c88893edca
Patch-Id: cfe98662b2df749996200b77d39a6d86ab0a120c
Reviewed-At: 2026-11-23T08:32:44Z
Model: claude-haiku-5-5
Cost: $0.0055 USD, 1 call(s), 43.3s
Diff: 5581 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=Test-gate scan fix only; no user-facing change.
Dropped: 0
Body-Sig: e86af6371ad38b38

## Findings

### d6bcbbce.1 [low] .ci/rediacc_ci/tests/gates/test_gate_fanout_timeout_declarable.py:421
Anchor: in-diff
Claim: The gate.ok line runs for every driver after the broken-check, so a driver whose problems() were just reported via log_fail at line 415 also gets a success line saying its subjects declare a timeout. The ok is unconditional in the original too, but this commit rewrites that line.
Class: doc-contradicts-code
Resolution: fixed 39f2a137f4c26d3b9970e251ba57603a377bdae5 | d778be9d 2026-11-26T18:48:13Z

### d6bcbbce.2 [low] .ci/rediacc_ci/tests/gates/test_gate_fanout_timeout_declarable.py:38
Anchor: in-diff
Claim: The comment says the real scan lists 'well over a thousand test and hook modules', but the commit never measures the scanned subset: its probe counted 2,184 .py across the whole tree, and the 200 floor is set without the scanned count.
Class: doc-contradicts-code
Resolution: fixed 39f2a137f4c26d3b9970e251ba57603a377bdae5 | d778be9d 2026-11-26T18:48:14Z

### d6bcbbce.3 [low] .ci/rediacc_ci/tests/gates/test_gate_fanout_timeout_declarable.py:390
Anchor: in-diff
Claim: The docstring says the corpus is 'tracked and untracked .py under the two test trees', but the pattern '.claude/*.py' matches every .py under .claude, because git pathspec '*' crosses '/'. The scope in the code is wider than the docstring says. The extra files are filtered by is_fanout_driver, so no result changes.
Class: doc-contradicts-code
Resolution: open
