# Review dd1bae46: fix(backup): scope the restore-session conformance keys, pin /session storeId, classify rollback lines in every locale

Commit: dd1bae46468e5fdbc11e2d1d10abf62d5c0dea35
Repo: console
Branch: 1104-1
Parent: a4afcb47c29ecb936deb2c3bec9b57da183abdd5
Patch-Id: 8351420cdf48861acc22b72ef97e420aeb4309cf
Reviewed-At: 2026-11-07T15:50:40Z
Model: claude-haiku-5-5
Cost: $0.0100 USD, 1 call(s), 71.1s
Diff: 22242 bytes, 5 files, truncated: no
Unreviewed: (none)
Verdict: findings
Attempt: 1
Labels: bump=patch kind=bug,ci why=Fixes store-fault classification for rollback lines and tightens the conformance gate; no new user-facing capability.
Dropped: 0
Body-Sig: 3ec3dac135475c65

## Findings

### dd1bae46.1 [medium] scripts/gates/check-backup-protocol-conformance.ts:117
Anchor: in-diff
Claim: postBodyOf anchors on the first occurrence of '/backups/restore-session' in the speaker, so a mention of that path before the real POST (a comment, a constant, a GET) makes the scan take the next 'body:' of a different request; the restore keys are then checked against the wrong body and the gate can pass while the real body drops storeId.
Resolution: fixed 1a0788d86478593b5ee3ff33c38c8e7259b253b8 | d778be9d 2026-11-07T15:59:13Z

### dd1bae46.2 [medium] scripts/gates/check-backup-protocol-conformance.ts:160
Anchor: in-diff
Claim: The /session leg gains requestScope: sessionRequestStruct, but no self-test control exercises it, so if the sessionRequest struct is dropped or the scope is mis-sliced, the gate's own controls stay green while the /session storeId check changes behaviour.
Resolution: fixed 1a0788d86478593b5ee3ff33c38c8e7259b253b8 | d778be9d 2026-11-07T15:59:13Z

### dd1bae46.3 [medium] packages/cli/src/services/backup/__tests__/backup-store-pick.test.ts:167
Anchor: in-diff
Claim: The 'every locale' parity test iterates a hard-coded list of 13 language codes instead of the catalog directory, so a 14th renet locale with a rollback line is never compared against ROLLBACK_LINES and its copy-out failure is silently classified as a store fault and retried elsewhere.
Resolution: fixed f9408f6b21bf53d9ac4a8cec750c90da600f24fc | d778be9d 2026-11-07T15:59:13Z

### dd1bae46.4 [low] packages/cli/src/services/backup/__tests__/backup-store-pick.test.ts:165
Anchor: in-diff
Claim: The parity test hard-fails when the private/renet checkout is absent, so any run without that path (outside the author's machine) fails rather than skipping or reporting an unrun check.
Resolution: fixed f9408f6b21bf53d9ac4a8cec750c90da600f24fc | d778be9d 2026-11-07T15:59:13Z

### dd1bae46.5 [low] scripts/gates/check-backup-protocol-conformance.ts:591
Anchor: in-diff
Claim: The per-key text choice keys off requestKeys only, so a key listed in both requestKeys and responseKeys on a requestScope leg has its response check run against the request slice; no current leg does this, but it would silently weaken the response check.
Resolution: fixed 1a0788d86478593b5ee3ff33c38c8e7259b253b8 | d778be9d 2026-11-07T15:59:14Z

### dd1bae46.6 [low] packages/cli/src/services/backup-image/store-fetch.ts:187
Anchor: in-diff
Claim: failureOf no longer unwraps `cause` for any error except a marked session refusal, so an error whose HTTP status lives only in `cause` now classifies without its status and may stop being retried on another store; the new test covers only the runRenet case.
Resolution: fixed 1a0788d86478593b5ee3ff33c38c8e7259b253b8 | d778be9d 2026-11-07T15:59:14Z
