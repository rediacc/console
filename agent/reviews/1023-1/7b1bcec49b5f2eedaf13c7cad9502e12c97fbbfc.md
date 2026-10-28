# Review 7b1bcec4: feat(renet,cli): per-flavor renet output paths and a flavor-keyed CLI clean build (PLAN-per-flavor-renet-binary-paths P1, P4)

Commit: 7b1bcec49b5f2eedaf13c7cad9502e12c97fbbfc
Repo: console
Branch: 1023-1
Parent: 9d4aff01165a355349be4e6b48f53fa0471c5300
Patch-Id: 63dc8cb676af1fc1a6ebf6eba809795d4797fde3
Reviewed-At: 2026-10-28T06:28:18Z
Model: claude-haiku-5-5
Cost: $0.0098 USD, 1 call(s), 51.1s
Diff: 38365 bytes, 8 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature,ci why=Adds enforce-flavor dirty-tree clean builds and flavor-keyed cache (new capability); shard manifest and tests updated.
Dropped: 0
Body-Sig: 2194b7572e8e80c1

## Findings

### 7b1bcec4.1 [medium] packages/cli/src/services/renet/renet-execution.ts:241
Anchor: in-diff
Claim: selectRenetUploadBinary now runs `go version -m` on the working-tree binary before the cache lookup, so a dirty-tree upload whose binary cannot be read by go (no Go toolchain, or a non-Go file) throws here even when a complete cached build exists; the previous code only ran go on a cache miss. No test covers this failure path.
Resolution: open

### 7b1bcec4.2 [low] .ci/rediacc_ci/tests/test_private_renet_build_dev_flavor.py:138
Anchor: in-diff
Claim: The control test's pytest.raises accepts any AssertionError or FileNotFoundError, so it also passes when build.sh fails for an unrelated reason (non-zero exit trips the returncode assert), and does not prove that the planted collapsed directory is the cause.
Resolution: open
