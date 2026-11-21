# Review d1c98d2e: fix(ci-runner): review backlog group 6, path-trace parser, ledger and write-back soundness

Commit: d1c98d2efa10dbd22b150f2d6ec33caab7d3d4a6
Repo: console
Branch: 1104-1
Parent: 83f9183bab49d80e5e36ba7f7fa37f421f3b2987
Patch-Id: da1573d1ae32fb51599f9278d2650bd0e4559a6a
Reviewed-At: 2026-11-19T05:42:51Z
Model: claude-haiku-5-5
Cost: $0.0088 USD, 1 call(s), 52.7s
Diff: 26628 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Internal ci-runner path-trace fixes: parser, cwd tracking, ledger round-trip and write-back soundness; no new capability.
Dropped: 0
Body-Sig: 8155e8d99bc3498a

## Findings

### d1c98d2e.1 [medium] scripts/ci-runner/path-trace.ts:360
Anchor: in-diff
Claim: A thread's chdir calls setCwd, which sets cwd on every peer but flushes pending and execsWithoutCwd only for the chdirring process; a peer that named relative paths before any cwd was known resolves them against the new directory on its next line instead of its start cwd.
Class: other
Resolution: fixed 9a2ce56865770e7da777e105eda1e6fe94014c91 | d778be9d 2026-11-19T07:07:32Z

### d1c98d2e.2 [medium] scripts/ci-runner/path-trace.ts:469
Anchor: in-diff
Claim: With a symlinked root, root is now realpathed for the return value, but gitDirs is still built with path.resolve(root, ...) on the unresolved root, so a relative --git-common-dir result (e.g. '.git') stays in symlink form while strace reports realpaths.
Class: other
Resolution: fixed 9a2ce56865770e7da777e105eda1e6fe94014c91 | d778be9d 2026-11-19T07:07:33Z
