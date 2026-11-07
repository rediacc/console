# Review 7acdec1f: fix(ops-health): break a refresh lock whose recorded pid is dead

Commit: 7acdec1f3dad176efd80b6c488ec1def1fd8710a
Repo: console
Branch: 1104-1
Parent: abfeaa93f899e9d81c176c06e50a873cc7c55c25
Patch-Id: fc33c17ae58319d9d1e968dbec50ab63984ff7fd
Reviewed-At: 2026-11-07T11:14:14Z
Model: claude-haiku-5-5
Cost: $0.0072 USD, 1 call(s), 47.5s
Diff: 14432 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes stale refresh-lock handling so a dead holder no longer blocks refreshes; no new capability.
Dropped: 0
Body-Sig: 78afd9f34fa21cc2

## Findings

### 7acdec1f.1 [medium] .claude/hooks/stop/test-opshealth.py:488
Anchor: in-diff
Claim: The spawn check cannot tell the refresher's pid from the hook's own pid: the fake child reports os.getpid(), which is the test process's pid, so writing the hook's pid instead of the child's would still pass this check.
Resolution: fixed d7b0da2731bf30ca2fb9af10e926cf1330bf0c21 | d778be9d 2026-11-07T11:24:03Z

### 7acdec1f.2 [medium] .claude/hooks/stop/wl_opshealth.py:223
Anchor: in-diff
Claim: After Popen, the lock is rewritten with write_text outside the flock guard and without checking ownership. If the spawned refresher already released the lock, or another hook has since taken it, this write creates or overwrites the lock with a dead or foreign pid, so the next stop can take it over while a refresher is still running and two refreshers run at once.
Resolution: fixed d7b0da2731bf30ca2fb9af10e926cf1330bf0c21 | d778be9d 2026-11-07T11:24:03Z

### 7acdec1f.3 [low] .ci/rediacc_ci/ops/ops_health.py:1135
Anchor: in-diff
Claim: A manual `refresh --lock-held` now stamps its own pid unconditionally, even when no lock exists or a live refresher holds it. The live holder's pid is then replaced, so when this run releases the lock the other refresher loses its protection. Before this change, `--lock-held` never touched the lock file.
Resolution: fixed d7b0da2731bf30ca2fb9af10e926cf1330bf0c21 | d778be9d 2026-11-07T11:24:03Z

### 7acdec1f.4 [low] .ci/rediacc_ci/ops/ops_health.py:902
Anchor: in-diff
Claim: pid_alive uses os.kill(pid, 0), which succeeds for a zombie or a reused pid. A crashed refresher that is not reaped, or whose pid was reused, keeps its lock for the full 20 minutes, so the 'stale at once' promise in the docstring does not hold in those cases.
Resolution: fixed d7b0da2731bf30ca2fb9af10e926cf1330bf0c21 | d778be9d 2026-11-07T11:24:03Z
