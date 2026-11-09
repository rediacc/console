# Review b366523f: fix(account): the web console drops the dead edgeBadge key and tests the link-sent note

Commit: b366523fe4da8bdccace28eebd2ab74d30de87c5
Repo: private/account
Branch: 1104-1
Parent: 195f66642d6e9c624e7a6b7aef3bdfa3a6d084af
Patch-Id: fc694910f36251a4c832e8536259a324970ad5e4
Reviewed-At: 2026-11-09T09:13:44Z
Model: claude-haiku-5-5
Cost: $0.0027 USD, 1 call(s), 11.9s
Diff: 15420 bytes, 15 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=none kind=bug why=Removes a dead translation key and adds a test; no user-facing behaviour change.
Dropped: 0
Body-Sig: 8eb54860e426f613

## Findings

### b366523f.1 [medium] web/src/pages/__tests__/login-cross-tab.test.tsx:130
Anchor: in-diff
Claim: The new assertion's regex /sent a sign-in link|passwordStepDescription/i also matches the raw i18n key name, so the test passes whenever any element containing that key text renders, even if the link-sent note is not shown. The test name also claims 'after every successful request' but the body exercises only one requestLink() call.
Resolution: open

### b366523f.2 [low] web/src/pages/__tests__/login-cross-tab.test.tsx:128
Anchor: in-diff
Claim: The new test sits inside the describe block 'Login continues the CLI handoff tab after a sign-in elsewhere', which does not match what it checks (link-sent note), so a future reader may misjudge its scope.
Resolution: open
