# PLAN: Make deletion reachable — segmented chains, chain-aware prune, enforced retention
Status: draft
Owner: 97604f47
Updated: 2026-08-14

Scope: the three legs the operator chose, and how they compose. Everything below is
anchored to branch `backup-storage` and re-verified against the tree by me, not taken
from the brief. Where the brief was right I say so once; where I found something it did
not mention I flag it.

---

## 0. The defect, re-verified

**Confirmed, all three claims.**

**0.1 The chain is strictly linear.** `buildPlan`
(`private/renet/pkg/chunkstore/pipeline_linux.go:155-263`) always builds the FULL
inventory into `manifest` (`:228-243`), then, when and only when the anchor is trusted
(`:245-259`), derives `deltaManifest` against a parent synthesized from
`journal.Anchor` — whose `SnapshotID` is the previous run's. `trusted` goes false in
exactly four places: no/corrupt journal (`:174-180`), grid geometry change (`:189-191`),
anchor verification failure (`:192-193`), and a mid-run compare failure (`:214-219`).
`--reseed` reaches the same place through the journal. So after the first backup every
manifest is a delta whose parent is the manifest before it.

`Upload` commits the delta when one exists (`uploader.go:180-184`), and
`SessionControlPlane.CommitManifest` sends `parentSnapshotId` only when `m.Parent != ""`
(`session.go:460-462`).

**0.2 `pruneManifest` is correct and unreachable.**
`private/account/src/services/backup-gc.service.ts:298-327`. Its dependents query
(`:299-311`) refuses with 409 whenever any retained row names the target in
`parentSnapshotId`. In a strictly linear chain every manifest except the newest is
somebody's parent, so the refusal fires on every candidate a retention policy would
pick. It is dead code with a passing test.

Beyond the brief: **`pruneManifest` has zero callers in production.** The only
invocations anywhere are `private/account/tests/integration/backup-gc.test.ts:401-404`.
`runMaintenance` (`backup-gc.service.ts:72-96`) calls `sweepExpired` ×3,
`retentionSweep` (`:331`), `overQuotaSweep`, and `gcSubscriptionChunks` (`:123`) — never
`pruneManifest`. And `private/account/src/routes/backups.ts` (152 lines, 9 endpoints)
exposes **no delete verb at all**: `/session` `:63`, `/streams` `:75`, `/grants` `:83`,
`/read-grants` `:94`, `/exists` `:102`, `/commit` `:111`, `/usage` `:119`, `/manifests`
`:129`, `/verify` `:145`. So even if the chain shape allowed a prune, nothing could ask
for one over the wire.

**0.3 `RetentionPolicySchema` is write-only.**
`packages/shared/src/config-schema/schemas.ts:474-481`, consumed at `:491` by
`BackupStrategyConfigSchema.retention`. A repo-wide grep for
`RetentionPolicySchema|retentionPolicy|RetentionPolicy` over `packages`, `private`,
`scripts` and `.ci` returns exactly those two lines. No writer, no reader, no
account-side consumer. Its own doc comment already claims "Enforcement is server-side
(the chunk store's GC)" — a statement about code that does not exist.

**0.4 The consequence the operator named.** `backupUsage.storedBytes`
(`private/account/src/db/schema.ts:1380-1389`) only ever moves by `+addedBytes` at
commit (`backup-storage.service.ts:878-894`) and by `-freed` from chunk GC
(`backup-gc.service.ts:238-245`). Chunk GC frees only what no indexed manifest
references (`:186-201`), and no manifest is ever deleted, so nothing ever becomes
unreferenced. `storedBytes` is monotonically non-decreasing for the life of the account.
The quota check at grant mint (`backup-storage.service.ts:426+`, `computeUsed`
`:396-420`) then refuses the customer's next backup, permanently, with a 403 that says
"prune or upgrade" (`packages/cli/src/commands/backup-storage.ts:227`, `:269`) about a
prune verb that does not exist.

**0.5 Two live stale comments that will mislead the implementer.** Both must be
rewritten as part of this work; leaving either is how the next session re-derives the
wrong model.
- `backup-storage.service.ts:62-70` — "Nothing consolidates delta chains today, so this
  bound WILL be reached on a long-lived lineage". True today, false after leg 1.
- `docs/backup-storage/02-design.md:54-58` — "periodic server-side synthetic-full
  consolidation" and "kilobyte-scale manifest consolidation, done server-side" are
  described as design, and **none of it exists**. Grepping `synthetic` over
  `private/account/src`, `private/renet/pkg`, `packages`, `docs/backup-storage` and
  `scripts/drills` finds only two comments, both merely noting that `parentSnapshotId`
  is null for "full/synthetic-full" (`backup-storage.service.ts:110`,
  `db/schema.ts:1432`). The brief's belief that none of it exists is correct.

---

## 1. Chain shape: options, scored

The unit of cost is bytes, so each option is scored on chunk bytes, manifest bytes, and
machine CPU. Two facts set the scale and kill most of the intuition:

- **A full manifest costs no extra chunk bytes.** Every cell hash it names is already
  stored; `existsBatch` (`backup-storage.service.ts:718`) dedups them and `addedBytes`
  at commit is what was actually uploaded (`session.go:449-457`, client-declared). A
  full manifest emitted in place of a delta uploads a bigger JSON document and zero
  extra chunks.
- **The full inventory is already computed every single run.** `buildPlan` builds
  `manifest` with a complete `Cells` array before it decides whether to derive a delta
  (`pipeline_linux.go:228-259`). Today it discards it on the trusted path. Emitting it
  is a choice between two objects already in memory, not new work.

Manifest sizes, for scoring: a full manifest is ~67 bytes per non-zero cell
(`"<64 hex>",`) and 3 bytes per ZERO cell; a delta is ~76 bytes per changed cell
(`"<index>":"<64 hex>",`). For a 100 GiB image at 1 MiB cells that is ~6.9 MB full
versus ~78 KB for 1% churn.

| Option | Chunk bytes | Manifest bytes | Machine CPU/IO | Restore | Verdict |
|---|---|---|---|---|---|
| **A. Periodic full emitted by renet** (segment roots every K snapshots) | zero extra | +full/K amortized: at K=32, 100 GiB/1 MiB repo ≈ 215 KB per snapshot on top of a ~78 KB delta | **zero extra** — the inventory is already built | chain ≤ K hops, strictly shorter than today | **WIN** |
| **B. Server-side synthetic-full consolidation** | zero extra | same as A, but the server writes it | zero on the machine; the SERVER must fetch and materialize the whole chain | same | loses as the shape mechanism, **kept as the prune primitive** (leg 2) |
| **C. Capped depth forcing `--reseed`** | zero extra | same as A | **worst**: `rehashAllCells` (`pipeline_linux.go:307-325`) reads and SHA-256s the entire image, minutes to tens of minutes per boundary on a production repo | same | **dominated by A** — identical outcome, gratuitous cost |
| **D. Delta against a fixed base** (parent always the segment root) | zero extra | **quadratic within a segment**: changedCells accumulates all churn since the base, so segment total ≈ K²/2 × per-snapshot churn | zero extra hashing, but the journal must cache a SECOND inventory (the base) alongside the anchor's `CellHashes` (`journal.go:45-47`) and prove its trust separately | always 2 hops, best | **second** — genuinely attractive, loses on journal complexity and quadratic manifest bytes |

**Chosen: A, with B reduced to the prune primitive.**

B is rejected as the *shape* mechanism on one concrete ground beyond cost: the Workers
runtime has a 128 MB memory ceiling, and a full manifest for a large repo approaches it
(1 TiB at 1 MiB cells ≈ 70 MB of JSON, before the parsed object). Making that the
routine path puts the store's growth policy on the wrong side of a memory limit. It
survives in leg 2 only for the rare interior-delete case, with an explicit bound
(§2.4).

D deserves a note because it makes leg 2 nearly unnecessary: with a fixed base, no
non-root manifest is ever a parent, so `pruneManifest` fires today. It loses because A
with a small K approximates it at linear rather than quadratic manifest cost, and
because the second cached inventory reintroduces exactly the trust problem `AnchorRecord`
(`journal.go:31-48`, with its inode guard) was built to solve once.

### 1.1 Implementation of A

`private/renet/pkg/chunkstore/journal.go` — new record on `Journal` (`:68-79`):

```go
// SegmentRecord tracks the current delta segment: which snapshot is its FULL
// root and how many manifests hang off it. A nil Segment means "no known
// root", which is why the zero value is safe: an existing journal decodes with
// Segment nil and the next backup emits a full, closing the old unbounded
// chain without a migration.
type SegmentRecord struct {
    RootSnapshotID string `json:"rootSnapshotId"`
    Depth          int    `json:"depth"` // manifests since the root, root excluded
}
```

`pipeline_linux.go:245` — the delta is derived only when
`trusted && journal.Segment != nil && journal.Segment.Depth+1 < SegmentMaxDepth`.
Otherwise the full `manifest` is uploaded and the segment resets. `Plan.Commit`
(`pipeline_linux.go:337`) updates `journal.Segment` alongside the anchor.

`SegmentMaxDepth` is a renet constant with a `--segment-depth` override on
`renet backup snapshot`. Default **32**, chosen to sit safely under
`BACKUP_MANIFEST_CHAIN_MAX = 64` (`backup-storage.service.ts:71`) so the server's
backstop can only fire on data written before this change.

**The zero value does the right thing, which is why no migration is needed.** A journal
written before this change has no `segment` key; Go decodes it as nil; the first backup
after the change emits a full manifest and starts segment 1.

### 1.2 What happens to an EXISTING chain (the constraint the brief demanded an answer to)

**Nothing breaks, and nothing is rewritten.**

- The existing linear chain keeps its rows and objects exactly as they are. Its newest
  manifest is unchanged.
- The next backup appends a **full** manifest with `parentSnapshotId = null`. It does not
  reference the old chain and does not invalidate it. Restore of any old snapshot still
  walks the old chain, exactly as it does today.
- `resolveManifestChain` (`backup-storage.service.ts:581-648`) needs **no change**: it
  already terminates on `row.parentSnapshotId ?? null` (`:644`). A full manifest is a
  natural chain terminator today; the change only makes them appear regularly.
- **The bound (`BACKUP_MANIFEST_CHAIN_MAX`, `:71`) stays at 64 and its meaning
  inverts.** Today it is a prophecy ("this bound WILL be reached"); after leg 1 it can
  only be reached by pre-change data, so it becomes a backstop against exactly that. Its
  doc comment (`:62-70`) is rewritten to say so. It stays a NAMED 409
  (`BACKUP_CHAIN_TOO_LONG`, `errors.ts:76`) and never a truncation — that property is
  load-bearing and is not touched.
- A pre-change chain already longer than 64 can exist in D1 (commit does not bound
  depth) and would fail only at restore. Leg 1 stops it growing; leg 3 eventually
  deletes it wholesale once a newer segment exists. This is the one honest wart, and it
  is a pre-existing one this change improves rather than creates.
- `MaterializeManifest` (`manifest.go:219-268`) and `MaterializeChain`
  (`download.go:174-197`) are untouched by leg 1. `MaterializeChain` requires
  `chain[0]` to be full (`:183-191`); segment roots make that requirement *easier* to
  satisfy, never harder.
- `extractManifestHashes` (`backup-gc.service.ts:495-537`) sees more `cells`-shaped
  manifests and fewer `changedCells`-shaped ones. Both branches exist (`:508-524`,
  `:525-534`) and both stay covered by §4.

---

## 2. Chain-aware prune

Leg 1 bounds growth. It does **not** by itself make an interior manifest deletable — a
delta inside a segment is still its successor's parent. Leg 2 is the primitive that
collapses.

### 2.1 The composition rule

For a doomed run of consecutive manifests `d1 … dn` (oldest first) with a surviving
child `S` (a delta naming `dn` as parent), let `base = parent(d1)`:

```
S'.parent       = d1.parentSnapshotId          (may be null)
S'.changedCells = merge(d1.changedCells, …, dn.changedCells, S.changedCells)   // later wins
S'.imageBytes   = S.imageBytes                  // everything else copied from S
```

Correctness, by cases on cell index `i`, writing `apply(P, m)` for materialisation:
- `S` changed `i` → `S'[i] = S.changed[i] = Sfull[i]`. ✓
- else some `dk` changed `i` (latest wins) → `S'[i] = dk.changed[i] = Sfull[i]`. ✓
- else nobody changed `i` → both resolve to `base[i]` (or ZeroCell past base's grid). ✓

**The one case where the merge is WRONG, and the guard for it.** The last case assumes
"past base's grid ⇒ ZeroCell" holds identically on both sides. If any `dk` or `S` shrank
*below* `base.imageBytes` and a later member grew again, then an index in
`[min grid, S.grid)` that no map covers resolves to `base[i]` under `S'` but to ZeroCell
under the real chain. So:

> **Merge is permitted iff `m.imageBytes >= base.imageBytes` for every `m` in
> `[d1 … dn, S]`.** Otherwise the survivor is PROMOTED to a full manifest instead
> (§2.3). Never merged-and-hoped.

`BuildDeltaManifest` (`manifest.go:156-207`) and `MaterializeManifest`
(`manifest.go:219-268`) are the two functions whose exact grid semantics this proof
leans on; both were re-read for it.

### 2.2 Branching

The schema permits several rows to name one parent (`backupManifests.parentSnapshotId`,
`db/schema.ts:1434`; the index at `:1443` is on `(subscriptionId, lineageGuid)`, not
unique on parent). Today renet produces only linear chains, but a fork family shares a
lineage. So the collapse re-parents **every** surviving child of `dn`, each with its own
merge. No code may assume at-most-one child.

### 2.3 Promotion (the `base == null` case)

When `d1` is the segment ROOT (its `parentSnapshotId` is null, so it is the full
manifest), there is nothing to re-parent onto. The survivor must become a full
manifest: materialize `d1 ⊕ d2 ⊕ … ⊕ dn ⊕ S` and write `S'` with `cells` set,
`parent` unset.

### 2.4 The bound on promotion, and its graceful degradation

Promotion is the only step whose memory cost scales with image size rather than churn.
Add to the constants block in `backup-storage.service.ts` (beside
`BACKUP_MANIFEST_CHAIN_MAX` at `:71`):

```ts
/** Max cells in a manifest the server will materialize during a collapse.
 *  Above this a promote-to-full would approach the Workers memory ceiling, so
 *  the segment ROOT is retained instead and only the interior collapses. */
export const BACKUP_COLLAPSE_MAX_CELLS = 262_144;   // ~17 MB of JSON
```

Over the bound, the sweep **keeps the segment root** and collapses only the interior
onto it, and records a NAMED entry in `BackupMaintenanceReport` (`:49-63`,
new field `collapseDeferred: {lineageGuid, snapshotId, cells}[]`) plus a
`backup_retention_collapse_deferred` system event. Never a silent skip. Cost of the
degradation, stated plainly: one extra manifest object survives per affected segment,
plus whatever chunks it uniquely references. With leg 1 this is rare, because retention
normally drops whole segments (§3.4) and never touches a root's children.

### 2.5 Write order, and what each crash window leaves

1. PUT each `S'` manifest object (same key — `backupKeys.manifest`, the key is derived
   from the snapshot id, `backup-storage.service.ts:790`).
2. One `runAtomic` D1 batch: update each `S` row's `parentSnapshotId`; delete the
   `d1 … dn` rows. **`addedBytes` and `addedChunkCount` are NOT touched** — they are the
   billing record of what was uploaded, and the chunks are still there. `storedBytes`
   moves only when chunk GC actually frees bytes.
3. Delete the `d1 … dn` manifest objects from the bucket.

Crash windows, each loud rather than wrong:
- **After 1, before 2.** The row says `S.parent = dn`, the object says `S` is full (or
  is `base`-relative). Restore resolves the chain `[…, dn, S]` and
  `MaterializeManifest` refuses by name — "manifest S is already full"
  (`manifest.go:214`) or the parent-name mismatch at `manifest.go:222-223`. A loud
  409-shaped failure, never wrong bytes. The sweep is idempotent: re-running rewrites
  the same object and completes.
- **After 2, before 3.** Orphan manifest objects with no D1 row. GC's roots come from
  D1 rows (`backup-gc.service.ts:136-139`), so their chunks are correctly treated as
  unreferenced. The objects themselves are litter under the lineage's manifest prefix;
  `runMaintenance` gains a small orphan-manifest sweep (list the manifest prefix, delete
  keys with no row, subject to the same 7-day grace).

### 2.6 The new invariant this creates, and its guard

**Today only renet (Go) writes manifest objects. After leg 2 the account server (TS)
writes them too, and renet must decode them.** That is the biggest new coupling in this
plan and it gets an explicit guard: a `validateManifestShape()` in the account service
that mirrors `Manifest.Validate` (`manifest.go:68-125`) rule for rule — version must be
1; delta must not carry `cells`; full must not carry `changedCells`; `len(cells)` must
equal `CellCount(imageBytes, cellBytes)`; every hash lowercase hex SHA-256 or the empty
ZeroCell; `snapshotId != parent`. Every collapse output passes through it before the
PUT. Cross-language conformance is pinned in the drill (§4.4), where both languages are
live, rather than by a Go re-implementation of the merge (see §6).

---

## 3. Retention: who reads the policy, and why

### 3.1 The two candidates

Two hard facts frame it. **Only the account server can delete** — the design's own rule,
stated at `backup-gc.service.ts:7-9` ("Storage deletes go through the server's own
credential only — no grant can delete anything"), and enforced by the grant minters
never issuing a delete verb (pinned by `backup-storage.test.ts:650`). **Only the CLI
holds the config** — `backup.strategies[].retention` lives in the user's config file
(`schemas.ts:491`), which never leaves the machine.

| | CLI enforces | Server enforces |
|---|---|---|
| Policy source | already local | must be pushed and persisted |
| Runs when the machine is offline | **no** | yes |
| GFS implementation | duplicated in TS on the client | one, server-side |
| Delete authority | must expose a per-snapshot delete route anyway | already has it |
| Drift risk | none | **a config edit that never reaches the server silently does nothing** |

### 3.2 The decision: the CLI DECLARES, the server ENFORCES

The deciding argument is the operator's own framing — "self-managing rather than needing
manual deletes". A quota that only self-manages while a machine is up is not
self-managing: the machine most likely to eat quota forever is the one that died. And
CLI enforcement would need a per-snapshot delete route regardless, so it buys nothing
in surface area while duplicating the GFS logic.

The drift risk is real and gets a named mitigation: `rdc backup retention show` reads the
policy **back from the server**, never printing the local config, so "what is actually
enforced" is always what is displayed.

### 3.3 The wiring

**New D1 table** (migration `private/account/migrations/0051_backup_retention.sql`;
`0050_backup_read_sessions.sql` is the current head, and `drizzle-kit` is the generator
per `private/account/package.json:15-16`):

```
backup_retention_policies(
  id, subscription_id → subscriptions(cascade), lineage_guid,
  keep_last, keep_hourly, keep_daily, keep_weekly, keep_monthly, keep_yearly,  -- all nullable
  updated_at )
unique index on (subscription_id, lineage_guid)
```

Keyed per lineage, not per stream: retention is a property of a lineage's history, and a
lineage has one row per machine in `backupStreams` (`db/schema.ts:1506-1526`, unique on
`(subscription, repositoryGuid, machineId)` at `:1520`). Nullable-per-knob preserves the
schema's own semantics — unset means unbounded for that bucket
(`schemas.ts:468-472`) — and an ABSENT ROW means no policy at all, which is
distinguishable from a row with every knob null.

**New route**, `private/account/src/routes/backups.ts`:
`PUT /backups/retention` and `DELETE /backups/retention?lineage=` under
`apiTokenAuth('backup:manage')`, plus `GET /backups/retention` under the existing
`backup:read`.

**New scope `backup:manage`**, added at all three sites that currently carry
`backup:read`: `packages/shared/src/subscription/types.ts:243` (the `ApiTokenScope`
union), `private/account/src/types/api-token.ts:26`, and the device-code default grant
at `private/account/src/services/device-code.service.ts:148`. A read-scoped token must
not be able to delete data; §4.2 tests exactly that.

**CLI**, `packages/cli/src/commands/backup-storage.ts` (registrar `:294`) — three verbs
alongside `usage` (`:66`) and `manifests` (`:123`), using the same
`accountServerFetch` channel those two already use (`:73`, `:144`):
`backup retention show [repo-ref]`, `set <repo-ref> --keep-last/--keep-daily/…`,
`clear <repo-ref>`. Repo→lineage resolution reuses the block at `:135-143`
(`repo.grandGuid ?? repo.repositoryGuid`).

**Automatic push** is what makes it self-managing: the `backup strategy` group
(`backup-strategy.ts:186-187`) and each `backup run` (`backup-ops.ts:391`) expand the
strategy's repos to lineages and PUT the declared policy, so the operator never issues a
retention command by hand.

**New sweep**, `backup-gc.service.ts`: `retentionPolicySweep(now, report)` called from
`runMaintenance` (`:72-96`) **after** `retentionSweep` (`:85`) and **before**
`gcSubscriptionChunks` (`:90`). The order is load-bearing: chunks freed by the sweep are
collected in the same maintenance pass rather than a day later. §4.2 pins it.

### 3.4 The algorithm, and how the three legs compose

1. For each `(subscription, lineage)` with a policy row, load its `backupManifests` rows.
2. GFS keep-set over `createdAt` (`db/schema.ts:1441`, server-stamped at commit,
   `backup-storage.service.ts:860`): `keepLast` N most recent, then the most recent in
   each of the N most recent hour/day/week/month/year buckets. **The newest manifest of
   a lineage is always kept**, whatever the policy says, including `keepLast: 0`. A
   lineage must never be emptied by a retention sweep; emptying it is what
   `deleteSubscriptionBackups` is for.
3. `doomed = all − keep`. Group into maximal consecutive runs by parent links.
4. For each run: collapse per §2, then delete.
5. `gcSubscriptionChunks` then frees whatever became unreferenced, subject to the
   existing 7-day grace (`BACKUP_CHUNK_GC_GRACE_DAYS`, `:45`).

**How leg 1 makes leg 2 rare and leg 3 cheap.** With segment roots, the common retention
shape is "drop the tail". A tail drop takes whole segments: the doomed run is
`[root, d1 … dK]` and its surviving child is the NEXT segment's root — which is a FULL
manifest with `parentSnapshotId = null` and therefore names nothing. **Zero collapses,
zero materialization, pure deletes.** The collapse path is reached only for interior
thinning (a `keepHourly` policy inside a live segment), and the expensive promotion path
only when a policy deletes a segment root while keeping its children — which
`keepLast`-shaped policies never do.

---

## 4. Tests, each with the defect it catches and where it runs in CI

The standing rule is that every test is wired into CI. All four surfaces below are
already wired; the one exception is called out in §4.4 and is a finding in its own
right.

### 4.1 Go — `private/renet/pkg/chunkstore/`

Wired: `private/renet/.ci/scripts/test/run-tests.sh:59` runs
`gotestsum … ./pkg/... ./cmd/...`, so **any new `_test.go` under `pkg/chunkstore` runs
automatically**. The `//go:build btrfs` tier is an explicit list at `run-tests.sh:173`
that already names `./pkg/chunkstore/...`. Workflow entry: `ct-tests.yml:1465` job
`test-renet`, step `:1499`, command `:1516`. (Note: `.ci/scripts/test/run-tests.sh` at
the monorepo root does **not** exist; the file is inside the renet submodule. The brief
had this path slightly wrong.)

| Test | File | Defect it catches |
|---|---|---|
| `TestBuildPlan_EmitsFullAtSegmentBoundary` | new `pipeline_segment_test.go`, `//go:build btrfs` (matching `pipeline_integration_test.go:2`) | the boundary never fires; chains stay unbounded. Planted defect: increment the depth but never compare it → the Parent sequence stays all-delta and the assertion on `[full, delta×(K-1), full]` fails |
| `TestBuildPlan_NilSegmentEmitsFull` | same | **the no-migration guarantee**. An existing journal (trusted anchor, no `segment` key) must produce a FULL. Planted defect: treat nil as depth 0 → emits a delta → the old chain keeps growing forever and the test fails |
| `TestMaterializeChain_AcceptsACollapsedChain` | `restore_test.go` (beside `:404` `TestRestore_WalksTheChainToTheFullRoot`) | the collapse output is not decodable/composable by the machine. Builds a chain the way the SERVER will leave it (root full + one merged delta) and asserts the materialized inventory equals the uncollapsed chain's. Planted defect: take only the newest map instead of the union → inventories differ |
| `TestMaterializeChain_RefusesAPromotedChildStillNamedAsDelta` | `restore_test.go` | the §2.5 crash window silently restoring wrong bytes. Asserts the failure is the NAMED refusal, not a materialization |

### 4.2 Account vitest — `private/account/tests/integration/`

Wired: `private/account/vitest.config.ts:7` includes `tests/integration/**/*.test.ts`,
so a new file is picked up with no registration. `.ci/scripts/private/run-account.sh:45`
runs `npm run test` (`private/account/package.json:12` → `vitest run`), invoked from
`.github/workflows/ci-quality.yml:1265-1267`.

New file `backup-retention.test.ts`:

| Test | Defect it catches |
|---|---|
| `collapses a linear chain so a mid-chain manifest can be deleted` | A(full)→B→C, prune B. Asserts C's row parent is now A **and** that materializing `[A, C']` equals materializing `[A,B,C]`. Planted defect: re-point the row without merging the maps → the inventories diverge |
| `collapses a whole doomed run in one write` | A→B→C→D keeping {A,D}: exactly one manifest PUT, not three |
| `refuses to merge across a shrink and promotes instead` | the §2.1 correctness hole. Planted defect: merge unconditionally → cells past the shrunken grid resolve to the base instead of ZeroCell |
| `defers promotion above BACKUP_COLLAPSE_MAX_CELLS and says so` | asserts the report carries a named `collapseDeferred` entry and the segment root survives. Planted defect: no bound → a huge materialization runs, and the assertion on the named entry fails |
| `re-parents every child of a branched manifest` | the §2.2 assumption. Planted defect: `children[0]` only → the second child's chain breaks |
| `keeps the newest manifest under keepLast: 0` | a policy that empties a lineage |
| GFS bucket table (hourly/daily/weekly/monthly/yearly) | off-by-one bucket selection; each case names its expected keep-set |
| `extractManifestHashes sees a collapsed delta` | **the exact bug fixed this session.** Feeds the TS-written collapsed manifest through `extractManifestHashes` (`backup-gc.service.ts:495`) and asserts the merged hashes land in the referenced set and the lineage is NOT in `skippedLineages`. Planted defect: write the merged map under a key named `cells` → the `Array.isArray` check at `:508` fails, the `changedCells` branch is not reached, `:536` throws, the lineage is marked unreadable and **chunk GC silently skips the whole lineage** |
| `a collapsed manifest passes the same structural rules renet enforces` | the §2.6 cross-language coupling, checked TS-side. Planted defect: emit a full manifest that keeps `parent` → Go's `Validate` (`manifest.go:96-99`) would reject it at restore; this rejects it at write |

Additions to existing files:

| Test | File | Defect |
|---|---|---|
| `PUT /backups/retention` requires `backup:manage` and rejects `backup:read` | `backup-storage.test.ts` | a read-scoped token can schedule deletions |
| retention DTO conformance | `dto-conformance.test.ts` (backup usage precedent at `:586`) | the wire shape drifts from the declared DTO |
| the policy sweep rides `runMaintenance` **before** `gcSubscriptionChunks` | `cron-wiring.test.ts` (`:141` already asserts backup GC rides the cron) | the sweep is written but never called, or is called after GC so freed chunks wait a full day |

### 4.3 packages/shared

Wired: `packages/shared/vitest.config.ts:7` (`src/**/__tests__/**/*.test.ts`), local
manifest entry `check:test-shared` at `package.json:149` and
`scripts/ci-runner/manifest.ts:112`, workflow step `ci-quality.yml:822-824`.

`src/config-schema/__tests__/` — `RetentionPolicySchema` stops being write-only, so it
gets tests: a strategy round-trips its retention; an **absent** `retention` is
distinguishable from one with every knob unset (absent = no policy pushed, all-unset =
policy present and unbounded); negative and non-integer knobs are rejected. Defect
caught: the CLI push path cannot tell "no policy" from "unbounded policy" and either
deletes nothing or clears a policy it should have left alone.

### 4.4 Drill — `scripts/drills/backup.sh`

New `leg_l_retention`, added to `LEGS` at `:95` and the dispatch at `:1377-1387`. It
reuses leg b's seed (`:736`) and leg c's incremental (`:823`) to build a REAL 3-deep
chain through real renet, then:

1. PUT a retention policy over the new route.
2. Trigger maintenance. **This needs a new seam.** The drill deliberately disables the
   maintenance timer (`BACKUP_MAINTENANCE_INTERVAL_MS=0` at `backup.sh:359`, so GC
   cannot run underneath the drill) and there is no way to trigger it on demand:
   `runMaintenance` is reachable only from `entry/node.ts:76`, `entry/on-premise.ts:219`
   and `entry/cloudflare.ts:85`, and `routes/test.ts` has backup seeding seams
   (`:956`, `:1022`, `:1041`) but no maintenance trigger. Add
   `POST /test/backup/maintenance` accepting a `now` override, so the drill can cross the
   7-day chunk grace without waiting.
3. Assert, in order: the pruned snapshot is gone from `GET /backups/manifests`; the
   surviving snapshot **restores byte-identically through real renet** (leg d already has
   the chain-fetch and compose machinery at `:913-935` and the byte assertions at
   `:989-996`); and `GET /backups/usage` `storedBytes` is **strictly lower** than before
   the sweep.

That third assertion is the cross-language conformance guard from §2.6: a manifest the
TypeScript server wrote is decoded and composed by the Go binary, and the bytes come out
right.

**Wiring finding, not asked for but in scope.** `scripts/drills/backup.sh` (1392 lines,
11 legs) **is not run by CI at all.** `ct-tests.yml:1728` job `test-drills` runs only
`./run.sh drill universe` (`:1784-1787`) and `./run.sh drill transfer` (`:1796-1803`);
grepping `backup.sh|drills/backup` over `.github/workflows`, `.ci`, `scripts` and
`package.json` returns nothing, and `.ci/scripts/ci/scope-map.cjs:200-205` documents the
two-drill list explicitly. The whole existing backup drill — session mint, quota
refusal, point-in-time restore, wire conformance — has been running only when a human
runs it. **This plan adds a `drill backup` step to `test-drills` alongside the other
two**, following the `--keep-work` + `tee` pattern at `:1785-1787`. Without that step,
leg l is not wired into CI and the standing rule is not met.

### 4.5 The CONTROL for the headline claim

The claim is "deletion became reachable", and the honest proof is bytes going down, not
a new code path executing. Two controls, one per surface:

**Control 1 (account vitest, deterministic).** In `backup-retention.test.ts`:
commit three snapshots with distinct chunks; run `gcSubscriptionChunks` and record
`backupUsage.storedBytes` — it must be UNCHANGED, proving GC has nothing to free while
manifests are immortal. Apply a `keepLast: 1` retention sweep. Run
`gcSubscriptionChunks(subId, now + 8 days)` to cross the grace. Assert:
`storedBytes` is **strictly less** than the recorded value; the kept snapshot still
materializes to a byte-identical inventory; and `pruneManifest` of the deleted ids is now
a no-op rather than a 409.

Its planted defect is the whole fix: **disable the collapse step in
`retentionPolicySweep`.** The sweep then hits `pruneManifest`'s dependents refusal
(`backup-gc.service.ts:299-311`), deletes nothing, and `storedBytes` stays equal — the
strict inequality fails. This is the test that distinguishes "a new path ran" from
"deletion became reachable"; a test asserting the 409 would have passed before the fix
and is explicitly not what is being written.

**Control 2 (drill, end-to-end).** Leg l's `GET /backups/usage` assertion, above: real
renet, real chunk store, real HTTP, bytes down, and the survivor still restores.

---

## 5. Change inventory

**renet** (leg 1 only): `pkg/chunkstore/journal.go` (+`SegmentRecord`),
`pkg/chunkstore/pipeline_linux.go:245-259` (the emit choice) and `Commit`
(`:337`, segment bookkeeping), `cmd/renet/backup_snapshot.go` (`--segment-depth`).

**account**: `migrations/0051_backup_retention.sql`; `db/schema.ts`
(+`backupRetentionPolicies`); `services/backup-gc.service.ts` (collapse in
`pruneManifest`, new `retentionPolicySweep`, orphan-manifest sweep, report fields);
`services/backup-storage.service.ts` (+`BACKUP_COLLAPSE_MAX_CELLS`,
`validateManifestShape`, retention CRUD, and the rewritten `:62-70` comment);
`routes/backups.ts` (3 endpoints); `routes/test.ts` (maintenance seam); `errors.ts`
(+`BACKUP_COLLAPSE_REFUSED`).

**shared**: `subscription/types.ts:243` (+`backup:manage`);
`config-schema/schemas.ts:474-481` doc comment corrected to describe enforcement that
now exists.

**cli**: `commands/backup-storage.ts` (`backup retention show|set|clear`),
`commands/backup-strategy.ts` + `commands/backup-ops.ts` (automatic push), i18n keys in
all 13 locales per `docs/i18n/CONVENTIONS.md`.

**ci/docs**: `ct-tests.yml` `test-drills` (+`drill backup`);
`docs/backup-storage/02-design.md:54-58` corrected from aspiration to description.

---

## 6. Deliberately left out, and the cost

- **No Go re-implementation of the merge rule.** A `ComposeDelta` in `pkg/chunkstore`
  would be an executable specification for the TS collapse, but it would be dead in
  production (only the server collapses) and would itself need proving equivalent. The
  guard instead is TS-side `validateManifestShape` (§2.6) plus the drill's live
  cross-language restore (§4.4). **Cost:** the merge rule is written twice in prose (§2.1
  and the TS implementation) and once in tests, and a divergence is caught at drill time
  rather than at Go compile time.
- **No rewrite of existing chains.** Clean break means no migration, and §1.2 shows none
  is needed. **Cost:** a pre-change chain keeps its depth until retention deletes it
  wholesale, and one already past 64 stays unrestorable until then. That is a
  pre-existing condition this change stops from worsening, not one it introduces.
- **No portal UI for retention.** `portal.ts:394` shows usage; retention is CLI-only.
  **Cost:** a browser-only operator cannot see or set the policy.
- **No per-strategy reconciliation of stale server policies.** The CLI upserts per
  lineage; removing a repo from a strategy leaves its server-side policy in place until
  `backup retention clear`. Reconciling would mean the CLI authoritatively deleting
  policies for lineages it does not currently name, which would clobber a policy set from
  another config. **Cost:** a stale policy keeps enforcing retention on a repo the
  strategy no longer covers. Deliberate — enforcing too long is safe, enforcing on data
  another universe owns is not.
- **No change to the 7-day chunk grace or to `addedBytes` accounting.** Both are billing
  and safety invariants the collapse deliberately does not touch (§2.5).

---

## 7. Blockers

None. Every anchor in this plan was opened and read on branch `backup-storage`; nothing
in the design depends on a claim I could not verify. Two facts the implementer should
carry forward because they are easy to re-derive wrongly: `pruneManifest` has **zero**
production callers (not merely an unreachable one), and `scripts/drills/backup.sh` is
**not** wired into CI today.
