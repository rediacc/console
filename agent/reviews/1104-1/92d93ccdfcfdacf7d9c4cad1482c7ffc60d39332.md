# Review 92d93ccd: test(e2e): skip Rediaccfile up()/down() tests where Landlock is inactive by default

Commit: 92d93ccdfcfdacf7d9c4cad1482c7ffc60d39332
Repo: console
Branch: 1104-1
Parent: 831e5bf97e052d2664c9f67827aabd74667d11f1
Patch-Id: 0f54d653017093f2df828ad49b3486874b251fab
Reviewed-At: 2026-11-14T12:20:27Z
Model: claude-haiku-5-5
Cost: $0.0062 USD, 1 call(s), 21.8s
Diff: 36961 bytes, 13 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=ci why=E2E test-only change: adds Landlock skip gating for oracle-10 in e2e suites; no user-facing behavior.
Dropped: 0
Body-Sig: 6db8abc7814009af

## Findings

### 92d93ccd.1 [high] packages/e2e-tests/src/utils/landlock.ts:22
Anchor: in-diff
Claim: The field() regex is built from lowercase names ('id', 'version_id') with no case-insensitive flag, but /etc/os-release keys are uppercase (ID=, VERSION_ID=), so the match is always empty, workerOsId throws on every worker, and skipWithoutLandlock fails the beforeAll of every suite that calls it (05, 07, 12a, 12b, 13, 13b, 15, 23, 26, 28, 29) on every OS, not just ol-10.
Class: other
Resolution: not-a-bug | getCombinedOutput lowercases the whole output (packages/e2e-tests/src/utils/renet-functions/helpers/TestHelpers.ts:15 returns (stdout + stderr).toLowerCase()), so field('id') and field('version_id') match the lowercased ID=/VERSION_ID= lines; 01-system-checks.test.ts:131-135 parses the same way and passes in CI | d778be9d 2026-11-14T12:21:15Z

### 92d93ccd.2 [medium] packages/e2e-tests/tests/23-cli-migrate-routing.test.ts:165
Anchor: in-diff
Claim: Suite 23 uses two workers (w1 and w2) but only calls skipWithoutLandlock(w1), so when w2 is an OS in LANDLOCK_INACTIVE_BY_DEFAULT and w1 is not, the suite runs and its renet-side steps fail on w2 instead of being skipped.
Class: other
Resolution: not-a-bug | each CI leg boots every VM from one image: .github/workflows/ct-tests.yml:431 sets VM_IMAGE from matrix.os-image for the whole job, so w1 and w2 always share the OS and skipping on w1 covers w2 | d778be9d 2026-11-14T12:22:40Z

### 92d93ccd.3 [low] packages/e2e-tests/src/utils/landlock.ts:18
Anchor: in-diff
Claim: workerOsId and skipWithoutLandlock have no unit test; the parsing bug above would have been caught by a single test feeding a real os-release sample, so the new skip gate is currently unverified by any check that can fail.
Class: missing-control-test
Resolution: fixed 1e43b97e8a02cb1d3cd4699de458008a8ea5b08a | d778be9d 2026-11-14T12:22:40Z
