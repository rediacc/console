# Review 7b53e7e2: test(e2e): the Landlock check expects the measured state per OS, so Oracle Linux 10 reports NOT AVAILABLE and every other leg AVAILABLE

Commit: 7b53e7e2ce74d5faa1fb7152ffa87251cbbcfdfb
Repo: console
Branch: 1020-1
Parent: 2eb541432341be9904d77c2d28e5c0bef155f531
Patch-Id: 4877bf2a068ab0501784ca9417e29b675c8a041c
Reviewed-At: 2026-10-21T18:05:54Z
Model: claude-haiku-5-5
Cost: $0.0034 USD, 1 call(s), 26.1s
Diff: 4159 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Test-only change to the e2e Landlock assertion; no shipped behaviour changes.
Dropped: 0
Body-Sig: 87fd4fc60f1c7985

## Findings

### 7b53e7e2.1 [medium] packages/e2e-tests/tests/01-system-checks.test.ts:154
Anchor: in-diff
Claim: On the ol-10 leg the test passes for any output containing 'status: not available' and never checks the cause (lsm= contents or the 'landlock: Disabled' log line), so a renet detection regression that also reports NOT AVAILABLE on Oracle Linux 10 passes silently, and that leg can no longer catch it.
Resolution: fixed 10e90e317e4533b1a2988243fc2e1b359494958e | d778be9d 2026-10-21T18:07:27Z

### 7b53e7e2.2 [low] packages/e2e-tests/tests/01-system-checks.test.ts:138
Anchor: in-diff
Claim: If the os-release read yields no `os=` match, os becomes 'unknown' and the test silently takes the AVAILABLE branch with no message naming the failed OS lookup, so an unreadable /etc/os-release is reported as an ordinary Landlock result.
Resolution: fixed 10e90e317e4533b1a2988243fc2e1b359494958e | d778be9d 2026-10-21T18:07:28Z
