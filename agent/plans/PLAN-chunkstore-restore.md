# PLAN: Snapshot-addressed restore from chunk storage
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-chunkstore-restore.md
Full-Text-Blob: 2b5bd24cd38dbb04b69cb118dfb5164fd26b3697
Record-Sig: 5da27895

## Why
The download half of the backup-storage program did not exist: upload was live and restore was a stub that refused `--at` by name. This plan designed the read path after correcting three things the brief had wrong, each of which changed the design. There was no read GRANT and, one layer earlier, no read SESSION: a lapsed subscription could not mint a session at all, so
retain-on-cancel kept 60 days of bytes the product had no way to hand back. The write grant already carried `GetObject`, an accident rather than a design, and one that does not exist on the presigned path everything but R2 uses. And the parent chain is of unbounded depth, while `MaterializeManifest` composes exactly one delta over a full parent and refuses a delta parent by name.

## Outcome
SHIPPED IN FULL. THE HEADER SAYS `draft` AND THE TREE CONTRADICTS IT. Measured 2026-09-06, every named deliverable exists.

- Engine: `private/renet/cmd/renet/backup_restore.go` with `backup_restore_test.go`, and
`private/renet/pkg/chunkstore/restore.go` and `download.go`, alongside `restore_holes_linux_test.go`, `transient_restore_linux_test.go` and `readgrant_wire_test.go`.
- Section 2.3: `app.post('/read-grants', backupSessionAuth, ...)` at
`private/account/src/routes/backups.ts:101`.
- Section 2.2, the grant split rather than the accident: `BACKUP_READ_GRANT_ACTIONS` at
`private/account/src/services/backup-chunk-store.ts:407`, consumed at `:720`.
- Section 2.1, the layer the brief did not reach: `BackupSessionIntent` with a `restore`
arm at `private/account/src/services/backup-storage.service.ts:81-266`, and BOTH refusals mirrored, at `:459` (a restore-intent session cannot upload) and `:707` (a backup-intent session cannot fetch chunks).
- Section 6.3: `scripts/drills/backup.sh` legs j and k mint a restore-intent session and
restore through a read grant (blob 07ae79e2da898a510c08caf278b026d50d68eebb).
- Section 6.4: `packages/e2e-tests/tests/26-backup-storage-cli.test.ts` exists (blob
8170f741e70bd1ec29b64bb7ac5f37fc0e6f1997).

Console-side landing: commit 120cd9e73, "feat(backup): chunk-store cold path, rclone decommission, stop-hook cadence" (2026-08-18), which carries the drill legs and the suite. The renet and account halves are submodule commits and are named by subject here rather than by sha, because a gitlink is not an object in this repository.

## Lessons
- `Status: draft` over a fully shipped design is the most expensive header shape in this
tree. It stood for 22 days and the work was still being counted as unstarted when this record replaced it.
- Reading the struct beat reading the brief three times in one plan. All three section-0
corrections came from opening the file the brief described instead of trusting the description.
- The refusal MIRROR is the part worth copying: a read path is not finished when reads
work, it is finished when the write verbs refuse a read session by name and the read verbs refuse a write session by name.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:30:33Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: private/renet/cmd/renet/backup_pull.go, packages/cli/src/commands/backup.ts, packages/e2e-tests/tests/26-backup-storage-cli.test.ts, private/account/src/db/schema.ts, packages/shared/src/subscription/types.ts, scripts/drills/backup.sh, packages/cli/src/services/executor/local-executor.ts, packages/cli/src/services/account/license.ts
Gates: check:ci-account-layer-isolation, check:ci-account-scope-audit, check:ci-cli-contract, check:ci-command-planes, check:ci-command-tree, check:ci-renet-tiers, check:ci-renet-types
Why-Source: author
Read-History: `git show 2b5bd24cd38dbb04b69cb118dfb5164fd26b3697` recovers the text; `git log --find-object=2b5bd24cd38dbb04b69cb118dfb5164fd26b3697 --all` names the commit

## History
- 2026-09-06T17:30:33Z compacted by 8f55d4f0 from `draft` (record-sig 5da27895)
