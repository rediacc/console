# Review cac6cc8b: feat(hooks): worklist.py --git rebase-proof names what a rebase left owed

Commit: cac6cc8be8abfa1f33dd968fcf579ca0e14fcff6
Repo: console
Branch: 1104-1
Parent: 09484b7e19768aab07884838ca570314aaaab1f1
Patch-Id: 4b5cce238770558d5adf9358ef96f73195e7af66
Reviewed-At: 2026-11-20T12:21:47Z
Model: claude-haiku-5-5
Cost: $0.0075 USD, 1 call(s), 48.7s
Diff: 13668 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=New rebase-proof verb and rebase_proof pairing: a new capability for worklist.py --git.
Dropped: 0
Body-Sig: d111785babb90b1a

## Findings

### cac6cc8b.1 [high] .claude/hooks/stop/wl_rebase.py:150
Anchor: in-diff
Claim: A commit dropped by the rebase is reported CHANGED instead of MISSING whenever any new commit has the same subject (e.g. 'wip', 'fix lint'), because the pairing matches on subject alone; rebase-proof's MISSING check then passes and the gate does not refuse the lost commit (S9).
Class: security
Resolution: fixed 9155564933d07c571751efd2f92d1a270d7fd060 | d778be9d 2026-11-20T12:23:14Z

### cac6cc8b.2 [medium] .claude/hooks/stop/wl_rebase.py:116
Anchor: in-diff
Claim: _subjects returns [] when `git log` fails, so rebase_proof treats the range as empty and reports 0 carried, 0 missing and a pass instead of None when git cannot answer.
Class: swallowed-error
Resolution: fixed 9155564933d07c571751efd2f92d1a270d7fd060 | d778be9d 2026-11-20T12:23:14Z

### cac6cc8b.3 [medium] .claude/hooks/stop/wl_git.py:1191
Anchor: in-diff
Claim: The new `rebase-proof` verb (its MISSING refusal, CHANGED notes and check_state gate) has no test in test-rebase-consistency.py; the tests only call wl_rebase.rebase_proof directly, so a regression in the verb's refusal path would not be caught.
Class: missing-control-test
Resolution: fixed 9155564933d07c571751efd2f92d1a270d7fd060 | d778be9d 2026-11-20T12:23:15Z

### cac6cc8b.4 [low] .claude/hooks/stop/wl_git.py:1235
Anchor: in-diff
Claim: The CHANGED note asserts the cause 'conflict-resolved', but CHANGED is inferred from a subject match and also fires for any commit whose patch moved for another reason, so the message can state a cause the code did not establish.
Class: doc-contradicts-code
Resolution: fixed 9155564933d07c571751efd2f92d1a270d7fd060 | d778be9d 2026-11-20T12:23:15Z

### cac6cc8b.5 [low] .claude/hooks/stop/wl_rebase.py:128
Anchor: in-diff
Claim: The docstring says rebase_proof returns None when git cannot answer, but a failing `git log` (via _subjects) yields a dict with empty lists instead of None.
Class: doc-contradicts-code
Resolution: fixed 9155564933d07c571751efd2f92d1a270d7fd060 | d778be9d 2026-11-20T12:23:15Z
