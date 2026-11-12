# Review e5ff36fc: fix(hooks): withdraw the worktrees.py lease-root change, a file name is masked before the mention is read

Commit: e5ff36fc3d9df1d8dd45ea07e09d0ce4e9af67e9
Repo: console
Branch: 1104-1
Parent: aeea89c457fca5f4010f630b31cc8a827c08c6db
Patch-Id: da41e0ebbce8958ae3e0f62b15017dca3075c85a
Reviewed-At: 2026-11-12T08:56:54Z
Model: claude-haiku-5-5
Cost: $0.0016 USD, 1 call(s), 10.8s
Diff: 3190 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Reverts a hook regex and its test row; internal guard behavior fix, no user-facing feature.
Dropped: 0
Body-Sig: d17fa1d525d353f2

## Findings

### e5ff36fc.1 [medium] .claude/rediacc_hooks/guards/block_worktree_add.py:1193
Anchor: in-diff
Claim: The revert restores `(?![\w-])` so `.claude/worktrees.py` matches as a lease root again, and the commit deletes the only test row (e59de231.2) that pins this case, so no test in the diff would catch a regression in how a `worktrees.py` mention is read.
Class: missing-control-test
Resolution: fixed 6534bdcc481bbd4f476f49462389e855aab41c8f | d778be9d 2026-11-12T09:21:05Z
