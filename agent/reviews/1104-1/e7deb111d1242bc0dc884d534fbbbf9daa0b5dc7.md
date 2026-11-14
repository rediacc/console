# Review e7deb111: feat(account): backup store registry routes and the session names its store

Commit: e7deb111d1242bc0dc884d534fbbbf9daa0b5dc7
Repo: private/account
Branch: 1104-1
Parent: f9471a2a8a17bd646d501d903725cd28036e309c
Patch-Id: ca703447f6826ca7ffb5103733d72ab1d920ec5b
Reviewed-At: 2026-11-07T14:16:38Z
Model: claude-haiku-5-5
Cost: $0.0152 USD, 1 call(s), 73.0s
Diff: 115051 bytes, 12 files, truncated: yes
Unreviewed: tests/integration/backup-store-registry.test.ts, tests/integration/backup-store-session.test.ts
Verdict: findings
Attempt: 1
Labels: bump=minor kind=feature why=Adds new backup store registry routes and an optional storeId on session requests/responses, a new capability; the response change is additive.
Dropped: 0
Body-Sig: c47e532d774e9114

## Findings

### e7deb111.1 [high] src/dto/backup.dto.ts:389
Anchor: in-diff
Claim: backupSessionResponse now requires storeId (z.string()), and the commit's own run leaves three existing backup- tests red (exact-key assertions in backup-storage.test.ts and backup-restore-session.test.ts), so the backup test gate fails at this commit.
Resolution: not-a-bug | private/account/tests/integration/backup-storage.test.ts:1066 the three exact-key assertions gained storeId in account 0033710, landed with e7deb11 in gitlink c2422a15f; npx vitest run tests/integration/backup- 1002 passed on that tree, so no landed tree has the red | d778be9d 2026-11-07T14:20:59Z

### e7deb111.2 [high] src/services/backup-store-registry.ts:277
Anchor: in-diff
Claim: On re-registration (rotation) of an existing id, the upsert overwrites endpoint and bucket (and kind) with the request's values with no check against live manifests, so any snapshot tagged with that storeId is silently repointed to a different bucket and restores read the wrong store.
Resolution: fixed d7adc45817c7c1b3589c2af77fad5cb2d04df11e | d778be9d 2026-11-07T14:28:29Z

### e7deb111.3 [high] src/services/backup-store-registry.ts:229
Anchor: in-diff
Claim: Registration sends HEAD/PUT/DELETE from the server to any https endpoint the caller names (the schema only checks the https:// prefix, no host allowlist), so a registrant can make the Worker or on-prem server issue requests to internal https hosts (SSRF).
Resolution: fixed 3a80af334d9bbe976ac7b7be0aa554d8f2d7f8bf | d778be9d 2026-11-07T14:28:29Z

### e7deb111.4 [low] src/services/backup-storage.service.ts:521
Anchor: in-diff
Claim: requireSessionPlane falls back to this.requirePlane() (the home plane) when planeForSession returns null; planeForSession currently throws for every non-home store, so this is latent, but a future null return would silently send a customer-store session's bytes to home, contrary to the comment's guarantee.
Resolution: fixed d59ad4780a4abff6f002a571c0c571f94b64c897 | d778be9d 2026-11-07T14:28:29Z
