# PLAN: chunk-store BROWSE, engine-first

Status: proposal. Read-only investigation, no code written.
Branch: `0815-1`. Author: engine-first angle.

## Summary in one paragraph

A file listing is **not derivable from a chunk-store manifest today, at any cost**. The
manifest is a grid of cell hashes over the repository's LUKS **ciphertext**; it contains
no filesystem information whatsoever, not even indirectly. Browse therefore cannot be a
read-side feature bolted onto what is already stored. It needs a new artifact, produced at
snapshot time while the plaintext filesystem is still reachable, and carried alongside the
manifest. The good news is that renet already owns every piece required to produce it:
`pkg/repodiff` opens a LUKS image read-only and walks its ext4 filesystem with FIEMAP
extents, which is exactly the index builder. The plan below stages the work so that the
first stage ships a genuinely useful, credential-free, CI-testable and tutorial-able verb
with **no format change and no server change**, and only the later stages pay for remote
and historical browse.

---

## 0. Verification log

Everything below was read this session. Design docs were treated as hypotheses; every
load-bearing claim here is cited to code.

| Claim | Evidence |
|---|---|
| Manifest is a cell grid over ciphertext, no filesystem data | `private/renet/pkg/chunkstore/manifest.go:38-59` (the whole struct: `Cells []string`, `ChangedCells map[string]string`, plus geometry and identity) |
| Cells are SHA-256 of **ciphertext**, and the grid is fixed, not content-defined | `private/renet/pkg/chunkstore/grid.go:1-19` (package doc) and `manifest.go:22-25` |
| Inside the LUKS container is **ext4** | `private/renet/pkg/repodiff/types.go:4-7`; `private/renet/pkg/filesystem/ext4.go:36-62` |
| renet can already open a repo image read-only and mount its ext4 | `private/renet/pkg/repodiff/mountset.go:52-131` (`openRepoReadOnly`), `:132-147` (`mountTemp`, `ro,noatime,nosuid,nodev`) |
| renet already walks the mount and records per-file FIEMAP extents | `private/renet/pkg/repodiff/walk.go:30-70` (`walkMount`, `nodeInfo`) |
| The exclusion list for renet-managed scaffolding already exists | `private/renet/pkg/repodiff/walk.go:12-25` (`RenetManagedNames`) |
| Snapshot staging is a read-only reflink, flushed first | `pipeline_linux.go:328-354` (`StageSnapshot`), `:724-735` (`reflinkSnapshot` calls `flushBeforeReflink`, then chmods `0400`) |
| The staged reflink path is exposed on the Plan | `pipeline_linux.go:66-70` (`Plan.SnapshotPath`) |
| Restore assembles the **whole** image; there is no partial-materialize API | `private/renet/pkg/chunkstore/restore.go:29-120` (`assembleImage` truncates to `ImageBytes` and fetches every non-zero cell) |
| Object key layout, and GC's sweep prefix | `private/account/src/services/backup-chunk-store.ts:45-55` (`backupKeys`: `.../c/<hash>`, `.../m/<snapshotId>`) |
| **GC deletes any object under `/c/` not referenced by a manifest** | `private/account/src/services/backup-gc.service.ts:267-277` (lists `chunkPrefix`, deletes what is not in `referenced`), `:882-894` (`extractManifestHashes` reads only `cells` / `changedCells` / legacy `chunks`) |
| Prune deletes the manifest object itself | `backup-gc.service.ts:491` (`store.delete(deletable.map(r => r.manifestKey))`) |
| D1 stores only references, never the manifest body | `private/account/drizzle/0049_backup_storage.sql:23-40` (`backup_manifests` has `manifest_key`, no blob column) |
| No endpoint returns a manifest body; clients read it from the bucket under a read grant | `backup-storage.service.ts:1085` (`listManifests` does no bucket reads), `:682-753` (`mintReadGrant` returns `manifestChain` + manifest GET URLs) |
| Read grants are separable from write grants and require a **restore-intent session** | `backup-chunk-store.ts:407-411` (`BACKUP_READ_GRANT_ACTIONS`), `backup-storage.service.ts:707-714` (a `backup`-intent session is refused) |
| A session is minted with a signed licence blob, not an API token | `private/account/src/routes/backups.ts:70-79`; licence verification in `subscription.service.ts:1157-1231` |
| LUKS slot 0 is the high-entropy vault credential, slot 1 the machine-local keyfile | `private/renet/pkg/luks/luks.go:62`, `:592`; `private/renet/pkg/credentials/keyfile.go:15-41` |
| `pkg/vaultcrypto` exists (AES-256-GCM + PBKDF2) but **returns plaintext unchanged when no password is set** | `private/renet/pkg/vaultcrypto/vault.go:46-51` |
| zstd is already a dependency | `private/renet/pkg/embed/embed.go:21` (`klauspost/compress/zstd`) |

Two claims I could **not** fully close, carried into §11 as open questions: whether a fork's
vault credential is identical to its parent's (it must be, since a reflink shares the LUKS
header, but I did not run the command to prove it), and the exact per-repo credential plumbing
from the CLI config into renet.

---

## 1. Question 1: is a file listing derivable from a manifest? No, and not partially.

This is the finding that decides the whole design, so it is worth being blunt about.

`Manifest` (`manifest.go:38-59`) carries exactly: version, snapshot id, repository GUID,
lineage, datastore id, cell size, image size, creation time, optional parent, and either
`Cells []string` or `ChangedCells map[string]string`. Each entry is either `ZeroCell` (the
empty string, meaning a FIEMAP hole, `manifest.go:27-31`) or the lowercase hex SHA-256 of
that cell's **ciphertext** (`manifest.go:22-25`).

There is no file name, no inode, no directory structure, no extent table, and no pointer to
anything that holds them. The relationship is not "hard to extract", it is "absent". Three
consequences follow, and all three matter:

1. **No amount of manifest reading yields a listing.** Not even a partial or approximate one.
   The only derivable quantities are geometry and churn, which is precisely what the design
   doc intends to be leaky (`manifest.go:33-37`).
2. **Downloading chunks does not help without the repo key.** The cells are LUKS ciphertext.
   Reconstructing the filesystem means reconstructing the image and opening the LUKS container.
3. **There is no partial-materialize path.** `assembleImage` (`restore.go:29-120`) truncates
   to the full `ImageBytes` and fetches every non-zero cell. Even a hypothetical
   "fetch just the cells holding ext4 metadata" is chicken-and-egg: you cannot know which
   cells hold the inode tables without first reading the superblock, which means at minimum
   a multi-round-trip, root-requiring, dm-crypt-backed random-access reader over a remote
   object store. I would not build that (see §10).

### The minimum that must change

An additional artifact, produced at snapshot time and stored beside the manifest.

**It does not alter the manifest format.** `ManifestVersion` stays 1, `Validate()` is
untouched, and the server's `WireManifest` port (`backup-gc.service.ts:937-952`) stays in
lockstep with the Go struct. That is deliberate and is the single most important
compatibility property of this plan: the manifest is the one structure with a
cross-language, cross-service, GC-critical duplicate implementation, and touching it means
touching renet, the server's GC, and the server's collapse writer together.

**It must NOT be stored as a chunk.** This is a trap worth stating loudly. Content-addressing
the index and writing it under `t/<sub>/l/<lineage>/c/<hash>` looks natural and is fatal:
`backup-gc.service.ts:267-277` lists that exact prefix and deletes every object whose hash is
not in some manifest's `cells` / `changedCells`. An index chunk would be silently deleted on
the next GC pass, and the failure would surface as "browse worked last week and does not
today". The index needs its own prefix.

Proposed key: `t/<sub>/l/<lineage>/x/<snapshotId>`, added to `backupKeys`
(`backup-chunk-store.ts:45-55`) so it stays in the single-source helper rather than being
string-built at a call site.

---

## 2. Design: three stages, each independently useful

Stage 1 is the one I would build first and the only one that is fully credential-free.

### Stage 1: the reader (local images, no server, no egress, no format change)

`renet backup browse` opens a LUKS image read-only, mounts its ext4 at a temp dir, walks it,
prints a listing, unmounts. Sources it can read, all local:

- the **live repository** (the canonical mount, reused in place if already mounted),
- the **anchor reflink** at `prune.BackupAnchorPath(datastore, guid)`, which is the last
  successfully committed snapshot (`chunkstore/anchor.go:17-20`),
- an arbitrary **image path**, which is what makes "restore to a scratch datastore, then
  browse" work today for any historical snapshot.

This is close to pure reuse. `openRepoReadOnly` (`repodiff/mountset.go:52-131`) already does
the LUKS open, the mapper handling, the temp mount and the LIFO cleanup that never touches a
mount it did not create. `walkMount` (`repodiff/walk.go:30-70`) already produces the node
records. The work is extracting an image-path-addressed variant of `openRepoReadOnly` and
adding a listing formatter.

What stage 1 answers: "what is in this repository right now", "what was in the last
committed snapshot", and after a restore, "what is in this snapshot". What it does **not**
answer: "is my file in last Tuesday's backup" without first restoring Tuesday.

### Stage 2: the writer (index emitted and uploaded during snapshot)

During `backup snapshot`, after `StageSnapshot` returns the read-only reflink and before or
alongside `PlanFromStaging`, open the **staged reflink** read-only and walk it. The reflink
is the right source, not the live mount: it is the exact bytes the manifest describes, so the
index cannot skew from the snapshot it claims to describe. Walking the live mount instead
would produce an index that disagrees with its own snapshot by whatever changed during the
run, which for a browse feature whose entire purpose is answering "will the restore contain
this file" is the one lie it must not tell.

Cost note: this is an O(files) walk, not O(image). It rides the expensive half
(`PlanFromStaging`, which is O(image) on a rehash), so it should be close to free in
relative terms. It must be measured, not assumed (§8).

The index is compressed, then encrypted client-side (§4), then uploaded under the new `/x/`
key, then referenced from D1 at commit time.

### Stage 3: the remote reader (browse a historical snapshot without restoring it)

`renet backup browse --at <snapshotId>` mints a **restore-intent** session, requests a read
grant naming only the index key, does one GET, decrypts, and prints. One small object, no
chunk traffic, no image assembly.

Snapshots taken before stage 2 shipped have no index. The honest behaviour is to say so and
name the escape hatch, not to print an empty listing:

```
No file index for snapshot 20260812T031500Z-1a2b3c4d (taken before indexing was enabled).
Restore it and browse locally:
  rdc backup restore my-app --at 20260812T031500Z-1a2b3c4d --as my-app-inspect
  rdc backup browse my-app-inspect
```

Per the repo's clean-break rule there is no backfill command and no dual path. Old snapshots
age out under retention and the gap closes on its own.

---

## 3. Question 2: what works offline and without the account server

Precisely:

| Capability | Account server | Licence | Network |
|---|---|---|---|
| Browse live repo (stage 1) | no | no | no |
| Browse anchor / last snapshot (stage 1) | no | no | no |
| Browse an arbitrary local image (stage 1) | no | no | no |
| **Emit** an index during snapshot (stage 2) | no, for the emit itself | no | no |
| **Upload** that index (stage 2) | yes | yes | yes |
| Browse a remote historical snapshot (stage 3) | yes | yes | yes |

The split falls out of the existing auth model and is not a design choice I am free to make.
`POST /backups/session` is authenticated by an Ed25519-signed licence blob
(`routes/backups.ts:70-79`), and a read grant additionally requires that session to carry
`restore` intent (`backup-storage.service.ts:707-714`). So anything that touches the bucket
requires an installed repository licence and a reachable account server, full stop.

One nuance worth carrying into the CLI's error text: a `restore`-intent session is allowed on
a **lapsed** subscription within the retention window
(`backup-storage.service.ts:249-269`, `:276-332`). Browse is a read operation and should ride
that same path, so an operator whose subscription lapsed can still inspect what they have
before deciding whether to restore it. That is the correct behaviour and it is free, provided
browse mints its session with `intent: 'restore'` rather than the default `'backup'`
(`dto/backup.dto.ts:36`).

---

## 4. Question 3: encryption, and what leaks. Treated as a security question.

### What the store can see today

Chunks are LUKS ciphertext, so the bucket operator and the account server see **nothing** of
content. Manifests are deliberately plaintext, and the design is explicit that what they leak
is "grid geometry and churn" (`manifest.go:33-37`). That is the current, deliberate boundary.

### What a naive index would leak

A plaintext file index moves file names, sizes, permissions, ownership and mtimes across that
boundary. That is a material regression, not a UX detail. File names are content: `/etc/
shadow`, `/var/lib/postgresql/`, customer names in an export directory, the shape of an entire
deployment. Anyone who can read the bucket would gain the full file tree of every backed-up
repository, for every snapshot, forever.

**So the index must be encrypted client-side, and must fail closed.**

### Which key

Not the machine keyfile. `{datastore}/.credentials/keys/<guid>.key`
(`credentials/keyfile.go:38-41`) lives in the datastore, outside the image, and is therefore
**gone in the disaster the feature exists to serve**. An index encrypted with it would be
undecryptable on a fresh machine, which is exactly when an operator wants to browse before
committing to a multi-hour restore.

The durable secret is the **LUKS slot-0 vault credential** (`luks.go:592` calls it the
vault-password slot; `luks.go:62` documents it as a high-entropy credential, never
human-chosen). It lives in the config universe, which is itself the thing that survives the
machine, so it is available wherever a restore is possible.

Proposed derivation: `HKDF-SHA256(vaultCredential, salt = lineage GUID, info =
"rediacc-backup-index-v1")`. The authority granted is then exactly equal to the authority to
restore: anyone who can decrypt the image can read the index, and nobody else. No new
capability is created, which is the property that makes this defensible.

### The failure mode to design against explicitly

`pkg/vaultcrypto` is the obvious thing to reach for and it must **not** be used here as-is.
`EncryptString` returns the plaintext unchanged when no password is set
(`vaultcrypto/vault.go:46-51`). For a config field that is a reasonable convenience. For a
backup index it means a misconfigured or credential-less snapshot run would upload the
complete plaintext file tree of the repository to the object store, successfully, with no
error anywhere. That is precisely the class of silent-wrong-result failure the chunkstore
package spends its comments ruling out.

The index writer therefore gets its own small module that **errors** rather than degrading,
and the test suite gets an explicit negative for it (§8).

### Residual leak even when encrypted

The `/x/<snapshotId>` object's **existence and size** are visible to the store. Size
correlates loosely with file count. That is a real but small leak, of the same order as the
churn already visible from manifests, and I would accept it rather than pad. It should be
written down in `docs/backup-storage/02-design.md` rather than left implicit.

### One more, easy to miss

`backup-gc.service.ts:491` deletes manifest objects on prune. If the index is not deleted on
the same path, pruned snapshots leave their indexes behind: a storage leak, and worse, file
metadata that outlives the snapshot it describes and the retention policy that was supposed
to erase it. Index deletion belongs in that same batch, not in a follow-up sweep.

---

## 5. Question 4: cost

Egress is dominated by the design choice, not by tuning.

Rough arithmetic for a 20 GiB repository at the default 4 MiB cell size
(`grid.go:26-33`) holding 50,000 files:

| Path | Bytes moved | Notes |
|---|---|---|
| Manifest fetch (already happens on restore) | ~350 KB | 5,120 cells x ~68 bytes of JSON |
| **Index fetch (proposed browse)** | **~1 MB** | est. 120 bytes/record raw, ~6 MB, zstd to roughly 1 MB |
| Restore-then-browse (today's only option) | 20 GiB | full `assembleImage`, every non-zero cell |

That is roughly a 20,000x reduction, and it is the entire justification for stage 2. The
numbers marked "est." are estimates and must be replaced with a measurement from the local
round-trip proof before the design doc quotes them.

On billing specifically: Cloudflare R2 does not charge egress, so on R2 the cost is Class B
operations, and browse is **one** Class B operation against roughly 5,000 for the equivalent
restore. On the presigned-S3 backend, which is what production actually selects
(`backup-chunk-store.ts:948-985`), egress is billed per byte, and at typical S3 pricing a
restore-to-browse on this example is on the order of a dollar or two per inspection while an
index browse is a fraction of a cent. Either way the ratio, not the absolute number, is the
argument.

Two further cost properties worth locking in as requirements:

- Browse must request a read grant naming **only** the index key. Read grants on the
  presigned-S3 backend are per-object (`backup-chunk-store.ts:780`, `:855-871`), so this is
  achievable and should be asserted in a test, not merely intended. A browse that
  incidentally mints chunk URLs would be handing out restore-scale authority for a listing.
- Browse must not walk the manifest chain. `mintReadGrant` resolves the full chain root to
  requested (`backup-storage.service.ts:617-625`, `:719`), which for a deep segment means real
  work on the server and a chain-length failure mode that has nothing to do with browsing. The
  index is self-contained per snapshot by construction, so browse should ask for the index key
  alone and never trigger chain resolution.

---

## 6. Question 5: the verb and its shape

Positional refs, matching the house convention and the neighbouring backup verbs
(`backup verify <repo-ref>` at `backup-storage.ts:232`, `backup restore <artifact-ref> --at`
at `backup.ts:159`).

```
rdc backup browse <repo-ref> [--at <snapshot>] [--path <subdir>] [--depth <n>]
                             [--limit <n>] [--long]
```

- `<repo-ref>` is the usual `name`, `name:tag`, `name@machine` ref. Machine is derived.
- `--at <snapshot>` mirrors `backup restore --at` exactly. Absent means the live repository.
- `--path <subdir>` mirrors the retired `rdc storage browse --path`
  (`packages/cli/src/commands/storage.ts:259`), which preserves continuity for the operator
  who lost that verb.
- Default table columns are `name`, `type`, `size`, `modified`, which is byte-for-byte the
  shape the retired browser produced (`storage.ts:274-289`). An operator who used the old
  verb gets the same output shape back.

The renet side is `renet backup browse`, contract function name `backup_browse`, invoked
through `executeRepoFunction(..., { captureOutput: true })` exactly as `backup verify` does
(`backup-storage.ts:238-256`), with the JSON payload extracted using the existing
`stripCallbackPrefix` / `extractBackupListPayload` helpers
(`packages/cli/src/commands/repo-backup-list.ts:32-65`).

**One non-negotiable output requirement.** Every browse result, table and JSON, states its
source and that source's timestamp:

```
Source: snapshot 20260812T031500Z-1a2b3c4d  (2026-08-12 03:15:00 UTC, remote index)
```

The verb can answer from the live repository, the local anchor, or a remote index, and those
are three different questions. Printing a listing without saying which one was answered is
how an operator concludes a file is safely backed up when they are actually looking at the
live working tree.

**Related, and I would include it:** `rdc backup manifests` should gain an `indexed` column so
the operator knows which snapshots are browsable before they ask. That needs a nullable
`index_key` column on `backup_manifests` (`drizzle/0049_backup_storage.sql:23-40`) plus the
DTO field (`dto/backup.dto.ts:256-270`). Without it, browse is guess-and-check across a
retention window.

---

## 7. Implementation plan, in dependency order

### Stage 1: local browse (no server change, no format change)

1. `private/renet/pkg/repodiff/mountset.go`
   Extract an exported, image-path-addressed opener from `openRepoReadOnly` (`:52-131`).
   Today it hardcodes `filepath.Join(datastore, "repositories", guid)` at `:56` and resolves
   credentials by GUID at `:114-122`. Stage 1 needs `(imagePath, keyOrCredential)`. Keep the
   existing GUID entry point as a thin wrapper so `repo diff` is untouched.
   *Consider moving the opener to a new `pkg/imagemount` if `repodiff` importing cleanly
   proves awkward; decide when the extraction is in hand, not now.*
2. `private/renet/pkg/backupindex/index.go` (new)
   The record type and the NDJSON writer/reader. Reuse `repodiff`'s `nodeInfo` shape
   (`walk.go:60-70`) and `RenetManagedNames` (`walk.go:12-25`) rather than redefining either.
   Header record carries version, snapshot id, repo GUID, lineage, created-at, file count,
   total bytes.
3. `private/renet/pkg/backupindex/walk.go` (new)
   Thin adapter over `repodiff.walkMount`. If `walkMount` needs exporting, export it rather
   than copying it. A hand-written twin of a walker is exactly the duplication `grid.go:15-19`
   warns about.
4. `private/renet/cmd/renet/backup_browse.go` (new)
   The verb: resolve source (live / anchor / explicit image path), open read-only, walk,
   filter by `--path` and `--depth`, emit JSON on stdout with the source header.
5. `private/renet/pkg/i18n/locales/*.go`
   New message keys, all 13 locales.
6. CLI surface. Per the checklist established for this repo:
   - `packages/cli/src/commands/backup-storage.ts` (register inside
     `registerBackupStorageCommands`, `:512`)
   - `packages/cli/src/i18n/locales/en/cli.json` plus the 12 other locales
   - `packages/cli/src/i18n/locales/.translation-hashes.json` (regenerate)
   - `packages/cli/src/config/command-planes.ts` (mandatory; `machine`)
   - `packages/cli/src/config/command-metadata.ts` (mcp block or exclude reason)
   - `packages/cli/src/config/command-docs.ts` (examples, keywords, and an output hint,
     since this is a list-shaped verb; `primaryKey` must be in `columns`)
7. Regenerated artifacts, all committed:
   - `packages/shared/src/cli-contract/data/contract.generated.ts`
   - `packages/shared/src/cli-contract/data/contract.json`
   - `packages/shared/src/cli-contract/data/i18n/*.json` (13 files)
   - `packages/cli/scripts/command-tree.json`
   - `.claude/skills/rdc/reference.md`
   - `packages/shared/src/renet-contract/data/functions.generated.ts` (new renet verb)
8. `.e2e-coverage-allowlist` only if stage-1 coverage genuinely cannot land in the same
   change. It should land (see §8), so this line should not be needed.

### Stage 2: index emission and upload

9. `private/renet/pkg/backupindex/crypto.go` (new)
   HKDF derivation and chunked AES-256-GCM framing. **Fails closed** with no credential.
   Explicitly does not use `pkg/vaultcrypto` (`vault.go:46-51`).
10. `private/renet/pkg/chunkstore/session.go` and `uploader.go`
    Request and use an index key in the write grant.
11. `private/renet/cmd/renet/backup_snapshot.go` and `backup_snapshot_cold.go`
    Build the index from `Plan.SnapshotPath` (`pipeline_linux.go:66-70`), upload, and pass the
    index key to commit. Both paths, since the cold path is a separate orchestrator.
12. `private/account/src/services/backup-chunk-store.ts`
    Add `index:` to `backupKeys` (`:45-55`); extend write-grant and read-grant minting to sign
    the index key. Do **not** add it to the chunk keyspace.
13. `private/account/src/services/backup-storage.service.ts`
    `commitManifest` (`:807`) records `index_key`; `mintReadGrant` (`:682`) can sign an index
    key **without** resolving the manifest chain.
14. `private/account/drizzle/00NN_backup_index.sql` (new)
    Nullable `index_key` on `backup_manifests`.
15. `private/account/src/db/schema.ts`, `src/dto/backup.dto.ts`
    Schema and DTO for the above, including the `indexed` field on the manifests listing.
16. `private/account/src/services/backup-gc.service.ts:491`
    Delete the index object alongside the manifest on prune. **This one is a data-retention
    requirement, not housekeeping** (§4).

### Stage 3: remote browse

17. `private/renet/cmd/renet/backup_browse.go`
    `--at` path: restore-intent session, read grant for the index key only, one GET, decrypt,
    print. Honest refusal with the restore-then-browse hint when no index exists.
18. `packages/cli/src/commands/backup-storage.ts`
    Surface `--at`; map the "no index" condition to the hint text rather than an empty table.

---

## 8. Test plan

### Renet unit tests (run in plain `go test ./pkg/...`, no VM, no root where possible)

`pkg/backupindex/index_test.go`
- round-trip: write N records, read them back, byte-identical
- header/version refusal, matching the strictness of `manifest.go:74-130`
- truncated file fails loudly rather than yielding a short listing
- `RenetManagedNames` exclusions are honoured (a `.rediacc.json` at top level never appears)

`pkg/backupindex/crypto_test.go`
- **the negative that matters most**: no credential means `error`, never plaintext output.
  This is the direct guard against the `vaultcrypto/vault.go:46-51` behaviour, and it is the
  one test whose absence would let the leak ship. Assert on the returned error AND assert the
  output buffer is empty.
- wrong key fails authentication rather than producing garbage
- a flipped byte anywhere in the ciphertext fails the GCM tag
- derived key changes when lineage changes

`pkg/backupindex/walk_test.go` (btrfs/root tier, alongside the existing LUKS test helpers at
`pkg/testutil/luksext4.go:19-81`)
- build a real LUKS+ext4 image, populate it, index it, assert the listing matches
- index the **staged reflink** while the live mount is being written, and assert the index
  matches the reflink and not the live tree. This is the skew property from §2 and it is the
  reason to prefer the reflink; an assertion is what makes it a property rather than an
  intention.

`cmd/renet/backup_browse_test.go`
- flag parsing, source-precedence, and the source header appearing in output
- `--at` with no index produces the refusal text and a non-zero exit, not an empty listing

### Which e2e suite, and what actually runs in CI

Stage 1 belongs in **suite 25** (`packages/e2e-tests/tests/25-backup-chunk-store.test.ts`),
and this is the important scheduling point in the whole plan.

Suite 25 runs **unconditionally** in CI (`packages/e2e-tests/playwright.config.ts:113`) and
is the only real chunk-store coverage that executes today. It runs against the KVM fleet with
a `--nolicense` renet and **no account server**. Stage 1 requires neither, so stage-1 browse is
fully exercisable there.

Suite 26 (`26-backup-storage-cli.test.ts`) is gated behind `BACKUP_STORAGE_SUITE`, which
appears in **no workflow and nowhere under `.ci/`**. It collects zero tests in CI, and
`.e2e-coverage-allowlist:39-55` says so explicitly. Stage 2 and stage 3 coverage lands there
and therefore **does not run in CI** until someone wires a live account server plus a real
machine into a workflow. I would not pretend otherwise in the plan or in the allowlist.

So, stated plainly:

- **Runnable in CI**: browse the live repo, browse the anchor, `--path` and `--depth`
  filtering, the source header, the no-index refusal path, and every renet unit test above.
- **Not runnable in CI**: index upload, remote index fetch, read-grant scoping, and anything
  touching the account API. These run in `programs/backup-storage/local-roundtrip.sh` and
  `scripts/drills/backup.sh`, which are operator-driven.

**Making the runnable part meaningful rather than a smoke test.** A browse test that asserts
"exit code 0 and some output" would pass against a stub. Three assertions give it teeth:

1. **Write a known tree, then assert the listing exactly.** Create a specific set of files
   with specific sizes and modes inside the repo, and assert the full listing matches, including
   that renet-managed scaffolding is absent. A listing that is merely non-empty proves nothing.
2. **Assert the source header names the right source.** Run browse with and without an
   intervening `backup snapshot` and assert the live-repo and anchor listings **differ** in the
   expected direction. This is the mutation check for the whole feature: if browse silently
   answered from the live tree in both cases, this is the only assertion that catches it.
3. **Assert the no-index refusal is a refusal.** Non-zero exit and the hint text, so the
   stage-3 fallback cannot regress into an empty table.

For the read-grant scoping requirement from §5, the meaningful assertion is server-side and
belongs in the account server's own vitest rather than e2e: given a browse-shaped read-grant
request, assert the response contains the index URL and **zero** chunk URLs.

---

## 9. Tutorial plan

Skipping a tutorial is denied, and the constraint that shapes the answer is that the tutorial
harness has **no account credentials and a `--nolicense` renet**
(`.ci/tutorials/tutorial-backup-restore.sh:18-34` measures this and records the exact
failures: `backup snapshot --dry-run` exits 1 with "no installed repository license",
`backup manifests` and `backup usage` exit 2 with "Subscription token required";
`.github/workflows/ci-ops-test.yml:203-292` sets no `REDIACC_ACCOUNT_SERVER`).

**Stage 1 browse is fully demonstrable under that constraint, and stages 2 and 3 are not.**
That is not a workaround, it is the same property that makes stage 1 CI-testable.

### Recommendation: it belongs in `tutorial-backup-restore`, not its own tutorial

Three reasons:

1. The tutorial is **already being rewritten this campaign** because it taught the retired
   rclone flow. Its committed cast still types `rdc storage import`, `rdc storage list`,
   `rdc repo push/pull` and `rdc backup list`, and the storyboard's first two cast scenes are
   `rdc storage import rclone.conf` and `rdc storage list`. A re-record is already required, so
   adding browse costs one more scene rather than a whole new artifact set (script, storyboard,
   cast, 13 transcript files, 13 timeline files, and a docs page per locale).
2. Browse without restore is not a story. "Check before you restore" is a beat in the
   restore narrative, not a separate lesson, and it is the beat that most directly replaces
   what `rdc storage browse` used to provide.
3. A separate tutorial would need its own place in the `order:` frontmatter sequence
   (`.ci/tutorials/run-sequence.sh:5-10, 36-46`), which reshuffles the whole sequence for a
   verb that takes fifteen seconds to demonstrate.

### What the scene demonstrates

Executed live on camera, credential-free:

```
rdc backup browse my-app
rdc backup browse my-app --path app/config
```

Narrative beat: "before you restore, look inside." Then the existing restore beat follows and
lands harder, because the operator has just seen the file they are restoring.

Two constraints from the cast gates, both easy to satisfy and both easy to trip:

- `validate-tutorial-cast-output.js` rejects raw CLI JSON envelopes where a table belongs, and
  it is exactly why `rdc backup verify` is currently kept off camera in the silenced setup
  block (`tutorial-backup-restore.sh:29-34`). Browse must print a **table** by default. The
  column shape inherited from the retired browser (`name`, `type`, `size`, `modified`) is
  already the right answer.
- The gate also rejects on-camera `|| true`, `2>/dev/null` and `timeout N`
  (`validate-tutorial-cast-output.js:48-51`), so the browse command must genuinely succeed on
  the tutorial fleet with no licence. Stage 1 does. This is worth a live check on the harness
  before the scene is written rather than after the re-record.

**Explicitly out of tutorial scope:** stage 2 and stage 3. Uploading and fetching a remote
index cannot run without an account server and a licence, and a `type_only_cmd` scene that
types `rdc backup browse my-app --at <snapshot>` without executing it is what the tutorial
already does for the chunk store generally. If the campaign wants the remote story on camera,
that is a request for account credentials in the tutorial harness, which is an operator
decision and a much larger change than this feature.

---

## 10. Trade-offs, and what I would not build

**I would not build remote random-access into the image.** Fetching only the cells that hold
ext4 metadata, assembling a sparse image, and opening dm-crypt over it is the design that needs
no index. It is also multi-round-trip, needs root and a loop device on the browsing machine,
turns one predictable GET into an unpredictable number of them, and its cost scales with
filesystem fragmentation rather than with anything the operator can reason about. The index is
one object and one GET.

**I would not add a field to `Manifest`.** It is duplicated across languages
(`manifest.go:38-59` and `backup-gc.service.ts:937-952`), it is validated on encode and decode
in both, the server now writes it during collapse, and GC correctness depends on reading it
exactly right. A sidecar under a new prefix buys the same capability for none of that risk.

**I would not content-address the index.** Covered in §1: GC would delete it
(`backup-gc.service.ts:267-277`). Deduplication across snapshots would be a real win here since
most file trees barely change, but not at the price of an object the garbage collector believes
is garbage. If dedup becomes worth it later, the right shape is a delta index parented like the
manifest chain, and that decision should wait for a measurement showing index storage actually
matters.

**I would not backfill indexes for existing snapshots.** It would mean restoring every
historical snapshot to walk it, which is the exact cost the feature exists to avoid, times the
retention window. Clean break, per the repo's standing rule: old snapshots are not browsable,
browse says so, and the window closes as retention rolls forward.

**I would not put browse behind the MCP surface** without a separate look. It lists file names,
which is the most useful thing an agent could exfiltrate from this system, and
`command-metadata.ts` already carries `mcpExcludeReason` for the interactive file browser
(`:841`). Defaulting to excluded and revisiting deliberately is the cheaper mistake.

**Accepted trade-off: hot-snapshot indexes describe a crash-consistent filesystem.** The
staged reflink is taken after a flush (`pipeline_linux.go:724-735`) but without quiescing, so a
hot snapshot's ext4 journal may be dirty. Mounting read-only with `norecovery` gives a listing
that can miss the last few seconds of metadata updates. Mounting without `norecovery` lets the
kernel replay the journal, which writes, and the reflink is chmod `0400`. The cold path
(`backup_snapshot_cold.go`) quiesces containers and has neither problem. I would use
`norecovery`, document the bound, and note in the output header when the source was a hot
snapshot. Attempting journal replay on a backup artifact to make a listing marginally fresher
is not a trade I would make.

---

## 11. Open questions and risks

1. **Fork credential identity.** A fork is a reflink and shares the LUKS header, so slot 0
   should be identical to the parent's and an index encrypted under the lineage should be
   readable across the fork family. I did not prove it. Verify before building §4's derivation:
   fork a repo, then `cryptsetup luksDump` both images and compare slot 0, and confirm the
   parent's credential opens the fork.
2. **CLI-to-renet credential plumbing.** I found the LUKS side (`luks.go:80-222`, password on
   stdin) but did not trace how the per-repo vault credential reaches renet for a given verb.
   Trace it before writing `backupindex/crypto.go`; the derivation is only as available as that
   plumbing is.
3. **Index walk cost on a large repository.** Asserted to be O(files) and cheap relative to the
   O(image) rehash. Measure it on a repo with a large file count before stage 2 lands, and put
   the number in `docs/backup-storage/02-design.md`. If it turns out to be significant, the
   mitigation is to make indexing opt-out per repo, not to move the walk to the live mount.
4. **Estimated sizes in §5.** Replace with measurements from the local round-trip proof.
5. **Scope check for the operator.** Stage 1 is small, self-contained, credential-free, and
   ships the tutorial requirement. Stages 2 and 3 are a cross-repo change spanning renet, the
   account server, and a D1 migration, and their tests cannot run in CI as it stands. My
   recommendation is to land stage 1 in this campaign and take stages 2 and 3 as one deliberate
   big-bang rather than trickling them, but the packaging is the operator's call.
