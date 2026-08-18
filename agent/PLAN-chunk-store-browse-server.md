# PLAN: chunk-store BROWSE, argued from the account server and the CLI

Angle assigned: server-and-client-first, renet changes as a last resort.
Branch: `0815-1`. Status: design only, no code written.

Every load-bearing claim below carries a `file:line`. Claims I could not verify
by running something are marked **UNMEASURED** and carry the command that would
settle them.

---

## 0. Verdict first

**The engine has to produce the file index. My angle cannot avoid that, and a
plan that pretended otherwise would be lying.** But the engine is the wrong
place to *serve* a browse, and that half of the sibling angle is wrong. The
correct split is:

| Concern | Owner | Why |
|---|---|---|
| Producing a file index for a snapshot | **renet**, at snapshot time | Only the machine holding the LUKS credential can see filenames, and only the staged reflink is byte-consistent with what was uploaded |
| Storing it | **account server + bucket**, opaquely | It must survive the machine that made it |
| Serving it | **account server**, over the existing E2E tunnel | A browse whose whole purpose is "should I restore?" must work when **no machine survives**. Routing it through an executor makes it useless in the disaster it exists for |
| Reading it | **CLI**, decrypting locally | The server must never learn filenames |

So: one small, well-bounded renet change (a TOC writer), and the rest is server
and CLI. If the sibling plan proposes `renet backup browse` executed on a
machine that holds the repo, it has designed a browse that cannot run during a
disaster recovery, and that is the case that motivated the verb.

**Ship order:** the verb `rdc backup browse <repo-ref>` lands with a degraded
but honest v0 that needs no renet at all (§5, Increment A), then gains file
listing when the engine starts writing TOCs (Increment B). One verb, two
fidelity levels, no second command.

---

## 1. What is actually true (verified)

### 1.1 A snapshot is a block image. There is no file list anywhere.

`chunkstore.Manifest` (`private/renet/pkg/chunkstore/manifest.go:38-59`) is:
version, snapshotId, repositoryGuid, lineage, datastoreId, cellBytes,
imageBytes, createdAt, parent, and either `Cells []string` (positional array,
index = 4 MiB cell number, value = SHA-256 hex or `""`) or
`ChangedCells map[string]string`. There is no path, size, mode, uid, or mtime
field. The comment at `manifest.go:33-37` says so outright: manifests are
"structurally plaintext... the only things they leak are grid geometry and
churn."

What gets chunked is the **LUKS container file**, opened at
`filepath.Join(opts.DatastorePath, "repositories", opts.GUID)` and reflinked
(`private/renet/pkg/chunkstore/pipeline_linux.go:346-347`, `:724-729`), read
with `ReadAt` at raw offsets (`private/renet/pkg/chunkstore/uploader.go:397-406`).
The hash is over ciphertext by design
(`private/renet/pkg/chunkstore/hash.go:15-16`). **The snapshot path never
unlocks or mounts a filesystem.** That is not an oversight, it is what makes
the chunk store safe to hand to a server.

Consequence: nobody in either repo can answer "what files are in this
snapshot" today, and the data to answer it does not exist at rest.

### 1.2 The server's snapshot knowledge is exactly eleven columns

`backup_manifests` (`private/account/src/db/schema.ts:1421-1444`):
`subscription_id, lineage_guid, stream_id, snapshot_id, manifest_key,
parent_snapshot_id, cell_size_bytes, total_bytes, added_bytes,
added_chunk_count, created_at`. Indexes at `:1442-1444`.

The worker *can* read the manifest object from the bucket, and already does:
`BackupGcService` GETs and parses manifests at
`private/account/src/services/backup-gc.service.ts:246` and `:618`, and writes
collapsed ones back (`validateManifestShape`, `:977`). Its parsed shape,
`WireManifest` (`backup-gc.service.ts:937-952`), is the same block grid. So the
server today knows: how big the image is, how the grid is cut, which cells
changed, and when. It knows nothing about the namespace inside.

### 1.3 The bucket has exactly two key families

`t/<subId>/c/<sha256>` and `t/<subId>/l/<lineage>/m/<snapshotId>`
(`private/account/src/services/backup-chunk-store.ts:45-56`). Both GC
(`backup-gc.service.ts:694`) and the reconciliation endpoint
(`private/account/src/services/backup-storage.service.ts:1258-1263`) classify
bucket listings into exactly those two branches. There is no index object, no
TOC, no `index.json` (confirmed by grep across both repos).

### 1.4 There is no browse endpoint, and `rdc storage browse` is NOT retired

The team-lead brief says `rdc storage browse` "gave" file-level visibility, past
tense. **Correction, verified:** it is still registered and still works. It is
at `packages/cli/src/commands/storage.ts:257-291`, spawning the operator's own
`rclone` from `PATH` (`packages/cli/src/services/repo/storage-browser.ts:60,89`),
and the campaign's own decommission doc explicitly keeps it:
`docs/backup-storage/05-docs-and-decommission.md:88-89` ("`rdc repo push/pull
--to/--from` and `storage browse` stay") and `docs/backup-storage/README.md:89`
lists it under **Explicitly OUT**.

This matters for the design: `storage browse` browses a **customer rclone
remote**, a different storage system with a different trust model. The chunk
store must not be bolted onto that noun. Two storage systems behind one verb is
how an operator ends up unable to say what they are looking at.

On the server, a grep for `browse|/files|listFiles|/tree` across
`private/account/src/**` returns zero route matches. The closest surfaces are
`GET /backups/manifests` (`private/account/src/routes/backups.ts:136`, D1 rows
only) and `POST /backups/verify` (`:204`, six counters, never keys).

### 1.5 The CLI cannot fetch bucket objects at all today

This is the constraint that shapes the whole transport design, and it is easy
to miss.

The bucket-facing endpoints (`/grants`, `/read-grants`, `/exists`, `/commit`)
are all guarded by `backupSessionAuth`
(`private/account/src/routes/backups.ts:59-64`), which requires an
`X-Backup-Session` token minted at `POST /backups/session` by presenting an
**Ed25519-signed repository license blob**. That blob lives on the machine. The
CLI does not have one.

The CLI's own credential is an API token with `backup:read`
(`private/account/src/routes/backups.ts:126,138,154,206`), which reaches only
the D1-index reads. So **a CLI-side browse cannot presign or fetch a bucket
object without a new server route.** Adding that route is the central
server-side deliverable of this plan.

### 1.6 The offline cache does not cover this, and CLAUDE.md overstates it

`accountServerFetch` (`packages/cli/src/services/account/account-client.ts:191-268`)
is seal, POST to `/account/api/v1/tunnel`, open, throw on `status >= 400`. No
cache read, no cache write, no unreachable-error classification.

The offline cache is config-storage only. Its serve branch is
`packages/cli/src/services/config/config-base.ts:194-222`, keyed on
`RemoteUnreachableError` minted only by the config adapter
(`packages/cli/src/adapters/remote-config-adapter.ts:399-411`), and the "cache"
is the config file itself re-merged (`packages/cli/src/services/config/remote-cache.ts:27-46`).

Also worth recording, because a later session will otherwise trust the claim:
**"encrypted-at-rest local cache" is conditional.** Field encryption only fires
when `config.encryption.mode === 'master-password'`
(`packages/cli/src/adapters/config-file-storage.ts:42-44,84-97`), which is set
only by `rdc config init --master-password`
(`packages/cli/src/commands/config.ts:56-69`). `config remote enable` does not
set it. A remote-enabled config without a master password caches the whole
server copy as plaintext JSON at mode 0600.

### 1.7 Team scoping on backup data does not exist

`apiTokenAuth` checks `token.teamId` only for existence and archival
(`private/account/src/middleware/api-token.ts:21-27`), then sets
`apiTokenSubscriptionId` (`:48`). Every backup handler uses that subscription id
directly as the entire query scope (`private/account/src/routes/backups.ts:128,
142, 158, 175, 190, 206`). There is **no team column on any of the eight backup
tables** (`schema.ts:1380-1595`).

So the answer to "what stops one team browsing another's snapshots" is: **within
one subscription, nothing.** Any `backup:read` token sees every lineage. Today
that exposes sizes, chunk counts and snapshot times. A file listing would turn
the same hole into filename disclosure across teams. See §3.3 for why this
argues for the encrypted design rather than against browse.

### 1.8 The engine already has the hard part of building a TOC

`private/renet/pkg/repodiff/` walks a mounted repo and records every regular
file's byte ranges. `openRepoReadOnly` (`private/renet/pkg/repodiff/mountset.go:52-131`)
resolves a GUID to a readable ext4 mount: reuse a live mount in place, or mount
the canonical mapper read-only at a temp dir, or LUKS-open the image under a
**transient mapper name** with the autostart keyfile
(`mountset.go:112-127`) and mount it `ro,noatime,nosuid,nodev`
(`mountset.go:132-146`), with a LIFO `close()` that touches nothing it did not
create (`mountset.go:149-170`). The per-file walk with FIEMAP extents is
`private/renet/pkg/repodiff/walk.go:28,126-129`.

This is roughly 80% of a TOC writer, already written, already shipped behind
`rdc repo diff`. That is why the engine-side producer is a bounded change and
not a new subsystem.

---

## 2. The five questions, answered

### Q1. What does the server know, and what would it have to store?

**Knows:** §1.2 (eleven D1 columns) plus, if it fetches the manifest object,
the block grid and the changed-cell map (§1.2). Nothing about the namespace.

**Would have to store:** a per-snapshot table of contents, produced by the only
party that can see one. There is no computation over existing data that yields a
file list; the plaintext is behind LUKS and the server holds no key.

**Cost per snapshot** (Increment B, full TOC per snapshot, §5):

- Wire entry: path, size, mode, mtime, type, and (optionally) inode. Raw is
  roughly `len(path) + 32` bytes. With a 60-byte mean path that is ~92 B/file.
- Path-sorted lists compress hard. Assume 6x with zstd: **~15 B/file**.
- 10k files: ~150 KB. 100k files: ~1.5 MB. 1M files: ~15 MB.
- **UNMEASURED.** Settle it on the fleet with:
  `rdc term connect <repo> -c "find / -xdev -printf '%p %s %m %T@\n' | wc -l"`
  on a representative repo, and compress the same output to get the real ratio.

**Does it change the upload path? Yes, materially, and this is the honest cost
of my angle.** Today `backup snapshot` never mounts anything (§1.1). Adding a
TOC means the snapshot path acquires a LUKS open and an ext4 mount of the staged
reflink. New failure modes: `cryptsetup` missing, no autostart keyfile
(`mountset.go:118-121` already fails exactly this way for `repo diff`), and a
dirty ext4 journal on a hot (crash-consistent) reflink.

That last one is a **trap, flagged not asserted**: `repodiff` mounts with
`ro,noatime,nosuid,nodev` and no `noload` (`mountset.go:137`). An ext4 mount of
a crash-consistent image with an unreplayed journal can refuse with "recovery
required on readonly filesystem". `repo diff` forks live repos and presumably
hits the same case, so it may be fine in practice, but do not assume. Prove it
before designing around it:

```
rdc repo fork my-app --tag toc-probe          # crash-consistent reflink of a live repo
rdc term connect <machine> -c "sudo mount -o ro,noatime /dev/mapper/<guid> /mnt/probe; echo $?"
```

If it refuses, the TOC writer needs `noload` (which is correct anyway: the TOC
must describe the bytes uploaded, not the bytes after a journal replay the
uploaded image does not contain).

**Time cost: UNMEASURED.** A walk is `readdir` + `lstat` per entry; warm cache
on 100k files is seconds, cold is dominated by inode-table reads. It must be
measured before it is added to the hot path, and it must be **skippable**
(`--no-index`) so a churn-sensitive 5-minute cadence is not held hostage to it.

### Q2. The zero-knowledge boundary. Can the server see filenames, and should it?

**Can it today: no.** Nothing in D1 and nothing in the bucket carries a
namespace (§1.1, §1.2, §1.3). Chunk payloads are LUKS ciphertext keyed by the
SHA-256 of that ciphertext (`backup-chunk-store.ts:806-807`); the worker holds
no data key.

**Should it: no, and this is the decisive answer for my angle.** A design where
the server answers `browse` by reading a file list it stores in the clear is a
**privacy regression**, and I will not design it. Concretely it would:

1. Turn a store that leaks only grid geometry and churn (`manifest.go:33-37`)
   into one that leaks the customer's directory tree.
2. Convert the existing cross-team hole (§1.7) from "sizes" to "filenames".
3. Break the product claim the whole campaign rests on. `docs/backup-storage/`
   and the config-storage story both sell zero-knowledge; a plaintext TOC in D1
   or a plaintext TOC object in R2 makes that claim false.

Note the boundary is already *qualified*, and I would rather say so than let a
later session discover it and conclude the whole claim was theatre:
`backup_exists_pins.hashes` (`schema.ts:1490`) is a stored set of ciphertext
chunk hashes, which is a set-membership oracle; and manifests expose image size,
cell size, grid occupancy and a changed-cell map, which is a churn and locality
signal. Those are side channels over ciphertext. **Filenames are a categorical
step beyond, and crossing it cannot be walked back.**

**The design around it.** The TOC is encrypted by the producer and the server
stores a blob it cannot read.

- Key: `HKDF-SHA256(ikm = repoCredential, salt = lineageGuid,
  info = "rediacc-backup-toc-v1|" + snapshotId)` -> 32 bytes, AES-256-GCM,
  random 12-byte nonce prefixed to the ciphertext.
- `repoCredential` is the repo's LUKS passphrase. The machine has it (deployed
  by `deployRepoKeyIfNeeded`, used at `packages/cli/src/commands/backup.ts:309,406`),
  and the CLI has it in config (`backup.ts:206` reads `source.credential` on the
  restore path).
- **Why that key and not a new one:** browse must require exactly what restore
  requires, no more and no less. If you can restore this snapshot you can read
  its TOC; if you cannot, you cannot. That makes the security argument one
  sentence long, and it needs no new key distribution, no new slot in
  config-storage, and no new recovery story.
- Per-snapshot `info` means one leaked TOC key does not read the lineage.

The server therefore sees: an opaque blob, its byte length, and which snapshot
it belongs to. Byte length weakly correlates with file count. That is a real,
small, and acceptable leak, and it should be written down in the design doc
rather than discovered later. Pad to a 4 KiB boundary if the operator wants it
gone; recommend not bothering in v1.

### Q3. Auth and multi-tenancy

**Today:** subscription-scoped only, team never compared (§1.7). Enforcement on
the machine plane is implicit through key derivation: the principal's
subscription id builds the object key prefix (`backup-chunk-store.ts:45-55`,
used at `backup-storage.service.ts:550,725,775,830`) and is the `WHERE
subscription_id =` on every read (`:628-637,839-844,863-872`). A caller cannot
name another tenant's lineage because it never supplies a subscription id. That
holds across subscriptions. It does nothing across teams inside one.

**For browse, the encrypted design makes crypto do the isolation the schema does
not.** A `backup:read` token from team A can request team B's TOC blob and gets
back ciphertext it cannot open, because the repo credential lives in team B's
config. This is not an accident of the design, it is the reason to prefer it:
the alternative (server-side listing) would require adding a `team_id` column to
`backup_manifests` plus an enforcement point, and would still be one missed
`WHERE` clause away from a cross-team filename leak.

**Still do this, and say it out loud:** the index endpoint (§5, B4) must
enforce, in order:

1. `apiTokenAuth('backup:read')` (existing middleware, gets IP binding and
   archived-team refusal for free, `api-token.ts:29-45`).
2. `WHERE subscription_id = c.get('apiTokenSubscriptionId')` on the
   `backup_manifests` lookup, exactly as `listManifests` does
   (`backup-storage.service.ts:1094-1122`). Never accept a caller-supplied
   subscription id, never accept a caller-composed object key. The engine is
   already forbidden from composing keys
   (`private/renet/pkg/chunkstore/session.go:622-630`); hold the CLI to the same
   rule.
3. Derive the object key server-side from the row, so a caller who guesses a
   snapshot id of another subscription gets a 404 from the `WHERE`, not a
   presigned URL.

**Recommended follow-up, out of scope for this plan but filed loudly:** add
`team_id` to `backup_streams` and `backup_manifests` and enforce it in
`apiTokenAuth`-guarded reads. Browse does not need it (crypto covers it) but
`backup usage`, `backup manifests` and `backup retention set` already leak and
already mutate across teams today. See §9, Finding 1.

### Q4. Offline

**Does browse participate today? No, and it cannot without new plumbing**
(§1.6). `accountServerFetch` has no cache path at all
(`account-client.ts:191-268`), and the config cache's storage shape is an
`RdcConfig` merged by section (`remote-cache.ts:32-45`); it cannot hold an
arbitrary response body.

**v1 recommendation: browse does not participate, and says so.** It fails the
same way `backup manifests` fails today. Adding a general body cache to the
account tunnel is a separate change with its own correctness questions
(invalidation, per-config keying, what "stale" means for a mutable index) and
should not ride a browse PR.

**v2, and it is genuinely valuable:** cache the **decrypted** TOC on disk keyed
by `snapshotId`, because a TOC is immutable once committed. Immutability is what
makes this cache trivially correct: there is no invalidation problem, only an
eviction one. The DR story then becomes "the server is down, and I can still
see what was in my last three backups", which is exactly the moment an operator
wants it.

Hard constraint on v2: a decrypted TOC on disk **re-leaks the filenames to the
local filesystem in plaintext**, which is precisely what §1.6 shows the config
cache already does when no master password is set. So either store it
re-encrypted under the same derived key (cheap, it is already the format that
arrived) or do not store it. **Store the ciphertext, decrypt on read.** Then the
cache inherits the repo credential's protection and there is nothing new to
reason about.

Staleness text: reuse the shape of `formatStaleCacheWarning`
(`remote-cache.ts:82-89`) so the operator sees one vocabulary, not two.

### Q5. The verb and its shape

```
rdc backup browse <repo-ref> [--at <time|snapshot-id>] [--path <subdir>]
                             [--depth <n>] [--long] [--debug]
```

Reasoning against the repo's conventions:

- **Positional ref.** The thing acted on is a repo's snapshot, so the repo ref
  is positional, matching `backup verify <repo-ref>`
  (`packages/cli/src/commands/backup-storage.ts:233`) and `backup snapshot
  <repo-ref>` (`:298`). No `--name`, no `--repo`.
- **`--at` is already the point-in-time selector** on `backup restore`
  (`packages/cli/src/commands/backup.ts:167`), and its resolver is already
  written and already exported: `resolveSnapshotAt(lineage, at)` at
  `backup.ts:353-385`, which accepts either a snapshot id matching
  `SNAPSHOT_ID_RE` (`backup.ts:341`) or any parseable time and picks the newest
  snapshot at or before it. **Reuse it verbatim.** A second time-resolution
  implementation is how `browse --at` and `restore --at` come to disagree about
  which snapshot the operator meant, which is the worst possible bug for this
  pairing.
- **Default `--at` is the newest snapshot**, so `rdc backup browse my-app` is the
  question an operator actually asks.
- **`--path` filters, so it is a flag**, matching `storage browse --path`
  (`storage.ts:261`). The filter is applied **client-side after decryption**;
  the server cannot filter a blob it cannot read, and pretending otherwise would
  be the privacy regression in disguise.
- **Do NOT extend `rdc storage browse`.** That verb is a live rclone-remote
  browser and is explicitly retained (§1.4). One noun, one storage system.
- **Do NOT add a second `backup` listing verb** (an `ls` beside `browse`). The
  repo already rejected growing one verb per route rather than per concept; see
  the comment at `backup.ts:216-220` refusing a separate restore-snapshot verb
  beside `restore --at`.

Resolution helper: use **`resolveRepoRefLocal`**, the config-only resolver that
`backup manifests` uses (`backup-storage.ts:129`), never `resolveRepoRef`
(`backup-storage.ts:240`) which resolves a machine. Browse must work when the
machine is gone. This one import choice is the difference between a DR tool and
a convenience.

Command plane: **`other`**, alongside `backup usage` and `backup manifests`
(`packages/cli/src/config/command-planes.ts:96-105`). Declaring `machine` would
fail `check:ci-command-planes`, whose Rule 3 hard-fails a leaf claiming
`machine` whose module imports no executor seam.

---

## 3. The three designs I considered

### A. Snapshot-space browse (server + CLI only, zero renet)

Render what the server already has: the parent chain, sizes, churn, the
changed-cell count, and what a restore would cost to download. Answers "which
snapshot, and how much moved" and explicitly **not** "which files".

Cost: ~2 days. Privacy delta: zero. Value: real but partial.

### B. Encrypted TOC written at snapshot time (RECOMMENDED)

§2 Q1/Q2. The engine walks the staged reflink, writes an encrypted TOC object,
the server stores and serves it opaquely, the CLI decrypts.

Cost: one bounded renet change (reusing `repodiff`'s mount machinery), one new
object family, one new endpoint, one migration. Privacy delta: zero for the
server; a bounded metadata leak (blob length).

### C. Sparse on-demand ext4 read (rejected for v1, named as the upgrade path)

Because aes-xts is length-preserving and sector-local
(`private/renet/pkg/chunkstore/grid.go:10-13`), a holder of the repo credential
can decrypt **individual cells**. So a client could fetch only the cells holding
the ext4 superblock, group descriptors, inode tables and directory blocks, and
walk the namespace without downloading the image. No snapshot-time cost, no new
object, no upload-path change at all.

**Rejected for v1** because it requires a correct ext4 reader. In TypeScript
that is a large lift and a correctness hazard (extent trees, 64-bit features,
inline data, htree directories, and every one of those is a way to print a wrong
file list confidently). In Go it is smaller, but it puts the reader back on a
machine and loses the machine-free property that is the point.

**Keep it named.** If measurement (§2 Q1) shows TOCs are too big or the walk is
too slow for the snapshot cadence, C is the answer, and it is strictly better
than B on cost-per-snapshot. It is worth revisiting once, with a measurement,
not before.

**Recommendation: A now, B next, in one verb.** C only if B measures badly.

---

## 4. What I am NOT proposing, explicitly

- No plaintext file index on the server, in D1 or in the bucket. §2 Q2.
- No presigned URL handed to an API-token principal. Presign is currently a
  machine-plane privilege earned by a signed license blob
  (`backup-chunk-store.ts:755,767-840`); extending it to CLI tokens is a new
  privilege class and this verb does not need one (§5, B4 proxies instead).
- No delete verb. The grant action union has no delete at all
  (`backup-chunk-store.ts:368-377`) and browse must not be the thing that adds
  one.
- No new noun. `backup` already owns this.

---

## 5. Implementation plan, exact files in dependency order

### Increment A: the verb, with block-level fidelity (no renet, ships alone)

**A1. Server: extend the manifest read with the block facts it already has.**
`private/account/src/services/backup-storage.service.ts:1094-1122` (`listManifests`)
already returns everything needed except the changed-cell shape. Add
`GET /backups/manifests/:snapshotId` returning one row plus, optionally, the
parsed `WireManifest` grid summary the worker can already produce
(`backup-gc.service.ts:937-952` for the shape, `:246` for the fetch-and-parse it
already does). Scope with `apiTokenAuth('backup:read')` and
`WHERE subscription_id = c.get('apiTokenSubscriptionId')`.

Files: `private/account/src/routes/backups.ts` (new route beside `:136`),
`private/account/src/services/backup-storage.service.ts` (new service method),
`private/account/src/dto/backup.dto.ts` (new response DTO beside `:256`).

**A2. CLI: `rdc backup browse <repo-ref>`.**
`packages/cli/src/commands/backup-storage.ts` : new `registerBackupBrowse`,
wired into `registerBackupStorageCommands` (`:512-518`). Reuses
`resolveLineage` (`:128`) and `resolveSnapshotAt` imported from `./backup.js`
(`packages/cli/src/commands/backup.ts:353`).

Output when no TOC exists: snapshot id, created, parent, image size, cell size,
cells changed, bytes added, plus one line saying file listing needs a snapshot
taken by a renet that writes an index. **Not an error, and not silence.** An
empty table here would be read as "the backup is empty".

### Increment B: the file index

**B1. renet: the TOC writer.** New `private/renet/pkg/chunkstore/toc.go`:

- `type TOCEntry struct { Path string; Type string; Size int64; Mode uint32; MTime int64 }`
- `type TOC struct { Version int; SnapshotID, RepositoryGUID, Lineage string; CreatedAt string; Entries []TOCEntry }`
- `BuildTOC(mountPath string) (*TOC, error)` : a `filepath.WalkDir` of the mount,
  path-sorted, symlink targets recorded but never followed.
- `SealTOC(toc *TOC, credential, lineage, snapshotID string) ([]byte, error)` :
  JSON, zstd, then AES-256-GCM under the HKDF key of §2 Q2. `OpenTOC` inverse.
- Version constant and a hard reject of any other version, mirroring
  `manifest.go:20,75-77`.

**B2. renet: mount the staged reflink and call it.**
`private/renet/pkg/chunkstore/pipeline_linux.go` around the staging that already
exists at `:346-347`. Do not write a new mounter: lift the `openRepoReadOnly`
pattern from `private/renet/pkg/repodiff/mountset.go:52-170` (transient mapper
name, temp mount, LIFO close that touches nothing it did not create). Add
`noload` to the mount flags at the equivalent of `mountset.go:137` if the probe
in §2 Q1 says it is needed.

Gate it behind a param so the cadence is not hostage to the walk: `index: bool`
on the `backup_snapshot` FunctionDef
(`private/renet/pkg/functions/commands/backup.go:154`), default true, with
`--no-index` reaching it from the CLI.

**B3. renet + server: the third key family.** `i/<snapshotId>` under the lineage
prefix.

- `private/account/src/services/backup-chunk-store.ts:45-56` : add `indexKey`
  beside `chunkKey`/`manifestKey`.
- `private/account/src/services/backup-chunk-store.ts:820-830` : mint
  `indexPutUrl` beside `manifestPutUrl` in the write grant, same create-only
  `IfNoneMatch: '*'` treatment as `:811`.
- `private/renet/pkg/chunkstore/session.go:587-619` (`PutManifest`) : a sibling
  `PutIndex`, same create-only semantics, same refusal to compose keys
  (`session.go:622-630`).
- `private/renet/pkg/chunkstore/uploader.go:207-224` : index PUT before commit,
  same ordering rule as the manifest.

**B3-TRAP, and this one will bite silently.** Two places classify bucket objects
into exactly the two existing families and must learn the third, or GC will
either delete live indexes or leak them forever:

- `private/account/src/services/backup-gc.service.ts:694` (GC classification)
- `private/account/src/services/backup-storage.service.ts:1258-1263`
  (`POST /backups/verify` reconciliation, which will otherwise report every
  index object as drift)

**B4. Server: the index read endpoint.** `POST /backups/index` (or
`GET /backups/manifests/:snapshotId/index`), `apiTokenAuth('backup:read')`.

- Look up the `backup_manifests` row with `WHERE subscription_id = ... AND
  snapshot_id = ...`, exactly as `listManifests` scopes (`:1094-1122`).
- Derive the object key server-side from the row. Never from the request.
- `BackupChunkStore.get()` the blob (the interface already has it,
  `backup-chunk-store.ts:35`, R2 impl `:94`, S3 impl `:216`) and return it
  base64 in the response body, **through the existing E2E tunnel**.
- Refuse over a cap (recommend 8 MiB) with a distinct error code, and let the
  engine write multi-part indexes (`i/<snapshotId>/<n>`) if a repo exceeds it.

**Why proxy rather than presign.** It keeps the whole exchange inside the
E2E-sealed tunnel, and it adds no presign privilege to CLI tokens (§4). The cost
is worker egress on a rare, small object. Switch to presign only if measurement
(§2 Q1) puts typical TOCs above a few MiB; the presign machinery already exists
at `backup-chunk-store.ts:849-881` and the prefix guard at `:855,865` already
does the right thing for a key under the lineage prefix.

**B5. Server: schema and accounting.**
`private/account/src/db/schema.ts:1421-1444` plus a new `drizzle/00XX_*.sql`:
add `index_key TEXT` and `index_bytes INTEGER NOT NULL DEFAULT 0` to
`backup_manifests`. Thread `indexBytes` through the commit DTO
(`private/account/src/dto/backup.dto.ts:86`) and into the `backup_usage` /
`backup_lineage_usage` upserts (`backup-storage.service.ts:931-983`), so index
bytes count against quota. An index that does not count is an index that grows
without an operator ever seeing why their usage moved.

Also register nothing new in `private/account/src/db/scope-registry.ts:72-79`
(no new table), but re-run `check:ci-account-scope-audit` because the columns
change.

**B6. Shared contract.** `packages/shared/src/cli-contract/data/*` is
**generated**; do not hand-edit. Regenerate per §6.

**B7. CLI: decrypt and render.** `packages/cli/src/commands/backup-storage.ts`
(the browse action from A2 gains the index fetch), plus a new
`packages/cli/src/services/backup/backup-index.ts` holding the HKDF + AES-GCM
open and the zstd inflate, mirroring `SealTOC`. The repo credential comes from
`configService.getRepository(repoKey).credential`, the same field the restore
path reads (`packages/cli/src/commands/backup.ts:206`).

Render as a table (name, type, size, modified) with the same column vocabulary
`storage browse` uses (`packages/cli/src/commands/storage.ts:281-287`), so the
two browsers read alike even though they browse different systems.

---

## 6. The gate checklist (this is where a CLI PR actually dies)

In order. Steps 8-12 are generated artifacts and must be committed.

1. Command in `packages/cli/src/commands/backup-storage.ts`, wired at `:512-518`.
2. English keys in `packages/cli/src/i18n/locales/en/cli.json`, as **static
   string literals** in `t(...)` (a template literal hides the key from
   `check:ci-i18n-cli-key-usage`, which checks both directions).
3. `packages/cli/src/config/command-metadata.ts` : a `'backup browse'` entry with
   `mcp:{...}` or `mcpExcludeReason`. Mandatory: `packages/cli/src/commands/mcp/__tests__/mcp-coverage.test.ts:108-112`
   walks live leaves and fails any with no `COMMAND_METADATA` entry.
4. `packages/cli/src/config/command-planes.ts:96-105` : `'backup browse':
   {plane:'other'}`.
5. `packages/cli/src/config/command-docs.ts` : examples/keywords/output hints
   (optional but curated; every `descriptionKey` must exist in `en/cli.json` or
   the contract generator exits 1).
6. `docs/design/06-cli-reshape.md:59` : add `browse` to the `rdc backup` leaf
   transcript. `check:ci-design-tree` is bidirectional.
7. Translate into the other 12 locales (`ar de es et fr it ja ko pt ru tr zh`),
   naturalized, not English-copied (`MAX_UNTRANSLATED_PERCENT = 0`).
8. `npm run i18n:generate-hashes` : **after** translating, never before.
9. `npm run build:packages` (the exporters import the live CLI through
   `@rediacc/shared` dist; skipping this diffs against stale output).
10. `npm run export:command-tree -w @rediacc/cli` : nine validators read this
    file and fail **open** when stale, so it goes first.
11. `npm run generate:cli-contract -w @rediacc/cli`
12. `npm run generate:skill-reference -w @rediacc/cli` and
    `npm run generate:cli-docs -w @rediacc/www`
13. Verify: `check:ci-command-tree`, `check:ci-cli-contract`,
    `check:ci-command-planes`, `check:ci-design-tree`, `check:cli-examples`,
    `check:test-cli`, `check:i18n`, `check:ci-account-scope-audit`,
    `check:ci-account-server`, `check:ci-tutorial-cli-validity`.

If any option long needs a resource-kind or format hint, add an override keyed
`'backup browse --<long>'` in
`packages/cli/scripts/lib/option-classification.ts`; stale classification exits
the contract generator with 1.

---

## 7. Test plan

### 7.1 Runnable in CI, with no credentials

**Account server integration tests. Fully runnable, and this is the strongest
leg.** `private/account` vitest runs in CI at
`.github/workflows/ci-quality.yml:1384` via
`.ci/scripts/private/run-account.sh test` (`:43-46`). The existing suites inject
an in-memory plane: `createApp(getTestEnv, () => db, undefined, undefined,
undefined, () => plane)` with `MemoryBackupChunkStore` + `MemoryGrantMinter`
(`private/account/tests/integration/backup-storage.test.ts:71-88`), and mint API
tokens directly via `apiTokenService.create` (`:765-774`).

New file `private/account/tests/integration/backup-index.test.ts`:

1. **Happy path.** Seed a manifest row + an index object in the memory store;
   `GET` with a `backup:read` token; assert the exact bytes come back.
2. **Cross-subscription refusal.** Two subscriptions, each with a snapshot;
   subscription A's token asking for B's snapshot id gets 404, **not** 403 and
   not a body. Assert on the response body being empty, because a 404 that still
   leaks the key would pass a status-only assertion.
3. **Scope refusal.** A token with `subscription:read` only gets 403 with
   `Missing required scope: backup:read`.
4. **Caller-supplied key refusal.** Post a body carrying an `indexKey` /
   `manifestKey` field and assert the server ignores it and derives its own.
   This is the mutation that would otherwise turn the endpoint into an arbitrary
   bucket reader.
5. **Cap.** An index object over the cap returns the distinct error code, not a
   truncated body.
6. **Ciphertext only.** Assert the returned bytes do not contain any plaintext
   path fixture string. This is the test that fails loudly if someone later
   "helpfully" makes the server parse the TOC.
7. **GC and reconciliation.** Extend `backup-gc.test.ts` and the verify path so
   an `i/` object is neither reported as drift nor swept while its manifest
   lives, and IS swept when the manifest is pruned. This covers the B3-TRAP.

**Control (the instrument must be provable).** Before trusting suite item 2,
break the `WHERE subscription_id` clause locally and confirm the test goes red.
A tenancy test that cannot fail is worse than no test, because it certifies the
hole.

**CLI unit tests. Fully runnable.** New
`packages/cli/src/commands/__tests__/backup-browse.test.ts`, following the exact
pattern at `packages/cli/src/commands/__tests__/backup-storage.test.ts:66-73`:
throwaway `Command`, register only the module, `parseAsync` real argv, assert on
mocked seams (`accountServerFetch`, `resolveRepoRefLocal`, `outputService`,
`handleError` rethrowing). Model the assertions on the `backup manifests` block
(`backup-storage.test.ts:150-178`), which asserts the exact URL.

Cases: default `--at` picks the newest; `--at <time>` goes through
`resolveSnapshotAt` and requests the resolved snapshot id (not the raw time);
`--at` with no snapshot at or before it produces
`commands.backup.restore.atNoSnapshot`; `--path` filters after decryption;
a missing index renders the Increment-A block summary rather than an empty
table; `-o json` emits the envelope.

**Crypto round-trip. Fully runnable, and it is the one that matters most.** A
Go test in `private/renet/pkg/chunkstore/toc_test.go` (`SealTOC` -> `OpenTOC`)
plus a **cross-language vector** committed as a fixture: a small sealed TOC
produced by the Go implementation, opened by the TypeScript one in
`packages/cli/src/services/backup/__tests__/backup-index.test.ts`, and the
reverse. Two independent implementations of one HKDF label drift silently, and
the failure mode is "browse works in dev and returns garbage in production".

### 7.2 Runnable in CI, on the fleet, without account credentials

Suite 25 already drives `backup snapshot --dry-run` on the fleet with no account
plane. Extend it to assert that a dry run **reports the index it would write**
(entry count and sealed size) without uploading. That makes the fleet leg
meaningful rather than a smoke test: it exercises the LUKS open, the ext4 mount
and the walk, which are the three genuinely new failure modes, and it needs no
server at all.

### 7.3 NOT runnable in CI as it stands

`packages/e2e-tests/tests/26-backup-storage-cli.test.ts` skips without
`REDIACC_ACCOUNT_SERVER` and `E2E_ACCOUNT_API_TOKEN` (`:96,168-175`); the
declared instruction there is literally "mint an api token carrying the
`backup:read` scope and export it". Add the browse leg to suite 26 anyway, so it
runs locally and the day the token gap closes it runs everywhere.

**And the gap is closeable, cheaply, which is worth saying rather than filing.**
`scripts/drills/backup.sh` already mints exactly this token from a dev account
session: `drill_account_mint_token "$jar" "$SUBSCRIPTION_ID" drill-backup
'["license:read","license:activate","subscription:read","backup:read"]'`
(`scripts/drills/backup.sh:521-522`), then logs the CLI in at `:1151`, and has a
"Leg f: the CLI read surfaces" section for exactly `backup usage` / `backup
manifests`. **Add a browse leg to leg f**, and port `drill_account_mint_token`
(`scripts/drills/lib.sh:772-788`) into the Playwright ACCOUNT tier so suite 26
stops depending on a hand-exported token. That is the reuse the operator's
standing preference asks for, and it needs no server change.

---

## 8. Tutorial plan

**Browse belongs in `tutorial-backup-restore`, not in its own tutorial**, and it
belongs there specifically because the rewrite in flight has a hole that browse
fills.

The current script (`.ci/tutorials/tutorial-backup-restore.sh`) teaches the
machine-to-machine story, and its header records, measured rather than assumed,
why the chunk store is only *named* on camera:

```
rdc backup snapshot my-app --dry-run
  -> exit 1, {"status":"failed","reason":"no installed repository license"}
rdc backup manifests my-app / rdc backup usage
  -> exit 2, "Subscription token required"
```
(`.ci/tutorials/tutorial-backup-restore.sh:19-27`)

So the harness has no account credentials and no repository license. Any browse
demo that reads the server would print "Subscription token required" on camera.

**What runs in the harness with no credentials, and is still a real
demonstration:**

Step 4a, between the existing "Disaster, the primary goes offline"
(`:135`) and "Restore the copy" (`:140`):

```
section "Step 4a: Look inside the backup before restoring it"
run_cmd "rdc backup browse my-app@$M2"
```

This is the honest, credential-free leg **only if** the verb answers a
machine-held artifact as well as a chunk-store snapshot. That is a real design
decision, not a tutorial hack, and I recommend taking it: `backup browse
<ref>@<machine>` on a pushed artifact is answerable entirely executor-side (the
artifact is a repo image on that machine, and `repository_cat --stat`
(`private/renet/pkg/functions/commands/repository.go:454-467`) plus the
`repodiff` mount machinery already reach inside one). It gives the tutorial its
"look before you leap" beat and it gives the operator the verb in the one case
where they have a machine and no subscription.

If that is judged out of scope, the fallback that is **still not a skip**:

```
type_only_cmd "rdc backup browse my-app --at 2026-08-16T10:00:00Z"
```

using the existing `type_only_cmd` helper the script already uses for the chunk
store (`:28-30`), narrated as the point-in-time browse, with the credential
requirement stated on camera. The script's own header establishes this pattern
and its reason, so it is consistent rather than an excuse.

**Do not create a separate browse tutorial.** Browse has no standalone story; it
is the question you ask *before* a restore, and separating it from the restore
would teach it as a curiosity.

**Re-record cost, and it is not small.** `docs/backup-storage/05-docs-and-decommission.md:81-84`
notes the cast is re-recorded only if wave 2 changes the recorded argv, because
that decision gates a 13-locale re-narration chain. Adding a step to the cast
triggers it. **Land browse in the same wave as the rewrite that is already
happening**, so one re-record pays for both. If the rewrite has already been
recorded by the time browse lands, the `type_only_cmd` fallback avoids a second
narration bill, and that trade should be the operator's call, not a silent one.

Gate to satisfy either way: `check:ci-tutorial-cli-validity`
(`.ci/scripts/quality/check_tutorial_cli_validity.py`) validates every command
and flag in `.ci/tutorials` against `command-tree.json`, so the tree must be
regenerated (§6 step 10) before the tutorial change is committed.

---

## 9. Findings encountered on the way (not asked for, reported per session rules)

1. **Cross-team backup exposure inside one subscription.** `apiTokenAuth` never
   compares `token.teamId` to anything on the backup tables, and no backup table
   has a team column (`private/account/src/middleware/api-token.ts:21-27,48`;
   `private/account/src/routes/backups.ts:126-206`;
   `private/account/src/db/schema.ts:1380-1595`). Any `backup:read` token sees
   every lineage on the subscription; any `backup:manage` token can rewrite any
   lineage's retention policy, which is the surface that decides what gets
   deleted (`backup-storage.service.ts:1168`). Not caused by this work, made
   worse by it if browse were ever served in plaintext. Recommend a `team_id`
   column plus enforcement as its own change.

2. **Three user-facing strings name a retired env var.**
   `errors.subscription.tokenRequired` / `notLoggedIn` / `tokenWarning` tell the
   operator to set `REDIACC_SUBSCRIPTION_TOKEN`
   (`packages/cli/src/i18n/locales/en/cli.json:2176-2179`), but the only variable
   read is `REDIACC_TOKEN`
   (`packages/cli/src/services/account/subscription-auth.ts:8,63`).
   `REDIACC_SUBSCRIPTION_TOKEN` is on the tombstone ban list
   (`packages/cli/src/__tests__/env-tombstones.test.ts:29`); the gate misses it
   because its scanner only walks `.ts`/`.tsx` (`:62`), so the dead name survives
   in all 13 locale files. Following the message verbatim yields exit 2 with the
   same message again. Small and local: fix the strings in all 13 locales and
   widen the tombstone scanner to JSON locales.

3. **CLAUDE.md overstates the offline cache.** "encrypted-at-rest local cache"
   holds only under `--master-password`, and only for `encryptAtRest`-marked
   leaves; a remote-enabled config without one caches the whole server copy as
   plaintext JSON at 0600
   (`packages/cli/src/adapters/config-file-storage.ts:42-44,84-97` versus
   `packages/cli/src/commands/config.ts:56-69`).

4. **The brief's premise about `rdc storage browse` is out of date.** It is not
   retired; it is explicitly retained
   (`docs/backup-storage/README.md:89`, `05-docs-and-decommission.md:88-89`) and
   still registered (`packages/cli/src/commands/storage.ts:257`). Worth
   correcting wherever the campaign notes say otherwise, because "the browse verb
   was removed" is the premise that would justify reusing its noun.

---

## 10. Honest summary of where my angle loses and where it wins

**Loses:** the file index cannot be computed server-side, cannot be computed
client-side without an ext4 reader, and cannot be avoided by any amount of
cleverness with the manifest. The producer is renet. If the assignment were
strictly "no renet changes", the correct output would be Increment A alone,
labelled as not answering the question that was asked.

**Wins, and I would defend this against the engine angle:** the *serving* of a
browse must not be executor-side. A browse exists to answer "should I restore
this?", and the sharpest version of that question is asked when the machine is
gone. An engine-side browse requires a live machine holding a repo, which is the
one condition a disaster removes. The server already has the index, the tunnel,
the auth, and the tenancy scope; it just needs a route that hands back a blob it
cannot read.

The right shape is therefore neither plan as briefed: **renet writes it, the
server keeps it and cannot read it, the CLI opens it.**
