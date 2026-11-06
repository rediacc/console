# Review 3cd1b54f: test(ebpf): the clone-leaf renewal tests no longer depend on inode numbers, and the uncreatable-leaf error is tested

Commit: 3cd1b54f66ad7eac67724cdd9d8e4fb8f7a5affc
Repo: private/renet
Branch: 1104-1
Parent: b54ad021d9683b5e5a345302b166c48c96c3ef60
Patch-Id: c54d4937350a7788941f5e3400cb23f8e46e08b6
Reviewed-At: 2026-11-06T21:43:50Z
Model: claude-haiku-5-5
Cost: $0.0032 USD, 1 call(s), 22.2s
Diff: 5585 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=none why=Test-only change; no user-facing behaviour changes.
Dropped: 0
Body-Sig: 38071faa32b61d3d

## Findings

### 3cd1b54f.1 [low] pkg/ebpf/clone_leaf_hold_test.go:169
Anchor: in-diff
Claim: The new test's comment says the uncreatable leaf is modelled on a host without cgroup write access, but the test only makes the parent a regular file (ENOTDIR); it never exercises a permission-denied case, so the comment overstates what is pinned.
Resolution: open

### 3cd1b54f.2 [low] pkg/ebpf/clone_leaf_hold_test.go:69
Anchor: in-diff
Claim: The removeCgroupDir stub calls unix.Rmdir directly instead of the saved hook 'old' as the sibling test in clone_leaf_test.go does, so this test would bypass any previously installed hook and the two tests count removals differently.
Resolution: open
