# Review 34e3aefc: test(account): automate the bench sidebar walk-through in three modes

Commit: 34e3aefcbef971ba0cc8936e7f59f4e96befaddc
Repo: private/account
Branch: 1104-1
Parent: 94fe8035edf7df6c67cd02a241cb53ebd246683d
Patch-Id: 86a8d866e152ac8daaa1283b81bdbbfd9a8af55d
Reviewed-At: 2026-11-19T15:22:08Z
Model: claude-haiku-5-5
Cost: $0.0082 USD, 1 call(s), 49.1s
Diff: 23435 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=none why=Test-only and e2e config changes; no user-facing behaviour change.
Dropped: 0
Body-Sig: b4c2927b164bbd59

## Findings

### 34e3aefc.1 [medium] e2e/src/utils/live-sidebar-walk.ts:130
Anchor: in-diff
Claim: The doc comment says applyLocaleAndTheme 'reloads so both apply', but the function only adds the cookie and sets localStorage and data-theme with no navigation; capture() in 07-90 calls it without navigating, so the dark screenshots may still render light and the walk reports them as dark.
Class: doc-contradicts-code
Resolution: open

### 34e3aefc.2 [medium] e2e/tests/07-navigation/07-90-live-sidebar.test.ts:282
Anchor: in-diff
Claim: In the mobile layout, `if (await trigger.isVisible()) await trigger.click();` silently skips opening the sidebar when the trigger is missing or not yet rendered (isVisible does not wait), so the 390 px screenshot is captured with the sidebar closed and the step still passes.
Class: swallowed-error
Resolution: open

### 34e3aefc.3 [low] e2e/playwright.live.config.ts:7
Anchor: in-diff
Claim: The header still says this config runs with no trace, screenshot or video and that the results directory holds no recording, but the new 07-90 spec writes masked PNG screenshots of the console into that same results directory.
Class: doc-contradicts-code
Resolution: open
