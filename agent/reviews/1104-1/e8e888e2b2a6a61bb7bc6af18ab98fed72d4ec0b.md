# Review e8e888e2: fix(hooks): a silent SubagentStop capture with an armed shell is written interim

Commit: e8e888e2b2a6a61bb7bc6af18ab98fed72d4ec0b
Repo: console
Branch: 1104-1
Parent: b124565bb1ec7aa1681298b215db5ea32074c221
Patch-Id: a93559bd52c8d364f063160eda38c52e4ed7d03a
Reviewed-At: 2026-11-10T15:44:56Z
Model: claude-haiku-5-5
Cost: $0.0040 USD, 1 call(s), 18.5s
Diff: 6017 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes SubagentStop capture so an unflushed api-request tail with an armed shell writes interim instead of blocking.
Dropped: 0
Body-Sig: b079a186bb74405d

## Findings

### e8e888e2.1 [low] .claude/hooks/stop/wl_roster.py:592
Anchor: in-diff
Claim: transcript_waiting now calls last_record(jsonl) before the mtime/WAIT_HORIZON_MIN check, so a missing or stale transcript that previously returned "" without being read now reaches last_record(); if last_record raises on a missing path, transcript_waiting raises where it used to return "" (the diff does not show last_record, so this is unverified).
Class: other
Resolution: not-a-bug | .claude/hooks/stop/wl_liveness.py:425 last_record returns None for a missing path (its reader catches OSError) and _record_is_idle(None) is False, so transcript_waiting still returns empty for a missing or stale transcript; test_wl_interim_reports pins both shapes | d778be9d 2026-11-10T16:18:08Z
