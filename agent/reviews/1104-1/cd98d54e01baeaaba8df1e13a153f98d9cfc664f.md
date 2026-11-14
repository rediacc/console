# Review cd98d54e: fix(daemon): the stop hook runs down() through a skewed daemon's old socket

Commit: cd98d54e01baeaaba8df1e13a153f98d9cfc664f
Repo: private/renet
Branch: 1104-1
Parent: 44ff5e42f981f6d89bb60f451c0e1f4ef6c8ed2e
Patch-Id: 399e2e3855e83a8e882f2e2e5cc52800ef936708
Reviewed-At: 2026-11-05T23:58:50Z
Model: claude-haiku-5-5
Cost: $0.0064 USD, 1 call(s), 20.2s
Diff: 45804 bytes, 16 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes a stop hook that skipped down() for a skewed daemon; no user-facing capability added.
Dropped: 0
Body-Sig: 49fb8f4f100c6457

## Findings

### cd98d54e.1 [medium] cmd/renet/daemon_stop_hook.go:100
Anchor: in-diff
Claim: On the legacy-socket branch, runDown returns EnsureDownBeforeStopVia(ctx, socket, true) and drops the DownOptions the hook builds (Unmount:false, NoRefresh:true, SkipHeal:true), so a skewed daemon's stop runs down() with different options than the current-socket path, and no test checks that the legacy branch honours them.
Resolution: not-a-bug | pkg/orchestration/down_before_stop.go:94 DownOptions{NoRefresh, SkipHeal, Force} with no Unmount, the same values the hook passes | d778be9d 2026-11-06T04:52:43Z
