# Review 014cce13: test(hooks): two-tree scope suite for the guards that judge the sibling bound tree

Commit: 014cce131f7af2d6f7debc6fee5f6c60652cfa9b
Repo: console
Branch: 1104-1
Parent: afdc8d8a614244160356256ccac53a091732865f
Patch-Id: 977234c0c3d91ae629d0ae3a2dbe3d0bd7b100cd
Reviewed-At: 2026-11-20T20:47:20Z
Model: claude-haiku-5-5
Cost: $0.0071 USD, 1 call(s), 44.9s
Diff: 15381 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Adds only a test suite and a generated-ledger row; no user-facing change.
Dropped: 0
Body-Sig: 36ee2091df13571b

## Findings

### 014cce13.1 [medium] .claude/rediacc_hooks/guards/test-two-tree-scope.py:162
Anchor: in-diff
Claim: run() treats any exit code 2 as a refusal and never checks that stderr names the guard, so a dispatcher or guard that blocks everything (or fails with rc 2) passes every want-True case in CASES, since the record and planted checks only compare booleans.
Class: missing-control-test
Resolution: open

### 014cce13.2 [low] .claude/rediacc_hooks/guards/test-two-tree-scope.py:184
Anchor: in-diff
Claim: The block_second_branch case uses the same command as block_nonstandard_branch_name on line 183 ('git -C ... branch feature-x'), so it cannot isolate the second-branch rule and can pass on the naming rule alone.
Class: missing-control-test
Resolution: open
