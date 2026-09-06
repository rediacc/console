# PLAN: chunk-store BROWSE, engine-first
Status: compacted
Full-Text: f7a5351a9 agent/PLAN-chunk-store-browse-engine.md
Full-Text-Blob: cf248906f1dd29b1206e9331c84bfcc95eee8314
Record-Sig: 8207a732

## Why
An operator wanting to know whether a particular file is inside a backup had no way
to ask. The decisive finding, established by reading the manifest struct rather than
the design docs, is that a file listing is NOT derivable from a chunk-store manifest
at any cost: the manifest is a fixed grid of SHA-256 hashes over the repository's
LUKS CIPHERTEXT, carrying no filename, inode, directory structure or extent table,
not even indirectly, and the chunks themselves are ciphertext, so downloading them
without the repository key buys nothing. There is no partial-materialize path either.
Browse therefore could not be a read-side feature bolted onto stored data; it needed
a new artifact produced at snapshot time while the plaintext filesystem is still
reachable. renet already owned the machinery: `pkg/repodiff` opens a LUKS image
read-only and walks its ext4 with FIEMAP extents.

## Outcome
PARTIALLY SHIPPED, measured 2026-09-06. Stage 1 is in the tree; stages 2 and 3 do not
exist. THE HEADER SAYS "proposal. Read-only investigation, no code written" AND THE
TREE CONTRADICTS THAT FOR STAGE 1.

- Stage 1 shipped in renet: `private/renet/cmd/renet/backup_browse.go`, added by renet
  commit 2de8f2a, "feat(renet): backup browse, the verb over repodiff.Browse"
  (2026-08-17), with follow-ups 8ec47e0, 3d68aba and f2360f3, all ancestors of the
  renet remote's main.
- The engine landed as `private/renet/pkg/repodiff/browse.go` rather than as the
  proposed new `pkg/backupindex`, which is the plan's own section 7.1 hedge taken
  further. It carries the section 6 non-negotiable that a listing names its source.
- The "never look complete when it is not" instinct shipped as a reported cap:
  `private/renet/cmd/renet/backup_browse.go:21` defines `const browseListCap = 10000` and the truncation is
  reported rather than silent.
- The CLI surface shipped in console commit 3f52d5d52, "feat(cli): rdc backup browse,
  and the reference the retention fix still owed" (2026-08-18):
  `registerBackupBrowse` at `packages/cli/src/commands/backup-storage.ts:208`, with
  columns `name/type/size/modified`, byte for byte the retired `storage browse` shape.
- CI coverage went into suite 25 as the plan recommended:
  `packages/e2e-tests/tests/25-backup-chunk-store.test.ts` drives `backup_browse` and
  asserts on its exit code.

STAGE 2 AND STAGE 3 DO NOT EXIST, and they are the stages that carried the security
risk. `private/renet/pkg/backupindex/` is absent, so there is no index encryption and
no fail-closed negative test for it; the account server has no index key column and no
index prefix. The registered CLI command takes only `--path`, `--depth`, `--limit` and
`--debug`, with no `--at`, so historical browse is not reachable. The section 9
tutorial scene was never added. Those two hazards are dormant, not resolved.

RELATED RECORD: `agent/PLAN-chunk-store-browse-DECISION.md` already records this same
conclusion and flags that this plan's stale header caused it to be misread as live
design work eighteen days after stage 1 was built.

## Lessons
- Read the struct, not the design doc. The whole shape of this work follows from one
  fact about `manifest.go` that no design document stated: the grid hashes ciphertext,
  so nothing about the filesystem survives into the stored artifact.
- A stale `Status:` header on a finished plan costs real time. This one said "no code
  written" for eighteen days after stage 1 shipped, and a later session had to write a
  separate DECISION document to stop it being read as live design work.
- Staging a plan so the first stage needs no format change and no server change is
  what let stage 1 ship at all. The stages that needed both are the ones still unbuilt.

## Boxes
(this plan carried no checkbox tasks)

## Record
Record-Kind: compacted
Prior-Status: proposal
Compacted-By: 8f55d4f0
Compacted-At: 2026-09-06T17:06:10Z
Boxes: 0 attested, 0 open, 0 abandoned
Epics: none
Touched: private/renet/pkg/chunkstore/manifest.go, private/renet/pkg/chunkstore/grid.go, private/renet/pkg/repodiff/types.go, private/renet/pkg/filesystem/ext4.go, private/renet/pkg/repodiff/mountset.go, private/renet/pkg/repodiff/walk.go, private/renet/pkg/chunkstore/restore.go, private/account/src/services/backup-chunk-store.ts, private/account/src/services/backup-gc.service.ts, private/account/src/routes/backups.ts, private/renet/pkg/luks/luks.go, private/renet/pkg/credentials/keyfile.go, private/renet/pkg/vaultcrypto/vault.go, private/renet/pkg/embed/embed.go, packages/cli/src/commands/storage.ts, packages/cli/src/commands/repo-backup-list.ts, packages/e2e-tests/playwright.config.ts, .e2e-coverage-allowlist, .ci/tutorials/tutorial-backup-restore.sh, .github/workflows/ci-ops-test.yml
Gates: none
Why-Source: auto
Read-History: `git show cf248906f1dd29b1206e9331c84bfcc95eee8314` recovers the text; `git log --find-object=cf248906f1dd29b1206e9331c84bfcc95eee8314 --all` names the commit

## History
- 2026-09-06T17:06:10Z compacted by 8f55d4f0 from `proposal` (record-sig 8207a732)
