# Review 4cbba90b: chore(agent): hook ledger, queue and worklist records before promotion

Commit: 4cbba90b3c34c6ace7f7a0ae9ab1c2e4851d1ad8
Repo: console
Branch: 1121-1
Parent: 6bab3a912837750096928cadaea7d4c05d6ac32e
Patch-Id: 58188880b2cb1d897a4e6b3748f9aad4bd1145d0
Reviewed-At: 2026-11-22T20:34:32Z
Model: claude-haiku-5-5
Cost: $0.0016 USD, 1 call(s), 9.6s
Diff: 70894 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Ledger rows only, no user-facing change; supports landing --promote clean checkout.
Dropped: 0
Body-Sig: e0ca0eb7abba0ca3

## Findings

### 4cbba90b.1 [low] agent/ledgers/ops-health.jsonl:77
Anchor: in-diff
Claim: The commit message says QUEUE.md's generated block and the session worklist are committed too, but the STAT and diff touch only agent/ledgers/ops-health.jsonl, so a reader relying on the message will expect files that are absent from this commit.
Class: doc-contradicts-code
Resolution: open
