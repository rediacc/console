# Review e58ef9b2: feat(console): callers outside the executor's org get the coded 503 instead of a relayed 401

Commit: e58ef9b292b3ac150cfaf1ddabb211abf8cc9bd2
Repo: private/account
Branch: 1023-1
Parent: c76a4e6e4f05615b9398c5b7aa7694243d696f84
Patch-Id: 8ca42ee28a037288502c2156fc1c61506407c868
Reviewed-At: 2026-10-26T02:20:28Z
Model: claude-haiku-5-5
Cost: $0.0063 USD, 1 call(s), 30.9s
Diff: 14768 bytes, 3 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug why=Cross-org callers now get a coded 503 instead of a relayed 401; a behaviour fix with a new gate, no new capability.
Dropped: 0
Body-Sig: eebf2ac93e54be87

## Findings

### e58ef9b2.1 [medium] src/routes/console.ts:122
Anchor: in-diff
Claim: When EXECUTOR_ISSUER_ORG_ID is set but the ROOT_EMAIL user is missing, the owner lookup returns null before the override is checked, so every caller gets CONSOLE_EXECUTION_UNAVAILABLE even though the doc comment says the override is used when set.
Resolution: not-a-bug | private/account/src/services/executor-issuer.service.ts:118 refuses ISSUER_OWNER_UNSET when ROOT_EMAIL is unset and :121 resolves the owner by that email before any org override is consulted, so private/account/src/routes/console.ts:118-122 returning null (coded 503) mirrors what the issuer itself refuses; no executor token can exist for any caller in that state | d778be9d 2026-10-26T04:47:52Z

### e58ef9b2.2 [medium] src/routes/console.ts:118
Anchor: in-diff
Claim: With EXECUTOR_ISSUER_ORG_ID set and ROOT_EMAIL unset, this line returns null, so the override is ignored and every caller in every org gets the 503, which the doc comment's 'override when set' rule does not describe.
Resolution: not-a-bug | private/account/src/services/executor-issuer.service.ts:118 refuses ISSUER_OWNER_UNSET when ROOT_EMAIL is unset and :121 resolves the owner by that email before any org override is consulted, so private/account/src/routes/console.ts:118-122 returning null (coded 503) mirrors what the issuer itself refuses; no executor token can exist for any caller in that state | d778be9d 2026-10-26T04:47:53Z

### e58ef9b2.3 [medium] tests/integration/executor-mode-wiring.test.ts:42
Anchor: in-diff
Claim: The new discovery regex no longer matches a plain wrangler.toml, so if that file still exists and is deployed, the EXECUTOR_MODE/TEST_MODE [vars] check never scans it and the exact-name test passes without noticing.
Resolution: fixed 257625a82e188c404df23dc45a64924921bbe572 | d778be9d 2026-10-26T07:06:52Z
