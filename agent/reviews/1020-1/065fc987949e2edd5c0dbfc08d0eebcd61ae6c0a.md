# Review 065fc987: test(e2e): the system checks record Landlock on every OS leg

Commit: 065fc987949e2edd5c0dbfc08d0eebcd61ae6c0a
Repo: console
Branch: 1020-1
Parent: 063da71f1a6139c92413c9857c1ca48a475503dc
Patch-Id: 6c5259214e83c009540e13794f59892995b4a7ec
Reviewed-At: 2026-10-20T15:39:41Z
Model: claude-haiku-5-5
Cost: $0.0021 USD, 1 call(s), 17.2s
Diff: 1651 bytes, 1 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=Adds an e2e test assertion and annotation only; no user-facing change.
Dropped: 0
Body-Sig: 44ef951d42a0d721

## Findings

### 065fc987.1 [low] packages/e2e-tests/tests/01-system-checks.test.ts:137
Anchor: in-diff
Claim: The blanket `expect(output).not.toContain('not available')` fails the test whenever `renet sandbox-exec --detect` prints 'not available' for any other item, even when the Landlock status line is 'available'. The `status:\s*available` check already covers the Landlock status, so this negative check adds only a false-failure risk.
Resolution: open
