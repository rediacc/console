# PLAN: Snapshot-addressed restore from chunk storage
Status: draft
Owner: 97604f47
Updated: 2026-08-14

Scope: build the download half of the backup-storage program. Upload is complete and
live; restore is a stub that refuses. Everything below is anchored to the tree as it
stands on branch `backup-storage`.

---

## 0. What the tree actually says, corrected where the brief was wrong

Four claims in the handoff are confirmed:

- `private/renet/cmd/renet/backup_pull.go:195-197` refuses `--at` by name. The flag is
  registered at `:143`, so the refusal is reachable and honest, not a parse error.
- `pkg/chunkstore` exports no fetch-to-disk function. `MaterializeManifest`
  (`manifest.go:209-257`) composes cell inventories in memory and touches no network.
- `rdc backup restore --at` is shipped CLI surface
  (`packages/cli/src/commands/backup.ts:160`), passed through to renet at
  `backup.ts:269-279` and `pkg/functions/commands/backup.go:581-587`. Today every
  invocation of it ends at the refusal above.
- The upload half is whole: `cmd/renet/backup_snapshot.go`, `chunkstore.Upload`
  (`uploader.go:101-193`), `SessionControlPlane` (`session.go:232-520`), and the
  account routes at `private/account/src/routes/backups.ts`.

Three things the brief got wrong or under-stated. All three change the design.

### 0.1 There is no read grant AND there is no read SESSION

The brief asks about the grant. The grant is the second problem. The first is that a
lapsed subscription cannot mint a session at all, so "retain-on-cancel, read-only for
60 days" is unreachable one layer earlier than expected.

`mintSession` (`backup-storage.service.ts:136-184`) calls
`SubscriptionService.authenticateLicenseBlob`, which ends in
`resolveEntitledSubscription` (`subscription.service.ts:1206-1226`). A cancelled or
suspended subscription throws there, and the catch maps `SUBSCRIPTION_EXPIRED` and
`SUBSCRIPTION_SUSPENDED` to a 403 `SUBSCRIPTION_LAPSED`. The machine never gets a
session token, so it never reaches `/grants` to be refused by the separate lapse check
at `backup-storage.service.ts:316-322`. Meanwhile `BACKUP_RETENTION_AFTER_CANCEL_DAYS`
is 60 (`backup-gc.service.ts:43`) and the retention sweep keeps the bytes
(`backup-gc.service.ts:332-387`). The product retains data it has no way to hand back.

So the read path needs a change at BOTH layers, and this plan designs both.

### 0.2 The write grant already carries `GetObject`, which is both a shortcut and a leak

`BACKUP_GRANT_ACTIONS` (`backup-chunk-store.ts:349-359`) lists `GetObject`,
`HeadObject` and `ListBucket` alongside the write verbs, and `R2JwtGrantMinter.mint`
(`:478-503`) stamps that whole list into every temp credential. So on the R2 path a
restore could technically read with a write grant today.

That is not a design, it is an accident with two consequences. First, an uploader holds
read authority over the entire lineage prefix it is writing to, which is more than a
writer needs. Second, the presigned path (`S3PresignGrantMinter`, `:515-570`) signs
PUTs only, so the shortcut does not exist there at all, and the presigned path is what
local dev, elite RustFS and customer S3 all use (`createBackupPlane:643-651`).

The plan splits the action list rather than leaning on the accident. The split is also
what makes the drill's new control possible (section 6.3).

### 0.3 The parent chain is NOT one hop, and `MaterializeManifest` refuses to walk it

The brief's sketch says "materialize the full cell list (composing deltas up the parent
chain)". `MaterializeManifest` cannot do that. It composes exactly ONE delta over a
FULL parent and refuses a delta parent by name:

```go
if parent.IsDelta() {
    return nil, fmt.Errorf("parent %s is itself a delta; materialize it first", parent.SnapshotID)
}
```
(`manifest.go:219-221`)

And the chain in the store IS deep. `buildPlan` builds a delta against the LOCAL anchor
whenever that anchor is trusted (`pipeline_linux.go:227-242`), and the anchor's snapshot
id is the previous run's, which was itself usually a delta. A full manifest is emitted
only when the trust check fails (`pipeline_linux.go:161-186`), which means at first
backup, at a geometry change, at a corrupt journal, and on `--reseed`, and not
otherwise. `02-design.md:51-52` names server-side synthetic-full consolidation as the
thing that would bound the chain; I found no implementation of it, and `commitManifest`
(`backup-storage.service.ts:466-636`) stores `parentSnapshotId` without ever
consolidating.

Restore must therefore resolve a chain of unbounded depth by walking DOWN from the
nearest full manifest, materializing one hop at a time. This is the single largest
correction to the brief and it lands in both the engine (section 3) and the read grant
(section 2.3, the server presigns the whole chain because the machine cannot discover
it in one round trip on the presigned path).

---

## 1. Decision: a new verb, `renet backup restore`

`backup pull --at` is the wrong home. Three reasons, in order of weight:

1. **Tier.** `backup_pull` is `TierRepoLicenseFull` (`pkg/license/tiermap.go:50`). The
   operator's standing decision for this entire program is `TierNone`, recorded in the
   map itself at `tiermap.go:55-59`: "every tier gets the same functionality and
   STORAGE QUOTA is the only lever". Hanging restore off `backup_pull` puts the
   program's restore behind a lever the operator explicitly removed, and worse, it does
   so invisibly. A new verb registers `TierNone` and the two decisions stop fighting.
2. **Body.** `runBackupPull` (`backup_pull.go:152-346`) is rsync and rclone: source
   type, `--src-host`, `--rclone-backend`, CoW pre-seeding (`:253-266`), delta-base
   pull. A chunk restore shares none of it. `--at` would be an early return placed
   above 150 lines of irrelevant flag parsing, which is exactly the shape that makes a
   later reader believe the flags apply.
3. **It is already written down.** `packages/e2e-tests/tests/26-backup-storage-cli.test.ts:726-729`
   already sketches the argv:
   `renet backup restore --repo <guid> --datastore <ds> --lineage <guid> --at <snap>`,
   marked TRANSCRIPT-CONFIRM because no binary existed to read it off. Matching it
   costs nothing and turns a dark tier live.

The `--at` stub on `backup pull` stays a refusal, with its message changed to name the
new verb. It does not silently forward: `backup pull`'s tier and its safety checks are
different, and a silent redirect would make the tier decision meaningless again.

`rdc backup restore` stays ONE command. It already takes `--at` and already exists; the
CLI routes on the flag (section 5.3). Growing a second user-facing restore verb would
make the operator choose between two commands that mean the same thing.

---

## 2. The read path on the account side

### 2.1 Session intent (the layer the brief did not reach)

`backupSessions` (`private/account/src/db/schema.ts:1533-1549`) gains one column.
Migration `drizzle/0050_backup_read_sessions.sql` (0049 is the current head).

```
intent TEXT NOT NULL DEFAULT 'backup'   -- 'backup' | 'restore'
```

- `backupSessionRequest` (`dto/backup.dto.ts:15-30`) gains
  `intent: z.enum(['backup', 'restore']).default('backup')`.
- `mintSession` passes the intent to a new lapse-tolerant entitlement resolution when
  it is `'restore'`: the subscription is resolved, and a status outside
  `active`/`grace` is accepted only while `backupUsage.retentionStartedAt` is set and
  within `BACKUP_RETENTION_AFTER_CANCEL_DAYS` of now. Past the window, and for a
  subscription that does not exist, it refuses exactly as today.
- `BackupSessionPrincipal` (`backup-storage.service.ts:64-68`) carries `intent`.
- `mintGrant` (`:291`) refuses a `restore`-intent session up front, with a distinct
  code. A read session must not be able to write, and the check has to live in
  `mintGrant` rather than in the route, because the route is not where the lease and
  quota decisions are.

Note what this does NOT do: it does not weaken the write path. The lapse check at
`:316-322` stays exactly where it is, and a `backup`-intent session on a lapsed
subscription still fails at `mintSession` as it does today.

### 2.2 Splitting the grant actions

`backup-chunk-store.ts:338-359`. `BackupGrantAction` stays one union (it is the
allowlist, and deletes stay structurally absent from it). The single
`BACKUP_GRANT_ACTIONS` constant becomes two:

```ts
export const BACKUP_WRITE_GRANT_ACTIONS = [
  'PutObject', 'HeadObject',
  'CreateMultipartUpload', 'UploadPart', 'CompleteMultipartUpload',
  'AbortMultipartUpload', 'ListMultipartUploadParts',
];
export const BACKUP_READ_GRANT_ACTIONS = ['GetObject', 'HeadObject', 'ListBucket'];
```

`GetObject` and `ListBucket` leave the write set. That is a tightening of a live path,
so it is called out in the summary as a change nobody asked for: an uploader currently
holding read authority over its lineage loses it. Nothing in `pkg/chunkstore` reads
through a grant (`grants.go` implements `objectPutter` only, `:79-85`), so no shipped
caller regresses. `HeadObject` stays in both: the write path's create-only collision
handling (`grants.go:117-135`) does not use it, but multipart abort recovery on a large
cell plausibly would, and removing it buys nothing.

### 2.3 `POST /backups/read-grants`

Behind `backupSessionAuth` (`routes/backups.ts:48-53`), the same middleware the write
routes use. The machine holds no API token, by the same design that put `/session`
outside `apiTokenAuth`.

Request (`backupReadGrantRequest`):

```ts
{ lineageGuid: guidSchema, snapshotId: snapshotIdSchema, hashes?: sha256HexSchema[] }
```

Response (`backupReadGrantResponse`), a discriminated union parallel to
`backupGrantSchema` (`dto/backup.dto.ts:92-121`):

```ts
{ kind: 'r2-temp-creds', accessKeyId, secretAccessKey, sessionToken,
  endpoint, bucket, prefix, expiresAt,
  manifestChain: string[] }
{ kind: 'presigned-s3', endpoint, bucket, prefix,
  getUrls: Record<string, string>,          // keyed by BARE HASH
  manifestGetUrls: Record<string, string>,  // keyed by SNAPSHOT ID
  expiresAt, manifestChain: string[] }
{ kind: 'direct-https', baseUrl, token, prefix, expiresAt, manifestChain: string[] }
```

`manifestChain` is the ordered snapshot ids from the nearest FULL manifest down to the
requested one, resolved server-side by walking `backupManifests.parentSnapshotId`. The
server has this index already (`listManifests`, `backup-storage.service.ts:719-747`);
the machine does not, and on the presigned path cannot derive keys at all. Resolving it
server-side turns an N-round-trip discovery into one call.

`getUrls` is keyed by bare hash and not by object key. This is not a preference: the
write path already paid for the other choice and the fix is documented in place at
`backup-chunk-store.ts:541-546` ("Keying it by the full object key meant every lookup
missed"). The read side matches, and a test asserts it (section 6.2).

Service behavior (`mintReadGrant`), and what it deliberately does NOT do:

- **No quota check.** Reading spends no storage. The quota block at
  `backup-storage.service.ts:324-349` has no analogue here.
- **No lease.** The lease upsert at `:351-374` exists to hold quota for bytes about to
  be written. A read grant that took a lease would inflate `leasedBytes` and refuse the
  customer's own next backup, which is the exact failure mode of accidentally reusing
  the write path.
- **Accepts a lapsed-but-retained subscription**, matching the session intent above.
  This is the whole point of the change.
- **Prefix scoped** to `backupKeys.lineagePrefix(sub.id, lineageGuid)`
  (`backup-chunk-store.ts:46-47`), identical to the write grant at `:386`.
- **Chain depth is bounded.** A walk longer than `BACKUP_MANIFEST_CHAIN_MAX` (start at
  64) refuses with a named error rather than presigning a thousand manifests. Since
  nothing consolidates chains today (section 0.3), the bound WILL be hit eventually,
  and hitting a named refusal is the correct outcome: it is the signal that
  consolidation has become necessary. It must not be a silent truncation.
- **A missing manifest row is fatal.** If the walk reaches a `parentSnapshotId` with no
  row, the response is an error, never a partial chain. A partial chain restores the
  wrong bytes and exits zero, which is the one failure this whole program exists to
  rule out.

`BackupGrantMinter` (`backup-chunk-store.ts:403-408`) gains `mintRead(input)`.
`R2JwtGrantMinter` signs the same JWT shape with the read action list.
`S3PresignGrantMinter` presigns `GetObjectCommand` per key, keeping the prefix guard at
`:540`. `MemoryGrantMinter` hands out an inert read grant.

TTL reuses `BACKUP_GRANT_TTL_SECONDS` (one hour, `backup-storage.service.ts:41`). A
long restore re-mints mid-run, exactly as `grantSource` (`uploader.go:381-450`) does for
writes, and for the same reason: expiry is a normal event, not an error.

### 2.4 What stays untouched

`/exists` (`routes/backups.ts:86-91`) is not part of restore. It writes 24h GC pins
(`backup-storage.service.ts:447-459`) and answers a question restore does not ask:
restore knows which hashes it wants from the manifest and finds out about absence by
the GET failing. Reusing it would write pins for a read, which is meaningless
bookkeeping.

---

## 3. The engine: what restore actually produces

New files: `pkg/chunkstore/download.go` (portable: the fetch loop, the getter seam, the
chain walk) and `pkg/chunkstore/restore_linux.go` (the sparse write, `//go:build linux`
like `pipeline_linux.go` and `zerodetect_linux.go`).

### 3.1 The corrected shape

Verified against `grid.go` and `manifest.go`, with the brief's sketch corrected:

1. Resolve the snapshot. `--at` takes a snapshot id or an RFC3339 time. A time resolves
   against `GET /backups/manifests` (`routes/backups.ts:113-125`), newest snapshot with
   `createdAt <= at`, scoped to the lineage. Snapshot ids are already
   time-sortable (`MintSnapshotID`, `manifest.go:290-296`), but the resolution reads
   `createdAt` rather than parsing the id: the id's timestamp is when it was minted, not
   when the manifest committed, and the two can differ by the length of the upload.
2. Mint a restore-intent session, then a read grant. The grant answers with
   `manifestChain`.
3. Fetch every manifest in the chain, `DecodeManifest` each (`manifest.go:139-148`,
   which validates, so nothing downstream sees an unvalidated one).
4. Walk DOWN: `full := chain[0]` must satisfy `!IsDelta()`; then for each subsequent
   delta, `full = MaterializeManifest(delta, full)`. This is the only order
   `MaterializeManifest` accepts (`manifest.go:219-221`).
5. Create the staging file, `ftruncate` to `ImageBytes`.
6. For each cell index with `cells[i] != ZeroCell`: GET the object, verify, write at
   `CellStart(i, CellBytes)`.
7. Leave every `ZeroCell` untouched. It stays a hole.
8. Verify the assembled image, then rename into place.

### 3.2 The five details the sketch missed, each of which silently corrupts

- **The final cell is short.** `CellLength(index, imageBytes, cellBytes)`
  (`grid.go:58-67`) charges the last cell only up to `imageBytes`. The uploader honors
  this (`readCell`, `uploader.go:361-371`) so the stored tail object is short. A
  restore that assumes a full cell writes past the end.
- **`ftruncate` to `ImageBytes` is mandatory, not tidy.** If the trailing cells are
  holes, writing cells alone leaves the file SHORT. Nothing else in the flow sets the
  length. This is the defect that a sha256-only fixture with a non-hole tail cannot see.
- **Every chunk is re-hashed before it is written.** The store is content addressed, but
  nothing on the wire proves the bytes match the key: not the presigned URL, not
  SigV4, not the R2 JWT. The check is `sha256(data) == cells[i]` plus
  `len(data) == CellLength(i, ...)`. The existing negative test already asserts exactly
  this property (`negatives_test.go:435-444`) and names the failing cell.
- **`ZeroCell` is never filled with zeros.** `ZeroCell` is `""` and is FIEMAP-derived,
  never content-derived (`manifest.go:24-28`). Writing explicit zeros produces a
  byte-identical file that is no longer sparse, inflating the datastore by the size of
  every hole. sha256 cannot detect this. Section 6.1 has the test that can.
- **A hash appearing at several indices is fetched once.** `NonZeroHashes`
  (`manifest.go:263-286`) already returns the de-duplicated set in deterministic cell
  order. Restore builds `hash -> []index` and writes one fetched buffer at every index
  that wants it. On an image with large identical regions this is the difference
  between one GET and hundreds.

### 3.3 The getter seam

Mirror `objectPutter` (`grants.go:79-85`) with `objectGetter`:

```go
type objectGetter interface {
    Get(ctx context.Context, hash string) ([]byte, error)
}
```

Three implementations mirroring the three putters: `s3Getter` (SigV4 GET),
`presignedGetter` (URL per bare hash, with the same `errNoPresignedURL` re-mint
behavior as `presignedPutter`, `grants.go:180-194`), and `httpsGetter`.

`signSigV4` (`sigv4.go:43`) works for GET as-is: the canonical request takes the method
verbatim at `:85` and the payload hash for an empty body is the SHA-256 of the empty
string. Its header comment at `:20-21` says "single-part PUT/HEAD-shaped requests",
which becomes inaccurate the moment a GET is signed with it. Update the comment in the
same change. A stale comment about what a signer supports is how the next session
concludes it needs a second signer.

Concurrency reuses the uploader's shape (`uploadRun`, `uploader.go:296-335`): a work
channel, a bounded pool, `errOnce` plus `cancel` on first failure. Default parallelism 4
to match `uploader.go:242-245`. No new abstraction, and deliberately no shared
worker-pool refactor: the two loops are 30 lines each and a premature merge would
couple the resume semantics.

---

## 4. Where it lands, and what it must not run over

### 4.1 Staged beside, renamed in

This mirrors both existing precedents. `backup pull` assembles into
`<datastore>/repositories/.<name>` and renames (`backup_pull.go:222`, `:759-803`), and
`PlanSnapshot` stages a reflink and promotes it in one rename after the server-side
commit (`pipeline_linux.go:105-144`, `:321-344`). The ordering comment at `:321-328`
warns explicitly against "improving" it. Restore takes the same discipline in the
mirror direction:

1. `locking.AcquireExclusive(locking.GetLockPath(datastore, guid))`, matching
   `backup_pull.go:238`. Not the shared lock `PlanSnapshot` takes at
   `pipeline_linux.go:127`: a restore is a writer.
2. `validateLocalRepoSafety(guid, repositoryPath, mountPath)`
   (`cmd/renet/backup_safety.go:18-33`) before touching anything, when the target
   exists. This is the shared helper `validatePullSafety` delegates to at
   `backup_pull.go:710`. Restore calls it directly rather than going through
   `validatePullSafety`, whose first branch (`:704-707`) returns nil for DIRECTORY
   repos. A chunk-store image is always a LUKS file; a directory target is a caller
   error and gets its own refusal.
3. Assemble into `<datastore>/repositories/.restore-<guid>`.
4. Re-check the mount after assembly and before the rename, matching
   `backup_pull.go:299-305`. A restore of a large image runs for minutes and the repo
   can be mounted underneath it.
5. `verifyRestoredImage`: size equals `ImageBytes`, and `cryptsetup isLuks` passes
   (the check at `backup_pull.go:749`, reused not re-implemented). The LUKS check is
   what catches an assembly that is internally consistent but built from the wrong
   lineage: every cell hash verified, and the result is not a LUKS container.
6. `os.Rename` staging over target, then `os.Chmod(0o400)`, matching
   `finalizeTransfer:789-791`. No reflink fallback: `finalizeTransfer` needs one
   because rsync may have written across filesystems; the staging file here is created
   by us in the same directory as the target, so a rename failure is a real error and
   is reported as one.

### 4.2 A restore in flight must make a concurrent snapshot skip

`prune/identifiers.go` gains `RestoreStagingPrefix = ".restore-"` beside
`PullStagingPrefix` (`:113-116`), and `TransientReason` (`pipeline_linux.go:66-80`)
gains a fourth case naming it. Without this, `renet backup snapshot` running on a timer
can reflink a half-assembled image, hash it, and upload a manifest of garbage that
commits cleanly. It would be discovered at the NEXT restore.

Reusing `.pull-` instead would get the skip for free but would make `backup sync pull`
and restore collide silently on the same staging path. A distinct prefix costs one
constant and one branch.

The prune reclaimer already sweeps by prefix; the new prefix needs adding to whatever
`prune` enumerates as reclaimable staging, or an abandoned restore litters forever.
That is the class this repo has been bitten by before (`SweepOrphanJournals`,
`journal.go:129-137`, exists for exactly this reason).

---

## 5. The full surface trail

### 5.1 renet

| Artifact | Change |
| --- | --- |
| `cmd/renet/backup_restore.go` | New verb. Flags: `--repo` (target GUID, required), `--datastore`, `--lineage` (required), `--at` (required), `--parallelism`, `--bwlimit`, `--dry-run`. One JSON record on stdout, same discipline as `backup_snapshot.go:161-183`. |
| `cmd/renet/backup_pull.go:195-197` | Refusal message points at `renet backup restore`. |
| `pkg/chunkstore/download.go`, `restore_linux.go` | The engine (section 3). |
| `pkg/chunkstore/session.go` | `MintReadGrant`, `wireReadGrant`, `intent` on `sessionRequest` (`:71-77`). |
| `pkg/chunkstore/grants.go` | `objectGetter` and its three implementations. |
| `pkg/chunkstore/sigv4.go:20-21` | Comment correction (GET is now signed here). |
| `pkg/prune/identifiers.go` | `RestoreStagingPrefix`, plus the reclaim sweep. |
| `pkg/chunkstore/pipeline_linux.go:66-80` | Fourth `TransientReason` case. |
| `pkg/functions/commands/backup.go` | `backup_restore` FunctionDef + `BackupRestoreCommand`, modeled on the `backup_snapshot` pair at `:217-231` and `:645-683`. Params: `lineage`, `at`, `dry_run`. Requirements `{machine, team, repository, storage}`. |
| `pkg/license/tiermap.go` | `"backup_restore": {tier: TierNone}` with the reasoning at `:55-59` extended, not repeated. |

The record shape mirrors `BackupSnapshotRecord` (`backup_snapshot.go:35-55`): GUID,
status, reason, plus `snapshotId`, `lineage`, `chainDepth`, `cellsTotal`, `cellsZero`,
`chunksFetched`, `bytesFetched`, `imageBytes`, `durationMs`. Statuses: `restored`,
`skipped`, `failed`. There is deliberately no `quota-refused`: reading spends no quota.

`isQuotaRefusal` (`backup_snapshot.go:392-403`) still applies for
`SUBSCRIPTION_LAPSED` and `BACKUP_NOT_CONFIGURED`, but the new
lapsed-beyond-retention refusal needs its own code so the operator is told "the
retention window closed" and not "prune or upgrade". Exit code: reuse 1. Do not spend a
second reserved code; `quotaRefusedExit = 16` (`backup_snapshot.go:79`) exists because
the operator action differs, and here it does not.

### 5.2 Account

`routes/backups.ts` (`POST /read-grants`), `dto/backup.dto.ts` (request + response),
`services/backup-storage.service.ts` (`mintReadGrant`, session intent, `mintGrant`
refusal of read sessions), `services/backup-chunk-store.ts` (action split, `mintRead` on
three minters), `db/schema.ts:1533-1549` plus `drizzle/0050_*.sql`, and the scope
registry entry the `check:ci-account-scope-audit` gate requires.

No new API-token scope. `backup:read` (`packages/shared/src/subscription/types.ts:239-243`)
covers the CLI's manifest listing, which is the only token-authenticated read restore
needs. The grant itself rides the session, not a token.

### 5.3 CLI

`rdc backup restore` stays one command and routes on `--at`:

- `--at` absent: today's artifact path, `backup_pull` via `runRestorePull`
  (`backup.ts:256-291`). Unchanged.
- `--at` present: `backup_restore`, with `lineage` resolved the way
  `registerBackupManifests` already resolves it (`backup-storage.ts:127-134`:
  `repo.grandGuid ?? repo.repositoryGuid`).

The `--at` passthrough at `backup.ts:271` and `pkg/functions/commands/backup.go:585-587`
is removed from `backup_pull` in the same change: leaving a parameter wired to a verb
that refuses it is how the next session concludes the path works.

Also touched: `packages/cli/scripts/command-tree.json` and the generated contract
(`packages/cli/scripts/generate-cli-contract.ts` writing
`packages/shared/src/cli-contract/data/contract.{json,generated.ts}`), and the generated
tier table `packages/shared/src/renet-contract/data/license-tiers.generated.ts`.
`command-metadata.ts:133-136` already declares `backup restore` as grand-guarded and
destructive, which stays correct. `command-planes.ts:56` already puts the `backup`
domain on the machine plane, and restore inherits it, so `plane-coverage.test.ts` counts
do not move: no new `rdc` command is added. That is a deliberate side benefit of routing
rather than adding.

`command-docs.ts:251-260` gains a third example under `'backup restore'` showing `--at`.

### 5.4 i18n

New English keys under `commands.backup.restore.*` in
`packages/cli/src/i18n/locales/en/cli.json`, keeping the file alphabetically sorted.
Then `npm run i18n:naturalize-status` for the delta, re-naturalize only the stale keys
through `private/growth/i18n_pipeline` with `--model haiku`, and
`npm run i18n:generate-hashes`. Twelve derived locales, never bulk-replaced. Renet's own
Go catalog needs the new verb's strings if any of its output goes through `i18n.T`;
`backup_snapshot.go` uses none, and `backup_restore.go` follows it.

### 5.5 Gates this touches

`check:ci-renet-tiers`, `check:ci-renet-types`, `check:ci-cli-contract`,
`check:ci-command-tree`, `check:ci-command-planes`, `check:ci-account-scope-audit`,
`check:ci-account-layer-isolation`, and the i18n chain. Run them; do not read them.

---

## 6. Tests that fire on a planted defect

The rule this section is written to: the byte-identity assertion has to be able to FAIL
for the right reasons, and a sha256 comparison alone cannot see two of the five failure
modes in section 3.2.

### 6.1 Go, `pkg/chunkstore`

`negatives_test.go:351-444` already asserts the restore SHAPE, using a test-local
`restoreFromInventory` helper. That helper is a hand-written twin of the function this
plan builds, and `grid.go:15-19` warns in the package doc about exactly that: "a
hand-written twin is exactly how a fixture format once left a battery check dormant for
its whole life". **Deleting the helper and re-pointing the test at the product function
is part of the work, not a follow-up.**

New and rewritten tests, each with its planted defect named:

| Test | Planted defect it must catch |
| --- | --- |
| `TestRestore_ByteIdenticalWithShortTailAndHoles` | write a full cell for the tail instead of `CellLength` |
| `TestRestore_TrailingHolesKeepTheImageLength` | drop the `ftruncate(ImageBytes)`; fixture's last two cells are holes so the file comes back short |
| `TestRestore_HolesStayHoles` (linux) | write explicit zeros for `ZeroCell`. Asserted with `WrittenRanges` (`zerodetect_linux.go:22-35`), NOT sha256, because sha256 passes |
| `TestRestore_ACorruptChunkIsRefusedByName` | skip the per-chunk re-hash; corrupts the SHORT last cell specifically |
| `TestRestore_AWrongLengthChunkIsRefused` | length check omitted; a full-length chunk served for the short tail |
| `TestRestore_WalksTheChainToTheFullRoot` | feed a delta directly to `MaterializeManifest` against another delta; must fail, not produce plausible cells |
| `TestRestore_RefusesAnIncompleteChain` | a chain whose root is a delta with no parent manifest; must fail rather than restore the partial inventory |
| `TestRestore_ResumeAfterAKillFinishesWithTheSameBytes` | resume path. **Control: assert the interrupted staging file does NOT already hash equal**, or the test proves nothing |
| `TestRestore_FetchesOneObjectForARepeatedHash` | de-dup dropped; counts GETs against a fake getter |

### 6.2 Account, `tests/integration/`

Beside `backup-storage.test.ts` and the lifecycle twin the drill names at
`scripts/drills/backup.sh:73-76`.

| Test | What would otherwise pass silently |
| --- | --- |
| read grant carries no delete verb | structural assertion over the action union |
| read grant is minted for a LAPSED subscription inside retention | the whole 60-day promise |
| and REFUSED past `retentionStartedAt + 60d`. **Control: an active subscription's identical request succeeds** | otherwise the refusal could be any rejection |
| a `restore`-intent session is refused by `mintGrant` | a read session that can write |
| a read grant creates NO lease. **Control: a write grant in the same test moves `leasedBytes`** | a read that consumes quota headroom |
| presigned read URLs keyed by BARE HASH | the exact defect documented at `backup-chunk-store.ts:541-546` |
| a key outside the lineage prefix is never signed | tenant isolation, mirroring the write-side assertion |
| the chain walk refuses past `BACKUP_MANIFEST_CHAIN_MAX` | silent truncation restoring the wrong point in time |

### 6.3 The drill, `scripts/drills/backup.sh`

Leg d today reads the store with the STORE's own credentials, and the header says so
plainly at `:67-71`: "Restore reads the store with the store's own credentials, because
there is no download grant". `restore_snapshot` (`:856-894`) uses `s3_curl` directly.

- **Rewrite leg d to mint a read grant and read through it.** Its byte-identity
  assertions at `:896-918` are already correct and become the acceptance for the new
  path. The "OLD snapshot still restores to the OLD bytes after the newer one landed"
  assertion at `:910-911` is the one that matters and does not change.
- **New leg j, the planted control: the same restore attempted with a WRITE grant's
  credentials must FAIL.** After the action split (section 2.2) a write grant carries no
  `GetObject`. Without this control, leg d passing proves only that the bytes are
  readable by someone, not that the read grant is what authorized it.
- **New leg k: the lapsed-subscription restore.** Cancel the drill subscription, mint a
  restore-intent session, restore, compare sha256. Control: a `backup`-intent session
  against the same lapsed subscription must be refused. This is the only place the
  60-day promise is exercised end to end.
- The header's "WHAT THIS DRILL DOES NOT PROVE" section (`:57-71`) shrinks by exactly
  the claims these legs now make, and not by more.
- `--selftest` must plant an unpassable assertion in each new leg, per the existing
  convention at `:78-79`.

### 6.4 e2e suite 26

`packages/e2e-tests/tests/26-backup-storage-cli.test.ts` already has the RESTORE tier
written and dark (`:614-741`), gated by `E2E_CHUNK_RESTORE_VERB` through `chunkVerbs`
(`src/utils/backupStorage.ts:296-301`).

- Set the default so the tier lights up from the built binary rather than from an env
  var, which is what the suite's own header demands at `:44-48`: the tier probes
  `renet backup --help` and must not go green because someone exported a variable.
- Confirm the TRANSCRIPT-CONFIRM argv at `:722-730` against the real binary and edit it
  to fact. It is currently derived from the design and is flagged as such at `:52-56`.
- The byte-identity assertion at `:735-740` is the load-bearing one and needs no change.
  It is the only place in the program where a restore is compared against a source image
  on a DIFFERENT machine.

---

## 7. Deliberately out of scope for the first implementation

Named, with the cost of leaving each out.

1. **The differential restore.** `02-design.md:34-39` describes restore as a DIFF
   against local state: the journal caches the anchor's cell hashes
   (`journal.go:29-30`, `:46-47`), so a same-machine point-in-time restore could
   download only the cells that differ. The first implementation downloads every
   non-ZERO cell. Cost: bandwidth on same-machine rollback, none on fresh-machine DR,
   which is the case that matters. No format change is needed to add it later, because
   `AnchorRecord.CellHashes` is already there and already says it is for this.
2. **Server-side synthetic-full consolidation** (`02-design.md:51-52`). Not built today and
   not built here. Restore instead walks arbitrary-depth chains with a bounded refusal
   (section 2.3). Cost: a very long-lived repo eventually hits the bound and must
   `--reseed`. The bound firing is the signal that consolidation has become the next
   piece of work, which is better than discovering it during a real recovery.
3. **Bandwidth limiting on the download side.** `--bwlimit` is registered and accepted
   for symmetry but wired to the existing `rateLimiter` (`uploader.go:454-496`) only if
   that is a one-line reuse. If it is not, the flag is dropped rather than stubbed.
4. **Restore into a mounted repo, and hot restore.** Refused, loudly, by
   `validateLocalRepoSafety`. There is no CRIU-style live path and this plan does not
   invent one.

---

## 8. The blocker this plan does not solve, stated plainly

**A fresh machine with no repo license cannot restore.**

`renet backup restore` needs a signed license blob to mint a session, exactly as
`backup_snapshot.go:224-235` does, because the blob is both credential and address book
(it carries the renewal URL the session URL is derived from, `:371-383`). On a target
machine the blob comes from `LoadPreferredRepoLicense` (`pkg/license/preferred.go:37-43`),
and the only writer of that file is `writeRepoLicenseAt`, called from exactly one place:
`pkg/license/renew.go:318`, which renews a blob that is already there.

The CLI's recovery path cannot bootstrap one either. `maybeIssueLicense`
(`packages/cli/src/services/executor/local-executor.ts:1152-1219`) says so in its own
comment at `:1170-1171`: batch refresh works because "the repo image exists on disk
there, so refreshRepoLicensesBatch can scan it and issue". For a restore the image does
not exist yet, which is the point. And the pre-provisioning branch does not fire:
`isRepoProvisioningFunction` (`renet-license-contract.ts:141-147`) matches only
`repository_*` create-tier verbs, and `backup_restore` is neither.

There is a partial answer that costs nothing and should ship with this plan. The backup
session principal carries only `{sessionId, subscriptionId, machineId}`
(`backup-storage.service.ts:64-68`, `:201`), and `authenticateLicenseBlob` resolves the
subscription from the blob without binding the session to the blob's repository GUID
(`subscription.service.ts:1147-1226`). Every subsequent call is scoped by the
`lineageGuid` in the REQUEST. So **any** valid repo license the restoring machine holds,
for any repo of the same subscription, authenticates a session that can read any lineage
of that subscription. The verb should therefore take the target's license when installed
and fall back to any installed license of the subscription, saying which it used. This
is not a hole: same subscription, same tenant prefix, same data the operator already
owns.

That leaves the genuinely bare machine, which holds no license for anything. That case
needs a CLI-side change (issue a repo license for the restore target before the verb
runs, sized from the manifest's `totalBytes`, `kind: 'grand'`, through
`issueRepoLicense` at `packages/cli/src/services/account/license.ts:398-448`). It is a
small change in an area with sharp edges: `issueRepoLicense` normally carries
`luksUuid` and `storageFingerprint` read from a live image
(`readRepoLicenseInputs`, and the comment at `license.ts:452-469` explains why those
bytes must come from renet's own scan and not from a `stat`). For a restore target
neither exists yet, so the license has to be issued without them and re-issued after
the image lands.

I am flagging this rather than folding it in silently because it is a CLI and licensing
change that the restore brief did not ask for, and because getting it wrong is the shape
of rediacc/console#482. It is not optional: **without it, fresh-machine disaster
recovery does not work**, and fresh-machine DR is the case the whole program exists for.
The engine, the read grant and the same-fleet restore are all deliverable and testable
without it, which is why it is called out as a separate decision rather than a
precondition.
