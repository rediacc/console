# Review cf43c1fd: test(ci): the SEA build call site's cwd and env are tested, and the deferral plan records how M1, M2 and M4 were really met

Commit: cf43c1fd5b95ecf024f2efd235cddc169fc21e4c
Repo: console
Branch: 1008-1
Parent: f4a0873d5a9b72d402db9fccad8cb9870621933f
Patch-Id: 5380d51b3c0814aabc91aa076ab87d253a853527
Reviewed-At: 2026-10-08T17:22:10Z
Model: claude-haiku-5-5
Cost: $0.0052 USD, 1 call(s), 33.2s
Diff: 11077 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=docs,ci why=Test addition and plan/ledger text only; no user-facing behaviour change.
Dropped: 0
Body-Sig: c2bd4ef237116a51

## Findings

### cf43c1fd.1 [low] .ci/rediacc_ci/native.py:181
Anchor: in-diff
Claim: The call-site comment is cut to '# The child imports rediacc_ci by module path: .ci leads PYTHONPATH (4a6641bf.4).', dropping why the old comment mattered (not relying on how this process found the package) and that caller entries follow .ci, so a later editor loses the reason for env=_ci_env(root).
Resolution: open

### cf43c1fd.2 [low] agent/plans/PLAN-deferred-findings-block-merge.md:182
Anchor: in-diff
Claim: M1 stays '- [x]' with its original acceptance ('worklist.py --list shows 15 new items') unchanged on the box line, while the amendment below says that acceptance was not met; the box now reads as passed against a criterion the note says was replaced.
Resolution: open

### cf43c1fd.3 [low] agent/plans/PLAN-deferred-findings-block-merge.md:189
Anchor: in-diff
Claim: M4 stays '- [x]' with its original acceptance ('naming the per-finding items that replaced them') unchanged, while the amendment says no replacement items exist, so the ticked box and its acceptance text now contradict each other.
Resolution: open

### cf43c1fd.4 [low] agent/plans/QUEUE.md:64
Anchor: in-diff
Claim: Generated queue ledger is hand-committed with live session state (5 writers, worker IDs, 6 leased items); these values go stale as soon as the session changes, adding churn to the PR.
Resolution: open
