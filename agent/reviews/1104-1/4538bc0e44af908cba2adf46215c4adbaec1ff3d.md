# Review 4538bc0e: fix(cli): dropping replication rules moves past a rule the server does not hold

Commit: 4538bc0e44af908cba2adf46215c4adbaec1ff3d
Repo: console
Branch: 1104-1
Parent: 1a7b124fc16c4f7e39a5d8df270bbe7ce005e29f
Patch-Id: b71ebb94b11334c3cd3fa7939861d54d4278dfbe
Reviewed-At: 2026-11-07T16:52:07Z
Model: claude-haiku-5-5
Cost: $0.0017 USD, 1 call(s), 10.3s
Diff: 5049 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes drop loop stopping early on a 404 for an unknown rule; no new capability.
Dropped: 0
Body-Sig: 219655866417549a

## Findings

### 4538bc0e.1 [medium] packages/cli/src/services/backup/backup-replication.ts:115
Anchor: in-diff
Claim: The RULE_UNKNOWN 404 exemption lives in the shared applyAll, so pushReplicationRules (a PUT) also counts a 404 with that code as done instead of failure or unsupported; no test covers this push-path change, and the commit message only describes drops.
Resolution: fixed 0b57095cfa60385df7474ebd456edcc73c9eeab1 | d778be9d 2026-11-09T15:21:08Z
