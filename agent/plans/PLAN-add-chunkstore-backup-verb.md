# PLAN: add the chunk-store backup verb (`renet backup snapshot` / `rdc backup snapshot`)
Status: compacted
First-Seen: 2026-09-17
Owner: 97604f47
Full-Text: f7a5351a9 agent/PLAN-add-chunkstore-backup-verb.md
Full-Text-Blob: 5de64f0839c4781cfdef2f2f3249a695cc96d2ef
Record-Sig: 51edf5ee

## Why
`pkg/chunkstore` was a complete content-addressed upload engine that nothing called: the plan opens by reproducing that `chunkstore.Upload` had zero callers, so the backup store the team had built was unreachable from any operator-facing verb. Two things had to happen together. First a prerequisite: the Go client had been written against a sketch of the server API and had drifted
from the real one across the auth header, the exists path and its polarity, the batch cap, the grant shape and the commit protocol, and the drift was invisible because every integration test drove an in-process fake that agreed with the client by construction. Then the verb itself, named `backup snapshot` after arguing down `seed`, `incremental` and `resume` as states the engine
detects rather than choices a user makes.

## Outcome
SHIPPED, and expanded beyond the plan, measured on 2026-09-06.

- `private/renet/cmd/renet/backup_snapshot.go` exists; the renet submodule commit
that added it is fb48c98, "feat(backup): cold path for the chunk store, and rclone leaves the binary" (2026-08-17).
- The function is registered: `private/renet/pkg/functions/commands/backup.go:172`
declares `Name: "backup_snapshot"`, with `BackupSnapshotCommand` at :640.
- The licensing decision landed as designed:
`private/renet/pkg/license/tiermap.go:73` reads `"backup_snapshot": {tier: TierNone}`.
- The generated contract was regenerated rather than hand-edited:
`packages/shared/src/renet-contract/data/functions.generated.ts:815` and `packages/shared/src/renet-contract/data/functions.schema.ts:92` (`BackupSnapshotParamsSchema`).
- The CLI shipped: `packages/cli/src/commands/backup-storage.ts:358` registers
`.command('snapshot')` and dispatches `'backup_snapshot'` at :373, hung off the backup group at `packages/cli/src/commands/backup.ts:404` (`registerBackupStorageCommands(backup)`), with its metadata entry at `packages/cli/src/config/command-metadata.ts:174`.
- The prerequisite reconciliation is done: `private/renet/pkg/chunkstore/session.go:218`
sends `X-Backup-Session`, :309 posts `/exists`, :498 posts `/commit`.

THE HEADER SAID `Status: draft` AND THE TREE DISAGREES. The work is in the tree; the header was never updated. The console-side commit carrying the plan and the CLI work is 120cd9e73, "feat(backup): chunk-store cold path, rclone decommission, stop-hook cadence", an ancestor of origin/main.

TWO DIVERGENCES, ONE OF WHICH IS AN OPEN DEFECT.

1. OPEN: the plan required `backup_snapshot` to get the 5-minute I/O budget rather
than the 30-second default, for the first backup of a large repository. It did not get it. `private/renet/cmd/renet/functions_commands.go:903` still reads `var slowFunctionNames = []string{"backup_push", "backup_pull"}` and `slowFunctionPrefixes` at :898 is `{"datastore_", "kube_", "ceph_", "repository_"}`, which does not cover `backup_`. So the verb runs on the default timeout
today.
2. The plan asserted restore would stay where it was, as the stubbed `backup pull
--at`. It did not: `backup_restore` is now its own registered function (`private/renet/pkg/functions/commands/backup.go:191`) with its own `cmd/renet/backup_restore.go`. The flag surface also grew past the plan's seven with `--include-repo`, `--exclude-repo`, `--segment-depth` and `--cold`.

## Lessons
- An engine with no caller passes every test it has. `chunkstore.Upload` was
complete, exercised and unreachable at the same time, and the only thing that surfaced it was asking who calls it.
- An integration test driving an in-process fake proves the client agrees with the
fake, not with the server. Eight separate client-server mismatches survived precisely because the fake had been written from the same sketch as the client.
- A timeout budget is a registry entry, not a property of the verb, so it is the
piece of a multi-file change most likely to be dropped: the code, the contract, the tier map and the CLI all landed here and the slow-function list did not.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: draft
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:09Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: private/renet/pkg/functions/commands/backup.go, private/renet/pkg/license/tiermap.go, packages/shared/src/renet-contract/data/functions.generated.ts, packages/cli/src/config/command-metadata.ts, packages/cli/src/commands/backup.ts, scripts/drills/backup.sh, docs/backup-storage/02-design.md, private/account/src/errors.ts, packages/cli/src/services/renet/renet-license-contract.ts, packages/cli/src/types/index.ts, packages/cli/src/commands/backup-storage.ts, .ci/scripts/quality/check-e2e-coverage.sh, .ci/scripts/quality/check-renet-types.sh, private/renet/cmd/renet/functions_commands.go, scripts/gates/check-e2e-coverage.ts, private/renet/.ci/scripts/quality/i18n.sh, packages/cli/scripts/check-command-planes.ts, packages/cli/src/commands/mcp/__tests__/mcp-coverage.test.ts, docs/design/06-cli-reshape.md, scripts/gates/check-design-tree.ts
Gates: check:ci-design-tree
Why-Source: auto
Read-History: `git show 5de64f0839c4781cfdef2f2f3249a695cc96d2ef` recovers the text; `git log --find-object=5de64f0839c4781cfdef2f2f3249a695cc96d2ef --all` names the commit

## History
- 2026-09-06T17:06:09Z compacted by 8f55d4f0 from `draft` (record-sig 51edf5ee)
