# Review f05ab392: fix(cli,hooks): the startTree race, and live-proof ticks that can be written

Commit: f05ab3927fdab1c1dc08c6644eaeadb31e3bf2db
Repo: console
Branch: 1104-1
Parent: 6e142634226b76922a48ada8e8b1d621b140f312
Patch-Id: 877e5b91fc08939cb3937ecc620d3397d41c5a8e
Reviewed-At: 2026-11-04T10:52:17Z
Model: claude-haiku-5-5
Cost: $0.0021 USD, 1 call(s), 25.7s
Diff: 2852 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Test-race fix and a hook evidence-line change; no user-facing product behaviour changes.
Dropped: 0
Body-Sig: 4ea46e68ef458176

## Findings

### f05ab392.1 [medium] .claude/hooks/stop/wl_liveproof.py:213
Anchor: in-diff
Claim: The new re.sub strips the renet commit from every evidence line's v= field, which changes what --tick writes for all rows, but no test in this commit covers the rewritten format, so a regression in the regex or its output would go unnoticed.
Resolution: fixed d3f62390c66e96977493ad237bf58d8f3d9ca73a | d778be9d 2026-11-04T12:18:53Z

### f05ab392.2 [low] .claude/hooks/stop/wl_liveproof.py:213
Anchor: in-diff
Claim: The pattern only matches lowercase hex of 7 to 40 characters after 'renet:'; any other version form (uppercase hex, a different prefix, a longer sha) passes through unchanged, so the citation-gate fix silently does nothing for it.
Resolution: fixed d3f62390c66e96977493ad237bf58d8f3d9ca73a | d778be9d 2026-11-04T12:18:53Z

### f05ab392.3 [low] .claude/hooks/stop/wl_liveproof.py:212
Anchor: in-diff
Claim: The comment says 'the sha256 and the row hold the identity', but the format string shown in this diff writes only id, target, check, rc and version, so the sha256 is not visible in the evidence line this comment describes.
Resolution: fixed d3f62390c66e96977493ad237bf58d8f3d9ca73a | d778be9d 2026-11-04T12:18:53Z

### f05ab392.4 [low] packages/cli/src/services/executor/__tests__/ops-timeout.test.ts:281
Anchor: in-diff
Claim: If the grandchild's pid write is observed mid-write, parseInt reads a truncated prefix (e.g. '12' of '1234') and the pid > 1 check accepts it, so the poll can return before the full pid is in the file.
Resolution: fixed 867b26ee28f371730519a1f4452a60e639e27fd7 | d778be9d 2026-11-04T12:20:09Z
