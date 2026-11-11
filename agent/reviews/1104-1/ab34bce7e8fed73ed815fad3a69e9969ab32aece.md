# Review ab34bce7: test(guards): pin both stdin procfs seams, default and override

Commit: ab34bce7e8fed73ed815fad3a69e9969ab32aece
Repo: console
Branch: 1104-1
Parent: 7ba9677a8257e68fd66dccaf7c4fdee51bcd31a6
Patch-Id: ecec0602ec80e099778cbe609e903a70b08d71a5
Reviewed-At: 2026-11-11T05:00:55Z
Model: claude-haiku-5-5
Cost: $0.0022 USD, 1 call(s), 11.6s
Diff: 9304 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only addition plus shard manifest and doc registry updates; no user-facing change.
Dropped: 0
Body-Sig: c80749b14533b85c

## Findings

### ab34bce7.1 [low] .claude/rediacc_hooks/tests/test_guard_stdin_procfs_seams.py:20
Anchor: in-diff
Claim: _load inserts HOOKS into sys.path[0] and never removes it, so the global import path stays modified for every test that runs after this module in the same pytest process.
Class: seam-not-restored
Resolution: fixed 70485fdea44f20aea15e375fc0c3cda61e5f9a78 | d778be9d 2026-11-11T05:08:05Z
