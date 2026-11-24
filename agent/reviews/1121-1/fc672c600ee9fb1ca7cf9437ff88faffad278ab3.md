# Review fc672c60: feat(hooks): the PR freeze is keyed on the landing tree role and its open PR

Commit: fc672c600ee9fb1ca7cf9437ff88faffad278ab3
Repo: console
Branch: 1121-1
Parent: c0544eff91f6fce3fff3a7cd7505d85861179e46
Patch-Id: b8617386f09c5e954a4c35bcfd9f7ef67b35921f
Reviewed-At: 2026-11-21T09:07:43Z
Model: claude-haiku-5-5
Cost: $0.0107 USD, 1 call(s), 32.7s
Diff: 195925 bytes, 12 files, truncated: yes
Unreviewed: .claude/rediacc_hooks/tests/goldens/block_pr_freeze_commit.jsonl, .claude/rediacc_hooks/tests/test_githook_pr_freeze.py, .claude/rediacc_hooks/tests/test_wl_focus.py
Verdict: findings
Attempt: 1
Labels: bump=minor kind=bug,feature,docs why=New PR-keyed freeze rule set and rule 6 (new capability), plus a defect fix for linked-tree submodule reads.
Dropped: 0
Body-Sig: ea74ac613ae3c3b7

## Findings

### fc672c60.1 [medium] .claude/rediacc_hooks/guards/block_pr_freeze_commit.py:156
Anchor: in-diff
Claim: The comment says a detached HEAD is left to the commit-msg hook, which skips it too; but pr_freeze.check now ignores its branch argument (`del branch`) and freezes by the landing record, so a detached commit in the landing tree is judged, not skipped. Only this guard skips it.
Class: doc-contradicts-code
Resolution: not-a-bug | already fixed in the current tree: .claude/rediacc_hooks/guards/block_pr_freeze_commit.py:97 | d778be9d 2026-11-24T11:09:37Z
