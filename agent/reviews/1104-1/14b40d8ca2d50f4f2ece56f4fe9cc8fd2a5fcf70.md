# Review 14b40d8c: fix(compose): a run after the privilege drop validates with the operator's grant

Commit: 14b40d8ca2d50f4f2ece56f4fe9cc8fd2a5fcf70
Repo: private/renet
Branch: 1104-1
Parent: 8a7e70a7a01fac8f2ed68049627cc4bdb0a6c34e
Patch-Id: ac31c4633c60a3f79ea247aa3b32190503f6c0e8
Reviewed-At: 2026-11-04T14:17:48Z
Model: claude-haiku-5-5
Cost: $0.0128 USD, 1 call(s), 48.7s
Diff: 77208 bytes, 23 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes compose validation after the privilege drop, a bug fix with no new capability or public API change.
Dropped: 0
Body-Sig: 073b818aa07b0fe4

## Findings

### 14b40d8c.1 [medium] cmd/renet/daemon_grant.go:355
Anchor: in-diff
Claim: The EnvComposeGrant branch of applyComposeDelegations ignores networkID and mount, which the Load path checks (ErrMountMismatch, per-network store). A dropped process validating compose for another repo or network applies the projection exported for a different mount, so the client-side check passes where the gate's own check for that mount would refuse. No test covers a value exported for another mount reaching applyComposeDelegations.
Resolution: open

### 14b40d8c.2 [low] cmd/renet/sandbox_exec.go:725
Anchor: in-diff
Claim: exportSessionComposeGrant silently unsets the variable on any Load error, including non-permission errors such as a corrupt grant file, with no log line. The applyComposeDelegations path warns for the same failure, so an operator gets no signal that the session's compose grant was dropped.
Resolution: open

### 14b40d8c.3 [low] pkg/dockergrant/gate_forgery_linux_test.go:40
Anchor: in-diff
Claim: The handler increments backendHits without synchronization and the test goroutine reads *hits after the HTTP response. Go's race detector does not treat socket I/O as a happens-before edge, so a go test -race run can report a data race on this counter.
Resolution: open
