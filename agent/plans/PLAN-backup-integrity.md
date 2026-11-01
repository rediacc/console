# PLAN: backup integrity: retention honours verification, every run proves its identity, restore proves the passphrase, failures alert, and a whole image can be proven

Status: approved -- operator ruling 2026-11-01: everything lands in the open PR rediacc/console#602, branch 1023-1, in the same PR; no customers yet, so a clean break with no compatibility shims
Owner: 45048a90
Priority: P1 -- repeated bad nights can evict every good version, a replaced or unopenable image can be stored or restored as success, a bad chunk is never repaired, and no failure reaches a person
Depends-On: no-dep -- every code box is inside this plan; box H5 closes box N4b of agent/plans/PLAN-backup-program.md, and H1 supplies the live read that box R1 of that plan asks for
Concurrency: parallel -- eight writers (A, G, K, L, V, C, S, D) with disjoint Owns; order in "Writer split and order"; wire shapes are fixed in Design so writers do not wait on each other to compile
Owns: agent/plans/PLAN-backup-integrity.md, private/account/drizzle/0073_backup_integrity.sql, private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts, private/account/src/dto/backup.dto.ts, private/account/src/errors.ts, private/account/src/routes/backups.ts, private/account/src/routes/configs.ts, private/account/src/entry/on-premise.ts, private/account/src/services/backup-storage.service.ts, private/account/src/services/backup-store-conformance.ts, private/account/src/services/backup-gc.service.ts, private/account/src/services/backup-refset.ts, private/account/src/services/backup-merkle.ts, private/account/src/services/notification.service.ts, private/account/src/services/email.service.ts, private/account/src/services/reminder.service.ts, private/account/src/services/communication.service.ts, private/account/src/types/communication.ts, private/account/src/email/templates/security.ts, private/account/web/src/api/types.ts, private/account/web/src/pages/Notifications.tsx, private/account/tests/integration/backup-*.test.ts, private/renet/pkg/chunkstore/**, private/renet/pkg/luks/**, private/renet/pkg/repository/mount.go, private/renet/pkg/orchestration/workflows.go, private/renet/pkg/credentials/**, private/renet/pkg/functions/executor_local.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/backupstate/**, private/renet/pkg/list/**, private/renet/pkg/i18n/**, private/renet/cmd/renet/backup_*.go, private/renet/cmd/renet/repository_limits.go, packages/cli/src/commands/backup-*.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/status.ts, packages/cli/src/commands/__tests__/backup-*.test.ts, packages/cli/src/services/jobs/**, packages/cli/src/services/backup/**, packages/cli/src/services/__tests__/backup-*.test.ts, packages/cli/src/config/command-metadata.ts, packages/cli/src/config/command-planes.ts, packages/cli/src/config/__tests__/plane-coverage.test.ts, packages/cli/src/i18n/locales/**, packages/shared/src/backup/**, packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/renet-contract/data/**, packages/shared/src/cli-contract/**, packages/www/src/content/docs/*/backup-restore.md, packages/www/src/content/docs/*/cli-application.md, docs/backup-storage/07-execution-record.md, .ci/rediacc_ci/drills/backup.py, .ci/rediacc_ci/drills/backup_renet.py, .ci/rediacc_ci/drills/backup_roundtrip.py, .ci/rediacc_ci/drills/backup_onprem.py, private/account (gitlink), private/renet (gitlink)
Live-Proof: bench, hostinger -- vm:check and both backup drills before the merge; bench proves the account surface after the edge deploy; hostinger proves the released renet after the release, read-only or on copies only
Updated: 2026-11-01
Worklist: #11c0d336, #f5f6ef74
First-Seen: 2026-11-01

## Findings as verified, with corrections

Each finding below was checked against the code on 2026-11-01. F1 to F13 are the brief's numbering. Anything still unproven is listed under Hypotheses.

- F1. `retentionKeepSet` (private/account/src/services/backup-gc.service.ts:3813) and `streamRetentionKeepSet` (:3861) keep the newest 3 per stream by position. `backup_manifests` (private/account/src/db/schema.ts:1540) has no verification column.
- F2. `validateRepoIdentity` (private/renet/cmd/renet/repository_limits.go:125-144) fails open when `cryptsetup luksUUID` errors.
  - Sibling: the same fail-open logic is at private/renet/pkg/functions/executor_local.go:617-625.
  - `ReadLUKSIdentity` (private/renet/pkg/chunkstore/luksid.go:54) already reads the UUID and key digest with no cryptsetup.
  - `BackupSessionPrincipal` (private/account/src/services/backup-storage.service.ts:141-153) carries no repository guid, and `getOrCreateStream` (:726) takes it from the client. The licence blob does carry it (private/renet/pkg/license/types.go:15). Commit only HEADs the manifest, so nothing compares its body with the commit input.
  - A passphrase change keeps the UUID and key digest, and only a re-encryption moves them (private/renet/pkg/chunkstore/luksid.go:21-26). The identity check therefore stops replaced images and re-encryptions, and a passphrase change passes it.
- F3. `verifyRestoredImage` (private/renet/cmd/renet/backup_restore.go:471-485) proves only size and the LUKS shape. `BackupRestoreCommand.Build` passes no passphrase. A snapshot taken before a passphrase change opens only with the old passphrase, so a failed test-open does not always mean a bad image.
- F4. private/renet/pkg/chunkstore/grants.go:590-593 reads 409 like 412. The comments at :389 and :429-437 repeat the claim, and :605 says proven on R2 while docs/backup-storage/07-execution-record.md:159 says tier B never ran. `recordUploaded` (private/renet/pkg/chunkstore/uploader.go:704) counts a 412 as uploaded. A manual probe already exists at private/elite/scripts/s3-conformance-probe.sh, and it checks If-None-Match; drill leg n covers the checksum.
- F5. Mount returns nil when already mounted (private/renet/pkg/repository/mount.go:112-115). Provisioning runs at three sites (private/renet/pkg/orchestration/workflows.go:352, :593, :687), and `WriteTOCPublicKey` overwrites silently (private/renet/pkg/credentials/tocpub.go:60-66). Two siblings:
  - `Repository.ValidatePassword` answers nil whenever the device is open (private/renet/pkg/repository/mount.go:503-506), so it cannot be the proof as written.
  - `KeyfileStore.Refresh` overwrites the keyfile (private/renet/pkg/credentials/keyfile.go:193) before the password has authorised anything (:197-202).
- F6. No verb changes a LUKS passphrase: a search of renet and the CLI finds none outside tests. Re-issue is therefore driven by a detected mismatch, not by a password-change hook. The machine's lineage is the licence's grandGuid (private/renet/pkg/orchestration/workflows.go:1246-1251), so the CLI's lineage must agree with it or the install must refuse.
- F7. Confirmed at private/renet/pkg/chunkstore/anchor.go:15-67 and private/renet/pkg/functions/commands/backup.go:654-680. Sibling: the `--level full` loop (private/renet/cmd/renet/backup_verify.go, the HashCell loop) has no read cap either.
- F8. Confirmed at packages/cli/src/services/jobs/steps.ts:234-237, private/renet/cmd/renet/backup_verify.go:111-115 and packages/cli/src/commands/backup-storage.ts:394 and :433-441.
- F9. The health signal travels `backupstate.Record` (private/renet/cmd/renet/backup_snapshot.go:397), then `loadBackupCoverage` (private/renet/pkg/list/list.go:170), then vault status, then `applyStaleness` (packages/cli/src/commands/machine/health.ts:159). The reusable customer channel is `NotificationService` (private/account/src/services/notification.service.ts) through the `hasSent`/`markSent` digest pattern (private/account/src/services/reminder.service.ts:276-316), with a `productOrg` preference and the portal page private/account/web/src/pages/Notifications.tsx.
- F10. Confirmed: the whole-image comparison exists only in .ci/rediacc_ci/drills/backup_roundtrip.py:287.
- F11. Confirmed: restore aborts on the first bad cell (private/renet/pkg/chunkstore/restore.go:225, :231).
- F12. `lineageReferencedHashes` (private/account/src/services/backup-gc.service.ts:2985) re-reads every manifest on each `--store` page. The same read happens on every `verifyHeadsSweep` visit (:3041), under the 300-call subscription budget.
- F13.
  - The envelope refusal is correct by the clean break, and it is a release-order fact. The header arrived in commit 9d0172906 on 2026-10-27, and v2.4.0, the newest tag, was cut on 2026-10-23 and does not contain it (`git merge-base --is-ancestor` confirms). The server refusal (private/account/src/routes/configs.ts:153-163) reached eu first.
  - The message misleads: "written by rdc >= 1.4.0" reads as satisfied by 2.4.0.
  - `strategy list` uses only `outputService.info`, which writes prose to stderr (packages/cli/src/services/core/output.ts:172-179, :353), so stdout is empty in every format.

## Design

### D-state. Verification state and what it means
`backup_manifests.verification_state` is one of:

| State | Set by | Proves |
|---|---|---|
| `unverified` | commit, the migration default | nothing yet |
| `verified` | post-run spot, `--deep`, or a clean full `--store` pass | machine anchor or store chunks match; not that the filesystem is sound |
| `proven` | `rdc backup check` test-open and one-file restore, or restore test | the passphrase opens real content |
| `failed` | spot, deep or store failure | do not rely on it |

A `failed` verdict sticks until a passing check that read what it was about: `full` or `deep` clears `spot`, `full` and `deep`; `store` clears those and `store`; `test-open` clears `test-open`; `restore-test` clears anything; `spot` clears nothing, since it samples other cells. `verificationClearsFailure` (private/account/src/services/backup-gc.service.ts) holds the table, and a new snapshot starts `unverified`. A machine session records only `spot`, `full` or `deep`.

Retention keeps, per stream, the positional floor plus the newest `verified` and the newest `proven` that are not `failed`. That adds at most two snapshots per stream. Attestation can only keep more data, never less, so a machine session's report cannot cause loss, and the kept bytes stay billed.

### D-wire. Wire shapes, fixed here
- Session mint stores `repository_guid` from the licence.
- `POST /backups/streams` also answers `previous: { snapshotId, luksUuid, luksKeyDigest, imageBytes, verificationState } | null`.
- `POST /backups/commit` adds:
  - `luksUuid`, `luksKeyDigest` (required when the image is LUKS);
  - `cellsRoot`, required on new manifests;
  - `identityChangeAccepted` (optional boolean);
  - `chunksAlreadyPresent` (integer; above 0 sets `reconcile_due_at`).
- Commit adds these error codes: `BACKUP_STREAM_MISMATCH`, `BACKUP_MANIFEST_BODY_MISMATCH`, `BACKUP_IDENTITY_CHANGED`.
- New routes:
  - `POST /backups/reports` (session): `{ kind: 'snapshot'|'verify', snapshotId?, level?, status, reason?, nextExpectedAt? }`.
  - `POST /backups/snapshots/:id/verification` (token, `backup:read`): `{ level: 'test-open'|'restore-test', status }`.
  - `POST /backups/chunks/repair` (token, `backup:manage` plus `requireManagerCreator`): `{ lineageGuid, hashes, dryRun }`, answering `{ deleted, stillGood, absent, affectedSnapshots }`.
- New renet records:
  - The verify record gains `reported`.
  - The snapshot record gains `indexStatus: 'sealed'|'no-key'|'no-listing-source'|'failed'`.
  - The restore record gains `passphraseCheck: 'opened'|'refused'|'not-available'`.

The account DTOs are non-strict, so a new renet talks to an old account without error. An old renet against a new account fails its commit on the missing required fields. The rollout order below prevents that, so no shim is written.

### D-identity. What the server can and cannot bind (F2)
The server **can** bind:
- a session to the licence's repository and lineage;
- a stream row to subscription, lineage, machine and repository;
- a manifest body to the commit input (one GET, already size-capped: snapshot id, lineage, repository, image bytes, cell bytes);
- a commit's declared LUKS identity to the previous row of that stream.

The last check catches a lost machine journal, which the machine alone cannot catch.

The server **cannot** prove that declared identity matches the bytes without reading the header chunk, and it cannot judge the filesystem inside the container. The declared UUID is not new exposure: the licence already carries `luksUuid`, and the header bytes are in the bucket.

**Rule on the machine for each hot and cold run:**
1. Read the identity from the image with `ReadLUKSIdentity`.
2. Compare it with the journal anchor, the licence's `LuksUUID` when set, and the server's `previous`.
3. A UUID or key digest change, or an unreadable header where a previous identity or licence names one, ends the run with status `identity-changed`, no upload, and a failed exit.
4. A size shrink ends the run the same way. Growth with the same identity passes and is recorded, because `repository_expand` is legitimate.

No previous identity means this is the baseline, and the run says so in its record. The explicit path is `--accept-identity-change` on the verb, the function and `rdc backup snapshot`. It forces a full manifest with no parent. A scheduled unit never carries it.

### D-root. Merkle root (F10)
`cellsRoot` is computed over the snapshot's resolved inventory:
- Leaf: SHA-256(0x00 || "rediacc-cells-v1" || u64be(index) || cell hash).
- Zero leaf: the same, with the fixed value SHA-256("rediacc-zero-cell-v1") in place of the hash.
- Node: SHA-256(0x01 || L || R), with RFC 6962 splitting.
- Root: SHA-256(0x03 || u64be(cellBytes) || u64be(imageBytes) || tree root).

The field is additive in the manifest JSON, so `ManifestVersion` stays 1 and `DecodeManifest` still reads hostinger's existing manifests, which report the root as absent. Anyone holding the manifests can recompute it, which catches corruption and chain mix-ups but does not resist a tampering store. Signing needs a key the server does not hold (decision O3).

### D-repair. What is safe (F11)
- **Deleting a chunk.** A chunk's key is the hash of its bytes, so an object whose bytes do not hash to its key can never satisfy a restore. Deleting it after a server-side rehash in the same call loses nothing. The repair route refuses when the lineage has a live lease, re-reads each object immediately before deleting, and never deletes one that now hashes correctly (`stillGood`). It sets `reconcile_due_at`.
- **Re-upload.** It reads the cell from the anchor and re-hashes it before the PUT. A hash absent from the machine's anchors cannot be repaired there. The answer names the affected snapshots and marks them `failed`.
- **Salvage.** It restores only under `--as <new name>`, never over an existing repository, writes bad cells as holes, reports them with byte ranges, exits non-zero with status `restored-damaged`, and never records the result as an anchor. A bad cell inside the LUKS header makes the image unopenable, and the report says so. `restore --path` already avoids unselected cells, so one file away from a bad cell restores cleanly.

`exists` stays HEAD-only: a store-wide content check at exists time is not affordable, so detection belongs to the verify ladder.

### D-alert. The alert path (F9)
Inputs:
- A machine report of a failed run or failed verify. `OnFailure=` covers a crash, and `POST /backups/reports` carries the status.
- A dead-man check: a stream whose `nextExpectedAt` has passed by more than the grace period, which catches a machine that cannot report.
- Sweep failures from `report.verify`, plus unreadable lineages and failed maintenance.
- An `index_regressed` commit (`hasIndex` flipped from 1 to 0 within a stream).

Output: one digest per subscription per day through `NotificationService`, under a new `backupHealth` `productOrg` preference defaulting to on, sent to the same recipients as the repo expiry digest. The pull path is `rdc machine health`, where a failed verify becomes a warning and a non-zero exit.

The hostinger observability stack is not a dependency, since it is one customer repository and could not alert on the machine it runs on (decision O5).

### D-policy. Verification schedule (F12)

| Check | Where it runs | Default | FREE, COMMUNITY | PROFESSIONAL | BUSINESS, ENTERPRISE |
|---|---|---|---|---|---|
| Spot, random cells | unit, after each run | on | on | on | on |
| `--deep`, one repo per night | machine timer | on | on | on | on |
| HEAD sweep | account maintenance | 100 per visit | yes | yes | yes |
| Sampled rehash | account maintenance | 3 per 7 days | 3 per 7 days | plus rolling 500 chunks per month | plus rolling 1000 chunks per month |
| Full `--store` | CLI, on demand | manual | manual | manual | manual |
| Test-open and one-file restore | `rdc backup check`, where the passphrase lives | monthly | documented | documented | documented |
| Restore test | `rdc backup verify --restore-test` | quarterly | documented | documented | documented |

- One repo per night is weekly only up to 7 repos: the cycle is max(7, repo count) nights, 11 nights on hostinger, and the record names it.
- A rolling 1000 chunks covers 4 GiB a month, which is a real sample and not a full pass. A full pass stays `--store`.
- Machine checks spend the customer's own CPU, so they do not vary by plan. Rolling samples spend server budget, so they do.
- The scheduled unit holds no passphrase by design (private/renet/cmd/renet/backup_snapshot_toc.go:35-39), so the two passphrase checks are a CLI verb the operator's own scheduler runs (decision O6).

### D-rollout. Order across the merge
1. Merge, then edge deploy; `H` boxes wait.
2. Bench proof on edge.
3. Release of the CLI and renet. This also resolves F13.
4. Re-deploy hostinger's schedule with the released CLI and renet, against the still-old stable account. The non-strict DTOs ignore the new fields, and a 404 on `/backups/reports` is a logged non-fatal outcome.
5. Stable eu account deploy. Migration 0073 goes through `wrangler d1 migrations apply` in `rediacc_ci.deploy.deploy_account`, after the CD clone check `rediacc_ci.deploy.test_d1_migrations`.

Reversing steps 4 and 5 would make hostinger's nightly commit fail on the missing fields.

## Writer split and order

- Writer A (account core): A1 first, then A2-A6.
- Writer G (account GC and alerts): G1-G5, after A1; G3 also after K3.
- Writer K (chunkstore): K1-K5.
- Writer L (LUKS and mount): L1-L4.
- Writer V (verbs and functions): V1 after K5; V2 and V5 after L1, L2, L4; V3, V4, V6 after K1-K4.
- Writer C (CLI verbs): C1 and C2 after V3; C3 after V2; C4 after V6; C5 after A3 and V2.
- Writer S (schedule and TOC key): S1 after L4; S2 after V5; S3 after V3 and V4.
- Writer D (artifacts, docs, drills): D1-D3 after every writer above has landed; D4 alongside.

Control rule: every new test fails without its fix. Each tick note records the test name and rc 1 from the tree with the fix stashed and the test kept. A box whose test passes on the unfixed tree is not done.

## Boxes

### A: account core (writer A)

- [x] A1: Migration 0073 and schema: `backup_manifests` gains `verification_state` (NOT NULL default `unverified`), `verification_level`, `verified_at`, `luks_uuid`, `luks_key_digest`, `cells_root`, `index_regressed`; `backup_sessions` gains `repository_guid`; `backup_lineage_usage` gains `store_verify_cursor`, `store_verify_started_at`, `store_verify_failures`, `sample_cursor`; a new table `backup_stream_status` holds stream id, last run at, status and reason, next expected at, last verify at and status. None of these writes moves the lineage `updatedAt` chunk GC compares.
  - Owns: private/account/drizzle/0073_backup_integrity.sql, private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts, private/account/tests/integration/backup-integrity-schema.test.ts
  - Test: `backup-integrity-schema.test.ts` applies every migration and asserts the columns and the default on a row inserted before 0073.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-integrity-schema.test.ts && npm run typecheck` rc 0. The clone check runs in CD (`rediacc_ci.deploy.test_d1_migrations`); P4 records it.
    (ticked) 2026-11-01T21:46:28Z by 45048a90: commit:private/account 239521c and 7aaddb9. Each new test recorded rc 1 before its fix in the writer report; the lead reran account vitest, 3212 of 3212 rc=0.
- [x] A2: Bind session, stream and manifest at commit (F2), per D-identity.
  - Owns: private/account/src/dto/backup.dto.ts, private/account/src/errors.ts, private/account/src/services/backup-storage.service.ts, private/account/src/routes/backups.ts, private/account/tests/integration/backup-commit-binding.test.ts
  - Tests: another repository's guid on `/streams`; a commit naming another machine's stream; a manifest whose `imageBytes` differs from `totalBytes`; a changed LUKS digest refused and then accepted with `identityChangeAccepted`, with the accepted case requiring no parent; `previous` returned; `chunksAlreadyPresent` above 0 sets `reconcile_due_at`.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-commit-binding.test.ts tests/integration/backup-storage.test.ts tests/integration/backup-lifecycle.test.ts` rc 0.
    (ticked) 2026-11-01T21:46:31Z by 45048a90: commit:private/account 239521c and 7aaddb9. Each new test recorded rc 1 before its fix in the writer report; the lead reran account vitest, 3212 of 3212 rc=0.
- [x] A3: Reports and verification routes (F1, F9), and `hasIndex` flip detection at commit, comparing with the stream's previous row. The commit response carries `indexRegressed`.
  - Owns: as A2, plus private/account/tests/integration/backup-reports.test.ts
  - Tests: a report naming another stream refused; `failed` then `verified` state moves; a restore session refused; a flip logs `backup_index_regressed` and sets the column, with a control that 0 to 0 does not.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-reports.test.ts` rc 0.
    (ticked) 2026-11-01T21:46:34Z by 45048a90: commit:private/account 239521c and 7aaddb9. Each new test recorded rc 1 before its fix in the writer report; the lead reran account vitest, 3212 of 3212 rc=0.
- [x] A4: Repair route per D-repair and D-wire, delegating to G5's `repairChunks`.
  - Owns: private/account/src/routes/backups.ts, private/account/tests/integration/backup-repair-route.test.ts
  - Tests: scope refusal for a read token, 404 outside team scope, `dryRun` writes nothing.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-repair-route.test.ts` rc 0.
    (ticked) 2026-11-01T21:46:36Z by 45048a90: commit:private/account 239521c and 7aaddb9. Each new test recorded rc 1 before its fix in the writer report; the lead reran account vitest, 3212 of 3212 rc=0.
- [x] A5: The envelope refusal tells the truth (F13): a request with no header says this rdc predates `x-config-envelope`, which first ships in the release after 2.4.0, and it stops citing the 1.4.0 write version. The status and code stay the same, and no server compatibility is added.
  - Owns: private/account/src/routes/configs.ts, private/account/tests/integration/config-envelope-message.test.ts
  - Test: the header-less message names the header and 2.4.0; the below-version message still reads `this rdc reads up to v<n>`.
  - Accept: `cd private/account && npx vitest run tests/integration/config-envelope-message.test.ts` rc 0.
    (ticked) 2026-11-01T21:46:39Z by 45048a90: commit:private/account 239521c and 7aaddb9. Each new test recorded rc 1 before its fix in the writer report; the lead reran account vitest, 3212 of 3212 rc=0.
- [x] A6: Store conformance preflight (F4): `checkStoreConformance` probes a private key under the plane's own prefix through the presigned path renet uses: a duplicate create-only PUT must answer 412, a wrong checksum must be refused, then the probe deletes its key. It runs at on-prem boot and once per deployment on the first grant, and the result is cached. The behaviour on failure follows decision O4.
  - Owns: private/account/src/services/backup-store-conformance.ts, private/account/src/entry/on-premise.ts, private/account/src/services/backup-storage.service.ts, private/account/tests/integration/backup-store-conformance.test.ts
  - Tests: a fake store ignoring If-None-Match, a fake store ignoring the checksum, a conforming store; the probe key never remains.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-store-conformance.test.ts` rc 0.
    (ticked) 2026-11-01T21:46:41Z by 45048a90: commit:private/account 239521c and 7aaddb9. Each new test recorded rc 1 before its fix in the writer report; the lead reran account vitest, 3212 of 3212 rc=0.

### G: account GC and alerts (writer G)

- [x] G1: Retention honours verification (F1): both keep-set functions add each stream's newest `verified` and newest `proven` that are not `failed`, and the preview names the reason a snapshot is kept. `DELETE /snapshots/:id` refuses those two as `BACKUP_SNAPSHOT_IS_LAST_VERIFIED`, alongside the anchor refusal at private/account/src/services/backup-gc.service.ts:2738. The orphan-expiry purge is unchanged and says so in a comment.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-retention-verified.test.ts
  - Tests: five bad nights after one verified snapshot with `keepLast: 1`, so the verified one survives (its delta chain collapses correctly) and restores; a `failed` snapshot is never pinned; a stream with no verified snapshot keeps the floor and logs `backup_stream_unverified`.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-retention-verified.test.ts tests/integration/backup-gc.test.ts` rc 0.
    (ticked) 2026-11-01T22:33:15Z by 45048a90: commit:private/account e5a7f09. Each new test recorded rc 1 before its fix or under a mutant in the writer report; the lead reran account vitest, 3329 of 3329 rc=0. Live delivery of the digest stays with box B1.
- [x] G2: One read of the referenced set (F12): `backup-refset.ts` keeps a sorted reference-set object at `t/<sub>/l/<lineage>/v/refset`, keyed by a digest of the manifest row set and built resumably under budget. `verifyLineageChunks`, `verifyHeadsSweep` and `verifySampleSweep` read that one object instead of M manifests. GC and purge must treat `v/` correctly, and a test proves purge removes it and the ledger ignores it.
  - Owns: private/account/src/services/backup-refset.ts, private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-refset.test.ts
  - Tests: a lineage of 800 manifests walks a full `--store` pass with every page at or under 1000 store calls, counted by a metered store; a lineage over 300 manifests still advances its HEAD cursor across visits; a new commit invalidates the set; a missing manifest still answers 409.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-refset.test.ts tests/integration/backup-verify-reconcile.test.ts` rc 0.
    (ticked) 2026-11-01T22:33:17Z by 45048a90: commit:private/account e5a7f09. Each new test recorded rc 1 before its fix or under a mutant in the writer report; the lead reran account vitest, 3329 of 3329 rc=0. Live delivery of the digest stays with box B1.
- [x] G3: A `--store` pass sets verification state (F1, F10, F12): the persisted cursor tracks a pass from `after: null` to the last page, and a page out of order restarts it. A clean full pass marks the lineage's manifests `verified`. A corrupt or missing hash marks every manifest referencing it `failed`. The last page recomputes `cellsRoot` through `backup-merkle.ts` up to `BACKUP_COLLAPSE_MAX_CELLS` and names a root it skipped. The collapse keeps the root unchanged. The rolling monthly sample follows D-policy.
  - Owns: private/account/src/services/backup-merkle.ts, private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-store-pass.test.ts, private/account/tests/fixtures/cells-root-vectors.json
  - Tests: state moves; a skipped page does not mark verified; TS root equals K3's Go vectors, including the zero leaf; a promote-to-full keeps the root.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-store-pass.test.ts` rc 0.
    (ticked) 2026-11-01T22:33:20Z by 45048a90: commit:private/account e5a7f09. Each new test recorded rc 1 before its fix or under a mutant in the writer report; the lead reran account vitest, 3329 of 3329 rc=0. Live delivery of the digest stays with box B1.
- [x] G4: The alert phase (F9), per D-alert: `backupHealth` preference, digest template, `NotificationService.sendBackupHealthDigest`, one send per subscription per day through `hasSent`/`markSent`, a run at the end of `runMaintenance`, and the portal toggle.
  - Owns: private/account/src/services/notification.service.ts, private/account/src/services/email.service.ts, private/account/src/services/reminder.service.ts, private/account/src/services/communication.service.ts, private/account/src/types/communication.ts, private/account/src/email/templates/security.ts, private/account/web/src/api/types.ts, private/account/web/src/pages/Notifications.tsx, private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-alerts.test.ts
  - Tests: each input sends once and a repeat the same day does not; a healthy subscription sends nothing; a stream past `nextExpectedAt` alerts; the preference off suppresses; a send failure does not fail maintenance.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-alerts.test.ts && npm run typecheck && npm run lint` rc 0, and `npm run check:ci-test-account-web` rc 0.
    (ticked) 2026-11-01T22:33:22Z by 45048a90: commit:private/account e5a7f09. Each new test recorded rc 1 before its fix or under a mutant in the writer report; the lead reran account vitest, 3329 of 3329 rc=0. Live delivery of the digest stays with box B1.
- [x] G5: `repairChunks` per D-repair.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-repair.test.ts
  - Tests: a corrupt object deleted; a good one kept as `stillGood`, even when named; a live lease refused; `reconcile_due_at` set; affected snapshots named.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-repair.test.ts` rc 0.
    (ticked) 2026-11-01T22:33:25Z by 45048a90: commit:private/account e5a7f09. Each new test recorded rc 1 before its fix or under a mutant in the writer report; the lead reran account vitest, 3329 of 3329 rc=0. Live delivery of the digest stays with box B1.

### K: renet chunkstore (writer K)

- [x] K1: 409 is a retryable conflict and 412 means exists, for every object kind (F4). `Put` reports created or already-present, `ChunksUploaded` and `BytesUploaded` count only created objects, and `ChunksAlreadyPresent` travels on the commit. The comments at private/renet/pkg/chunkstore/grants.go:389, :429-437, :605 and the retry note are rewritten: the conditional-write claim names the proof that actually ran.
  - Owns: private/renet/pkg/chunkstore/grants.go, private/renet/pkg/chunkstore/uploader.go, private/renet/pkg/chunkstore/session.go, private/renet/pkg/chunkstore/createonly_put_test.go, private/renet/pkg/chunkstore/put_retry_test.go
  - Tests: `TestPut_409ThenCreatedRetriesAndUploads`, `TestPut_409ExhaustedFails`, `TestPut_412ChunkIsPresentNotUploaded`, `TestPut_412ManifestStaysFatal`, `TestUpload_AddedBytesExcludeAlreadyPresent`.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'TestPut_|TestUpload_AddedBytes' -count=1` rc 0, and `go test ./pkg/chunkstore/ -count=1` rc 0.
    (ticked) 2026-11-01T21:45:00Z by 45048a90: commit:private/renet 9101f6b. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.
- [x] K2: Random spot cells per run (F7): `VerifyAnchor` picks 8 non-zero cells with crypto/rand from `CellHashes` at each call. `BuildSpotSample` and the `SpotSample` journal field are removed, with no reader kept. A test seam fixes the source.
  - Owns: private/renet/pkg/chunkstore/anchor.go, private/renet/pkg/chunkstore/journal.go, private/renet/pkg/chunkstore/anchor_test.go, private/renet/pkg/chunkstore/journal_test.go
  - Tests: `TestVerifyAnchor_SingleBadCellFoundAcrossRuns` (one bad cell of 64, found within a bounded number of runs at a fixed seed; the deterministic sampler never finds it); `TestVerifyAnchor_PicksDifferentCellsPerRun`.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'TestVerifyAnchor_' -count=1` rc 0, and `go test ./pkg/chunkstore/ ./cmd/renet/ -count=1` rc 0.
    (ticked) 2026-11-01T21:45:03Z by 45048a90: commit:private/renet 9101f6b. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.
- [x] K3: Merkle root per D-root: `CellsRoot(cells, cellBytes, imageBytes)`, the additive manifest field, computation at snapshot over the resolved inventory, and a comparison in restore that fails on a mismatch and reports an absent root plainly. Vectors at `pkg/chunkstore/testdata/cells_root_vectors.json`.
  - Owns: private/renet/pkg/chunkstore/manifest.go, private/renet/pkg/chunkstore/cellsroot.go, private/renet/pkg/chunkstore/cellsroot_test.go, private/renet/pkg/chunkstore/testdata/cells_root_vectors.json, private/renet/pkg/chunkstore/restore.go
  - Tests: domain separation (a zero leaf differs from any hash leaf; index moves change the root; an internal node cannot pose as a leaf); known answers; a v1 manifest with no root decodes and reports absent; a restore over a swapped chain member fails.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'CellsRoot|TestRestore_CellsRoot' -count=1` rc 0.
    (ticked) 2026-11-01T21:45:06Z by 45048a90: commit:private/renet 9101f6b. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.
- [x] K4: Salvage and repair upload per D-repair: `RestoreOptions.Salvage` continues past a bad or absent chunk and returns bad cells with byte ranges; `RepairUpload(anchor, hashes, grants)` re-reads, re-hashes and PUTs, and returns unrepairable hashes.
  - Owns: private/renet/pkg/chunkstore/download.go, private/renet/pkg/chunkstore/restore.go, private/renet/pkg/chunkstore/repair.go, private/renet/pkg/chunkstore/repair_test.go, private/renet/pkg/chunkstore/restore_test.go
  - Tests: one corrupt cell, default still aborts; salvage returns the cell, its range and a hole; salvage writes no anchor; a re-read whose hash disagrees is not uploaded.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'TestRestore_Salvage|TestRepairUpload' -count=1` rc 0.
    (ticked) 2026-11-01T21:45:09Z by 45048a90: commit:private/renet 9101f6b. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.
- [x] K5: Identity on the anchor (F2): `AnchorRecord` gains `LuksUUID` and `LuksKeyDigest`, and `CompareImageIdentity(prev, cur)` returns one named verdict. `RecordRestoredAnchor` records the restored image's identity. The manifest carries the same two fields for the server.
  - Owns: private/renet/pkg/chunkstore/journal.go, private/renet/pkg/chunkstore/luksid.go, private/renet/pkg/chunkstore/luksid_test.go, private/renet/pkg/chunkstore/restore_anchor_linux.go, private/renet/pkg/chunkstore/manifest.go
  - Tests: every verdict (same; UUID moved; digest moved; shrink; growth; unreadable; no baseline); a restored anchor carries the restored identity.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'CompareImageIdentity|RecordRestoredAnchor' -count=1` rc 0.
    (ticked) 2026-11-01T21:45:12Z by 45048a90: commit:private/renet 9101f6b. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.

K1 and K4 both touch `uploader.go` or `restore.go` only where stated, and writer K sequences its own boxes.

### L: renet LUKS and mount (writer L)

- [x] L1: `Device.TestPassphrase(ctx, password)` uses `cryptsetup open --test-passphrase` with no mapping. `Repository.ValidatePassword` uses it whether or not the device is open.
  - Owns: private/renet/pkg/luks/luks.go, private/renet/pkg/luks/luks_passphrase_test.go, private/renet/pkg/repository/mount.go, private/renet/pkg/repository/mount_password_test.go
  - Tests: a fake cryptsetup asserts the arguments and that the secret travels on stdin, never argv; `TestValidatePassword_OpenDeviceWrongPasswordRefused`.
  - Accept: `cd private/renet && go test ./pkg/luks/ ./pkg/repository/ -run 'TestPassphrase|TestValidatePassword' -count=1` rc 0.
    (ticked) 2026-11-01T21:45:15Z by 45048a90: commit:private/renet b1895f2. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.
- [x] L2: Only a proven password writes a key (F5): `provisionTOCPublicKey` at all three sites checks `have == want` first, which costs no KDF, and otherwise proves the password through L1. An unproven password writes nothing and logs a warning that names the repository. A replacement after proof logs a warning. `WriteTOCPublicKey` becomes `InstallTOCPublicKey(datastore, guid, pubLine, replace)`, used by V5 too. `KeyfileStore.Refresh` proves the password first and installs the new keyfile by temp file and rename only after the slot accepts it.
  - Owns: private/renet/pkg/orchestration/workflows.go, private/renet/pkg/orchestration/workflows_tockey_test.go, private/renet/pkg/credentials/tocpub.go, private/renet/pkg/credentials/tocpub_test.go, private/renet/pkg/credentials/keyfile.go, private/renet/pkg/credentials/keyfile_test.go
  - Tests: `TestMountWithDocker_AlreadyMountedWrongPasswordKeepsTOCKey` (the headline control), a right password on a missing key installs, `TestRefresh_WrongPasswordLeavesKeyfile`.
  - Accept: `cd private/renet && go test ./pkg/orchestration/ ./pkg/credentials/ -run 'TOCKey|TOCPublic|TestRefresh' -count=1` rc 0.
    (ticked) 2026-11-01T21:45:17Z by 45048a90: commit:private/renet b1895f2. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.
- [x] L3: Identity checks fail closed (F2): one helper built on `ReadLUKSIdentity` replaces the cryptsetup read at private/renet/cmd/renet/repository_limits.go:134 and private/renet/pkg/functions/executor_local.go:617-625. A licence naming a UUID with no readable header is a mismatch. A licence naming none, on a plain image, passes.
  - Owns: private/renet/cmd/renet/repository_limits.go, private/renet/cmd/renet/repository_limits_identity_test.go, private/renet/pkg/functions/executor_local.go, private/renet/pkg/functions/executor_local_identity_test.go
  - Tests: an unreadable header with a licensed UUID refuses at both sites; a matching UUID passes; a plain image with no licensed UUID passes.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/functions/ -run 'Identity' -count=1` rc 0.
    (ticked) 2026-11-01T21:45:20Z by 45048a90: commit:private/renet b1895f2. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.
- [x] L4: TOC key vectors (F6): a generated, committed `testdata/toc_key_vectors.json` covering generated-shape passphrases, a non-ASCII passphrase and two lineages, with a Go test holding `DeriveKeyPair` and `MarshalPublicKey` to it.
  - Owns: private/renet/pkg/chunkstore/toccrypt/toccrypt_test.go, private/renet/pkg/chunkstore/toccrypt/testdata/toc_key_vectors.json
  - Accept: `cd private/renet && go test ./pkg/chunkstore/toccrypt/ -count=1` rc 0.
    (ticked) 2026-11-01T21:45:23Z by 45048a90: commit:private/renet b1895f2. Each new test recorded rc 1 before its fix in the writer report, and the lead reran the suite rc=0: account vitest 3212 of 3212; renet go test -race over the touched packages.

### V: renet verbs and functions (writer V)

- [x] V1: Every run validates identity (F2), per D-identity, before planning and again on the staged copy; status `identity-changed`, flag `--accept-identity-change`, function param `accept_identity_change`. The stream's `previous` joins the comparison.
  - Owns: private/renet/cmd/renet/backup_snapshot.go, private/renet/cmd/renet/backup_snapshot_identity_test.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_snapshot_bwlimit_test.go
  - Tests: a swapped image on a hot run refused with no upload (the fake plane sees no grant); journal lost with server `previous` differing also refused; the flag forces a full manifest; the unit argv never carries it; the staged-copy recheck catches a swap between checks.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/functions/commands/ -run 'TestBackupSnapshot' -count=1` rc 0.
    (ticked) 2026-11-01T22:50:26Z by 45048a90: commit:private/renet f119c9d. Tests recorded rc 1 before the fix in the writer report, apart from the guards named there as weak; the lead reran go test -race, rc=0.
- [x] V2: Restore proves the passphrase (F3): `backup_restore` takes the credential on stdin (`--password-stdin`) and runs test-open on the staged file before the rename. The record states `passphraseCheck`. A refusal keeps the staged file and places nothing, per decision O2 (`--allow-unopenable`). With no passphrase the restore says plainly it could not check. Sibling: `backup pull` runs the same step when it has a password.
  - Owns: private/renet/cmd/renet/backup_restore.go, private/renet/cmd/renet/backup_restore_passphrase_test.go, private/renet/cmd/renet/backup_pull.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_restore_test.go
  - Tests: wrong passphrase, nothing placed, failed status; right one, `opened`; none, `not-available` and the record says so; the secret never appears in argv or logs.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/functions/commands/ -run 'TestBackupRestore|TestRestorePassphrase' -count=1` rc 0.
    (ticked) 2026-11-01T22:50:28Z by 45048a90: commit:private/renet f119c9d. Tests recorded rc 1 before the fix in the writer report, apart from the guards named there as weak; the lead reran go test -race, rc=0.
- [x] V3: Verify (F7, F8): `BackupVerifyCommand` takes the same low-priority prefix and a scope, default `CPUQuota=100%` (one core, as measured) with a `cpu_limit` param; `--read-bwlimit` default 50M paces `full`. A repo named by `--repo` with no backup exits 1 with `no-backup` (an enumerated run stays informational). `--exclude-repo` and `--next-due <age>` (pick the most overdue repo, one per run) are added. `backupstate` and `loadBackupCoverage` carry `last_verify_at` and `last_verify_status`.
  - Owns: private/renet/cmd/renet/backup_verify.go, private/renet/cmd/renet/backup_verify_test.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_verify_test.go, private/renet/pkg/backupstate/backupstate.go, private/renet/pkg/backupstate/backupstate_test.go, private/renet/pkg/list/types.go, private/renet/pkg/list/list.go
  - Tests: argv starts `sudo nice ionice systemd-run --scope`; exit codes asserted on the cobra path for verified, mismatch, failed, no-backup named and no-backup enumerated; full run paced on the fake clock; rotation picks the oldest; coverage JSON carries the status.
  - Accept: `cd private/renet && go test ./cmd/renet/ -run 'TestBackupVerify' -count=1 && go test ./pkg/functions/commands/ -run 'TestBackupVerify' -count=1 && go test ./pkg/backupstate/ ./pkg/list/ -count=1` rc 0.
    (ticked) 2026-11-01T22:50:31Z by 45048a90: commit:private/renet f119c9d. Tests recorded rc 1 before the fix in the writer report, apart from the guards named there as weak; the lead reran go test -race, rc=0.
- [x] V4: Reports and visible missing index (F6, F9): `renet backup report` posts a run or a verify under a licence session, spools to disk on failure, and flushes on the next run. Snapshot and verify report by themselves. `buildSnapshotTOC` warns on `errNoTOCKey` instead of Debug (private/renet/cmd/renet/backup_snapshot_toc.go:189-190), with a named no-listing-source warning for a repository with a key but neither keyfile nor mount, and the record carries `indexStatus`.
  - Owns: private/renet/cmd/renet/backup_report.go, private/renet/cmd/renet/backup_report_test.go, private/renet/cmd/renet/backup_snapshot_toc.go, private/renet/cmd/renet/backup_snapshot_toc_test.go, private/renet/cmd/renet/backup_snapshot.go
  - Tests: a logger hook sees a Warn for a missing key; each `indexStatus`; a spooled report flushes once; an unreachable server or a 404 never fails a run; nothing secret is posted.
  - Accept: `cd private/renet && go test ./cmd/renet/ -run 'TestBackupReport|TestSnapshotTOC' -count=1` rc 0.
    (ticked) 2026-11-01T22:50:33Z by 45048a90: commit:private/renet f119c9d. Tests recorded rc 1 before the fix in the writer report, apart from the guards named there as weak; the lead reran go test -race, rc=0.
- [x] V5: `renet backup toc-key` and function `backup_toc_key` (F6): `status` prints the stored key and license lineage, `install --lineage L --public-key <line>` validates the line, refuses a lineage that disagrees with the licence, is a no-op on an equal key, and refuses a different one. `install --replace --password-stdin` proves the password through L1 first, and only this explicit path carries a secret.
  - Owns: private/renet/cmd/renet/backup_toc_key.go, private/renet/cmd/renet/backup_toc_key_test.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_toc_key_test.go
  - Tests: each refusal; replace without a proven password writes nothing; install writes the exact bytes `MarshalPublicKey` writes.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/functions/commands/ -run 'TocKey|TOCKey' -count=1` rc 0.
    (ticked) 2026-11-01T22:50:36Z by 45048a90: commit:private/renet f119c9d. Tests recorded rc 1 before the fix in the writer report, apart from the guards named there as weak; the lead reran go test -race, rc=0.
- [x] V6: `renet backup repair --repo <guid> --hashes-stdin`, `renet backup restore --salvage` (only with a target that does not exist), and `renet backup compare --repo <copy> --against-anchor <source>` for the restore test: streaming sha256 under the read cap and scope, plus the copy's recomputed `cellsRoot`.
  - Owns: private/renet/cmd/renet/backup_repair.go, private/renet/cmd/renet/backup_repair_test.go, private/renet/cmd/renet/backup_compare.go, private/renet/cmd/renet/backup_compare_test.go, private/renet/cmd/renet/backup_restore.go, private/renet/pkg/functions/commands/backup.go
  - Tests: compare detects a one-byte difference and passes an identical copy; a salvage over an existing repo refused; a repair with an absent hash exits non-zero and names it.
  - Accept: `cd private/renet && go test ./cmd/renet/ -run 'TestBackupRepair|TestBackupCompare|TestRestore_Salvage' -count=1` rc 0.
    (ticked) 2026-11-01T22:50:38Z by 45048a90: commit:private/renet f119c9d. Tests recorded rc 1 before the fix in the writer report, apart from the guards named there as weak; the lead reran go test -race, rc=0.

V1 to V6 share `backup.go`, `backup_snapshot.go` and `backup_restore.go`, and one writer owns them, so the sequence is writer V's.

### C: CLI verbs (writer C)

- [ ] C1: Verify verdicts (F8): an unparseable verdict is status `unknown`, reports failure and sets exit 1. `recordVerifyVerdict` records the status from the verdict on both job outcomes, so `no-backup` never records `verified`. `--deep --store` is refused by name before any work.
  - Owns: packages/cli/src/services/jobs/steps.ts, packages/cli/src/services/jobs/plans-repo.ts, packages/cli/src/services/jobs/__tests__/steps.test.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/backup-storage-parser.ts, packages/cli/src/commands/__tests__/backup-storage.test.ts
  - Tests: garbage output, `no-backup`, `mismatch` on failure, `verified`, and `--deep --store`.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/services/jobs/__tests__/steps.test.ts src/commands/__tests__/backup-storage.test.ts` rc 0.
- [ ] C2: A failed verify is a health input (F9): `applyStaleness` takes verify failures from `backup_coverage`, adds a named issue and raises the exit code.
  - Owns: packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/status.ts, packages/cli/src/services/backup/backup-schedule-coverage.ts, packages/cli/src/commands/machine/__tests__/health-verify.test.ts
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/machine/__tests__/health-verify.test.ts` rc 0.
- [ ] C3: Restore passes the credential and speaks plainly (F3); `rdc backup verify --restore-test` (F10) restores the anchor's snapshot under a new name with `--no-seed` so bytes really come from the store, after a free-space check of 1.2x the image. It runs V6's compare, reports `proven` or `failed`, and deletes only the copy by its GUID, including after a failure. It refuses the source repo as the copy.
  - Owns: packages/cli/src/commands/backup-restore-chunk.ts, packages/cli/src/commands/backup-restore-test.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/__tests__/backup-restore-test.test.ts
  - Tests: the delete call names only the copy's GUID in every path; a mismatch exits 1; `passphraseCheck` is rendered in every format.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-restore-test.test.ts` rc 0.
- [ ] C4: `rdc backup repair <repo> [--dry-run]` (F11) drives `--store`, then the server delete, then the machine re-upload, and reports unrepairable hashes and affected snapshots; `rdc backup restore --salvage --as <new>`.
  - Owns: packages/cli/src/commands/backup-repair.ts, packages/cli/src/commands/backup-restore-chunk.ts, packages/cli/src/commands/__tests__/backup-repair.test.ts
  - Tests: `--dry-run` never deletes; a clean verify calls nothing; an unrepairable hash exits non-zero; `--salvage` without `--as` refused.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-repair.test.ts` rc 0.
- [ ] C5: `rdc backup check <repo> [--path <file>]` (F12) runs from where the passphrase lives: browse the recent listing with the passphrase, restore one file to a scratch directory, compare it with its listed size, post `proven` or `failed`, delete the scratch only. A snapshot with no index is reported plainly and is not `proven`.
  - Owns: packages/cli/src/commands/backup-check.ts, packages/cli/src/commands/__tests__/backup-check.test.ts
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-check.test.ts` rc 0.
- [ ] C6: `backup strategy list` and `show` print rows on stdout through `outputService.print` in every format (F13); an empty list is `[]` under `-o json`.
  - Owns: packages/cli/src/commands/backup-strategy.ts, packages/cli/src/commands/__tests__/backup-strategy.test.ts
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-strategy.test.ts` rc 0.
- [ ] C7: `rdc backup snapshot --accept-identity-change`, rendering `identity-changed` as a failure naming the flag.
  - Owns: packages/cli/src/commands/backup-storage-snapshot.ts, packages/cli/src/commands/__tests__/backup-snapshot-bwlimit.test.ts
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-snapshot-bwlimit.test.ts` rc 0.

### S: CLI schedule and TOC key (writer S)

- [ ] S1: `packages/shared/src/backup/toc-key.ts`: `deriveTocPublicKeyLine(credential, lineage)` by HKDF-SHA256 (salt lineage, info `rediacc-backup-toc-v1`), X25519, line `rediacc-toc-x25519 <base64>\n`, with no private half returned. The test reads L4's vectors from a committed copy, and a second test fails if the copy differs from private/renet's file.
  - Owns: packages/shared/src/backup/toc-key.ts, packages/shared/src/backup/__tests__/toc-key.test.ts, packages/shared/src/backup/__tests__/toc_key_vectors.json
  - Accept: `npx vitest run --root packages/shared src/backup/__tests__/toc-key.test.ts` rc 0.
- [ ] S2: Install at schedule deploy (F6): in `pushBackupSchedule`, after renet is provisioned, each repo in scope gets `status`, then a comparison. Missing: install the public half. Equal: silent. Different: a loud warning naming the repo, and no overwrite. Lineage from `grandGuid`, else the repository GUID. A repo with no credential warns. `rdc backup toc-key sync <repo> [--replace]` re-issues on demand, and `--replace` carries the passphrase to L1's proof. A scan after the install reports repositories with a key but neither keyfile nor mount as getting no listing.
  - Owns: packages/cli/src/services/backup/backup-schedule.ts, packages/cli/src/services/backup/backup-toc-key.ts, packages/cli/src/commands/backup-toc-key.ts, packages/cli/src/services/__tests__/backup-toc-key.test.ts
  - Tests: nothing but the public line leaves the CLI on the deploy path, asserted over every transport call; a mismatch never overwrites without `--replace`; a dry run touches nothing.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/services/__tests__/backup-toc-key.test.ts` rc 0.
- [ ] S3: Units (F9, F12): the service runs verify after the snapshot (same scope flags; a failed snapshot stops it), and `OnFailure=rediacc-backup-alert@%n.service` runs `renet backup report`. A new daily verify timer at a staggered offset runs `backup verify --level full --next-due 7d` under `CPUQuota=100%`. A strategy `verify` block (`spotAfterRun`, `deepSchedule`, `off`) goes through schema, sensitivity and validation. Reconcile and removal handle the new units.
  - Owns: packages/cli/src/services/backup/backup-schedule-unit-generator.ts, packages/cli/src/services/backup/backup-schedule-execute.ts, packages/cli/src/services/backup/backup-schedule-reconcile.ts, packages/cli/src/services/backup/backup-strategy-validate.ts, packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/cli/src/services/__tests__/backup-schedule-chunkstore.test.ts, packages/cli/src/services/__tests__/backup-schedule.test.ts
  - Tests: rendered unit text for each case; the alert template carries no secret; removing a strategy removes all its units; `off` renders neither.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/services/__tests__/backup-schedule-chunkstore.test.ts src/services/__tests__/backup-schedule.test.ts` rc 0, and `npm run typecheck -w @rediacc/cli` rc 0.

### D: artifacts, docs and drills (writer D)

- [ ] D1: Renet artifacts: regenerate the function contract (`renet functions generate-types`) for `backup_verify`, `backup_snapshot`, `backup_restore`, `backup_toc_key`; add new functions to the tier map; add every new `i18n.T` key to the renet catalogs and baselines.
  - Owns: packages/shared/src/renet-contract/data/functions.schema.ts, packages/shared/src/renet-contract/data/functions.generated.ts, private/renet/pkg/i18n/**
  - Accept: `npm run check:ci-renet-types && npm run check:ci-renet-tiers && npm run check:ci-renet` rc 0.
- [ ] D2: CLI artifacts: command metadata and planes for `backup repair`, `backup check`, `backup toc-key`; update the count pins with their reasons; CLI strings in all 13 locales; regenerate the contract and docs data.
  - Owns: packages/cli/src/config/command-metadata.ts, packages/cli/src/config/command-planes.ts, packages/cli/src/config/__tests__/plane-coverage.test.ts, packages/cli/src/i18n/locales/**, packages/shared/src/cli-contract/**
  - Accept: `npm run check:ci-i18n-completeness && npm run check:ci-i18n-hashes && npm run check:ci-i18n-cli-key-usage && npm run check:ci-i18n-placeholders && npm run check:ci-cli-contract` rc 0, and `npm run typecheck -w @rediacc/cli` rc 0.
- [ ] D3: Docs: the verification ladder and schedule, restore's passphrase statement, repair and salvage with what is safe, TOC keys and the no-listing case, the alert preference, in all 13 locales. docs/backup-storage/07-execution-record.md records tier B's real result (P3), with each claim dated.
  - Owns: packages/www/src/content/docs/*/backup-restore.md, packages/www/src/content/docs/*/cli-application.md, docs/backup-storage/07-execution-record.md
  - Accept: `npm run check:cli-docs && npm run validate:cli-docs -w @rediacc/www && npm run check:ci-i18n-docs-untranslated && npm run check:ci-docs-structure-parity` rc 0.
- [ ] D4: Drill legs, each with a planted control: leg p (identity refuses a swapped image, restore refuses a wrong passphrase and places nothing, in `backup_renet`), leg q (retention keeps a verified snapshot through bad nights), leg r (repair deletes a corrupt chunk, re-uploads it, and `--store` is clean), leg s (duplicate PUT and wrong checksum on the real store, named so a tier B run reads as R2's proof). `backup_roundtrip` asserts `passphraseCheck`. `backup_onprem` runs the conformance preflight against RustFS and a non-conforming fake.
  - Owns: .ci/rediacc_ci/drills/backup.py, .ci/rediacc_ci/drills/backup_renet.py, .ci/rediacc_ci/drills/backup_roundtrip.py, .ci/rediacc_ci/drills/backup_onprem.py, the drill tests under .ci
  - Accept: `./run.sh drill backup --selftest` rc 0, and the pytest for those drills rc 0.

### P: proof before the merge (lead)

- [ ] P1: VMs: the renet backup area on real cryptsetup and btrfs: a mounted repo with a wrong password keeps its TOC key, a wrong passphrase on restore places nothing, spot and deep run inside the scope.
  - Accept: `npm run vm:check` rc 0 with the backup leg VERIFIED, receipt recorded here.
- [ ] P2: Drills: `./run.sh drill backup` and `./run.sh drill backup-onprem`, with new legs p to s and their controls firing.
  - Accept: both rc 0; the receipt `block_backup_unverified_push` reads is fresh for this tree.
- [ ] P3: R2 tier B (needs decision O1): `./run.sh drill backup --legs a,s` with `DRILL_STORE_*` on the probe bucket, proving a duplicate PUT answers 412 and a wrong checksum is refused. The result corrects the grants.go comment and 07-execution-record.md in the same commit. If R2 refuses a wrong checksum differently than documented, that is a finding, not a retune.
  - Accept: the command rc 0, the status codes recorded here.
- [ ] P4: The D1 clone check covers migration 0073.
  - Accept: the CD or local `rediacc_ci.deploy.test_d1_migrations` run rc 0 for eu, recorded with its run id.

### B: bench, after the merge and edge deploy (lead)

- [ ] B1: A replayed bad night and alert on `eu-bench`: a failed verify and a stopped nightly produce one digest email; a repeat that day produces none.
  - Accept: `./rdc.sh --config eu-bench backup manifests <repo> -o json` rc 0 shows the states, and the delivery is recorded here.
- [ ] B2: Repair on bench with a chunk corrupted through the store's credentials.
  - Accept: `./rdc.sh --config eu-bench backup repair <repo>` rc 0, then `backup verify <repo> --store` rc 0.

### H: hostinger, after the release (lead)

Every H box uses the released `rdc` and its released renet. Mutating steps run only under a released renet. No original repo is deleted, pruned, replaced or downed. Only copies named `*-rt` are deleted, by GUID.

- [ ] H1: The released CLI reads `eu-remote` (F13), which also gives box R1 of PLAN-backup-program.md its live read.
  - Accept: `rdc --version` shows a release newer than 2.4.0, and `rdc --config eu-remote backup strategy list -o json` rc 0 with rows on stdout.
- [ ] H2: Read first: for each of the 10 mounted repositories, the CLI-computed key equals the machine's key where one exists. A mismatch stops the box and is reported, with no overwrite.
  - Accept: `rdc --config eu-remote backup toc-key sync <repo> --dry-run -o json` rc 0 for each, results recorded.
- [ ] H3: Re-deploy the schedule; public keys are installed, and units show verify and `OnFailure=`.
  - Accept: `rdc --config eu-remote backup schedule -m hostinger` rc 0, and `backup status -m hostinger` rc 0.
- [ ] H4: The next nightly: 10 repositories have `hasIndex` true and `indexStatus` sealed. demo-heartbeat is reported plainly: it has neither keyfile nor mount, so it gets no listing, and the warning is in its unit journal. Spot ran after the snapshot, and reports reached the account after the stable deploy.
  - Accept: `rdc --config eu-remote backup manifests <repo> -o json` rc 0 per repo, recorded here.
- [ ] H5: N4b single-file restore to a scratch directory on a repository with a listing, then tick box N4b in agent/plans/PLAN-backup-program.md.
  - Accept: `rdc --config eu-remote backup restore <repo> --at <snapshot> --path <file> --to <scratch>` rc 0, with the checksum equal to a read of the live file taken for comparison.
- [ ] H6: A deep verify of one mid-size repo under the sampler: scope usage stays at one core (CPUQuota=100%), and machine-wide busy CPU is recorded before and during.
  - Accept: `rdc --config eu-remote backup verify <repo> --deep` rc 0, figures recorded here.
- [ ] H7: A restore test of demo-heartbeat (2 GB): only the `-rt` copy is deleted.
  - Accept: `rdc --config eu-remote backup verify demo-heartbeat --restore-test` rc 0, then `repo list -m hostinger` shows the original with its GUID unchanged and no copy.
- [ ] H8: `rdc backup check` on one listed repo marks a snapshot `proven`, and `backup verify demo-heartbeat --store` runs one real full pass on the smallest lineage.
  - Accept: both rc 0; `backup manifests` shows the states.
- [ ] H9: The alert path through a harmless planted failure: `renet backup report --test` from the released binary, with no repository involved.
  - Accept: the command rc 0, and the digest's receipt recorded here.

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof, after this plan's bench-deployable boxes land.
  Accept: live-proof bench account-smoke

- [ ] LP-hostinger [live] Fresh hostinger receipt through worklist.py --live-proof, after this plan's hostinger-deployable boxes land.
  Accept: live-proof hostinger renet-live machine=hostinger

**Closes only after the merge:** B1, B2, H1 to H9, LP-bench, LP-hostinger. Everything else closes before it. The PR's merge rule therefore needs an `Operational-Reason:` naming these boxes or the operator's ruling on them, because the merge gate refuses open boxes on a plan on the PR's `Plan:` line.

## Operator rulings on the decisions below, 2026-11-01

- O1: the lead creates the R2 probe bucket through the Cloudflare API with the authorized credentials, and says so if they do not allow it.
- O2: a restore the passphrase cannot open is refused and the staged file kept, with `--allow-unopenable`, as recommended.

## Decisions that belong to the operator

- **O1. R2 proof bucket.** Tier D says the operator creates the bucket, and drills refuse a name without probe, test, scratch or bench. Recommended: create `rediacc-backups-probe` in the eu jurisdiction with an expiry lifecycle rule, used by P3 only.
- **O2. A restore the passphrase cannot open.** Recommended: refuse to place it and keep the staged file, with an explicit `--allow-unopenable` for the real case of a snapshot predating a passphrase change. The alternative, placing it and warning, gives a repo that will not mount.
- **O3. Sign the Merkle root?** Unsigned, it catches corruption and chain mix-ups, not a malicious store. The workable signing design: an Ed25519 key derived from the passphrase in the CLI, the private half installed root-only on the machine (it can only sign, not decrypt), so the server cannot forge it, while a compromised machine can. Recommended: ship unsigned now and revisit before a customer who needs tamper evidence. No box exists until this is answered.
- **O4. A customer store that fails the preflight.** Recommended: refuse grants when checksums are not enforced, since a bad body would be stored under a good hash; warn when If-None-Match is not enforced, since with checksums enforced an overwrite can only write the same bytes. Refusing on both is stricter and excludes more stores.
- **O5. Alert channel.** Recommended: email digest on by default for the repo-digest recipients, plus `machine health`. Grafana on otlp.rediacc.io (PLAN-telemetry-export.md) can be added later for Rediacc's own eyes but is not a dependency.
- **O6. Where the passphrase checks run on schedule.** The passphrase must live with the job. Recommended: the verb plus a documented schedule on the host that already holds the config, with no CI job, since a runner job would put vault credentials in CI secrets. If the operator wants the monthly check unattended, a runner job is the alternative, with that cost accepted.
- **O7. A slower KDF than HKDF (private/renet/pkg/chunkstore/toccrypt/toccrypt.go:95).**
  - An attacker holding a sealed index or the public key can test guesses at about a million per second per core. A hit also yields the LUKS passphrase, bypassing LUKS's Argon2id slot.
  - For generated credentials, 24 random bytes (packages/cli/src/commands/repo-create-delete.ts:36) make 192 bits, and no KDF matters. The CLI has no flag for a hand-picked credential; only a config edit gets one in.
  - Recommended: keep HKDF, and add one warning at install when a credential is shorter than the generated shape. Moving to scrypt or Argon2id needs a new seal version, keeps a reader for hostinger's existing indexes, and spends memory at each derivation, which is cost without benefit for generated credentials.
  - No box exists until this is answered.
- **O8. Verification defaults and the demo-heartbeat listing.** Recommended: the D-policy table as written, and leave demo-heartbeat without a listing and reported plainly, since enabling autostart adds a key slot to a production repo. Giving it a listing is the operator's call.

## Hypotheses, each with the box that settles it

- A lineage above about 300 manifests stalls its HEAD pass under the subscription budget. G2's test proves or refutes it.
- Node's X25519 from a raw scalar equals Go's, including clamping. L4 and S1's vectors settle it.
- The mount path's password bytes equal the config credential: `ReadPasswordFromStdin` trims whitespace (private/renet/cmd/renet/helpers.go:131), and generated credentials contain none. H2 proves it on 10 real repos.
- R2 enforces `x-amz-checksum-sha256` on a presigned PUT and answers 412 on a duplicate, as its docs state. P3 is the proof.
- `backup pull` holds a password at its verification step. V2 reads it and narrows that sibling if not.
- Recomputing a root for a 256 GiB image fits a Worker request. G3 caps it and names a skipped root either way.

## Risks

- A first full run after an accepted identity change costs a full seed; the flag's help says so.
- A pinned verified snapshot can hold old chunks and bill them for a long time. It is bounded to two per stream and visible in the preview, and is the requested behaviour.
- `identity-changed` will fire on an out-of-band `cryptsetup reencrypt`. That is intended, and the alert names the flag.
- A first hostinger run after the update has no stored identity and records a baseline, so one replaced image in that exact window would become the baseline. The licence's `LuksUUID` narrows the window where it is set.
- Test-open costs an Argon2id unlock, about 1 GiB and seconds, per restore. It runs once, on a restore.
- Spot and deep read through the anchor reflink, and btrfs and loop kernel work is not charged to the scope. H6 measures it.

## What this plan deliberately does not do

- It does not make `exists` read content; detection stays in the verify ladder.
- It does not build a passphrase-change verb. Re-issue is mismatch-driven through `toc-key sync --replace`.
- It does not sign the Merkle root or change the KDF until O3 and O7 are answered.
- It does not add a server read path for older clients. No customers exist, and the rollout order covers hostinger.
- It does not re-seal existing indexes or backfill `cellsRoot` on hostinger's existing manifests; they report the root as absent until retention replaces them.
- It does not run a whole-image proof on a hostinger repository larger than demo-heartbeat, and it never deletes, prunes, replaces or downs an original repo.
- It does not exercise repair on hostinger, which has no known corrupt chunk. Bench carries that proof.
- It does not treat `verified` as a proof of usable data. Only `proven` means that.
- It does not make the hostinger observability stack an alert dependency.
- It does not schedule the passphrase checks from CI.
