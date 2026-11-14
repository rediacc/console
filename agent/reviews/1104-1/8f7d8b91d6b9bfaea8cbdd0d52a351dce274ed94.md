# Review 8f7d8b91: fix(ci): the gates follow N5's per-run keys: step-scope floor 11, the dead e2e-account-server profile goes, and the unplaced tests join the pytest shards

Commit: 8f7d8b91d6b9bfaea8cbdd0d52a351dce274ed94
Repo: console
Branch: 1104-1
Parent: 932dd63afa5a3471eb8fef42d5f23d2471160850
Patch-Id: 3384bd5289997f60e4529d23d72c8014ede9aab3
Reviewed-At: 2026-11-09T14:36:40Z
Model: claude-haiku-5-5
Cost: $0.0041 USD, 1 call(s), 19.6s
Diff: 15151 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=CI gate thresholds, shard placement and a removed secret profile only; no user-facing product change.
Dropped: 0
Body-Sig: 97a036bf851d6321

## Findings

### 8f7d8b91.1 [low] .ci/rediacc_ci/quality/bws_step_scope.py:67
Anchor: in-diff
Claim: DEFAULT_MIN_WINDOWS drops from 24 to 11, so the gate now passes with 11 windows and no longer detects the loss of up to 13 scoped fetch windows; the floor is an exact match for today's count, so there is no slack for a future change to fail the gate before it is already below the floor.
Resolution: not-a-bug | .ci/rediacc_ci/quality/bws_step_scope.py:67 -- the floor is now 9 and equals the counted windows (2+3+4, recalibrated in 987943f5cb), so losing any window fails the gate at once; the claimed 24-to-11 slack no longer exists. | d778be9d 2026-11-09T16:26:36Z
