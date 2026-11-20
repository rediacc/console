# Review 7f84fd73: fix(ci): quality-pytest rebalance work budget follows the lane to 947 blocks

Commit: 7f84fd73dddb0e7a3e3fae73abfff8d3ca3790f1
Repo: console
Branch: 1104-1
Parent: 20baa72122be9130228dfce3d6778e982cb4f90c
Patch-Id: f58efb3554f65592479694d157faa1361bafec98
Reviewed-At: 2026-11-20T03:56:25Z
Model: claude-haiku-5-5
Cost: $0.0016 USD, 1 call(s), 8.3s
Diff: 3011 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Raises a CI-only evaluation budget constant and extends a comment; no user-facing change.
Dropped: 0
Body-Sig: e144b4332d816e06

## Findings

### 7f84fd73.1 [low] scripts/gates/check-lane-budget.ts:1310
Anchor: in-diff
Claim: The comment says both runs are 'each run far under the 10M per-run cap', but the 8,700,617 figure is the combined total of both local-search runs, so one run could be close to 8.7M, which is not clearly far under a 10M cap.
Class: doc-contradicts-code
Resolution: fixed 45cca55fdbbb6019088aa8ca223b821d16029dfc | d778be9d 2026-11-20T03:58:56Z
