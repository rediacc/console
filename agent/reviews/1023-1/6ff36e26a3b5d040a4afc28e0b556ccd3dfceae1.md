# Review 6ff36e26: feat(configs): password-enroll accepts a configId to scope the match

Commit: 6ff36e26a3b5d040a4afc28e0b556ccd3dfceae1
Repo: private/account
Branch: 1023-1
Parent: 43748d7d54f63247081ea294a38054350c877c4e
Patch-Id: c870b73467ac3876b896775b2c6bdc8c0aa93184
Reviewed-At: 2026-10-27T15:43:32Z
Model: claude-haiku-5-5
Cost: $0.0028 USD, 1 call(s), 20.6s
Diff: 7807 bytes, 2 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds an optional configId field to the password-enroll body, a new capability for callers.
Dropped: 0
Body-Sig: 8357e9455c8d6186

## Findings

### 6ff36e26.1 [medium] src/routes/configs.ts:1113
Anchor: in-diff
Claim: The new `!Array.isArray(parsed)` guard and the trailing else reject bodies that the old code accepted: `null`, `[]`, and bare JSON strings, numbers or booleans now get 400, although the commit says the no-configId behaviour is unchanged. No test covers these bodies.
Resolution: open
