# Review 13bfe1f8: fix(worktree): refuse a lease below a disk floor

Commit: 13bfe1f8a5acb1b195ffe1a9a5fddd2b285a41e7
Repo: console
Branch: 1121-1
Parent: 35cdd8074f4098120e4235e3ca23f64d41680946
Patch-Id: 30af37391914f707fcaab9e992bf1bb2587c99e7
Reviewed-At: 2026-11-23T20:08:52Z
Model: claude-haiku-5-5
Cost: $0.0053 USD, 1 call(s), 33.9s
Diff: 9615 bytes, 4 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Adds a disk-space refusal guard to make_lease that prevents ENOSPC seed failures; no new user-facing capability beyond the fix.
Dropped: 0
Body-Sig: 112d000ca3ab48dc

## Findings

### 13bfe1f8.1 [low] .ci/rediacc_ci/tests/test_dev_worktree_lease.py:3424
Anchor: in-diff
Claim: The control test says exactly the floor plus two leases is enough, but fake_free rounds free bytes up to 4096-byte blocks, and 2 * LEASE_ESTIMATE_BYTES is not a multiple of 4096, so the value tested is slightly above the boundary and a `<` to `<=` change at the gate would still pass both tests.
Class: missing-control-test
Resolution: open

### 13bfe1f8.2 [low] .ci/rediacc_ci/dev/worktree_lease.py:46
Anchor: in-diff
Claim: FREE_FLOOR_BYTES is 10 * GIB (2^30 bytes) while LEASE_ESTIMATE_BYTES is decimal 4.4e9, and the refusal message prints both as 'GB', so the stated floor is about 0.74 GB more than a reader of 'GB' expects.
Class: other
Resolution: open
