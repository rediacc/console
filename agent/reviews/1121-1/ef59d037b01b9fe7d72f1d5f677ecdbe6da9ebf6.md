# Review ef59d037: fix(ci): review findings of cluster CL-V-CI-PY-2 across land --run, drills, enterprise, housekeeping and native

Commit: ef59d037b01b9fe7d72f1d5f677ecdbe6da9ebf6
Repo: console
Branch: 1121-1
Parent: 10c2db1bdcf0b9f910b65a8133b4de93fc626fac
Patch-Id: 00bb7c39e0ee987ffbb8127f99e6289f7c9aea9a
Reviewed-At: 2026-11-26T17:56:41Z
Model: claude-haiku-5-5
Cost: $0.0101 USD, 1 call(s), 34.5s
Diff: 59970 bytes, 21 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Fixes review findings: refused-lane and count-mismatch failures now fail the run, drills no longer report unfiled VERIFIED, and false counts are malformed; no new capability.
Dropped: 0
Body-Sig: a8d0c077910414bf

## Findings

### ef59d037.1 [medium] .ci/rediacc_ci/dev/worktree_land_run.py:301
Anchor: in-diff
Claim: The landed-count mismatch is recorded with run.step but its return value is ignored, so _land_sub still calls _land_gitlink and bumps the console submodule pointer to the partial landed tip in the same run.
Class: other
Resolution: fixed f17af425d2ebbe6f1f46a962c22c1ce0dbeb939f | d778be9d 2026-11-26T18:48:21Z

### ef59d037.2 [medium] .ci/rediacc_ci/drills/vm_check.py:4320
Anchor: in-diff
Claim: When _publish_pinned fails, _unfiled downgrades status to NOT_VERIFIED, but the receipt already written to the clone by receipt_mod.write(self.root, ...) still records VERIFIED and is never rewritten, so the on-disk receipt contradicts the run's exit code.
Class: other
Resolution: fixed f17af425d2ebbe6f1f46a962c22c1ce0dbeb939f | d778be9d 2026-11-26T18:48:21Z

### ef59d037.3 [medium] .ci/rediacc_ci/drills/vm_check.py:4413
Anchor: in-diff
Claim: In the --only merge path the merged receipt is written with the pre-downgrade VERIFIED status before _publish_pinned is checked; a failed filing then only changes the in-memory status and the receipt on disk still reads VERIFIED.
Class: other
Resolution: fixed f17af425d2ebbe6f1f46a962c22c1ce0dbeb939f | d778be9d 2026-11-26T18:48:21Z
