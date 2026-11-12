# Review 20fdede2: fix(ci): order the shared-package builders and their readers under one per-checkout lock

Commit: 20fdede2ef83bf152daea9196d4d7fd82aa7e49e
Repo: console
Branch: 1104-1
Parent: 23a1c1e6ca3cb5fe8b495b25de78d1287cb1241f
Patch-Id: 030b058dad9494076f2d5c83a4bdcce403f01e74
Reviewed-At: 2026-11-11T11:51:45Z
Model: claude-haiku-5-5
Cost: $0.0100 USD, 1 call(s), 62.7s
Diff: 35262 bytes, 8 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug,ci why=CI-only lock ordering fix for a race in vm:check and the builders; no user-facing product change.
Dropped: 0
Body-Sig: da26494685020b4d

## Findings

### 20fdede2.1 [medium] .ci/rediacc_ci/core/local_common.py:767
Anchor: in-diff
Claim: ensure_deps now takes the exclusive prepare lock and re-checks the stamp under it, but no test exercises that path (test_core_prepare_lock.py only drives ensure_packages_built), so a regression that drops the lock or the re-check would pass the suite.
Class: missing-control-test
Resolution: fixed 97a4bd322cb9da7b512ce7aaa3a2b889ecd93aad | d778be9d 2026-11-12T09:06:26Z

### 20fdede2.2 [low] .ci/rediacc_ci/core/account_lifecycle.py:1011
Anchor: in-diff
Claim: test() now holds the prepare lock shared around vitest, and no test asserts that the lock is taken or released around the run, so removing the `with` would pass unnoticed.
Class: missing-control-test
Resolution: fixed 97a4bd322cb9da7b512ce7aaa3a2b889ecd93aad | d778be9d 2026-11-12T09:06:42Z
