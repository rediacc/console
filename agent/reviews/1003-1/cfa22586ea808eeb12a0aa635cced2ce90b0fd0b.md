# Review cfa22586: fix(hooks): warn_remote_drift admits the lease republish of a rebased live branch

Commit: cfa22586ea808eeb12a0aa635cced2ce90b0fd0b
Repo: console
Branch: 1003-1
Parent: 6cc0d175dbe3a0ca761f61cfcd127711c87f0b86
Patch-Id: 4bbb74ada1bebdacf13d0b63412b44f4bda9df63
Reviewed-At: 2026-10-03T09:56:21Z
Model: claude-haiku-4-5-20251001
Cost: $0.1151 USD, 1 call(s), 140.2s
Diff: 231366 bytes, 3 files, truncated: yes
Unreviewed: .claude/rediacc_hooks/tests/goldens/warn_remote_drift.jsonl
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Lease push validation crashes when remote has non-patch-equivalent commits. Hook fails to refuse the push with proper diagnostic.
Dropped: 0
Body-Sig: 85270b6802aef8d0

## Findings

### cfa22586.1 [high] .claude/rediacc_hooks/guards/warn_remote_drift.py:249
Anchor: in-diff
Claim: In _unmatched_remote(), line[2:].strip() returns the full git cherry output (SHA + message), not just the SHA. This fails when passed to git log as a ref on line 333, since the message portion is invalid as an argument.
Resolution: not-a-bug | .claude/rediacc_hooks/guards/warn_remote_drift.py:258 | d778be9d 2026-10-03T09:57:30Z

### cfa22586.2 [high] .claude/rediacc_hooks/guards/warn_remote_drift.py:333
Anchor: in-diff
Claim: If git log fails (likely given the above), subject will be None. Code does not check for this before passing to % format operator on line 336, causing malformed output or exception.
Resolution: not-a-bug | .claude/rediacc_hooks/hookio.py:418 | d778be9d 2026-10-03T09:57:30Z
