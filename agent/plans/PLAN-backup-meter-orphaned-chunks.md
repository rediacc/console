# PLAN: backup usage meters every chunk the store holds: chunks a killed run uploaded and a later commit references are billed at commit, not only at the next nightly run; crash debris is billed until GC deletes it; a reconcile verb repairs and checks the ledger against the store

Status: approved -- operator 2026-10-29 "Remember we must promote all the new plans!"; triaged BIG from worklist #3b154ea0 by session d778be9d on branch 1023-1
Owner: d778be9d
Priority: P1 -- on 2026-10-29 hostinger's subscription in rediacc-backups-eu held 3162 chunks (13,262,389,248 chunk bytes) while `rdc backup usage` reported 1594 chunks (6,685,720,576 bytes). About 6.58 GB, 49.6% of the stored bytes, was invisible to quota and retention.
Owns: agent/plans/PLAN-backup-meter-orphaned-chunks.md, private/account/drizzle/0069_backup_lineage_reconcile_due.sql, private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts, private/account/src/dto/backup.dto.ts, private/account/src/services/backup-storage.service.ts, private/account/src/services/backup-gc.service.ts, private/account/src/routes/backups.ts, private/account/src/errors.ts, private/account/tests/integration/backup-meter-orphaned-chunks.test.ts, private/account/tests/integration/backup-gc.test.ts, private/account/tests/integration/backup-verify-reconcile.test.ts, private/account (gitlink bump only), private/renet/pkg/chunkstore/uploader.go, private/renet/pkg/chunkstore/session.go, private/renet/pkg/chunkstore/journal.go, private/renet/pkg/chunkstore/uploader_test.go, private/renet/pkg/chunkstore/session_test.go, private/renet/pkg/chunkstore/journal_test.go, private/renet (gitlink bump only), packages/cli/src/commands/backup-reconcile.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/__tests__/backup-reconcile.test.ts, packages/cli/src/i18n/locales/*/cli.json, packages/shared/src/cli-contract/**, packages/www/src/content/docs/*/cli-application.md
Concurrency: parallel -- A1 (account), R1 (renet) and C1 (CLI) have disjoint Owns and run at the same time. C1 codes against the wire shape fixed in Design D5, and its live smoke waits for A1. The locale files in C1 wait for the leases held by PLAN-backup-restore-path.md and PLAN-detached-jobs.md, which both own packages/cli/src/i18n/locales/*/cli.json. PLAN-detached-jobs.md owns packages/cli/src/commands/backup-storage.ts only for the snapshot action, so C1 edits a different function there (one registration line). L0 runs before any merge and only reads. L1 (bench) follows the merge and the edge deploy. L2 (hostinger) follows the stable eu deploy of A1.
Depends-On: no-dep -- the code boxes need nothing outside this plan; L1 needs A1 on bench and R1 on a bench machine, L2 needs A1 on stable eu
Live-Proof: bench, hostinger -- bench is where the account surface is proven live, and L1 replays the killed-run sequence there. hostinger holds the measured drift, and L2 repairs it and checks the ledger against an independent R2 listing.
Updated: 2026-10-29
First-Seen: 2026-10-29
Worklist: #3b154ea0, PR-TASK 9f92c43e

## Finding (measured 2026-10-29 on hostinger against R2 bucket rediacc-backups-eu)

- `backup snapshot mautic` was killed at 600 s by renet's then-default execute timeout (fixed in d6ea91581, "data-moving backup verbs carry a renet --timeout above the 10-minute default"). By then it had uploaded about 1568 chunks (about 6.58 GB) and committed no manifest.
- The retry committed snapshot 20261029T090224Z (mautic retry). It uploaded 45 new chunks (188,743,680 bytes = 45 x 4 MiB) and found the rest already present.
- Afterwards:
  - `rdc backup usage` reads 6,685,720,576 bytes and 1594 chunks;
  - an R2 listing shows 3162 chunks plus 5 manifests, 13,262,668,835 bytes in total;
  - mautic's lineage shows 188,743,680 bytes and 45 chunks.
- Arithmetic check: every chunk is a full 4,194,304-byte cell.
  - 1594 x 4,194,304 = 6,685,720,576, exactly the ledger.
  - 3162 x 4,194,304 = 13,262,389,248. The remaining 279,587 bytes of the listing total are the 5 manifests, which the ledger never counts.
  - 3162 - 1594 = 1568 chunks = 6,576,668,672 bytes, exactly the killed run's uploads.
  - mautic physically holds 1568 + 45 = 1613 chunks (6,765,412,352 bytes). Its ledger row holds 45.
- Hypothesis "usage counts only chunks the committing run uploaded itself": CONFIRMED (see Root cause).

## Where usage is computed (verified 2026-10-29)

### renet (the client figure)
- The exists check: private/renet/pkg/chunkstore/uploader.go:186 (`existsBatched`, batches at :416-430) returns the hashes the store does NOT hold. Every hash the store holds is skipped, whoever uploaded it.
- The candidate set is all non-zero hashes on a fresh run (:174). The journal's pending set is used only when resuming the SAME snapshot id (:175-182). The retry minted a new snapshot id, so it did a fresh run and found the killed run's chunks present.
- The metered figure: private/renet/pkg/chunkstore/uploader.go:249-252 calls `RecordUploadMetrics(stats.BytesUploaded, stats.ChunksUploaded)`. That counts only this run's PUTs (`BytesUploaded += size` at :593).
- The commit body: private/renet/pkg/chunkstore/session.go:301-304 (fields) and :527-537 (`addedBytes`, `addedChunkCount` in the payload). Setter at :656-659.
- The journal: private/renet/pkg/chunkstore/journal.go:56-65 (`UploadProgress{SnapshotID, PendingHashes, ManifestCommitted}`). The killed run's journal still names its snapshot with `ManifestCommitted=false`, because private/renet/pkg/chunkstore/uploader.go:207-213 saves it before any upload.
- Lineage = the licence's grand GUID (private/renet/cmd/renet/backup_snapshot.go:509-516), so forks of one repository share one lineage.

### account (the ledger and quota)
- Exists answer: private/account/src/services/backup-storage.service.ts:960-1007 HEADs each chunk key and pins the found ones for 24 h (`BACKUP_EXISTS_PIN_HOURS`, :61). It cannot tell "referenced by a committed manifest and billed" from "debris of a killed run".
- Grant and lease: :606-762. The quota check at :659-691 uses `computeUsed` (:577-601), which adds live leases of OTHER snapshots. The lease upsert is at :693-716, with TTL 2 h (`BACKUP_LEASE_TTL_MS`, :59).
- Manifest commit: :1011-1288. The ledger moves by the client's numbers: `backup_usage` += addedBytes/addedChunkCount (:1220-1235) and `backup_lineage_usage` += the same (:1236-1258), in one atomic batch with the lease release (:1204-1260). :1128-1134 already names the gap: "a caller can still UNDER-report ... Closing it properly means the server deriving billed bytes from the chunks it can observe".
- Usage read: `getUsage` :1366-1398 returns the two ledger rows. Route `GET /backups/usage` is at private/account/src/routes/backups.ts:218. The CLI reader is packages/cli/src/commands/backup-storage.ts:76-130.
- Key layout: private/account/src/services/backup-chunk-store.ts:47-52. A chunk is `t/<sub>/l/<lineage>/c/<hash>`, so dedup is scoped to one lineage. No chunk is shared across lineages, and forks share by sharing the grand-GUID lineage.

### account (prune, GC and the existing self-heal)
- The nightly cron runs at 03:00 UTC (workers/account/wrangler.eu.toml:21, and likewise for every region) and calls `runMaintenance` (private/account/src/entry/cloudflare.ts:193-212).
- Phase order: private/account/src/services/backup-gc.service.ts:152-160. Budgets: 5 min, 800 store calls per run and 300 per subscription (:122-135).
- Chunk GC: `gcSubscriptionChunks` :1037-1226.
  - The referenced set comes from every D1-indexed manifest of the lineage, read from the bucket. A lineage with an unreadable manifest is skipped with no deletes (:1104-1129).
  - A chunk is deleted only when it is unreferenced, unpinned, its lineage holds no live lease (:1099-1102), and it is older than `BACKUP_CHUNK_GC_GRACE_DAYS = 7` (:65, :1163-1166).
- The existing physical re-bill (plan S5): :1195-1215 sets the lineage ledger to what the listing observed, through `reconcileLineageLedger` (:1246-1307, a compare-and-swap on the row's updatedAt, with the subscription total moved by the delta). It is skipped when no lineage row exists (`if (row && stamp !== null)`, :1202).
- The tenant scrub: `reconcileLedger` :334-385 and `reconcileOne` :870-910 only log `backup_ledger_drift` (:906-909) and repair nothing. It is reachable on demand at `POST /backups/verify` with no level (private/account/src/routes/backups.ts:394-412). The CLI does not expose it.
- Lease, pin and session sweep: `sweepExpired` :1017-1033. It deletes expired leases and records nothing.

## Root cause

1. renet meters only its own PUTs (private/renet/pkg/chunkstore/uploader.go:249-252, sent at private/renet/pkg/chunkstore/session.go:533-536). The account adds that figure to the ledger as given (private/account/src/services/backup-storage.service.ts:1220-1258). A chunk a killed run uploaded is found by the retry's exists check (private/renet/pkg/chunkstore/uploader.go:186; private/account/src/services/backup-storage.service.ts:960-1006), so no run reports it, although the retry's committed manifest references it.
2. The only correction is the nightly chunk-GC re-bill (private/account/src/services/backup-gc.service.ts:1195-1215). Until it runs, the ledger can be wrong for up to 24 h. The killed run's 2 h lease also inflates `computeUsed` (private/account/src/services/backup-storage.service.ts:577-601) for the retry's own quota check.
3. A lineage whose only activity is a killed run has no `backup_lineage_usage` row, so the re-bill skips it (:1202). Its debris is never billed and is deleted after 7 days. Repeating that crash keeps up to 7 days of chunks free of quota.
4. The tenant scrub sees the drift and only logs it (:906-909).

Prediction: tonight's 03:00 UTC run should re-bill mautic by itself. Its lineage row exists since the commit, and the killed run's lease expired about 2 h after it was minted. L0 records the state before that run, so the outcome is evidence either way.

## Design

### D1. Where the truth lives: the store, per lineage, physically
The ledger equals the chunk objects the store holds under each lineage prefix, referenced or not. That is the S5 rule already written at private/account/src/services/backup-gc.service.ts:1195-1201 and :1239-1243. A chunk occupies storage until GC deletes it, so it is billed until then. Three options were weighed:

| Option | Store cost | Correct for | Rejected because |
|---|---|---|---|
| Recount at every commit (list the lineage prefix inside `commitManifest`) | ceil(chunks/1000) Class A LIST per commit. A 1 TiB lineage at 4 MiB cells is 262,144 chunks = 263 LISTs per commit = about 189k per month hourly, about $0.85 per lineage-month at $4.50/M. Up to 263 serial subrequests and tens of seconds inside one commit request. | everything | Cost and latency scale with lineage size on every commit, including the common unchanged-repository run. |
| Attribute at commit (diff the new manifest's referenced set against every other committed manifest of the lineage) | No Class A. One Class B GET per lineage manifest per commit, plus a parse of each manifest (up to `BACKUP_MANIFEST_MAX_BYTES`) in Worker CPU. | referenced chunks | Misses unreferenced debris (Root cause 3). CPU grows with the retention depth. |
| Reconcile on evidence, plus nightly, plus an on-demand verb (CHOSEN) | Class A LISTs only after an abandoned run (a superseded or expired lease), capped per commit. The nightly chunk-GC phase already lists every lineage each night, so no new standing cost. | everything | -- |

R2 pricing used here: Class A (LIST, PUT) $4.50/M with 1M free per month; Class B (HEAD, GET) $0.36/M with 10M free.

### D2. Evidence of an abandoned run: `reconcile_due_at`
- New nullable column `backup_lineage_usage.reconcile_due_at` (migration 0069). Like the orphan and verify columns (private/account/src/db/schema.ts:1502-1520), setting or clearing it never moves `updatedAt`, which chunk GC uses as its compare-and-swap stamp.
- It is set when:
  - (a) a grant names `supersedesSnapshotId` (D3);
  - (b) `sweepExpired` is about to delete an expired lease, because an expired lease is a run that never committed;
  - (c) a commit lands on a lineage that had no ledger row before it.
- When no row exists, the setter inserts one with zero bytes, so debris-only lineages become visible to the re-bill (Root cause 3).
- It is cleared by any applied lineage reconcile: inline, nightly or on demand.

### D3. renet names the run it replaces: `supersedesSnapshotId`
- At the start of `Upload`, when `opts.Journal.Upload` names a different snapshot id with `ManifestCommitted == false`, that snapshot was the machine's earlier run and is dead. renet sends it as `supersedesSnapshotId` on every grant request of the new run.
- The account then:
  - deletes that lease when it is in the same subscription and lineage, that snapshot has no manifest row, and the lease was minted by the same machine as the new grant: `backup_upload_leases` gains a `machine_id` column in migration 0069, written from `principal.machineId` (the storage session principal, private/account/src/services/backup-storage.service.ts:128) when the lease is upserted, and compared with the new grant's `principal.machineId`; a lease from another machine, or a pre-0069 lease with no `machine_id`, is left to expire, which releases its quota hold from `computeUsed`;
  - sets `reconcile_due_at`.
- A superseded id that names another lineage, or a committed snapshot, is ignored and logged, not refused, so a stale journal never blocks a backup.
- Safety rests on one renet run per repository per machine. R1 verifies that an exclusion exists for the whole snapshot and adds a flock on the journal file if none does.
- The DTOs are non-strict `z.object`s (private/account/src/dto/backup.dto.ts:126-138), so an older account ignores the field and an older renet simply omits it.

### D4. Inline reconcile at commit
- After the commit batch, when the lineage row has `reconcile_due_at` set and the lineage holds no other live lease, the server lists the lineage chunk prefix and applies `reconcileLineageLedger`.
- The listing is capped at `BACKUP_COMMIT_RECONCILE_MAX_PAGES = 20` (20,000 chunks, about 78 GiB at 4 MiB cells).
- Over the cap, or with another live lease, the flag stays set and the nightly phase does it.
- The other-lease gate exists because in-flight chunks of a concurrent run would be billed now and again at that run's commit. This is the same reason GC skips leased lineages (:1097-1102).
- The commit response gains an optional `reconciled: boolean`.
- For the measured case:
  - with R1, the retry's grant superseded the killed lease, so the retry's commit re-bills mautic to 1613 chunks at once;
  - without R1, trigger (c) fires, but the killed lease is still live, so the bill waits for the nightly run.

### D5. Reconcile verb: `POST /backups/reconcile` and `rdc backup reconcile`
Request body:
```json
{ "lineageGuid": "<guid, optional>", "dryRun": false }
```

Response body:
```json
{ "subscriptionId": "...",
  "lineages": [ { "lineageGuid": "...", "ledgerBytesBefore": 0, "ledgerChunksBefore": 0,
                  "observedBytes": 0, "observedChunks": 0,
                  "referencedBytes": 0, "referencedChunks": 0,
                  "unreferencedBytes": 0, "unreferencedChunks": 0, "unreferencedPastGraceChunks": 0,
                  "applied": false, "skipped": null } ],
  "ledgerBytes": 0, "ledgerChunkCount": 0, "bucketChunkBytes": 0, "bucketChunkCount": 0, "driftBytes": 0 }
```

- `skipped` is `"leased"` when a live lease exists and `"unreadable"` when a manifest cannot be read. Either way nothing is applied.
- Per lineage the server lists the chunk prefix, builds the referenced set with `extractManifestHashes` over the lineage's manifests, and applies `reconcileLineageLedger` unless `dryRun` is set.
- After the per-lineage pass, when the subscription holds no live lease, `backup_usage.stored_bytes` and `chunk_count` are set to SUM over the lineage rows in one SQL statement. This repairs aggregate drift that no lineage row explains.
- It never deletes.
- Authority:
  - `dryRun:true` needs `backup:read`;
  - applying needs `backup:manage` plus `requireManagerCreator`;
  - both are limited by `tokenLineageScope`.
- The listing runs through `MeteredBackupStore` with a 900-call budget. Over budget the answer is 409 `BACKUP_RECONCILE_TOO_LARGE`, which names the nightly run.
- CLI: `rdc backup reconcile [repo-ref] [--dry-run] [--check]`. `--check` is a dry run that exits 1 when any lineage's observed figures differ from its ledger, or when `driftBytes != 0`.

### D6. Orphan policy (unreferenced chunks)
Most of this exists already, and A1 pins it with tests:
- Grace: an unreferenced chunk is deleted only past `BACKUP_CHUNK_GC_GRACE_DAYS = 7`, counted from `uploadedAt`, or from the release pin for chunks a prune orphans.
- It is also deleted only when unpinned and when its lineage holds no live lease.
- Never delete a referenced chunk:
  - the referenced set is the union over every committed manifest of the lineage;
  - an unreadable manifest skips the whole lineage;
  - there is no cross-lineage reference by key layout;
  - forks share the grand-GUID lineage and therefore its referenced set.
- New: debris is billed during the grace (D2), and the re-bill clears the flag. The verb reports `unreferencedPastGraceChunks` so an operator can see what the next GC deletes.

## Boxes

- [x] A1 [writer, account] Server-side metering of every stored chunk.
  Changes:
  - Migration private/account/drizzle/0069_backup_lineage_reconcile_due.sql (+ drizzle/meta/_journal.json) adding `backup_lineage_usage.reconcile_due_at` and `backup_upload_leases.machine_id` (one migration file carries both ALTERs; the name mentions only the first), and both columns in src/db/schema.ts (backupLineageUsage and backupUploadLeases only).
  - backup.dto.ts:
    - `supersedesSnapshotId: snapshotIdSchema.optional()` on `backupGrantRequest`;
    - `reconciled` optional on `backupCommitResponse`;
    - `backupReconcileRequest` and `backupReconcileResponse` per D5.
  - backup-storage.service.ts:
    - mintGrant handles supersede (D3);
    - commitManifest triggers (c) and D4;
    - new `reconcile(subscriptionId, scope, {lineageGuid, dryRun})`.
  - backup-gc.service.ts:
    - extract `listLineageChunks` and a listing-only reconcile from `gcSubscriptionChunks` (deletion logic unchanged);
    - create the lineage row when absent instead of skipping (:1202);
    - clear `reconcile_due_at` on an applied swap;
    - `sweepExpired` sets `reconcile_due_at` for each expired lease's lineage before deleting it.
  - routes/backups.ts: `POST /reconcile`.
  - src/errors.ts: `BACKUP_RECONCILE_TOO_LARGE`.
    (ticked) 2026-10-29T10:03:59Z by d778be9d: commit:c7106b415

  Tests (new tests/integration/backup-meter-orphaned-chunks.test.ts, in-memory store and SQLite). Each test except the last fails on the current tree:
  - T1 killed then retried, with supersede:
    - plant 8 chunk objects under lineage L as snapshot S1's uploads and mint S1's grant;
    - a second session mints S2's grant with `supersedesSnapshotId=S1`;
    - exists reports the 8, S2 uploads 1, and the commit sends `addedBytes` = 1 chunk.
    - Expect `getUsage` chunkCount 9 and bytes equal to the sum of the 9 objects, S1's lease row gone, and `reconciled:true`. Today it reads 1.
  - T2 no supersede, killed lease expired: same plant, clock past S1's lease expiry, no supersede field. The commit reconciles through trigger (c) and the expected figure is 9. Today it reads 1.
  - T3 concurrent live lease from another run: the commit does not reconcile (ledger = addedBytes, `reconcile_due_at` set). After that run commits and `runMaintenance` runs, the ledger equals the listing exactly once, with no double count. Today it fails on the column.
  - T4 debris-only lineage (grant minted, chunks planted, never committed):
    - after the lease expires, `runMaintenance` creates the row and bills the debris. Today it is unbilled;
    - at now + 8 days, `runMaintenance` deletes it and the row reads 0.
  - T5 reconcile route:
    - `dryRun` reports observed 9 against ledger 1 with no write;
    - apply sets the ledger to 9 and the aggregate to the sum of the lineage rows;
    - a live lease gives `skipped:"leased"`;
    - a `backup:read` token cannot apply;
    - another team's lineage gives 404, as every scoped route answers (requireLineageInScope in private/account/src/routes/backups.ts).
    - Today every call is 404.
  - T6 guard, which passes today and pins D6 across the extraction: a chunk referenced by a committed manifest, uploaded by a superseded run and older than the grace, is never deleted.

  Owns: private/account/drizzle/0069_backup_lineage_reconcile_due.sql (new), private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts (backupLineageUsage only), private/account/src/dto/backup.dto.ts, private/account/src/services/backup-storage.service.ts, private/account/src/services/backup-gc.service.ts, private/account/src/routes/backups.ts, private/account/src/errors.ts (one code), private/account/tests/integration/backup-meter-orphaned-chunks.test.ts (new), private/account/tests/integration/backup-gc.test.ts and backup-verify-reconcile.test.ts (only where an expectation changes), private/account (gitlink bump only).
  Accept: `cd private/account && npx vitest run tests/integration/backup-meter-orphaned-chunks.test.ts tests/integration/backup-gc.test.ts tests/integration/backup-storage.test.ts tests/integration/backup-verify-reconcile.test.ts tests/integration/backup-maintenance-isolation.test.ts` rc 0, `npm run typecheck` rc 0 and `npm run lint` rc 0. With the service changes reverted and the test kept, `npx vitest run tests/integration/backup-meter-orphaned-chunks.test.ts` rc 1.

- [x] R1 [writer, renet] renet names the run it supersedes.
  Changes:
  - uploader.go: before :207 overwrites `opts.Journal.Upload`, capture the prior snapshot id when it differs and is uncommitted. Hand it to the plane through a new optional `SupersedeRecorder` interface, following the `UploadMetricsRecorder` pattern at :55-61.
  - session.go: `MintGrant` (:359) adds `"supersedesSnapshotId"` when set and omits it when empty.
  - Verify that one snapshot per repository per machine is excluded for the whole run. If nothing enforces it, take an exclusive flock beside the journal in journal.go and refuse a second run with a named error.
    (ticked) 2026-10-29T10:23:31Z by d778be9d: commit:8bb2a14cc

  Tests (uploader_test.go, session_test.go, journal_test.go), each failing on the current tree:
  - a journal holding `Upload{SnapshotID:"old", ManifestCommitted:false}` plus a new manifest records `old` on a fake plane;
  - controls: the same snapshot id (resume) records nothing, and a committed `old` records nothing;
  - the grant payload carries the field when set and omits it when empty;
  - the second concurrent journal lock is refused, if the flock is added.

  Owns: private/renet/pkg/chunkstore/uploader.go, private/renet/pkg/chunkstore/session.go, private/renet/pkg/chunkstore/journal.go (the lock only, if needed), private/renet/pkg/chunkstore/uploader_test.go, private/renet/pkg/chunkstore/session_test.go, private/renet/pkg/chunkstore/journal_test.go, private/renet (gitlink bump only).
  Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'Supersede|JournalLock' -count=1` rc 0, `go test ./pkg/chunkstore/ ./cmd/renet/ -count=1` rc 0 and `go vet ./pkg/chunkstore/` rc 0. With the uploader change reverted, the Supersede test rc 1.

- [x] C1 [writer, CLI] `rdc backup reconcile`.
  Changes:
  - New packages/cli/src/commands/backup-reconcile.ts implementing D5. The repo-ref resolves through `resolveLineage`. Table output shows ledger, observed, referenced and unreferenced per lineage; `-o json` prints the response.
  - One registration line in `registerBackupStorageCommands` (packages/cli/src/commands/backup-storage.ts:531-539).
  - i18n keys under `commands.backup.reconcile.*` in every locale, under the leases named in Concurrency.
  - Regenerate the CLI contract and docs data.
    (ticked) 2026-10-29T10:23:34Z by d778be9d: commit:8bb2a14cc

  Tests (new packages/cli/src/commands/__tests__/backup-reconcile.test.ts, mocking `accountServerFetch`), each failing today because the command does not exist:
  - the POST body carries the resolved lineage and `dryRun`;
  - `--check` sets exit 1 on a drifting fixture and 0 on a clean one;
  - `--check` and `--dry-run` never send `dryRun:false`.

  Owns: packages/cli/src/commands/backup-reconcile.ts (new), packages/cli/src/commands/backup-storage.ts (the registerBackupStorageCommands line only), packages/cli/src/commands/__tests__/backup-reconcile.test.ts (new), packages/cli/src/i18n/locales/*/cli.json (reconcile keys only, under lease), packages/shared/src/cli-contract/** and packages/www/src/content/docs/*/cli-application.md (regenerated only).
  Accept: `npm run test:unit -w @rediacc/cli -- backup-reconcile` rc 0, `npm run typecheck -w @rediacc/cli` rc 0, `npm run check:ci-cli-contract` rc 0 and `npm run check:i18n` rc 0.

- [ ] L0 [live, read-only, now] Capture hostinger's state before any nightly run or deploy.
  1. `./rdc.sh --config eu-remote backup usage -o json` records storedBytes, chunkCount and the mautic lineage row.
  2. An independent R2 listing of `t/<subscriptionId>/` in rediacc-backups-eu, under the bws profile that binds the R2 pair (no value printed). Record the count and byte sum of `/c/` keys per lineage, and the `/m/` count.
  3. `./rdc.sh --config eu-remote backup manifests mautic -o json` records the committed snapshot ids.
  4. After 03:00 UTC on 2026-10-30, repeat 1 and record whether `backup_ledger_reconciled` fired for mautic. This confirms or refutes the self-heal prediction.

  Owns: agent/plans/PLAN-backup-meter-orphaned-chunks.md (receipts only).
  Accept: step 1 and step 3 rc 0, the listing command rc 0, and the receipts recorded in this box.
    (live record 2026-10-29, 9f92c43e) L0 steps 1-3 captured, read-only (step 4 waits for 03:00 UTC 2026-10-30). Usage at 2026-10-29T10:07:41Z (subscription 63284afd): storedBytes 6,685,720,576, chunkCount 1594, leasedBytes 6,668,943,360, activeLeases 1, usedBytes 13,354,663,936, quota 536,870,912,000. Lineage rows: 03ee0999 (mautic) storedBytes 188,743,680, chunkCount 45, logicalBytes 8,589,934,592, updatedAt 2026-10-29T09:03:47.616Z; 1b8e6a28 storedBytes 2,147,483,648, 512 chunks; 24effd58 storedBytes 4,349,493,248, 1037 chunks. Independent R2 listing at 2026-10-29T10:15:47Z (SigV4 ListObjectsV2, prefix t/63284afd-.../, bucket rediacc-backups-eu, profile backup-push-stable): 3167 objects, 3162 `/c/` keys (13,262,389,248 bytes) and 5 `/m/`. Per lineage: 03ee0999 (mautic) 1613 chunks, 6,765,412,352 bytes (metered 45 and 188,743,680, so 1568 chunks and 6,576,668,672 bytes are unmetered); 1b8e6a28 512 chunks, 2,147,483,648 bytes (matches the meter); 24effd58 1037 chunks, 4,349,493,248 bytes (matches the meter). Meter total 1594 chunks against 3162 listed. `backup manifests mautic`: one committed snapshot, 20261029T090224Z-ee7d3f5a8b53d30d (stream a6c92d8d, no parent, addedChunkCount 45, addedBytes 188,743,680, createdAt 2026-10-29T09:03:47.616Z). Commands: `backup usage -o json` rc=0; `backup manifests mautic -o json` rc=0 (both via bws_env exec --profile deploy-proxy, ./rdc.sh --config eu-remote); R2 listing via bws_env exec --profile backup-push-stable, a throwaway SigV4 script outside the repo, rc=0 (a first attempt looped forever on a script bug of mine and was killed, nothing written).

- [ ] L1 [live, bench, after merge and edge deploy] Replay the killed-run sequence.
  - On a bench machine running R1's renet, start `backup snapshot <repo> --bwlimit <low>` and kill it after at least 50 chunks have uploaded.
  - Rerun `backup snapshot <repo>`.
  - Immediately after the commit, before any nightly run, the bench `backup usage -o json` must show the lineage chunkCount equal to that lineage's `/c/` listing count, and `backup reconcile <repo> --check` must exit 0.

  Owns: agent/plans/PLAN-backup-meter-orphaned-chunks.md (receipts only).
  Accept: `./rdc.sh --config eu-bench backup reconcile <repo> --check` rc 0, and the recorded usage and listing counts are equal.

- [ ] L2 [live, hostinger, after A1 reaches stable eu] Repair, then check.
  1. `./rdc.sh --config eu-remote backup reconcile --dry-run -o json` records the before figures.
  2. With the operator's go, `./rdc.sh --config eu-remote backup reconcile -o json` applies.
  3. `./rdc.sh --config eu-remote backup usage -o json`: storedBytes must equal the sum of `/c/` object sizes and chunkCount the count of `/c/` keys in a fresh independent R2 listing of the subscription prefix. The figures expected at the time of writing were 13,262,389,248 and 3162; the seed has since grown the store (2026-10-29: R2 106,940,214,348 bytes in 25,496 chunks against a ledger of 17,321 chunks), so the check is equality with a fresh listing, not those numbers; manifests are not counted.
  4. Over the manifest set: per lineage the reconcile output's referenced and unreferenced chunk counts sum to the listing count. `unreferencedChunks` need not be 0: unreferenced debris stays billed until GC deletes it after the 7-day grace (the Orphans ruling below), and `unreferencedPastGraceChunks` names what the next GC deletes.
  5. The rerun class is covered: nextcloud's first seed attempt failed at commit after uploading about 6607 chunks, and its rerun committed after uploading only 50 (snapshot 20261029T154848Z-4960a85b93ae46e0), so its lineage read about 0.2 GB for a 22.6 GB repo. After the repair, nextcloud's lineage bytes equal the referenced chunk bytes of its manifest.

  Owns: agent/plans/PLAN-backup-meter-orphaned-chunks.md (receipts only).
  Accept: `./rdc.sh --config eu-remote backup reconcile --check` rc 0, the usage and listing figures recorded as equal in this box, and step 5's nextcloud lineage bytes recorded as equal to the referenced chunk bytes of its manifest.

## Operator rulings, second round (2026-10-29)

- Hostinger repair (ASKED 2026-10-29, "Let nightly run, then verify (Recommended)"): L0 captures the before state now, the 03:00 UTC maintenance run is allowed to re-bill, and L2 still runs `backup reconcile --check` after A1 reaches stable EU.
- Orphans (ASKED 2026-10-29, "Bill them (Recommended)"): usage counts every chunk the store holds, referenced or not, until GC deletes it after the 7-day grace.
