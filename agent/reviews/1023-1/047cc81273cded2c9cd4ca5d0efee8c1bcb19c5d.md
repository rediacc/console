# Review 047cc812: feat(free-license): the activation skip switch is gone, renet system tests run against a per-run account server, a WAF rate rule applier, and COMMUNITY usable a

Commit: 047cc81273cded2c9cd4ca5d0efee8c1bcb19c5d
Repo: console
Branch: 1023-1
Parent: 06823e7c83c736497d8dd594ca9637cef81737f3
Patch-Id: 3a2bfb0e8c88907fc6753ab151169e3e67a3d603
Reviewed-At: 2026-10-30T22:40:42Z
Model: claude-haiku-5-5
Cost: $0.0178 USD, 1 call(s), 116.3s
Diff: 76213 bytes, 21 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature,ci why=Adds a WAF rate-rule applier and lifts the COMMUNITY gate (user-visible capability via the account pointer); console-side changes are CI, tests and removal of an internal helper.
Dropped: 0
Body-Sig: 576d6c0eac877ce8

## Findings

### 047cc812.1 [high] .github/workflows/ct-tests.yml:2565
Anchor: in-diff
Claim: The bws-secrets step now exports ACCOUNT_ED25519_PRIVATE_KEY (the production signing key) into the job environment for every later step, not just the account-server start step, so the 'Run renet tests' step, which executes repo test code, can read it; only the start step needs it.
Resolution: fixed 445b83f6c6e5bffe06c2795cfc3bc56f003a8f83 | d778be9d 2026-10-30T23:23:19Z

### 047cc812.2 [medium] .ci/rediacc_ci/testrun/start_account.py:253
Anchor: in-diff
Claim: ACCOUNT_SERVER_API_KEY now comes from the caller's environment when set (Delta 9), but this commit adds no test for that branch, so a regression that drops or ignores the env key would pass the suite unnoticed.
Resolution: fixed a0e94ff0e7cfe191d9e48d9e0f5432c96e1de3df | d778be9d 2026-10-30T23:32:52Z

### 047cc812.3 [low] packages/cli/src/services/__tests__/local-executor-restore-license.test.ts:494
Anchor: in-diff
Claim: The deleted test that pinned 'REDIACC_SKIP_MACHINE_ACTIVATION no longer skips licence issuance' was the only guard against the switch being reintroduced, so a future skip path would no longer fail any test.
Resolution: not-a-bug | .ci/config/env-manifest.json:1367 keeps REDIACC_SKIP_MACHINE_ACTIVATION as a tombstone, and check:ci-env-manifest fails when any tracked file reads a tombstoned name again, so a reintroduced switch is caught there | d778be9d 2026-10-30T23:11:17Z
