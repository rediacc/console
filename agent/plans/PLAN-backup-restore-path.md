# PLAN: restore one file or directory from a chunk-store snapshot without a full image restore (box N4b of PLAN-backup-program.md)

Status: executing
Owner: d778be9d
Updated: 2026-10-28
Depends-On: PLAN-chunk-store-browse-toc-and-remote.md -- the sealed listing this plan extends; that plan closed 2026-10-27 with 11 of 11 boxes ticked
Priority: P2 -- operator ruling 2026-10-28 "Plan it, ride this PR"; today recovering a single file costs a full image restore of the whole repository, but no restore is broken, so it ranks below the P1 backup outage work in PLAN-backup-program.md
Concurrency: parallel -- R1 and R3 run in parallel. R2 follows R1. R4 follows R1, R2 and R3. R5 and R6 follow R4. L1 follows R5 with the renet pointer bumped. R7 runs last and alone. PLAN-backup-program.md owns private/renet/** and packages/cli/src/** broadly, so no writer of that plan may hold pkg/chunkstore/download.go, pkg/chunkstore/restore.go, cmd/renet/backup_browse_at.go or packages/cli/src/commands/backup.ts while R2, R3, R4 or R5 runs. The locale files wait for any other live plan that holds them.
Owns: private/renet/pkg/repodiff/types.go, private/renet/pkg/repodiff/browse.go, private/renet/pkg/repodiff/extents_linux.go (new), private/renet/pkg/repodiff/mountset.go (ImageHandle.DataOffset only), private/renet/pkg/repodiff/browse_list_test.go, private/renet/pkg/luks/resize.go (the strict data-offset reader only), private/renet/pkg/luks/luks_test.go, private/renet/cmd/renet/backup_snapshot_toc.go, private/renet/cmd/renet/backup_snapshot_toc_test.go, private/renet/cmd/renet/backup_browse_at.go, private/renet/cmd/renet/backup_browse_at_test.go, private/renet/cmd/renet/backup_restore_path.go (new), private/renet/cmd/renet/backup_restore_path_test.go (new), private/renet/cmd/renet/backup.go (one AddCommand and one help line), private/renet/pkg/chunkstore/download.go, private/renet/pkg/chunkstore/restore.go, private/renet/pkg/chunkstore/restore_ranges_test.go (new), private/renet/pkg/restorepath/** (new), private/renet/pkg/functions/commands/backup.go, private/renet/pkg/license/tiermap.go, private/renet/pkg/i18n/locales/**, private/renet (the gitlink bump only), packages/shared/src/renet-contract/data/** (regenerated only), packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-restore-path.ts (new), packages/cli/src/commands/backup-storage-browse.ts, packages/cli/src/commands/backup-storage.ts (the exit-18 constant move only), packages/cli/src/commands/__tests__/backup-restore-path.test.ts (new), packages/cli/src/services/renet/renet-license-contract.ts, packages/cli/src/services/executor/renet-function-access.ts, packages/cli/src/i18n/locales/*/cli.json, packages/www/src/content/docs/*/cli-application.md (regenerated only), packages/e2e-tests/tests/27-backup-browse-at.test.ts, agent/plans/PLAN-backup-program.md (the N4b tick only), agent/plans/PLAN-backup-restore-path.md
Live-Proof: hostinger -- the change is mostly renet: the snapshot-time recorder, the partial fetch, the decrypt and the restore-path verb all run on a machine against a real chunk store. The renet surface's only live target is hostinger (.ci/config/proof-tiers.json, surface `renet`, live ["hostinger"]). Bench's only CLI check (`cli-bench`) reads a subscription, which proves nothing about restore-path, so bench would be a hollow proof.
First-Seen: 2026-10-28
Worklist: #9169af71, PR-TASK 9f92c43e

## Problem

Box N4b (agent/plans/PLAN-backup-program.md:407) asks for `rdc backup restore <ref> --at <snapshot> --path <file-or-dir> [--to <dir>]`. The command must restore one file or one directory tree from a chunk-store snapshot without a full image restore. It fetches only the chunks that cover the path, writes byte-identical content and keeps mode and mtime. A missing path, or a snapshot with no table of contents, is refused with a named error and nothing is written. Today nothing in the stack can do this, for five reasons, each checked against the tree at ac6a26fd3.

- **The sealed table of contents has no positions.** The listing `backup snapshot` seals is a `repodiff.BrowseResult` (private/renet/pkg/repodiff/types.go:141). Its entries are `BrowseEntry` (types.go:114) with Path, Type, Size, Mode, ModTime and Target, and nothing else. No entry says where its bytes live in the image, so a reader holding the listing still cannot tell which cells to fetch.
- **Some listings can never carry positions.** `snapshotTOCListing` (private/renet/cmd/renet/backup_snapshot_toc.go, the function after `sealSnapshotTOC`) lists the STAGED reflink when the autostart keyfile opens it. For a password-only repository it falls back to the LIVE canonical mount and stamps `ListingSource: live-mount` (backup_snapshot_toc.go:33-45, and `ListLiveMount` in pkg/repodiff/mountset.go). Extents on the live mount describe the live image, not the staged copy that was uploaded. Their offsets can be wrong for the snapshot by whatever moved in between, so a live-mount listing must never be used to address cells.
- **The download engine fetches everything.** `chunkstore.RestoreOptions` (private/renet/pkg/chunkstore/download.go:39) has no way to name a subset. `assembleImage` (pkg/chunkstore/restore.go:30) feeds every hash in `m.NonZeroHashes()` to the worker pool, and the download.go header says so: "every non-ZERO cell is fetched".
- **The block-range machinery exists but drops what restore needs.** `walkMount` already records each regular file's ext4 device ranges via FIEMAP (pkg/repodiff/walk.go:65, `fileDeviceRanges` at walk.go:112). FIEMAP's Physical offset is relative to the dm-crypt mapper, which is the same coordinate space as image offset minus the LUKS data offset (walk.go:110-111). `imageRangesToDeviceRanges` (pkg/repodiff/intersect.go:83) is the inverse mapping, and `openRepoReadOnly` reads the offset with `luks.Device.GetDataOffset` (mountset.go:81). However, `fileDeviceRanges` throws away the extent's Logical offset and its Flags (pkg/fiemap/fiemap.go:48-55). Without Logical a sparse file cannot be rebuilt. Without Flags an unwritten (preallocated) extent cannot be told from a written one: an unwritten extent reads as zeros through ext4, but its raw device bytes are whatever ciphertext was there.
- **The image is ext4 inside LUKS.** `LUKSStorage.Format` runs `mkfs.ext4 -F` on the opened mapper (private/renet/pkg/storage/luks.go:241, pkg/filesystem/ext4.go:48), so no extra features such as inline_data are enabled. The cells are ciphertext. Reading a file therefore means fetching the LUKS header cells as well as the data cells, opening the sparse result with cryptsetup and the passphrase, and reading plaintext from the mapper.

Two more facts shape the design. `luks.Device.GetDataOffset` (pkg/luks/resize.go:145) silently returns a 16 MiB default when it cannot parse `luksDump`. A guessed offset is harmless for its current callers but would point a byte-exact restore at the wrong bytes. Second, a new renet function is checked in both directions by the e2e coverage gate (.ci/rediacc_ci/quality/e2e_coverage.py with .ci/policy/.e2e-coverage-allowlist), so `backup_restore_path` needs a live suite that calls it.

## Design

**1. Positions in the sealed listing, staged copies only (R1, R2).**

- `BrowseEntry` gains `Extents []FileExtent` with compact JSON tags and `omitempty`. A `FileExtent` holds Logical, Physical and Length (bytes) and an Unwritten bool.
- `BrowseEntry` also gains `NoExtents bool` (`omitempty`). It is set when a regular file of non-zero size has no usable extent map: FIEMAP failed, or any extent carries `FIEMAP_EXTENT_UNKNOWN`, `DELALLOC`, `ENCODED`, `DATA_INLINE`, `NOT_ALIGNED` or `DATA_TAIL`.
- `BrowseResult` gains `LUKSDataOffset uint64` (`omitempty`).
- `BrowseOptions` gains `RecordExtents bool` with `json:"-"`. `ListEntries` (pkg/repodiff/browse.go:70) calls a new `fileExtents` helper (pkg/repodiff/extents_linux.go) only when the flag is set, so local `backup browse` and the live-mount lister do not change.
- `fileExtents` keeps Logical and Flags, which `fileDeviceRanges` drops. It is a sibling helper; the diff path is left alone.
- `ImageHandle` gains `DataOffset()`. `OpenImageReadOnly` fills it from a new strict reader, `luks.(*Device).DataOffsetStrict`, which returns an error where `GetDataOffset` falls back to 16 MiB. The parsing is factored into a pure function that both share, so the fallback stays for existing callers only.
- `snapshotTOCListing` passes `RecordExtents: true` on the staged branch and stamps `LUKSDataOffset`. If the strict offset fails, the extents are dropped and the listing is sealed without positions. The snapshot and the browse listing are unaffected, so the step stays best-effort, as its header promises.
- The live-mount branch records no extents and no offset.
- `browseAtSnapshot` (cmd/renet/backup_browse_at.go) clears `Extents`, `NoExtents` and `LUKSDataOffset` before printing, so `rdc backup browse --at` output stays exactly as it is today.
- The positions ride inside the same AEAD-sealed object under the same `lineage/snapshotID` additional data. They are authenticated with the entries, need no new object, need no server change, and reveal nothing to the server.

**2. A fetch-only-these-ranges option in chunkstore (R3).**

- `RestoreOptions` gains `OnlyRanges []Range`, a list of image byte ranges; nil means the whole image, as today. `Restore` maps them to cells with the existing `TouchedCells(ranges, ImageBytes, CellBytes)` (pkg/chunkstore/grid.go:93) after the chain is materialized. This is why the caller passes ranges and not cell indices: the caller does not know `CellBytes` until the manifest is resolved.
- `assembleImage` builds its `indices` map and its feed loop from the selected cells only. ZeroCells in the selection are skipped, as they are today. The read grant is re-armed with the selected hashes only.
- `RestoreStats` gains `CellsSelected`. The existing `ChunksWanted` and `ChunksFetched` become the selection's counts, and these counters are what the tests assert against `CellsTotal - CellsZero`.
- A partial restore refuses up front, with a named i18n error, when `DestPath` already exists or `Seeds` is non-empty. Resume, seeding and stale-hole punching all assume a whole image, and a partial staging file is a scratch file, never an adoptable one.
- The mandatory `Truncate(ImageBytes)` still runs, so the staging file has the right length and every unselected cell stays a hole.

**3. The restore engine, `pkg/restorepath` (R4).**

- `plan.go` is pure, carries no build tag and is unit-tested on every target. It resolves the path and builds the fetch plan:
  - It refuses with `NO_LISTING` (exit 18, reusing `browseAtNoIndexExit`) when `ListingSource` is `live-mount`, or when `LUKSDataOffset` is 0. The payload carries a `reason` of `live-mount` or `no-positions`, beside the `absent` reason the verb already gives for a snapshot with no listing. One exit code keeps the CLI's existing exit-18 handling. The reason field names which of the three cases happened.
  - It resolves `--path` with `repodiff.CleanSubPath` against the entries. An exact match on a file or symlink restores that one entry. A directory selects itself and everything below it, through `repodiff.FilterEntries` with only `Path` set. No match is `NO_SUCH_PATH` (exit 19, the next unspent code after 18).
  - It refuses with `POSITIONS_UNAVAILABLE` when any selected regular file has `NoExtents` set.
  - It maps each written extent to the image range `[Physical+off, Physical+off+Length)`. It adds the header range `[0, off)` and returns the union as `OnlyRanges`.
  - It computes every destination path under `--to` (a file lands at `<to>/<basename>`, a directory at `<to>/<basename>/...`, as `cp -r` does). Any destination that already exists is refused with `DEST_EXISTS`.
  - Every refusal happens before a session is minted, a cell is fetched or a byte is written.
- `restorepath_linux.go` runs the plan:
  1. Create a sparse staging file at `<datastore>/repositories/.restore-<fresh uuid>` while holding the exclusive flock on `.lock-<that uuid>`. This deliberately reuses `prune.RestoreStagingPrefix`, so the existing sweep in pkg/prune/datastore.go:667 reclaims a killed run's file and needs no change.
  2. Call `chunkstore.Restore` with `OnlyRanges`.
  3. Refuse with `POSITIONS_INCONSISTENT` if any written extent lands in a ZeroCell. A written block in an image hole means the listing and the manifest disagree, and reading it would yield decrypted garbage.
  4. Open the staging file with cryptsetup. The argv is `open --readonly <img> <transient name>`, matching `luks.Device.openArgs` minus `--allow-discards` plus `--readonly`, with the passphrase on stdin as `Device.Open` does.
  5. Cross-check `DataOffsetStrict` on the staging file against the sealed `LUKSDataOffset`, and refuse on a mismatch.
  6. Read each file's written extents with `pread` on the mapper and `pwrite` them at the Logical offset into `<dest>.rdc-partial-<rand>`. Unwritten extents and gaps are left as holes. Truncate to `Size`, which also clips any preallocation beyond EOF.
  7. Set the mode, fsync, rename into place and set the mtime.
  8. Recreate symlinks with `os.Symlink` and set their mtime with `unix.UtimesNanoAt(..., AT_SYMLINK_NOFOLLOW)`.
  9. Create directories first. Set each directory's mode and mtime post-order, after its children. Skip `TypeOther` entries and count them in the record.
  10. Close the mapper and remove the staging file and its lock file in a deferred block that also runs on failure.
  11. A failure after writing has started removes every path the run created, in reverse order, and reports it. The guarantee that nothing is written covers every refusal, all of which happen in the pure plan before any write.
- `restorepath_other.go` returns an unsupported-platform error, so cmd/renet still builds for darwin and windows.
- The default `--to` is `<datastore>/restores/<snapshot-id>`, created 0700 only after the plan passes. A `--to` under `<datastore>/repositories` is refused, because prune owns that directory.

**4. The verb `renet backup restore-path` and the function `backup_restore_path` (R4).**

- cmd/renet/backup_restore_path.go takes `--datastore`, `--repo`, `--lineage`, `--at` (a snapshot id; a time is refused by name through `looksLikeTime`), `--path`, `--to` and `--password-stdin`.
- The licence, session-mint and listing-fetch half of `browseAtSnapshot` is factored into a shared `openSnapshotListing` that returns the opened `BrowseResult` and the `SessionControlPlane`, so both verbs read and open the listing in one way. `openBrowseAtListing` is reused unchanged.
- The verb prints one JSON record on stdout: snapshot id, path, to, files, dirs, symlinks, skipped, bytesWritten, cellsTotal, cellsSelected, chunksFetched, bytesFetched.
- The `FunctionDef` in pkg/functions/commands/backup.go mirrors `backup_browse_at`: lineage, at, path and to params; password on stdin; the same Requirements.
- pkg/license/tiermap.go gets `"backup_restore_path": {tier: TierNone}`, for the reason given for `backup_restore` and `backup_browse_at`: a tier gate on reading a customer's own backed-up data would let an expired licence lock them out.
- The contract under packages/shared/src/renet-contract/data is regenerated with `renet functions generate-types` (the command `rediacc_ci.quality.renet_types` prints).

**5. The CLI (R5).**

- `registerBackupRestore` gains `--path <file-or-dir>` and `--to <dir>`. When `--path` is set, the action branches before `resolveRestoreTarget`, so no target record, network id or credential copy is created, and calls `runRestorePath` in a new packages/cli/src/commands/backup-restore-path.ts. backup.ts is already near the 512-line cap in scripts/gates/check-max-lines.ts.
- The CLI refuses each of these before any execution:
  - `--path` without `--at`;
  - `--to` without `--path`;
  - `--path` combined with `--as`, `--up`, `--health-window` or `--health-timeout`;
  - a ref whose place is a storage and not a machine.
- `runRestorePath` resolves the repo record and its lineage (`lineageOf`, now exported from backup-storage-browse.ts) and requires `repo.credential`, as `runBrowseAt` does. It resolves the snapshot with the same stream scope `runChunkRestore` uses; that scope computation is extracted into an exported helper so the two paths cannot pick different snapshots for one time.
- It runs `executeRepoFunction('backup_restore_path', ...)` on `-m` or the ref's machine, and renders the record. Exit 18 is handled through the constant `RENET_NO_LISTING_EXIT`, moved from backup-storage.ts into backup-storage-browse.ts. The CLI prints a named message for each reason and propagates the renet exit code.
- `backup_restore_path` joins `RESTORE_LICENSE_FUNCTIONS` (renet-license-contract.ts) and `RENET_FUNCTION_ACCESS` as `provision`.
- The locales and the generated cli-application.md docs follow.

## Alternatives rejected

- **Restore the full image to a temp path, open it, mount it read-only and copy the path out.** Rejected as the implementation, with reasons:
  - It fetches every non-empty cell, which is exactly what N4b's accept forbids ("chunk-fetch count asserted below the full-image count").
  - It needs the image's full allocated size free on the datastore.
  - Its time grows with repository size, not with the size of the path.
  - Opening needs the passphrase anyway.
  - A read-write mount would replay the journal into a scratch copy, and a `noload` mount gives the same view this plan reads.

  It does have real advantages: it works for older snapshots and for live-mount listings, and it keeps ownership, xattrs, hard links and setuid bits. Those are the reasons it stays available as the manual fallback the refusal messages name (`rdc backup restore --at` followed by a copy). It is not wired as an automatic fallback, because a silent full download behind a flag that promises a partial one is the dishonest outcome.
- **Fetch ext4 metadata as well and mount the sparse partial image.** Rejected. The set of blocks a mount touches (superblock copies, group descriptors, bitmaps, inode tables, extent index blocks, directory blocks, journal) cannot be enumerated from a listing with confidence. A missed block reads as decrypted garbage, which the kernel's ext4 parser would then interpret. Reading known extents from the mapper needs no filesystem driver at all.
- **Decrypt LUKS2 in process (Argon2id keyslot, AF merge, AES-XTS) instead of using cryptsetup.** Rejected. It reimplements security-critical code that cryptsetup already provides on every machine renet runs on, and the passphrase path (`luks.Device.Open`) is already proven.
- **Store positions in a second sealed object beside the listing.** Rejected. The server addresses one index object per snapshot (`IndexKeys` in pkg/chunkstore/grants.go), so a second object needs an account-side change and a second fetch. Stripping the fields on the browse path costs three assignments.
- **Add `path` and `to` to `backup_restore`.** Rejected, on the precedent backup_browse_at.go:24-28 sets. `backup_restore` requires a target repository GUID and places a whole image under a target-exists check, whereas this verb places files and needs the passphrase. One verb with two contracts would make its help text a lie.
- **Lazy per-cell fetching through `cellFetcher.ReadAt` (pkg/chunkstore/seed.go) behind an nbd or FUSE device.** Rejected. It saves nothing over a precomputed range set, because the listing already names every byte needed, and it adds a long-lived userspace block device under root.

## Tasks

- [ ] R1 [writer] Record per-file extents and a strict LUKS data offset (Design 1, first five bullets). Add `FileExtent`, `BrowseEntry.Extents`, `BrowseEntry.NoExtents`, `BrowseResult.LUKSDataOffset` and `BrowseOptions.RecordExtents`. Add the `fileExtents` helper, which keeps Logical, Length and the unwritten flag, and sets `NoExtents` on any refused flag. Wire it into `ListEntries` behind the flag. Add `luks.(*Device).DataOffsetStrict` over a pure parser shared with `GetDataOffset`, and `ImageHandle.DataOffset()`. Tests:
  - `ListEntries` without the flag records no extents.
  - With the flag, a written file's extents sum to at least its size.
  - A file with a punched hole has a Logical gap.
  - An empty file has no extents and no `NoExtents`.
  - The pure parser returns the LUKS2 byte offset and the LUKS1 sector offset, and returns an error (not 16 MiB) on output with no offset.

  Owns: private/renet/pkg/repodiff/types.go, private/renet/pkg/repodiff/browse.go, private/renet/pkg/repodiff/extents_linux.go, private/renet/pkg/repodiff/mountset.go, private/renet/pkg/repodiff/browse_list_test.go, private/renet/pkg/luks/resize.go, private/renet/pkg/luks/luks_test.go. Accept: `cd private/renet && go test ./pkg/repodiff/ ./pkg/luks/ -run 'TestListEntries|TestParseDataOffset' -count=1` rc 0.
- [ ] R2 [writer] Seal positions into staged listings only, and strip them from browse output (Design 1, last three bullets). `snapshotTOCListing` passes `RecordExtents: true` and stamps `LUKSDataOffset` on the staged branch. A strict-offset failure drops the extents and still seals. The live-mount branch carries neither. `browseAtSnapshot` clears all three fields. Tests in backup_snapshot_toc_test.go, through the existing opener seam:
  - A staged listing opened from the seal carries extents and the offset.
  - A live-mount listing carries neither.
  - An offset failure still seals a listing, without positions.

  In backup_browse_at_test.go: browse-at JSON never contains the extents key or the offset key, even when the sealed listing has them.

  Owns: private/renet/cmd/renet/backup_snapshot_toc.go, private/renet/cmd/renet/backup_snapshot_toc_test.go, private/renet/cmd/renet/backup_browse_at.go, private/renet/cmd/renet/backup_browse_at_test.go. Accept: `cd private/renet && go test ./cmd/renet/ -run 'TestSnapshotTOC|TestBrowseAt' -count=1` rc 0.
- [ ] R3 [writer] Fetch only the cells covering given image ranges (Design 2). Add `RestoreOptions.OnlyRanges` and `RestoreStats.CellsSelected`, and select through `TouchedCells` after `resolveChain`. Re-arm the grant with the selected hashes only. Refuse a partial restore onto an existing `DestPath` or with `Seeds`, under new i18n keys in every renet locale. New restore_ranges_test.go, using the existing `fakeReadStore` and `buildSnapshotFixture`:
  - Two ranges in a 32-cell fixture fetch exactly the covering cells: the GET count equals `ChunksFetched`, which equals the selection size, below `CellsTotal - CellsZero`.
  - The selected cells are byte-identical to the source, and the unselected cells read as holes (SEEK_DATA).
  - The file length equals `ImageBytes`.
  - A range touching a ZeroCell fetches nothing for it.
  - An existing `DestPath` is refused with zero GETs.
  - nil `OnlyRanges` behaves exactly as before (the existing `TestRestore_*` stay green).

  Owns: private/renet/pkg/chunkstore/download.go, private/renet/pkg/chunkstore/restore.go, private/renet/pkg/chunkstore/restore_ranges_test.go, private/renet/pkg/i18n/locales/**. Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'TestRestore' -count=1` rc 0.
- [ ] R4 [writer] The engine, the verb and the function (Design 3 and 4). Add pkg/restorepath (plan.go, restorepath_linux.go, restorepath_other.go). Add cmd/renet/backup_restore_path.go with the `openSnapshotListing` factoring in backup_browse_at.go, the `backup_restore_path` FunctionDef, the TierNone tiermap row, the AddCommand and help line in cmd/renet/backup.go, and the i18n keys in every renet locale. Regenerate the renet contract.

  Tests in pkg/restorepath/plan_test.go (pure):
  - A file path selects one entry.
  - A directory selects its subtree.
  - The ranges are the header plus the shifted written extents, with unwritten extents excluded.
  - A missing path, a live-mount listing, a zero offset, a `NoExtents` file and an existing destination each return their named error.

  Tests in pkg/restorepath/restorepath_linux_test.go, on a REAL ext4-in-LUKS image. They require root and fail under `CI` without it, the pkg/storage/luks_test.go:49-55 pattern.
  - Setup: format a 256 MiB image with `luks.Device.Format`, open it, `mkfs.ext4`, and write:
    - a 5 MiB random file;
    - a directory holding a text file, a nested sparse file, an empty file and a relative symlink;
    - distinct modes and mtimes on everything.
  - Sync, unmount and close. Build the listing exactly as the snapshot step does: a read-only mount, then `ListEntries` with `RecordExtents`, then `DataOffsetStrict`.
  - Cut the image into 4 MiB cells (`HashCell`, `EncodeManifest`) behind a presigned fake `ReadPlane` that counts GETs.
  - Assert that restoring the 5 MiB file gives an equal sha256, mode and mtime, with chunk GETs equal to `ChunksFetched` and below the image's non-zero cell count.
  - Assert that restoring the directory gives a recursive comparison equal on type, sha256, mode, mtime, symlink target and sparse size.
  - Assert that `/nope` returns `NO_SUCH_PATH` with zero GETs, no `--to` directory created and no `.restore-*` left in the datastore.
  - Assert that a live-mount copy of the listing returns `NO_LISTING` with zero GETs.

  In cmd/renet/backup_restore_path_test.go, through seams: a time `--at` is refused, `ErrNoIndex` exits 18 with code `NO_LISTING` and reason `absent`, and the record JSON shape is pinned.

  Owns: private/renet/pkg/restorepath/**, private/renet/cmd/renet/backup_restore_path.go, private/renet/cmd/renet/backup_restore_path_test.go, private/renet/cmd/renet/backup_browse_at.go, private/renet/cmd/renet/backup.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/license/tiermap.go, private/renet/pkg/i18n/locales/**, packages/shared/src/renet-contract/data/**. Accept: `cd private/renet && sudo -E env PATH=$PATH go test ./pkg/restorepath/... ./cmd/renet/ -run 'TestRestorePath|TestPlan|TestBackupRestorePath' -count=1 -v` rc 0 with no `--- SKIP` line in its output, and `PYTHONPATH=.ci python3 -m rediacc_ci.quality.renet_types` rc 0.
- [ ] R5 [writer] The CLI flags and route (Design 5). Add `--path` and `--to` to `registerBackupRestore`, branching before `resolveRestoreTarget`. Add backup-restore-path.ts. Export `lineageOf` and `RENET_NO_LISTING_EXIT` from backup-storage-browse.ts, with backup-storage.ts importing the constant. Extract the stream-scope helper from `runChunkRestore`. Add the license-set and access-map rows and every CLI locale key, and regenerate the CLI docs with `npm run generate:cli-docs -w @rediacc/www`.

  New backup-restore-path.test.ts, modelled on backup-browse-at.test.ts:
  - `restore r --at T --path /a --to /b` calls `executeRepoFunction('backup_restore_path', ..., {lineage, at: <resolved id>, path: '/a', to: '/b'})` and calls none of `addRepository`, `allocateNetworkId` or `backup_restore`.
  - `--path` without `--at`, `--to` without `--path`, and `--path --up` each throw a ValidationError with zero executions.
  - A renet exit 18 sets exit code 18 and prints the reason-specific message.
  - A time `--at` resolves through the same scope helper `runChunkRestore` uses.

  Owns: packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-restore-path.ts, packages/cli/src/commands/backup-storage-browse.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/__tests__/backup-restore-path.test.ts, packages/cli/src/services/renet/renet-license-contract.ts, packages/cli/src/services/executor/renet-function-access.ts, packages/cli/src/i18n/locales/*/cli.json, packages/www/src/content/docs/*/cli-application.md. Accept: `cd packages/cli && npx vitest run src/commands/__tests__/backup-restore-path.test.ts src/commands/__tests__/backup-browse-at.test.ts` rc 0, `npx tsc --noEmit -p packages/cli` rc 0, and `npm run check:cli-docs` rc 0.
- [ ] R6 [writer] Give `backup_restore_path` a live e2e caller. Extend suite 27 (packages/e2e-tests/tests/27-backup-browse-at.test.ts), which already provisions a repo, snapshots it and reads its listing, with one restore-path tier. That tier restores one file and one directory from the snapshot the suite took and compares sha256 against the repo's live copies. It also asserts that `--path /missing` exits 19 and leaves no `--to` directory. If the coverage gate does not count suite 27 as live, add a BLOCKER entry to .ci/policy/.e2e-coverage-allowlist with the reason, and add that file to this plan's Owns. Owns: packages/e2e-tests/tests/27-backup-browse-at.test.ts. Accept: `PYTHONPATH=.ci python3 -m rediacc_ci.quality.e2e_coverage` rc 0.
- [ ] L1 [live] Hostinger, after R5 with the renet pointer bumped.
  1. Provision renet with the `renet-live` check: `PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --plan agent/plans/PLAN-backup-restore-path.md --box <sig> --target hostinger --check renet-live --write`.
  2. On an autostart repository that holds a TOC key, take a fresh snapshot with `./rdc.sh --config eu-bench backup snapshot <repo>`. Confirm that `./rdc.sh --config eu-bench backup browse <repo> --at <id>` reports `listingSource: staged`.
  3. Run `./rdc.sh --config eu-bench backup restore <repo> -m hostinger --at <id> --path <file unchanged since the snapshot> --to /tmp/rdc-restore-path-<stamp>`.
  4. Run the same with `--path <a directory>`.
  5. Compare with `./rdc.sh --config eu-bench term connect hostinger -c "sha256sum <live file> /tmp/rdc-restore-path-<stamp>/<basename>"`.
  6. Read the record's `chunksFetched` and `cellsTotal`.

  Owns: agent/plans/PLAN-backup-restore-path.md. Accept: the live_proof record rc 0; both restore commands rc 0; the two sha256 values equal; `chunksFetched` below `cellsTotal`; and `--path /no/such/path` rc 19 with `test ! -e /tmp/rdc-restore-path-<stamp>-missing` rc 0 on the machine.
- [ ] R7 [writer] Close N4b. Tick box N4b in agent/plans/PLAN-backup-program.md, citing R4's and R5's commits and L1's live_proof row, then move this plan to agent/plans/_done/. Owns: agent/plans/PLAN-backup-program.md, agent/plans/PLAN-backup-restore-path.md. Accept: `python3 .ci/scripts/quality/check_plan_deps.py` rc 0.

## Risks

- **No journal replay.** The staged copy is opened with `noload` (`imageMountOptions`, pkg/repodiff/mountset.go), because a replay would write to the uploaded bytes. On a hot snapshot, a file whose metadata was committed to the journal but not yet checkpointed can show its older extent map or size. The listing and the positions agree with each other, since both come from the `noload` view, but a full restore mounted read-write later replays the journal and can differ for writes inside the last commit interval (5 s by default). The tests and L1 sync before the snapshot. The restore record and the docs say a file written in the seconds before a hot snapshot may restore as its previous version, and that a full restore is the authority.
- **What is kept.** Permission bits only: `ListEntries` records `Mode().Perm()` (browse.go), so setuid, setgid and sticky bits are not kept. Neither are ownership (files land owned by the user renet runs as, root), xattrs, ACLs or hard links (each link restores as its own copy). Device nodes and FIFOs are skipped and counted. Each limit is named in the help text, so none of them passes silently. Recording ownership and the extra mode bits is a follow-up on the same listing fields.
- **Listing size.** Every regular file gains its extents, about 40 bytes per extent with the compact tags. A repository with millions of files grows a sealed object that is built, sealed and fetched in memory. No server-side cap on the index object was found in private/account. R2 measures the growth on the R4 fixture and on a 100k-file synthetic tree, and records both numbers in its commit.
- **Snapshot time.** FIEMAP adds one ioctl per regular file to the staged walk, which already stats every file. On a cold snapshot that time sits inside the stop window. The R2 commit records the extra walk time for the 100k-file tree.
- **Integrity scope.** Each fetched chunk is re-hashed against the manifest (pkg/chunkstore/seed.go, `cell`), and the positions are authenticated by the seal. There is no per-file content hash, because computing one would mean reading every file at snapshot time, so byte identity rests on the chunk hashes plus a correct extent map. The `POSITIONS_INCONSISTENT` check (a written extent in a ZeroCell) and the data-offset cross-check catch the two ways a correct-looking map can still point at the wrong bytes.
- **Exit codes and adoption.** Exit 19 must stay unspent. R4 greps cmd/renet for every `ExitCode()` before taking it. Older snapshots and every password-only repository refuse with exit 18 until an autostart snapshot is taken, and the refusal message says that.
