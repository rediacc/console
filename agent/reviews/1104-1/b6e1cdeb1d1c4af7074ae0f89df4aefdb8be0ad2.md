# Review b6e1cdeb: feat(account): backup-storage scopes need 2FA when a session mints them

Commit: b6e1cdeb1d1c4af7074ae0f89df4aefdb8be0ad2
Repo: private/account
Branch: 1104-1
Parent: 09a5e5461847509ba200e263b4c392e01d73c1ad
Patch-Id: 6316fd198ed52441ed2814939e083d1dfb87bf87
Reviewed-At: 2026-11-11T15:00:58Z
Model: claude-haiku-5-5
Cost: $0.0051 USD, 1 call(s), 18.9s
Diff: 21688 bytes, 8 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=New 2FA gate on backup-storage scope minting and device-code login scopes; a new capability with no change to existing public APIs.
Dropped: 0
Body-Sig: 953f887b7f711637

## Findings

### b6e1cdeb.1 [low] src/services/device-code.service.ts:347
Anchor: in-diff
Claim: The added comment says 'sign-in itself never requires 2FA', but tests/integration/backup-team-scope.test.ts and backup-restore-session.test.ts state that 'a user with 2FA must pass a challenge at login', so the commit documents two incompatible sign-in behaviours.
Class: doc-contradicts-code
Resolution: fixed 9768c6e25a8eb5863b4992751d2ea89a1f91e192 | d778be9d 2026-11-12T09:08:18Z
