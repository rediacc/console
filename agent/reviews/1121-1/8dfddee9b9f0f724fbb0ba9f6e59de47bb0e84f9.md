# Review 8dfddee9: feat(serve): bind a daemon to loopback by default and require TLS off loopback

Commit: 8dfddee9b9f0f724fbb0ba9f6e59de47bb0e84f9
Repo: console
Branch: 1121-1
Parent: 794b37a0eba911a42b90109efef09c47d984c7fa
Patch-Id: 5653a14e496a6d7ddc8cd04a31e4f2fcec2f9417
Reviewed-At: 2026-11-23T21:49:41Z
Model: claude-haiku-5-5
Cost: $0.0095 USD, 1 call(s), 20.6s
Diff: 105389 bytes, 33 files, truncated: yes
Unreviewed: packages/shared/src/cli-contract/data/i18n/it.json, packages/shared/src/cli-contract/data/i18n/ja.json, packages/shared/src/cli-contract/data/i18n/ko.json, packages/shared/src/cli-contract/data/i18n/pt.json, packages/shared/src/cli-contract/data/i18n/ru.json, packages/shared/src/cli-contract/data/i18n/tr.json, packages/shared/src/cli-contract/data/i18n/zh.json
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=New --tls-cert/--tls-key capability and loopback default; the daemon default change is user-visible.
Dropped: 0
Body-Sig: 4f9a0e0093fc5dd9

## Findings

### 8dfddee9.1 [medium] packages/cli/src/services/serve/bind.ts:66
Anchor: in-diff
Claim: A daemon started with --host '[::1]' passes isLoopbackHost (the brackets are stripped only for the check), then returns the raw '[::1]' as hostname, which Node's listen does not resolve, so the daemon fails at startup on that edge path; the test at hardening-daemon-bind.test.ts asserts hostname equals the bracketed input and so locks this in.
Class: other
Resolution: fixed 44036f09878c3995969abf668126aa1dcf996b31 | d778be9d 2026-11-24T09:58:17Z
