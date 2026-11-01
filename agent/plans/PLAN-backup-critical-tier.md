# PLAN: backup critical tier: minutes-level protection through frequent cloud uploads, with a declared target, a pre-backup hook, adjustable cells, delayed destruction, waiting chunks outside the quota, and maintenance that survives 288 runs a day

Status: approved -- operator rulings R1 to R4, 2026-11-01: a product capability for critical systems for any customer; everything lands in the open PR rediacc/console#602, branch 1023-1; no customers yet, so a clean break with no compatibility shims
Owner: 45048a90
Priority: P1 -- a repository cannot be protected at a minutes-level target today: nothing declares the target, a hung run never counts as a miss, the per-run exists check costs a whole manifest, and the daily sweep cannot keep up with 288 runs a day
Depends-On: PLAN-backup-integrity.md -- this plan builds on its verification state, alerts, `backup_stream_status`, reports route, refset and repair; the box-level order is in "Sequencing against the sibling plan"
Concurrency: parallel -- eight writers (M, Q, U, W, E, N, T, X) with disjoint Owns inside this plan; each starts only after the named sibling boxes land, since 26 files are shared with the sibling plan; wire shapes are fixed in D-wire so writers do not wait on each other to compile
Owns: agent/plans/PLAN-backup-critical-tier.md, private/account/drizzle/0074_backup_critical_tier.sql, private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts, private/account/src/dto/backup.dto.ts, private/account/src/errors.ts, private/account/src/routes/backups.ts, private/account/src/services/backup-storage.service.ts, private/account/src/services/backup-gc.service.ts, private/account/src/services/backup-refset.ts, private/account/src/services/notification.service.ts, private/account/src/email/templates/security.ts, private/account/src/entry/cloudflare.ts, private/account/src/entry/on-premise.ts, private/account/src/entry/node.ts, private/account/src/types/env.ts, private/account/wrangler.toml, workers/account/wrangler.eu.toml, workers/account/wrangler.us.toml, workers/account/wrangler.asia.toml, workers/account/wrangler.edge-eu.toml, workers/account/wrangler.edge-us.toml, workers/account/wrangler.edge-asia.toml, workers/account/wrangler.bench.toml, private/account/web/src/api/types.ts, private/account/web/src/pages/BackupStorage.tsx, private/account/web/src/data/study-content/mt6-backup.ts, private/account/tests/integration/backup-*.test.ts, private/renet/pkg/chunkstore/**, private/renet/pkg/backuphook/**, private/renet/pkg/orchestration/rediaccfile.go, private/renet/pkg/orchestration/rediaccfile_cleanenv_test.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_*_test.go, private/renet/pkg/backupstate/**, private/renet/pkg/list/**, private/renet/pkg/i18n/**, private/renet/cmd/renet/backup_snapshot*.go, private/renet/cmd/renet/backup_churn_*.go, private/renet/cmd/renet/backup_hook*.go, packages/cli/src/commands/backup-*.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/status.ts, packages/cli/src/commands/__tests__/backup-*.test.ts, packages/cli/src/commands/machine/__tests__/health-rpo.test.ts, packages/cli/src/services/backup/**, packages/cli/src/services/executor/repo-license-context.ts, packages/cli/src/services/__tests__/backup-*.test.ts, packages/cli/src/config/command-metadata.ts, packages/cli/src/config/command-planes.ts, packages/cli/src/config/__tests__/plane-coverage.test.ts, packages/cli/src/i18n/locales/**, packages/shared/src/backup/**, packages/shared/src/subscription/constants.ts, packages/shared/src/subscription/__tests__/schema.test.ts, packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/config-schema/__tests__/retention-policy.test.ts, packages/shared/src/renet-contract/data/**, packages/shared/src/cli-contract/**, packages/www/src/content/docs/*/backup-restore.md, packages/www/src/content/docs/*/cli-application.md, docs/backup-storage/07-execution-record.md, .ci/rediacc_ci/drills/backup.py, .ci/rediacc_ci/drills/backup_renet.py, .ci/rediacc_ci/drills/backup_roundtrip.py, .ci/rediacc_ci/drills/backup_onprem.py, private/account (gitlink), private/renet (gitlink)
Live-Proof: bench, hostinger -- vm:check and both drills before the merge; bench proves the account surface after the edge deploy; hostinger proves the released renet on `mail` in steps of 30, 15 and 5 minutes, after the sibling plan's H1 to H3
Updated: 2026-11-01
Worklist: #b21c2384
First-Seen: 2026-11-01

## Scope as ruled

- **In scope (R1):** frequent cloud uploads of changed cells. A local-only tier is not in scope.
- **Included (R2):** a pre-backup hook, immutable history, adjustable cell size.
- **Not chosen (R2):** a second destination. This plan does not build one, and D-immutable states what that leaves undefended.
- **Quota (R3):** chunks waiting for deletion are not charged. Quota counts only what kept versions can restore. Rediacc absorbs the waiting storage, under a safeguard (decision O2). The 7-day grace stays.
- **Required regardless (R4):** batched prune, changed-only exists checks, missed-target alerting.
- **Plan gating:** none is added unless the operator asks. Per-plan defaults are decision O3.

## Findings as verified, with corrections

Each finding was checked against the code on 2026-11-01. F1 to F14 are the brief's numbering. F15 onward were found while checking them. Anything still unproven is under Hypotheses.

- F1. Confirmed. `resolveOverrides` (packages/cli/src/services/backup/backup-schedule-targets.ts:193) resolves `repoSchedules` keys through the same `resolveRef`, so the fork-widening of a bare name applies to a per-repo target as well as to `--include`.
- F2. Confirmed. systemd also drops a timer tick while the oneshot is active, so a hung run stops all later ticks with no record.
- F3. Confirmed. Segment room is `Depth+1 < maxDepth` (private/renet/pkg/chunkstore/journal.go:114), so a 5-minute repo re-roots about every 160 minutes.
- F4. Confirmed (private/renet/pkg/chunkstore/uploader.go:215). Each answered hash writes into a pin row (private/account/src/services/backup-storage.service.ts:1346). See F15 for the path that relies on the whole-manifest ask.
- F5. Confirmed by reading; X1 proves it with a metered store. `composeSurvivor` and `collectReleasePins` each read the same doomed manifests, so a doomed manifest costs two GETs. A budget stop throws before any write, so the visit re-enters the same phase with nothing gained. The deployed cron is `0 3 * * *` in all seven configs under workers/account/, not only private/account/wrangler.toml, which its own header calls local.
- F6. Confirmed. `computeUsed` sums every unexpired lease (private/account/src/services/backup-storage.service.ts:803-810).
- F7. Confirmed. Plan quotas are FREE 0, COMMUNITY 10 GiB, PROFESSIONAL 100 GiB, BUSINESS 500 GiB, ENTERPRISE 2 TiB (packages/shared/src/subscription/constants.ts:38-58). `overQuotaOne` (private/account/src/services/backup-gc.service.ts:3386) computes `used` separately and must move with the grant path.
- F8. Corrected.
  - `renet backup churn-cells` does not exist. `Use:` in private/renet/cmd/renet/backup_churn_probe.go:64 is `churn-probe`, a hidden verb. `backup_churn_cells.go` holds only projection math, and private/renet/pkg/chunkstore/grid.go:27 carries the stale name.
  - The probe is not strictly read-only. It keeps a reflink base under `<datastore>/.churn-probe`, which pins extents until it rotates. J1 handles that base explicitly.
  - It projects 1, 2, 4 and 8 MiB.
  - `--cell-bytes` exists only on the renet verb (private/renet/cmd/renet/backup_snapshot.go:160). No function parameter, schema field or CLI option carries it. See F19.
- F9. Confirmed. `ExecuteFunction` returns `ErrFunctionNotDefined` through exit 42 (private/renet/pkg/orchestration/rediaccfile.go:216-223). See F20.
- F10. Confirmed: the machine's chunk PUT is create-only (private/account/src/services/backup-chunk-store.ts:775). A search of private/account/src/routes finds no admin route that deletes backups, and `deleteSubscriptionBackups` has one caller, the retain-on-cancel sweep (private/account/src/services/backup-gc.service.ts:3361). Its doc comment names a GDPR surface that does not exist in the routes. See Hypotheses.
- F11. Confirmed, and wider than `--at`.
  - The 500-row cap applies per lineage, so a fork family shares it.
  - `ownStreamOf` (packages/cli/src/commands/backup-restore-chunk.ts) answers `streamUnknown` when the anchor falls outside the 500 rows.
  - `backup purge` reports `history.manifests.length` as the snapshot count (packages/cli/src/commands/backup-purge.ts:142), so it understates at the cap.
  - The other callers to review are packages/cli/src/commands/backup.ts:539, packages/cli/src/commands/backup-retention-commands.ts:186 and packages/cli/src/services/executor/repo-license-context.ts:341.
- F12. Confirmed. `gfsKeepSet` (private/account/src/services/backup-gc.service.ts:3956) treats all-null knobs as keep-everything, so a new knob must join that test. Product text says "A policy counts snapshots, never days" (private/account/web/src/data/study-content/mt6-backup.ts:39), which `keepWithin` changes.
- F13. Corrected on one point: `RuntimeMaxSec=` cannot be the run deadline. The systemd manual says: "Note that this setting does not have any effect on `Type=oneshot` services, as they terminate immediately after activation completed (use `TimeoutStartSec=` to limit their activation)." The design uses a renet-side deadline with a finite `TimeoutStartSec=` backstop.
- F14. Adopted as X2 and the J boxes.
- F15. New. `promoteToFull` (private/renet/pkg/chunkstore/uploader.go:387-391) states "Nothing more has to be uploaded" because the candidate set was the whole inventory. Asking only about the delta makes that false: a refused parent is exactly the case where unchanged chunks may have lost their protection. Promotion must run the full ask first (U1).
- F16. New. Chunk GC has its own wedge, separate from prune. `loadReferenced` (private/account/src/services/backup-gc.service.ts:1138) issues one GET per manifest on every visit, before the first listing, and the sibling's G2 moves only the verify sweeps onto the refset. With 300 or more kept manifests in a subscription, that alone spends the 300-call budget, so chunk GC never lists.
- F17. New, interaction with the sibling. G2 keys its refset by a digest of the manifest rows, and a new commit invalidates it. At a commit every 5 minutes, a set built across visits is never valid. M5 makes it incremental.
- F18. New, interaction with the sibling. A3 alerts when `hasIndex` flips from 1 to 0 in a stream. Sealing an index every Nth run (F11) would fire that alert on every unsealed run. The commit must say the skip was deliberate (Q2, W4).
- F19. New. A repo re-seeded at 1 MiB would be re-seeded back to 4 MiB by any later run that does not pass the flag, because the verb defaults to `DefaultCellBytes` and `buildPlan` treats any difference as "grid geometry changed" (private/renet/pkg/chunkstore/pipeline_linux.go:473). U2 fixes this.
- F20. New, security. `executeFunction` starts from `os.Environ()` (private/renet/pkg/orchestration/rediaccfile.go:233). A hook run from a backup unit would inherit that unit's `EnvironmentFile=` credentials, and repository code would read them. The hook needs a built environment, not an inherited one (W1).
- F21. New. One unit per repo means repositories overlap, which breaks the operator's 2026-10-29 order of one repository at a time on a machine a provider has taken offline over load. Tier units need a machine-wide slot (W3).
- F22. New. The sibling's digest sends once per subscription per day, which is too slow for a 5-minute target. M9 adds a faster path for streams with a declared target.
- F23. New. `scheduled` runs `runRetentionSweeps` and `runBackupMaintenance` together with no cron check (private/account/src/entry/cloudflare.ts:244). More crons would run the audit sweep more often as well, so the handler must dispatch on `controller.cron` (M4).
- F24. New. An unchanged repository still commits a manifest on each run (private/renet/pkg/chunkstore/uploader.go:291-312; private/renet/cmd/renet/backup_snapshot.go:138). An idle repo at 5 minutes writes 288 rows a day for nothing (W3).
- F25. New. Most event-log writes per run are routine (`backup_grant_minted`, `backup_manifest_committed`). Kept at a 400-day audit retention, the row count grows with cadence. Q6 reduces them.
- F26. New. `collectReleasePins` pins a hash other kept manifests still name, "harmlessly" (private/account/src/services/backup-gc.service.ts:2152). That is fine for safety but cannot produce the R3 number, which needs an exact count.
- F27. New. `keepLast` cannot express a time window, and `keepHourly` is coarser than the target. `keepWithin` must be measured from the stream's newest snapshot, not from now, so that "backups that stop for months delete nothing" still holds.

## Design

### D-wire. Wire shapes, fixed here

These add to the sibling's D-wire.

- `POST /backups/grants` adds `streamId` and `baseSnapshotId` (the anchor the run skipped asking about; absent when the run asked about everything).
- `POST /backups/exists` adds `purpose: 'delta'|'sample'|'full'`. `sample` writes no pin.
- `POST /backups/commit` adds:
  - `baseSnapshotId`;
  - `consistency: 'app-quiesced'|'crash-consistent'`;
  - `indexSkipped: 'interval'` (optional).
- `POST /backups/commit` can answer the existing `BACKUP_PARENT_INVALID` when `baseSnapshotId` no longer has a row. New error codes: `BACKUP_CHURN_CAP` (see D-safeguard) and `BACKUP_DELETION_DELAYED` (informational status on a delayed destructive call).
- `POST /backups/reports` adds `targetSeconds`, `achievedRpoMs`, `ticksMissed`, `targetMet`, and status `unchanged`.
- `GET /backups/snapshots/resolve?lineage=&at=&anchorSnapshotId=&anyStream=&needIndex=` answers one row, or 404.
- `GET /backups/manifests` adds `before` and `limit`, and returns `nextBefore`.
- `GET /backups/usage` adds `liveBytes`, `waitingBytes`, `waitingChunks`, `churnCapBytes`, `churnCapped`; per lineage: `liveBytes`, `waitingBytes`. `storedBytes` stays physical.
- `GET|PUT /backups/immutability`, `POST /backups/snapshots/:id/undelete`, `POST /backups/lineages/:guid/purge/cancel`.
- Retention knobs add `keepWithinSeconds`.

New renet records:
- snapshot record `hook: { prepare, finish, frozenMs, thawedBy }`, each of `prepare` and `finish` one of `ok|absent|failed|timeout|not-running|not-applicable`;
- `consistency`, `targetSeconds`, `achievedRpoMs`, `ticksMissed`, `targetMet`, `indexMs`, `chunksSampled`;
- status `unchanged`, `seed-started`, `deadline-exceeded`, `hook-failed`;
- `indexStatus` gains `interval`.

Migration 0074 (next after the sibling's 0073):
- `backup_usage` and `backup_lineage_usage` gain `waiting_bytes` and `waiting_chunks`.
- `backup_lineage_usage` gains `last_classified_at`, `refset_recount_started_at`, `refset_recount_completed_at`, `purge_after`.
- `backup_manifests` gains `consistency`, `deleted_at`, `delete_after`, plus an index on (subscription, lineage, stream, created_at).
- `backup_upload_leases` gains `stream_id` and `base_snapshot_id`.
- `backup_retention_policies` gains `keep_within_seconds`, `pending_policy`, `effective_at`.
- `backup_stream_status` (sibling's table) gains `target_seconds`, `achieved_rpo_ms`, `ticks_missed`, `missed_since`.
- New tables:
  - `backup_waiting_chunks` (subscription, lineage, hash, bytes, waiting_since, delete_after; primary key on the first three);
  - `backup_refset_pending` (subscription, lineage, snapshot id, hashes JSON or null for a full manifest);
  - `backup_immutability` (subscription, immutable_days, pending_days, shorten_after).

None of these writes moves the lineage `updatedAt` that chunk GC compares.

### D-exists. Changed-only asks, and what protects the rest (F4, F15)

**What a run asks about:**
- The set of hashes in the new inventory that differ from the anchor's inventory, plus a rolling sample of 16 unchanged hashes marked `purpose: 'sample'`.
- A delta run and a segment-root run behave the same way, since both have a trusted anchor.
- The full ask remains for: no trusted anchor, `--reseed`, a promotion, or a missing sampled hash. A resume keeps using the journal's pending set.

**What protects an unasked chunk.** The pin existed to cover the gap between an exists answer and the commit. For a hash the run does not ask about, the protection is the base manifest:
1. A hash unchanged from the anchor is named by the anchor's inventory, and GC's roots are the manifest rows.
2. The lease names `baseSnapshotId`, and a prune cannot delete a row that a live lease names (D-lease).
3. If the base row has gone by commit time, the commit answers `BACKUP_PARENT_INVALID` and the machine promotes. Promotion now runs the full ask and uploads what is missing before committing (F15).

**What is lost and replaced.** Today a whole-manifest ask silently re-uploads a chunk lost from the store. That self-heal is replaced by three things: the sample, which covers a 4 GiB repo in about 5 hours at 5 minutes and a 256 GiB repo in about 14 days; the sibling's HEAD sweep; and the sibling's repair. A missing sampled hash triggers a full ask on that run and re-uploads from the anchor.

**Commit-time check.** A commit HEADs each delta hash the machine did not upload (normally none) and refuses if one is absent, which narrows the reuse race in D-ledger.

### D-prune. Batched, fair and lease-tolerant (F5, F16)

- **Batch shape.** Prune works oldest first, in whole segments. A wholly doomed segment needs no rewrite, because the next segment's root is a full manifest with no parent, so it costs one GET per row and one delete call, with no PUT. A partial batch happens only when one segment exceeds the visit's cap.
- **Per-visit read cache.** Each manifest is read at most once per visit, so F5's two GETs per doomed manifest become one.
- **Budget shares of one subscription visit (300 calls):** retention at most 50%, chunk work guaranteed 25%, verify and reconcile the rest. A budget stop in one phase advances to the next phase on the same visit and records its resume point per phase, so no phase can starve another.
- **Per-lineage fairness.** The retention share divides by lineages with work, minimum 20 calls each, and each visit rotates the starting lineage. A lineage is visited only when it has at least 33 doomed rows or its oldest doomed row is older than 6 hours, which caps the per-visit overhead.
- **Interior correctness.** The existing collapse stays as the rule, including `BACKUP_COLLAPSE_MAX_CELLS` deferrals. X2 asserts a restore at every kept minute.

**Sustained frequency.** Let `r` be runs a day, `v` lineage visits a day (at most 6 under the rule above), `M` kept manifests, and `L` list pages.

```
c_repo = r            (doomed GET)
       + 6v           (child GET, base GET, refset GET and PUT, delete, slack)
       + r/32         (full manifests folded into the refset)
       + M/6          (a full recount every 6 days)
       + L            (one classify pass a day)

sweeps_per_day >= max( ceil(sum of c_repo in the busiest subscription / 225),
                       ceil(sum of c_repo across the fleet / 800) )
```

225 is the 75% of 300 that retention and chunk work share. 800 is the run budget.

Worked example, 5 minutes, 4 GiB, a 24-hour window: `r=288, v=6, M=350, L=2` gives `c_repo = 288 + 36 + 9 + 58 + 2 = 393`.
- One repo needs 2 sweeps a day.
- Ten repos in one subscription need 18.
- An hourly cron (24 a day, 19,200 calls) carries about 48 such repos across the fleet, and every 15 minutes carries about 195.

Above that, the sweep needs a fan-out (decision O8). The recommended cron is hourly at a fixed minute, with the audit sweep still daily on its own cron.

### D-lease. Leases at minutes cadence (F6)

- Quota counts only the newest live lease per stream. A superseded run's bytes stop stacking at once, with no change to the 65-minute release rule, because that rule protects the ledger swap, not the quota number.
- **Prune interlock.** The prune's D1 batch deletes a doomed row only under `not exists (a live lease naming this row as base)`. A grant minted after that batch finds the row gone, and its commit promotes. This makes a sweep safe at any time, so a timer firing at 03:00 no longer skips that day's prune.
- **Chunk reaping** ignores leases: an in-flight run's new chunks are protected by the upload-time grace, its answered chunks by pins, and its unchanged chunks by the interlock.
- **The ledger swap from a listing** still requires no live lease. That condition is about double billing, not safety, so it stays.

### D-ledger. Live and waiting (R3, F7, F26)

**The pair.** `stored_bytes` stays the physical total. `waiting_bytes` is the part no kept manifest can restore. `live = stored - waiting`. Quota is `max(0, live + usageAdjustment) + leasedBytes(newest per stream)`, at grant, at commit and in `overQuotaOne`.

**How a chunk is known to be unreferenced across a fork family.** Dedup is per lineage, so a chunk is unreferenced only when no manifest of any stream in the lineage names it. The refset is therefore per lineage and counted: `hash -> (count, bytes)`, in a binary object at `t/<sub>/l/<lineage>/v/refset`. Bytes come from the cell length, which the manifest determines (`StoredBytesFor` semantics), so no HEAD is needed.

**Moves:**

| Event | Refset | Waiting table | Pair |
|---|---|---|---|
| Commit | pending row (delta hashes; null for a full manifest) | delete rows matching the manifest's hashes, in the commit's batch | a matched row moves bytes back to live at once; added bytes to stored |
| Visit | fold pending rows; a null row costs one GET | none | none |
| Prune | subtract doomed rows, apply rewrite differences | insert hashes that reach count 0, `delete_after = now + grace` | stored unchanged, waiting up, in the prune's batch |
| Classify (at most daily per lineage, sooner when `reconcile_due_at` is set) | read only | listed, count 0 and no row: insert with `delete_after = uploadedAt + grace`, minimum `now + 24h`; count above 0 with a row: delete the row | swap stored and waiting together from the listing, under the existing compare-and-swap and no-live-lease condition |
| Reap | none | delete due rows | stored and waiting both down |
| Purge, delete, orphan expiry | removed with the lineage | removed | debited together |

**Reuse during the wait.** A cell rewritten to identical bytes yields the same ciphertext hash, because aes-xts is deterministic per sector. The exists answer pins it and the machine skips the PUT, then the commit deletes the waiting row and returns the bytes to live in the same batch. The manifest body read by the sibling's A2 supplies the hashes:
- A delta looks up its changed hashes in batches of 90.
- A full manifest with a base needs only its difference from the base.
- A full manifest with no base reads the lineage's waiting rows once.

**Deletion is never decided by a counter.** A drifted count could otherwise release a live chunk. Reap therefore deletes a row only when:
1. a complete, independent recount (a resumable read of every kept manifest) started after the row's `waiting_since`;
2. that recount did not find the hash;
3. no live pin names it.

A recount that finds a counted-zero hash removes the row, returns the bytes to live, logs `backup_refset_drift` and feeds the sibling's alert. A recount every 6 days fits inside the 7-day grace. Counters drive the numbers shown and charged; the recount drives deletion.

**What reconcile recomputes.** `verify-reconcile` compares the listing with `stored` as today and adds `waitingDriftBytes` (listed unreferenced bytes against `waiting_bytes`). It repairs nothing and logs a nonzero value. Classify is what corrects.

**Abandoned uploads** are not restorable, so under R3 they are waiting and not charged. That is the free-storage path the safeguard below closes.

**Rollout.** Release pins already in `backup_exists_pins` expire within 7 days and still protect until then. The first classify pass corrects hostinger's pair, so its charged figure will drop at that point. New prunes write no release pins (clean break).

### D-safeguard. Heavy churn is not free storage (R3, decision O2)

At each grant, the server computes `waiting_bytes` against `churn cap = 2 x quota`. Above the cap, a grant on a stream whose previous commit is under 60 minutes old is refused with `BACKUP_CHURN_CAP`. The machine records `throttled`, and it counts as a missed target with the reason named. A stream committing hourly or slower is never refused.

The test uses server facts, not a declared target, so a client cannot talk its way past it, and a normal nightly is never affected. Bytes uploaded under a live lease count toward `used` as today, so debris stays bounded by the same check.

Worst-case absorbed cost at the cap is `2 x quota x $0.015` per GB-month: $0.30 on COMMUNITY, $3 on PROFESSIONAL, $15 on BUSINESS, $61 on ENTERPRISE. Shortening the grace is rejected for now because R3 keeps it at 7 days absent evidence, and X2 records the data that evidence would come from.

### D-hook. Pre-backup hook (F9, F20)

**Rediaccfile functions:** `backup_prepare` and `backup_finish`, both optional.

**Order on a hot run:**
1. Transient-state check, then the non-blocking staging flock. A contended flock is `skipped`, and no hook runs.
2. Arm the deadman: `systemd-run --on-active=<2 x timeout + 30s> --unit=rediacc-backup-thaw-<guid> renet backup hook-finish --repo <guid>`, which acts only if the marker `/run/rediacc/backup-hook/<guid>` exists.
3. `backup_prepare` in `FindAll` order, under the timeout, killed by process group.
4. Shared repo lock, `syncfs`, reflink, release the lock.
5. `backup_finish` in `FindAllReverse` order, always, with its own timeout, even after a failed prepare or reflink.
6. Clear the marker and stop the deadman.

Hash and upload run only after step 5, so the application is never held during them. The hook runs inside the staging flock so that two runs cannot overlap hooks, and outside the repo lock so that application code never holds it.

**The bound.** Writes held by a hook end when `backup_finish` returns. Even if renet is SIGKILLed, the deadman runs finish within `2 x timeout + 30s`. The default timeout is 30 s and the maximum 300 s. `frozenMs` is recorded. A finish that times out reports `finish: timeout` and alerts at once, since the application may still be quiesced.

**Reaching Docker.** The same `LifecycleEnv` and `DOCKER_HOST` the runtime sets (private/renet/pkg/reporuntime/docker.go:415-430), with the network id from the repo's config. The socket is the policy proxy, so `docker exec` into the repo's own containers works, and the proxy's restrictions stay in force.

**Cases:**

| Case | `hook.prepare` | `consistency` | Behaviour |
|---|---|---|---|
| No such function | `absent` | `crash-consistent` | no warning, one info line |
| Repo not mounted or daemon down | `not-running` | `crash-consistent` | nothing to quiesce, the run continues |
| Cold run | `not-applicable` | `crash-consistent` with `cold: true` | containers are already down |
| Prepare fails or times out, policy `continue` (default, O5) | `failed` or `timeout` | `crash-consistent` | a restore point beats none; alerted after 3 in a row |
| Same, policy `abort` | same | none | status `hook-failed`, no upload, non-zero exit, counts as a miss |

**Security.**
- A hook is repository content, so it runs as `up` runs: the Landlock sandbox from private/renet/pkg/orchestration/up_down_workflows.go:246, the repo cgroup and the socket proxy.
- It gets a built environment, with no inherited credentials from the unit (F20), and it receives no licence blob or keyfile path. A test enumerates the environment.
- Output is capped and goes to the unit journal.
- A frequent target makes this code run far more often than `up`, with no new privilege. Docs state that hook code should be small and idempotent.

### D-rpo. The declared target (F13, F21, F24)

**CLI.** `rdc backup strategy set <name> --rpo <duration>` for a strategy, and `--repo-rpo <ref>=<duration>` for one repository. `repoSchedules` is removed from the schema in favour of `repoTargets` (a clean break). A target resolves to exactly the named repository; `mail` no longer pulls `mail:trial` (F1), and `mail:*` asks for the family explicitly.

**Rendering, for target `T`:**
- `OnCalendar` from `T`, plus `RandomizedDelaySec=min(T/5, 60s)`, `FixedRandomDelay=true`, `AccuracySec=1s`. This gives each timer a stable offset, so many repos on one machine do not all mint a session in the same second.
- `Persistent=true` stays.
- `TimeoutStartSec=` becomes finite: `2 x deadline + 10 min`.
- The verb receives `--target T --deadline D`, where `D = clamp(3T, 10 min, 2 h)`.

**Seeding.** A finite deadline cannot hold a first seed. A run with no trusted anchor starts a detached transient seed unit with no deadline and exits `seed-started`. Later ticks are `skipped` on the flock with reason `seeding`, and the coverage output says so.

**The machine slot (F21).** Tier units take `/run/rediacc/backup-tier.lock`, default one at a time, waiting up to the deadline. The wait counts as lateness. A nightly strategy does not take this slot, since its hours-long run would otherwise block every target.

**Late runs.** A dropped tick stays dropped. The next tick runs, and there is no catch-up burst, in keeping with the gentleness order (decision O6). The record says what happened:
- `achievedRpoMs`: this run's commit time minus the previous stored capture time, which is the true loss window;
- `ticksMissed`;
- `targetMet`.

A `skipped`, `throttled`, `deadline-exceeded` or `hook-failed` run has `targetMet: false`. `nextExpectedAt` in the sibling's report becomes `capture + T + jitter + grace`, with grace = max(T, 5 min).

**Unchanged runs (F24).** A delta run with no changed cells commits nothing. It reports `unchanged`, drops the staged copy and keeps the anchor. `last_success_at` advances, so health stays correct, and `--at` still resolves to the snapshot holding that exact content. A segment boundary does not force a commit on an idle repo.

**Health.** `StaleBackupRepo` replaces `ageDays` and `intervalDays` with `ageSeconds` and `intervalSeconds`, because at sub-hour cadence both round to 0. A repo is stale when `age > T + grace`, and missed targets appear as named issues with a raised exit code.

**Estimate before enabling.** `--rpo` reads churn from `rdc backup churn <repo>` and prints the D-cost figures, the waiting total against the cap, and the plan's quota. It refuses without a measurement unless `--no-estimate` is given. It also fills a default `keepWithin` when no retention is declared, and says so.

### D-retention. A knob finer than hourly (F12, F27)

`keepWithin`, stored as `keep_within_seconds`. It keeps every snapshot of a stream within that duration of the stream's newest. CLI: `--keep-within 24h`, spec `within=24h`.

- It joins the "no knob set" test, so `keepWithin` alone is not keep-all.
- It is chosen over `keepMinutely` because a window maps directly to "any minute in the last day", while minute buckets count only slots that have a snapshot.
- `keepLast`, the buckets, the floor of 3 and the sibling's newest `verified` and `proven` all remain a union, so this knob only adds to what is kept.
- Within a bucket, the representative prefers a row with an index and `app-quiesced`, falling back to the newest. The bucket still yields one row, and a stream's newest row is always kept.
- The preview names the reason (`within`, `hourly`, `floor`, `verified`, `proven`, and so on).
- A `failed` row is never a preferred representative.

### D-listing. History, and browse (F11)

`--at` uses the new resolve route, an indexed query for the newest row at or before the time, in the named stream. `backup manifests` pages with `before`. `backup purge` shows the server's count, not a list length.

Index sealing is time-based: `indexEvery`, default 1 hour at this tier. It seals on the first run past the boundary, decided from the journal before the live listing is captured, so an unsealed run also skips that walk. An unsealed commit carries `indexSkipped: 'interval'`, so the sibling's regression alert ignores it (F18). `indexMs` is recorded; J2 reads it.

Browse or path restore at a time with no index uses `needIndex=1` to find the nearest indexed snapshot at or before that time, and states the time gap. A full `restore --at` still lands on the exact snapshot.

### D-cells. Adjustable cell size (F8, F19)

- `0` becomes the verb's default and means "keep the anchor's geometry, else 4 MiB". An explicit different value needs `--accept-grid-change`, because it re-seeds.
- Surface: `--cell-size` on `--repo-rpo` and on `backup snapshot`; `cell_bytes` on the function.
- Changing it stays in the same lineage and stream. The first run is a full manifest with no parent, so no chain crosses geometries. Every cell uploads again and is charged as live until retention drops the old chain, and forks at another size stop deduplicating with it. The CLI prints that cost first.
- Refused when `image / cell > 262,144` (the collapse cap). Above it, prunes are deferred. At 1 MiB that bound is a 256 GiB image.
- Manifests stay inside the 32 MiB write limit at those sizes (about 67 bytes per cell).

| Workload, from the probe's extent histogram | Recommendation | Why |
|---|---|---|
| Mostly writes at or under 64 KiB, scattered (mail stores, small-row databases) | 1 MiB when the projection saves at least 50% of bytes | same cell count, a quarter of the bytes |
| Mixed | 4 MiB (default) | the default balance |
| Mostly clustered writes at or above 4 MiB | 4 or 8 MiB | a smaller cell multiplies PUTs with no byte saving |

Break-even: one 4 MiB chunk over a 7-day wait costs about $0.0000137 in storage, and one PUT costs $0.0000045. Saving bytes wins when writes are scattered, and extra PUTs lose when they are clustered. HEAD sweep coverage also takes four times longer at 1 MiB.

### D-immutable. Immutable history (R2, F10)

**What the vendors offer.** Read 2026-11-01.
- R2 bucket locks: "Bucket locks prevent the deletion and overwriting of objects in an R2 bucket for a specified period — or indefinitely." "Each rule specifies which objects it covers (via prefix) and how long those objects must remain locked." "A bucket lock configuration can include up to 1,000 rules." "Bucket lock rules take precedence over lifecycle rules." "A bucket cannot be emptied while any bucket lock rules are configured."
- R2 S3 API (developers.cloudflare.com/r2/api/s3/api/): `PutObjectLockConfiguration`, `GetObjectLockConfiguration`, `PutBucketVersioning` and `GetBucketVersioning` are listed as not implemented, and the object-lock headers on PutObject as unsupported. `PutObjectRetention` is not listed.
- S3 Object Lock (for on-prem): "Object Lock works only in buckets that have S3 Versioning enabled." "Placing a retention period or a legal hold on an object protects only the version that's specified in the request." A simple DELETE "inserts a delete marker". In compliance mode an object version "can't be overwritten or deleted by any user, including the root user".

**Why a bucket rule does not fit:**
- The chunk store is one bucket keyed `t/<sub>/l/<lineage>/{c,m,i,v}/`. One rule per subscription reaches the 1,000-rule limit, and a prefix cannot select chunks across subscriptions.
- A lock lasts for an age or forever. A deduplicated store's oldest chunks are the ones every restore depends on, and an age lock would protect the newest deltas and leave the base unprotected (the exact age start is a hypothesis). Indefinite locks block retention entirely.
- A lock also refuses overwrites, and a manifest collapse rewrites at the same key (private/account/src/services/backup-gc.service.ts:2110), so collapse would fail on recent manifests. The refset object has the same problem.
- Locked objects block the waiting pool's reap, purge and prefix erasure.

**The design: delayed destruction, enforced by the server.** `backup_immutability.immutable_days = D` (decision O4):
- `DELETE /snapshots/:id` sets `deleted_at` and `delete_after = now + D`. The row stays a GC root, is hidden by default, and `rdc backup undelete` restores it.
- `purge` sets `purge_after`, and `purge --cancel` undoes it.
- A retention change that keeps less waits in `pending_policy` until `effective_at = now + D`. A change that keeps more applies at once. The sweep enforces whichever is in force.
- Shortening or disabling `D` itself waits for the old `D`. Raising it applies at once.
- Each of these sends an immediate notification to the owner and admins, not the daily digest.

**Interplay:**
- **Routine pruning** continues under the policy in force. Delayed deletion therefore means: whatever the policy in force `D` days ago would keep cannot be removed sooner than `D` days.
- **Waiting pool:** tombstoned rows are roots, so their chunks stay live and charged until final, and only then go through the 7-day wait. Total delay from delete request to bytes gone is `D + 7`.
- **Repair (sibling G5):** exempt, since it deletes only an object that a rehash proves corrupt in the same call. It is logged and alerted.
- **Collapse:** exempt, since it preserves the materialized view; a test holds this, and the sibling's G3 holds the root unchanged.
- **Retain-on-cancel:** the 60-day sweep is not delayed further, since it has already waited longer than any `D`.
- **Erasure:** `D` is clamped to 30 days and the `+7` wait applies, so a data-subject erasure finishes inside about 37 days unless a root-only path shortens it (decision O7). Lawyers must confirm the "one month" position.
- **Quota:** tombstones stay charged, so `D` is not free storage. The churn cap is unaffected.

**Corrections from the 2026-11-01 review.** A bucket lock also has a third type, retain until a date. A lock is removable at once by whoever holds bucket configuration rights, and no compliance mode is documented. The account Worker's `ACCOUNT_BACKUP_S3_*` token can delete, and the deploy credential can replace the Worker, so a vault in the same Cloudflare account does not stop a hostile deploy.

**The age anchor and erasure.** M10's anchor binds routine retention only. A lineage purge or a data-subject erasure removes the anchor too, under the delays above, so the erasure bound stands.

**What this cannot defend against, plainly:**
- Compromise of the Cloudflare account, R2 credentials or the delete-capable Worker secret, or Cloudflare deleting the bucket.
- A malicious or compromised Rediacc server, or a direct D1 write.
- An attacker who controls the owner's mailbox and account for the whole of `D`.
- A ransomware run that overwrites a repository's data, which is then faithfully backed up. Kept history is the defence there, so `D` only helps if detection happens within the window.
- A compromised machine, which cannot delete history today (its grants are create-only) but can write garbage as new snapshots.

The only defence against the first two is a second destination or store-level WORM, and R2 ruled out the former.

**On-prem.** Object Lock is possible only where the store offers it. It would need versioning, copy-on-write manifest keys and a version-aware reap. T4 records the store's capability without asserting it, and building on it is a later plan (decision O4).

### D-cost. Cost per repo (R2: $4.50 per million Class A, $0.36 per million Class B, $0.015 per GB-month)

R2's pricing page classes `PutObject` and `ListObjects` as A, `HeadObject` and `GetObject` as B, and says "Free operations include `DeleteObject`...".

With `N` changed cells per run, `C` cell size, `r` runs a day, `W` window days, `G = 7` grace days, `s = 16` sampled hashes and index sealing hourly:

```
A_run = N + 1 (manifest) + 1/k (index; k = runs an hour)
B_run = N + s + 4 (commit HEADs, body GET, prune GET)
monthly Class A = A_run x r x 30 x $4.50/M     (plus negligible list pages)
monthly Class B = B_run x r x 30 x $0.36/M
window GB       = N x C x r x W                 charged to the customer's quota
waiting GB      = N x C x r x G                 absorbed by Rediacc, up to the cap
monthly storage = (window + waiting) x $0.015
```

Worked at `C = 4 MiB`, `W = 1 day`, GiB treated as GB. It excludes the base image and older kept points, and assumes the same `N` on each run. Real churn does not scale linearly with interval, which is why the estimate reads the measured probe.

| Target | N | Class A | Class B | Window GiB ($) | Waiting GiB ($) | Total per month |
|---|---|---|---|---|---|---|
| 5 min (r=288) | 10 | 95,904, $0.43 | 259,200, $0.09 | 11.25 ($0.17) | 78.75 ($1.18) | $1.87 |
| 5 min | 30 | 268,704, $1.21 | 432,000, $0.16 | 33.75 ($0.51) | 236.25 ($3.54) | $5.42 |
| 15 min (r=96) | 10 | 31,968, $0.14 | 86,400, $0.03 | 3.75 ($0.06) | 26.25 ($0.39) | $0.62 |
| 15 min | 30 | 89,568, $0.40 | 144,000, $0.05 | 11.25 ($0.17) | 78.75 ($1.18) | $1.80 |
| 30 min (r=48) | 10 | 15,984, $0.07 | 43,200, $0.02 | 1.875 ($0.03) | 13.125 ($0.20) | $0.32 |
| 30 min | 30 | 44,784, $0.20 | 72,000, $0.03 | 5.625 ($0.08) | 39.375 ($0.59) | $0.90 |

- **Today's exists cost for contrast:** 1,024 hashes x 8,640 runs = 8.85 million Class B a month, $3.19, on a 4 GiB repo, plus about 22 MB a day of pin JSON. The plan's asks replace that at $0.09 to $0.16.
- **The cap is real.** On COMMUNITY (10 GiB quota, 20 GiB cap), 5 minutes at N=10 exceeds the cap in under two days, and the stream is throttled to hourly. PROFESSIONAL (200 GiB cap) holds N=10 at 5 minutes and not N=30. The estimate says this before enabling.
- **D1** costs extra, about `(10 + 2N) x r x 30` rows written a month: 259,200 at N=10 and 604,800 at N=30 at 5 minutes. D1's price is not in the brief, and X3 records the counted figure.

## Boxes

Control rule: every new test fails without its fix. Each tick note records the test name and rc 1 from the tree with the fix stashed and the test kept. A box whose test passes on the unfixed tree is not done.

### X: scale proof (writer X)

- [ ] X1: Prove the wedge first (F5, F16). A metered store and an injected clock drive 288 commits for one lineage, then a sweep at the real budgets. The test states the target: retention deletes something on the first visit, and chunk-gc reaches a listing. The tick note records the calls per phase from the unfixed tree. If the measured numbers differ from about 575 and 300, the D-prune shares are corrected before M1 starts, and a sweep with a live lease proves the skip.
  - Owns: private/account/tests/integration/backup-critical-wedge.test.ts, private/account/tests/integration/helpers/backup-metered-store.ts
  - Accept: `cd private/account && npx vitest run tests/integration/backup-critical-wedge.test.ts` rc 1 on the unfixed tree with the figures recorded here, and rc 0 after M1 to M3.
- [ ] X2: The week (F14): 288 runs a day for 7 simulated days, with no real waits, across two streams of a fork family, including a stream with a permanently live lease and a cell rewritten to earlier bytes during the wait. It asserts: calls per visit stay at or under budget; `stored`, `live` and `waiting` equal a brute-force recomputation from objects and manifests after each day; quota reads `live`; `--at` resolves any kept minute; retention matches the policy; a restore at a chosen minute materializes the expected cell map; every phase ran within 24 hours of simulated time.
  - Owns: private/account/tests/integration/backup-critical-week.test.ts
  - Accept: `cd private/account && npx vitest run tests/integration/backup-critical-week.test.ts` rc 0.
- [ ] X3: The cost formula against counted operations: the test counts Class A, Class B and D1 row writes per the simulated run and holds them within 10% of `rpo-cost.ts`.
  - Owns: private/account/tests/integration/backup-critical-cost.test.ts
  - Accept: `cd private/account && npx vitest run tests/integration/backup-critical-cost.test.ts` rc 0.

### M: account maintenance (writer M)

- [ ] M1: Resumable batched prune per D-prune: whole-segment batches, a per-visit cap and a per-visit read cache. `pruneManifests` no longer needs the whole doomed list in one call.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-prune-batched.test.ts
  - Tests: 300 doomed rows clear across visits with each visit under the cap; a wholly doomed segment costs no PUT; a manifest is read once per visit; a crash between each write leaves the existing documented state; an unreadable manifest defers only its batch.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-prune-batched.test.ts tests/integration/backup-retention.test.ts tests/integration/backup-gc.test.ts` rc 0.
- [ ] M2: Phase shares and per-lineage fairness: the resume point becomes per phase, and a budget stop advances the phase.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-maintenance-fairness.test.ts
  - Tests: one lineage with 2,000 doomed rows beside a small one, and the small one prunes on the first visit; chunk work runs on a visit where retention hit its share; the sibling's verify phases still progress; the persisted cursor round-trips.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-maintenance-fairness.test.ts tests/integration/backup-maintenance-isolation.test.ts` rc 0.
- [ ] M3: Lease-tolerant sweep per D-lease: the prune interlock replaces the lineage skip, and reap ignores leases. `report.retentionSkippedLeased` is replaced by rows kept for a lease.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-prune-lease.test.ts
  - Tests: a lease naming base B keeps B while other rows go; a lease appearing between the plan and the batch keeps the row; a commit after the prune is refused with `BACKUP_PARENT_INVALID`; an expired lease protects nothing.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-prune-lease.test.ts` rc 0.
- [ ] M4: Sweep frequency (F23): `scheduled` dispatches on `controller.cron`; backup maintenance runs at the O8 cadence and the audit sweep stays daily; seven configs carry both crons; the on-prem default interval moves from 6 hours to 1 hour.
  - Owns: private/account/src/entry/cloudflare.ts, private/account/src/entry/on-premise.ts, private/account/src/entry/node.ts, private/account/src/types/env.ts, private/account/wrangler.toml, workers/account/wrangler.eu.toml, workers/account/wrangler.us.toml, workers/account/wrangler.asia.toml, workers/account/wrangler.edge-eu.toml, workers/account/wrangler.edge-us.toml, workers/account/wrangler.edge-asia.toml, workers/account/wrangler.bench.toml, private/account/tests/integration/backup-cron-dispatch.test.ts
  - Tests: the backup cron does not run the audit sweep and the reverse; every config lists both crons.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-cron-dispatch.test.ts && npm run typecheck` rc 0.
- [ ] M5: Counted, incremental refset (F16, F17), extending the sibling's G2: counts and bytes in the object, pending rows folded per visit, an independent resumable recount, and chunk GC and verify reading the same object. A commit no longer invalidates the set.
  - Owns: private/account/src/services/backup-refset.ts, private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-refset-counted.test.ts
  - Tests: counts equal a recount after commits, prunes and collapses; a set ahead of D1 after a crash recovers; a full manifest folds through one GET; a visit with 400 kept manifests reads one object; a recount survives commits landing during it.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-refset-counted.test.ts tests/integration/backup-refset.test.ts` rc 0.
- [ ] M6: The pair per D-ledger: waiting rows replace release pins; classify and reap replace the GC loop; the safety conditions for reap; `overQuotaOne` reads `live`; purge, delete, orphan expiry and `deleteSubscriptionBackups` handle the new tables; reconcile reports `waitingDriftBytes`.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-ledger-pair.test.ts
  - Tests: a chunk named by a fork's stream does not move to waiting when the other stream prunes; a prune moves exact bytes; debris is classified and not charged; a count corrupted to zero is caught by the recount and never reaped (the headline control); a row with a live pin is not reaped; the grace stays 7 days from `waiting_since`; deleting a subscription leaves no rows.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-ledger-pair.test.ts tests/integration/backup-meter-orphaned-chunks.test.ts tests/integration/backup-verify-reconcile.test.ts` rc 0.
- [ ] M7: `keepWithin` per D-retention in the keep sets and the preview, and policies applying through `effective_at`.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-retention-within.test.ts
  - Tests: only `keepWithin` set is not keep-all; a stream stopped for a month deletes nothing from its window; interior prune plus a restore at each kept minute; the sibling's verified snapshot outside the window survives; bucket representative preference never drops the newest; the preview names reasons.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-retention-within.test.ts tests/integration/backup-retention-verified.test.ts` rc 0.
- [ ] M8: Delayed destruction per D-immutable: tombstones are roots, a finalize phase, delayed purge, and a shortened `D` waits. Repair, collapse and retain-on-cancel exemptions are explicit and tested.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-immutability.test.ts
  - Tests: a delete with `D=7` keeps restoring until final; undelete restores; a tightened policy waits while a loosened one applies at once; shortening `D` waits; a tombstoned snapshot's chunks stay live; repair still deletes a corrupt object; `D=0` behaves as today.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-immutability.test.ts` rc 0.
- [ ] M9: Missed-target alerting (R4, F22), extending G4: a stream with `target_seconds` past `nextExpectedAt`, or with 3 consecutive `targetMet: false`, sends at most one alert per stream per 6 hours from the end of each sweep, naming the target, the achieved figure and the reason. A destructive intent (M8) sends immediately. Detection latency equals the sweep interval, and docs state that.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/src/services/notification.service.ts, private/account/src/email/templates/security.ts, private/account/tests/integration/backup-target-alerts.test.ts
  - Tests: a hung run with no report alerts through the dead-man path; a `throttled` run names the cap; a repeat inside 6 hours sends nothing; a recovered stream clears `missed_since`; a stream with no target stays on the daily digest; the preference off suppresses both.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-target-alerts.test.ts tests/integration/backup-alerts.test.ts` rc 0.

- [ ] M10: The age anchor: each stream always keeps one snapshot older than `D`, so a flood of new versions or backed-up ransomware cannot age every good version out inside the window, and routine pruning cannot bypass delayed destruction.
  - Owns: private/account/src/services/backup-gc.service.ts, private/account/tests/integration/backup-age-anchor.test.ts
  - Tests: a 5-minute flood across a `D=7` window leaves a snapshot older than `D` restorable (the headline control); a stream younger than `D` keeps its oldest; the preview names `age-anchor`; `D=0` keeps no extra snapshot.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-age-anchor.test.ts` rc 0.

### Q: account storage, routes and schema (writer Q)

- [ ] Q1: Migration 0074 and schema per D-wire, with new tables in the scope registry.
  - Owns: private/account/drizzle/0074_backup_critical_tier.sql, private/account/drizzle/meta/_journal.json, private/account/src/db/schema.ts, private/account/tests/integration/backup-critical-schema.test.ts
  - Test: applies every migration and asserts columns and defaults on rows inserted before 0074.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-critical-schema.test.ts && npm run typecheck` rc 0, and `npm run check:ci-account-scope-audit` rc 0 from the console root. The clone check runs in CD; Y3 records it.
- [ ] Q2: Grants, exists and commit per D-exists and D-ledger: `baseSnapshotId` and `streamId`, sample with no pin, a pending row, waiting rows returned to live in the commit's batch, HEADs of unuploaded delta hashes, `consistency`, and `indexSkipped` read by the sibling's flip detection.
  - Owns: private/account/src/dto/backup.dto.ts, private/account/src/errors.ts, private/account/src/services/backup-storage.service.ts, private/account/src/routes/backups.ts, private/account/tests/integration/backup-commit-critical.test.ts
  - Tests: a missing base refuses and leaves the lease live; a reused waiting chunk returns to live exactly once across two commits; a deleted object named by a delta refuses; `indexSkipped: 'interval'` does not set `index_regressed` while an unexplained flip does; a sample writes no pin row.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-commit-critical.test.ts tests/integration/backup-commit-binding.test.ts tests/integration/backup-lifecycle.test.ts` rc 0.
- [ ] Q3: Quota per D-ledger, D-lease and D-safeguard: `computeUsed` reads `live` and the newest lease per stream; the churn cap; the usage report; the portal shows both numbers.
  - Owns: private/account/src/services/backup-storage.service.ts, private/account/src/dto/backup.dto.ts, private/account/src/errors.ts, private/account/web/src/api/types.ts, private/account/web/src/pages/BackupStorage.tsx, private/account/tests/integration/backup-quota-live.test.ts
  - Tests: waiting bytes do not count; ten failed runs on one stream count one lease; above the cap a run 5 minutes after its last commit is refused, while one 61 minutes after is allowed, as is a nightly (the headline control); the cap is reported.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-quota-live.test.ts tests/integration/backup-storage.test.ts && npm run typecheck && npm run lint` rc 0, and `npm run check:ci-test-account-web` rc 0.
- [ ] Q4: Listing per D-listing: the resolve route, pagination, and a read-scoped token staying inside team scope.
  - Owns: private/account/src/services/backup-storage.service.ts, private/account/src/routes/backups.ts, private/account/src/dto/backup.dto.ts, private/account/tests/integration/backup-resolve-at.test.ts
  - Tests: 3,000 rows resolve a time beyond the first 500; stream scope holds; the anchor resolves when older than 500; `needIndex` finds the nearest indexed row; a team token cannot resolve another lineage; a tombstoned row is not selected.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-resolve-at.test.ts tests/integration/backup-team-scope.test.ts` rc 0.
- [ ] Q5: Routes per D-immutable, using the same owner-or-admin check as the retention writes, and delegating to M8.
  - Owns: private/account/src/routes/backups.ts, private/account/src/services/backup-storage.service.ts, private/account/src/dto/backup.dto.ts, private/account/tests/integration/backup-immutability-routes.test.ts
  - Tests: a read token is refused; 404 outside team scope; values above 30 are refused; undelete after finalization answers plainly.
  - Accept: `cd private/account && npx vitest run tests/integration/backup-immutability-routes.test.ts` rc 0.
- [ ] Q6: Per-run write count (F25): one coalesced event for a routine run; a deviation still logs in full. The test counts D1 statements for one stored run at N=10 and holds it at or under the target recorded here from the unfixed tree minus the pin and grant event rows.
  - Owns: private/account/src/services/backup-storage.service.ts, private/account/tests/integration/backup-run-writes.test.ts
  - Accept: `cd private/account && npx vitest run tests/integration/backup-run-writes.test.ts` rc 0.

### U: renet chunkstore (writer U)

- [ ] U1: Changed-only asks per D-exists: delta candidates plus sample, the base declared on the grant and commit, and promotion running the full ask (F15). `stats.ChunksAsked` counts asked hashes, and `ChunksSampled` is new.
  - Owns: private/renet/pkg/chunkstore/uploader.go, private/renet/pkg/chunkstore/session.go, private/renet/pkg/chunkstore/uploader_delta_test.go
  - Tests: `TestUpload_AsksOnlyDelta` (N changed of 1,024 asks N plus sample), `TestUpload_SegmentRootAsksOnlyDifference`, `TestUpload_PromotionUploadsWhatIsMissing` (the headline control: a chunk gone from the store is uploaded before the promoted commit), `TestUpload_MissingSampleRunsFullAsk`, `TestUpload_NoAnchorAsksAll`, `TestUpload_ReseedAsksAll`, `TestUpload_ResumeUsesPending`.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'TestUpload_' -count=1` rc 0, and `go test ./pkg/chunkstore/ -count=1` rc 0.
- [ ] U2: Geometry per D-cells: `CellBytes` 0 inherits; an explicit change needs `AcceptGridChange`, else a named refusal; a cell-count check; grid.go's comment names `churn-probe`.
  - Owns: private/renet/pkg/chunkstore/pipeline_linux.go, private/renet/pkg/chunkstore/grid.go, private/renet/pkg/chunkstore/geometry_test.go
  - Tests: a 1 MiB anchor with no flag stays at 1 MiB; a different explicit value refuses; accepting it emits a full manifest with no parent; above 262,144 cells refuses.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'TestGeometry' -count=1` rc 0.
- [ ] U3: Hook seam: `PlanOptions.BeforeReflink` and `AfterReflink` run inside the staging flock and outside the repo lock; `AfterReflink` always runs. Also `Plan.CapturedAt`, and `Journal.Anchor.CapturedAt` for the achieved figure. A new `Consistency` field on the manifest is additive, so `ManifestVersion` stays 1.
  - Owns: private/renet/pkg/chunkstore/pipeline_linux.go, private/renet/pkg/chunkstore/journal.go, private/renet/pkg/chunkstore/manifest.go, private/renet/pkg/chunkstore/hookseam_linux_test.go
  - Tests: order asserted through a seamed reflink; After runs when the reflink fails; a contended flock calls neither; a v1 manifest with no field decodes.
  - Accept: `cd private/renet && go test ./pkg/chunkstore/ -run 'TestHookSeam' -count=1` rc 0.

### W: renet verbs and functions (writer W)

- [ ] W1: `pkg/backuphook` per D-hook: discovery, the built environment, sandbox, cgroup, timeouts, process-group kill, the marker, deadman arming, and `renet backup hook-finish`. `RediaccfileExecutor` gains a clean-environment mode.
  - Owns: private/renet/pkg/backuphook/hook.go, private/renet/pkg/backuphook/hook_test.go, private/renet/pkg/orchestration/rediaccfile.go, private/renet/pkg/orchestration/rediaccfile_cleanenv_test.go, private/renet/cmd/renet/backup_hook.go, private/renet/cmd/renet/backup_hook_test.go
  - Tests: unit credentials in the parent environment are absent from a hook (the headline control); an absent function, a timeout, a failing prepare and a hung finish; a sleeping child dies with the group; hook-finish runs only with the marker; docker env set only when a network id exists.
  - Accept: `cd private/renet && go test ./pkg/backuphook/ ./pkg/orchestration/ ./cmd/renet/ -run 'BackupHook|CleanEnv' -count=1` rc 0.
- [ ] W2: Wire hooks into the hot and cold paths: flags `--hook-timeout`, `--hook-failure`; function params; record fields; commit's `consistency`.
  - Owns: private/renet/cmd/renet/backup_snapshot.go, private/renet/cmd/renet/backup_snapshot_hook_test.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_snapshot_hook_test.go
  - Tests: every row of the D-hook case table asserts its record; `abort` uploads nothing (the fake plane sees no grant); upload starts only after finish; a cold run marks `not-applicable`.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/functions/commands/ -run 'SnapshotHook' -count=1` rc 0.
- [ ] W3: Target behaviour per D-rpo: `--target`, `--deadline`, the tier slot, seed detach, `unchanged`, the achieved figure, and the sibling's report carrying them. `backupstate` counts `unchanged` as a success, and coverage carries the target.
  - Owns: private/renet/cmd/renet/backup_snapshot.go, private/renet/cmd/renet/backup_snapshot_target_test.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/backupstate/backupstate.go, private/renet/pkg/backupstate/backupstate_test.go, private/renet/pkg/list/types.go, private/renet/pkg/list/list.go
  - Tests: a run past the deadline ends `deadline-exceeded` and abandons staging; a seed with no anchor starts the detached unit and exits `seed-started`; a skip reports `targetMet: false`; a second tier unit waits for the slot and counts the wait; zero changed cells commits nothing and advances `last_success_at`; `ticksMissed` from a fixed clock; no secret in the report.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/backupstate/ ./pkg/list/ -run 'SnapshotTarget|BackupState|Coverage' -count=1` rc 0.
- [ ] W4: Index interval per D-listing: `--index-every`, a journal `LastIndexAt`, `indexStatus: 'interval'`, `indexMs`, no live walk on an unsealed run, and `indexSkipped` on commit.
  - Owns: private/renet/cmd/renet/backup_snapshot_toc.go, private/renet/cmd/renet/backup_snapshot_toc_interval_test.go, private/renet/cmd/renet/backup_snapshot.go, private/renet/pkg/chunkstore/journal.go
  - Tests: sealed once per hour at 5-minute runs on a fake clock; a skipped run never walks; a sibling `no-key` status still warns.
  - Accept: `cd private/renet && go test ./cmd/renet/ -run 'TestSnapshotTOCInterval' -count=1` rc 0. Writer W edits journal.go after U3 lands.
- [ ] W5: The probe as a product instrument: unhidden; `--repo`, `--forget` removes the base, and function `backup_churn_probe` returns the record; the verb and any test keep the reflink lock rules.
  - Owns: private/renet/cmd/renet/backup_churn_probe.go, private/renet/cmd/renet/backup_churn_probe_test.go, private/renet/cmd/renet/backup_churn_cells.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_churn_probe_test.go
  - Tests: `--forget` removes only that repo's base and meta; the function's argv; a repo under transient state skips.
  - Accept: `cd private/renet && go test ./cmd/renet/ ./pkg/functions/commands/ -run 'ChurnProbe' -count=1` rc 0.

### E: CLI target and units (writer E)

- [ ] E1: Schema: `repoTargets` replaces `repoSchedules`, with `rpo`, `cellSize`, `indexEvery`, hook fields; `retention.keepWithin`; sensitivity entries; validation including the O6 minimum.
  - Owns: packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/shared/src/config-schema/__tests__/retention-policy.test.ts, packages/cli/src/services/backup/backup-strategy-validate.ts, packages/cli/src/services/__tests__/backup-strategy-validate.test.ts
  - Accept: `npx vitest run --root packages/shared src/config-schema/__tests__/retention-policy.test.ts` rc 0, `npm run test:unit -w @rediacc/cli -- src/services/__tests__/backup-strategy-validate.test.ts` rc 0, and `npm run check:ci-schema-coverage` rc 0.
- [ ] E2: Rendering per D-rpo: exact-ref resolution, jitter, finite timeouts and flags on the verb, and removal handling.
  - Owns: packages/cli/src/services/backup/backup-schedule-targets.ts, packages/cli/src/services/backup/backup-schedule-unit-generator.ts, packages/cli/src/services/backup/backup-schedule-execute.ts, packages/cli/src/services/backup/backup-schedule-reconcile.ts, packages/cli/src/services/__tests__/backup-schedule-targets.test.ts, packages/cli/src/services/__tests__/backup-schedule-renet-contract.test.ts, packages/cli/src/services/__tests__/backup-schedule-rpo.test.ts
  - Tests: `mail` renders one guid while `mail:*` renders the family; the unit text for 5, 15 and 30 minutes; `RuntimeMaxSec` never rendered; a nightly unit unchanged except for its scope excluding the target repo; removing a target returns the repo to the main scope.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/services/__tests__/backup-schedule-targets.test.ts src/services/__tests__/backup-schedule-renet-contract.test.ts src/services/__tests__/backup-schedule-rpo.test.ts` rc 0, and `npm run typecheck -w @rediacc/cli` rc 0.
- [ ] E3: Verbs: `backup strategy set --rpo`, `--repo-rpo`, `--no-estimate`, and the default window, using `rpo-cost.ts` and the probe.
  - Owns: packages/cli/src/commands/backup-strategy.ts, packages/cli/src/commands/__tests__/backup-strategy-rpo.test.ts
  - Tests: refuses without a measurement; prints cost and cap; `--dry-run` writes nothing; a re-seed warning on a cell change; a declared retention is left alone.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-strategy-rpo.test.ts` rc 0.
- [ ] E4: Coverage and health per D-rpo: seconds replace rounded days, `T + grace`, and missed targets as issues.
  - Owns: packages/cli/src/services/backup/backup-schedule-coverage.ts, packages/cli/src/commands/machine/health.ts, packages/cli/src/commands/machine/status.ts, packages/cli/src/commands/machine/__tests__/health-rpo.test.ts
  - Tests: a 5-minute target at 11 minutes is stale and renders minutes, not `0`; 4 minutes is not stale; `unchanged` is fresh; a hung run shows as missed; a nightly's result is unchanged.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/machine/__tests__/health-rpo.test.ts` rc 0.

### N: CLI restore, retention, usage and estimate (writer N)

- [ ] N1: `--at`, browse and counts per D-listing: every caller from F11 moves to the resolve route or pages, and purge shows the server's count.
  - Owns: packages/cli/src/commands/backup-restore-chunk.ts, packages/cli/src/commands/backup-restore-path.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/backup-purge.ts, packages/cli/src/commands/backup.ts, packages/cli/src/commands/backup-retention-commands.ts, packages/cli/src/services/executor/repo-license-context.ts, packages/cli/src/commands/__tests__/backup-resolve-at.test.ts
  - Tests: a time older than 500 rows resolves; `streamUnknown` no longer fires for an old anchor; browse with no index states the gap; purge reports the right count.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-resolve-at.test.ts src/commands/__tests__/backup-browse-at.test.ts src/commands/__tests__/backup-purge.test.ts` rc 0.
- [ ] N2: Retention per D-retention: `within=` in the parser, `--keep-within`, the cadence check, plan defaults and limits in constants (O3), and the preview.
  - Owns: packages/cli/src/services/backup/backup-retention.ts, packages/cli/src/commands/backup-retention-commands.ts, packages/shared/src/subscription/constants.ts, packages/shared/src/subscription/__tests__/schema.test.ts, packages/cli/src/services/__tests__/backup-retention.test.ts
  - Tests: `within=24h` parses; `within=24` and `within=1x` refuse; above the plan limit refuses by name; a 5-minute cron warns when no knob can use it.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/services/__tests__/backup-retention.test.ts` rc 0, and `npx vitest run --root packages/shared src/subscription/__tests__/schema.test.ts` rc 0.
- [ ] N3: `backup usage` shows live, waiting, cap and throttled state in every format; `backup manifests` shows consistency and tombstones.
  - Owns: packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/__tests__/backup-usage-pair.test.ts
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-usage-pair.test.ts` rc 0.
- [ ] N4: `backup immutability show|set`, `backup undelete`, `backup purge --cancel`.
  - Owns: packages/cli/src/commands/backup-immutability.ts, packages/cli/src/commands/backup-purge.ts, packages/cli/src/commands/__tests__/backup-immutability.test.ts
  - Tests: output names when a change takes effect; a delayed delete is reported as delayed, not done.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-immutability.test.ts` rc 0.
- [ ] N5: `rdc backup churn <repo> --samples <n> --interval <duration>` drives W5, prints the projection and cell recommendation per D-cells and always removes the base; `packages/shared/src/backup/rpo-cost.ts` holds the D-cost formulas.
  - Owns: packages/cli/src/commands/backup-churn.ts, packages/cli/src/commands/__tests__/backup-churn.test.ts, packages/shared/src/backup/rpo-cost.ts, packages/shared/src/backup/__tests__/rpo-cost.test.ts
  - Tests: the D-cost table as known answers; `--forget` is called on failure; a baseline is not read as zero churn.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-churn.test.ts` rc 0, and `npx vitest run --root packages/shared src/backup/__tests__/rpo-cost.test.ts` rc 0.

### T: artifacts, docs and drills (writer T)

- [ ] T1: Renet artifacts: regenerate the contract for `backup_snapshot` and `backup_churn_probe`, add new functions to the tier map, and add every new `i18n.T` key to the catalogs and baselines.
  - Owns: packages/shared/src/renet-contract/data/functions.schema.ts, packages/shared/src/renet-contract/data/functions.generated.ts, private/renet/pkg/i18n/**
  - Accept: `npm run check:ci-renet-types && npm run check:ci-renet-tiers && npm run check:ci-renet` rc 0.
- [ ] T2: CLI artifacts: command metadata and planes for `backup churn`, `backup immutability`, `backup undelete`; count pins with reasons; strings in all 13 locales; regenerate contract and docs data.
  - Owns: packages/cli/src/config/command-metadata.ts, packages/cli/src/config/command-planes.ts, packages/cli/src/config/__tests__/plane-coverage.test.ts, packages/cli/src/i18n/locales/**, packages/shared/src/cli-contract/**
  - Accept: `npm run check:ci-i18n-completeness && npm run check:ci-i18n-hashes && npm run check:ci-i18n-cli-key-usage && npm run check:ci-i18n-placeholders && npm run check:ci-cli-contract` rc 0, and `npm run typecheck -w @rediacc/cli` rc 0.
- [ ] T3: Docs in 13 locales: the tier and how to choose a target, what RPO means here (a loss window, including upload time), the hook with its bounds and security note, cell size, delayed destruction with its limits stated plainly, live and waiting, the churn cap, alert latency. Study text corrected for `keepWithin`. The execution record states what was run, dated.
  - Owns: packages/www/src/content/docs/*/backup-restore.md, packages/www/src/content/docs/*/cli-application.md, private/account/web/src/data/study-content/mt6-backup.ts, docs/backup-storage/07-execution-record.md
  - Accept: `npm run check:cli-docs && npm run validate:cli-docs -w @rediacc/www && npm run check:ci-i18n-docs-untranslated && npm run check:ci-docs-structure-parity` rc 0.
- [ ] T4: Drill legs, each with a planted control:
  - leg t: hook order against a real database container, including a killed renet thawed by the deadman;
  - leg u: `backup_onprem` records whether the store offers Object Lock and versioning, recorded and not asserted;
  - leg v: a sequence of tier-cadence runs with one chunk deleted from the store, healed by the sample;
  - leg w: a restore at a chosen run compared whole-image with that run's reflink;
  - `backup_roundtrip` asserts `consistency`.
  - Owns: .ci/rediacc_ci/drills/backup.py, .ci/rediacc_ci/drills/backup_renet.py, .ci/rediacc_ci/drills/backup_roundtrip.py, .ci/rediacc_ci/drills/backup_onprem.py, the drill tests under .ci
  - Accept: `./run.sh drill backup --selftest` rc 0, and the pytest for those drills rc 0.

### Y: proof before the merge (lead)

- [ ] Y1: VMs: a hook on a running repo, real reflink, a real unit at a 1-minute test target, a hung run killed at its deadline, two repos sharing the slot.
  - Accept: `npm run vm:check` rc 0 with the backup leg VERIFIED, receipt recorded here.
- [ ] Y2: Drills with legs t to w and their controls firing.
  - Accept: `./run.sh drill backup` and `./run.sh drill backup-onprem` rc 0, and the receipt `block_backup_unverified_push` reads is fresh for this tree.
- [ ] Y3: The D1 clone check covers migration 0074.
  - Accept: the CD or local `rediacc_ci.deploy.test_d1_migrations` run rc 0 for eu, recorded with its run id.

### Z: bench, after the merge and edge deploy (lead)

- [ ] Z1: A short-target stream on `eu-bench`: `backup usage` shows the pair moving after a prune, a stopped machine produces one target alert within the sweep interval and a repeat inside 6 hours does not, a delayed delete is undone.
  - Accept: `./rdc.sh --config eu-bench backup usage -o json` rc 0 shows `liveBytes` and `waitingBytes`, and the delivery and undelete are recorded here.
- [ ] Z2: The hourly cron runs maintenance on edge with the audit sweep still daily, and the report shows no phase starved over 24 hours.
  - Accept: the account's maintenance report or event log for the bench subscription, recorded here with its time span.

### J: hostinger, after the release and after the sibling's H1 to H3 (lead)

Every J box uses the released `rdc` and its released renet. No original repo is deleted, pruned by hand, replaced or downed. `nightly-hot` must keep running for the other repositories, checked in each day's box. J2 needs migration 0074 live on the stable eu account. J boxes stop on load above the sampler limit of the read-cap plan or on a missed nightly. No hook is added to `mail`'s Rediaccfile unless decision O9 says so; `hook.prepare: absent` is the expected record.

- [ ] J1: Churn measurement on `mail` before enabling, with the reflink base disclosed (F8): samples at 5-minute spacing through a busy hour, then the base removed.
  - Accept: `rdc --config eu-remote backup churn mail --samples 12 --interval 5m -o json` rc 0, with N, projected bytes per cell size and the recommendation recorded here, and a read showing no `.churn-probe` base remaining for `mail`.
- [ ] J2: Enable at 30 minutes with the estimate recorded; a day later: no missed target, `indexMs` and load peaks recorded, `nightly-hot` ran for the other repos.
  - Accept: `rdc --config eu-remote backup strategy set nightly-hot --repo-rpo mail=30m` then `rdc --config eu-remote backup schedule -m hostinger` rc 0; a day later `rdc --config eu-remote machine health -m hostinger` rc 0, and `backup manifests mail -o json` rc 0, recorded here.
- [ ] J3: The same at 15 minutes, with a day's check.
  - Accept: as J2 with `mail=15m`, figures recorded here.
- [ ] J4: The same at 5 minutes, with a day's check; the btrfs fragmentation and syncfs cost read-only under the sampler; actual Class A and B against the estimate.
  - Accept: as J2 with `mail=5m`, figures recorded here, with the estimate error stated.
- [ ] J5: A restore at a chosen minute from the last 24 hours, under a new name, compared by mail-store checksum on sampled messages; only the `-rt` copy is deleted, by GUID.
  - Accept: `rdc --config eu-remote backup restore mail --at <minute> --as mail-rt -m hostinger` rc 0, then `repo list -m hostinger` shows `mail` with its GUID unchanged and no copy after cleanup.
- [ ] J6: Seven days at 5 minutes: `waitingBytes` stabilizes near the formula, the first reap ran, and the churn cap state is known.
  - Accept: `rdc --config eu-remote backup usage -o json` rc 0 on day 8, with the series recorded here.

- [ ] LP-bench [live] Fresh bench receipt through worklist.py --live-proof, after this plan's bench-deployable boxes land.
  Accept: live-proof bench account-smoke

- [ ] LP-hostinger [live] Fresh hostinger receipt through worklist.py --live-proof, after this plan's hostinger-deployable boxes land.
  Accept: live-proof hostinger renet-live machine=hostinger

**Closes only after the merge:** Z1, Z2, J1 to J6, LP-bench, LP-hostinger. J6 takes about 10 days after J1. Everything else closes before the merge. The PR's merge rule therefore needs an `Operational-Reason:` naming these boxes or the operator's ruling on them, because the merge gate refuses open boxes on a plan on the PR's `Plan:` line.

## Rollout

1. Merge and edge deploy, with M4's cron on edge. Z boxes.
2. Release of the CLI and renet.
3. Sibling's H1 to H3. A new renet against the still-old stable account ignores new fields safely: its unasked chunks are protected there by the old skip-on-lease sweep.
4. Stable eu account deploy, with migration 0074 through `wrangler d1 migrations apply`.
5. J1, then J2 to J6.

No target is enabled before step 4, because the old account's daily sweep would hit the wedge this plan removes, and its quota still charges waiting bytes.

## Operator rulings on the decisions below, 2026-11-01

- O2: waiting above 2 x quota refuses a grant on a stream whose last commit is under 60 minutes old, as recommended.
- O4: delayed destruction at 7 days ships in this plan, with the age anchor of box M10, and it is described as delayed deletion, never as immutable, until the separate vault plan lands. That vault plan (a dedicated Cloudflare account holding the buckets and the only delete right) is written next and does not ride this PR.

## Decisions that belong to the operator

- **O1. Sweep cost and the immediate-alert path.** Recommended: both on, as designed. An hourly sweep means a stopped machine is alerted about an hour later at worst, which is longer than a 5-minute target. Faster alerting needs more frequent crons (see O8).
- **O2. Churn safeguard (R3).** Recommended: waiting above `2 x quota` refuses a grant on a stream whose last commit is under 60 minutes old, and never refuses slower streams. Alternatives: `1 x quota` (stricter, COMMUNITY gets little), or a shorter grace beyond the threshold (needs evidence under R3).
- **O3. Defaults per plan.** Recommended, with no feature gate:

  | | FREE | COMMUNITY | PROFESSIONAL | BUSINESS | ENTERPRISE |
  |---|---|---|---|---|---|
  | `--rpo` allowed | no storage | yes | yes | yes | yes |
  | Default `keepWithin` when a target is set | n/a | 24h | 24h | 48h | 72h |
  | Limit of `keepWithin` | 0 | 24h | 72h | 7d | 30d |
  | Default `immutableDays` | n/a | 7 | 7 | 7 | 7 |
  | Sampled unchanged hashes | n/a | 16 | 16 | 16 | 16 |

  COMMUNITY's existing limit forbids `keepHourly`, so allowing `keepWithin` there is a real change.
- **O4. Immutable design and default.** Recommended: server-enforced delayed destruction at 7 days, on for every paid plan, as D-immutable describes, and no R2 bucket lock. Alternatives: off by default; or a bucket-wide short age lock on `t/`, which is rejected because collapse overwrites recent manifests and it would not protect base chunks. Store-level WORM on-prem waits for T4's result and a later plan.
- **O5. Hook failure default.** Recommended: `continue`, recording `crash-consistent` and alerting after 3 failures, since a restore point beats none. `abort` stays available per repo.
- **O6. Late runs and minimum target.** Recommended: no catch-up burst, the next tick runs, and a 5-minute minimum for `--rpo`, with cron-based schedules refused below it too. Alternative: an immediate retry after a late run, which spends load when a machine is already behind.
- **O7. Erasure path.** Recommended: a customer's erasure request follows `D` and then the 7-day wait, with `D` capped at 30 days, and a root-only elevated path for a legal order. Legal review is needed before a customer relies on it. A route must exist first (see Hypotheses).
- **O8. Sweep frequency and fan-out.** Recommended: hourly now, and a fan-out to per-subscription invocations when `report.stoppedBy` shows run-budget stops on more than 3 consecutive sweeps. Every 15 minutes is the cheap interim step. No fan-out box exists until this is answered.
- **O9. Hook on `mail`.** Recommended: no hook on the sample repo in this plan, since editing production's Rediaccfile is the operator's call. The drill proves hooks. A dovecot or database quiesce on `mail` is a separate operator decision.
- **O10. Probe on hostinger.** The brief asks for a read-only measure, and the probe holds one reflink base. Recommended: accept it for J1, for one hour, on `mail` only, with the base removed afterwards. Alternative: infer churn from the first days at 30 minutes, which skips the pre-enable estimate.

## Hypotheses, each with the box that settles it

- The wedge exists at about 575 calls and chunk GC starves near 300 kept manifests. X1.
- Most mail churn is scattered small writes, so a smaller cell saves bytes. J1.
- `syncfs` plus a reflink every 5 minutes, and copy-on-write after each reflink, costs tolerable I/O and fragmentation on btrfs. J4 under the sampler, read-only.
- Index building at an hourly seal costs little. `indexMs` in J2 settles it.
- R2's lock age counts from upload. The documentation found gives only the `Age` condition with `maxAgeSeconds` and does not name the start. It does not change the recommendation; no box exists unless O4 changes.
- RustFS implements Object Lock and versioning. T4's leg u records it.
- A batch delete of some locked keys in R2 fails predictably. Not tested unless O4 changes.
- Account or subscription deletion leaves chunk objects behind, because the only `deleteSubscriptionBackups` caller is the retain sweep and a cascade removes only rows. M6's test on subscription deletion settles it. If true, it is a defect that O7 must also cover.
- `repoSchedules` is unused in live configs, so removing it costs nothing. J2 reads the config first, and a finding stops the box.
- `FixedRandomDelay` is available on every supported OS image. Y1 runs on the fleet's images; the renet OS matrix covers the rest.
- Reused chunks are rare enough that the commit's lookup cost does not matter. X2 counts them; J6 reads the real figure.
- The D1 pricing used for the note in D-cost. X3 counts rows; the price is the operator's to confirm.

## Risks

- **The reap-versus-reuse race.** A hash waiting past 7 days could be answered as present in the milliseconds between the reap's pin read and its delete call. The result is a hole in a new snapshot. Today's window is wider, since pins and leases are read once per visit. Re-reading per page, plus the commit-time HEAD, narrows it. The sibling's HEAD sweep and repair detect and repair the rest.
- **A counter bug** only affects displayed and charged numbers, never deletion, because the recount gates deletion. A long-lasting drift would overcharge or undercharge until the recount, and `backup_refset_drift` makes it visible.
- **Refset size** at about 40 bytes per chunk is about 10 MB at 262,144 cells, which is one object read per visit within Worker memory. Very large images are bounded by the cell check.
- **Absorbed waiting cost** is real and grows with customers: worst-case figures are in D-safeguard. `waiting_bytes` is the number to monitor.
- **The first classify on hostinger** moves charged figures, which is correct and looks like a jump. J6 expects it.
- **A delayed delete surprises someone** freeing quota: tombstones stay charged for `D` days. The CLI says so at the call.
- **A hook can degrade an application** while it runs. It is bounded, opt-in by writing the function, and documented.
- **Skipping the commit on idle repos** means `backup manifests` shows no new rows overnight. `machine health` and `backup status` show the last check, and docs explain it.
- **Machine slot contention**: many tier repos on one machine serialize, so their `achievedRpoMs` rises rather than the machine overloading. The record shows the wait, and the estimate warns when the sum of expected run times exceeds the target.
- **A seed unit with no deadline** can run for hours while its target is missed. That is reported as `seeding` and alerted as a miss, which is true.

## What this plan deliberately does not do

- It does not build a second destination (not chosen in R2) or a local-only tier (R1).
- It does not use R2 bucket locks or S3 Object Lock, and it does not claim WORM. D-immutable states what is undefended.
- It does not freeze a filesystem. Quiesce belongs to the hook, and an `fsfreeze` is the hook author's choice under the same bound.
- It does not shorten the 7-day grace.
- It does not gate the tier by plan. O3 proposes defaults only.
- It does not make alert latency equal to the target.
- It does not restate the sibling's verification state, identity checks, reports route, repair or verify units. It extends only the shapes named in D-wire.
- It does not fan the sweep out across invocations until O8 is answered.
- It does not edit `mail`'s Rediaccfile, migrate existing manifests, or re-seal older indexes on hostinger.
- It does not change `mail`'s cell size on hostinger, since that re-seeds. J1 only reports the recommendation.
- It does not offer a target below 5 minutes without an operator ruling.

## Sequencing against the sibling plan

**Files both plans edit**, so these writers run after the sibling's boxes on those files, and the lead serializes them: private/account/drizzle/meta/_journal.json, src/db/schema.ts, src/dto/backup.dto.ts, src/errors.ts, src/routes/backups.ts, src/services/backup-storage.service.ts, src/services/backup-gc.service.ts, src/services/backup-refset.ts, src/services/notification.service.ts, src/email/templates/security.ts, src/entry/on-premise.ts, web/src/api/types.ts; private/renet/pkg/chunkstore/uploader.go, session.go, journal.go, manifest.go, pkg/functions/commands/backup.go, pkg/backupstate/backupstate.go, pkg/list/*, pkg/i18n/**, cmd/renet/backup_snapshot.go, cmd/renet/backup_snapshot_toc.go; packages/cli/src/commands/backup-storage.ts, backup-restore-chunk.ts, backup-strategy.ts, machine/health.ts, machine/status.ts; packages/cli/src/services/backup/backup-schedule-coverage.ts, backup-schedule-unit-generator.ts, backup-schedule-execute.ts, backup-schedule-reconcile.ts, backup-strategy-validate.ts; packages/shared/src/config-schema/schemas.ts, sensitivity.ts, renet-contract/data/*, cli-contract/**; packages/cli/src/config/command-metadata.ts, command-planes.ts, __tests__/plane-coverage.test.ts, i18n/locales/**; the two www docs; docs/backup-storage/07-execution-record.md; the four drills.

| This plan | Must follow sibling box | Reason |
|---|---|---|
| Q1 | A1 | 0074 follows 0073; extends `backup_stream_status` |
| Q2, Q3 | A2, A3, K1 | commit reads the body; flip detection; `ChunksAlreadyPresent` |
| Q5, N4 | A3 | same route file; retention writes unchanged |
| M1, M2, M3 | G1, G2 | keep sets and budgets settle first |
| M5, M6 | G2, G3, G5 | counted set extends G2; recount reuses G3's pass; repair must debit the pair |
| M7 | G1 | union with verified and proven |
| M9 | G4 | extends the alert phase |
| X1 | none | proves the wedge on the tree as it stands, so it runs before M1, and can run now |
| U1 | K1 | Put and stats |
| U3 | K2, K5 | journal and manifest fields |
| W2, W3 | V1, V4 | identity first in the flow; the report verb |
| W4 | V4 | `indexStatus` |
| W5 | V3 | same function file |
| E1 | S3 | schema and sensitivity |
| E2 | S3 | unit generator with verify and `OnFailure` |
| E3 | C6 | strategy command output |
| E4 | C2 | coverage and health |
| N1 | C3, C4 | restore command file |
| N3 | C1 | backup-storage.ts |
| T1, T2, T3, T4 | D1, D2, D3, D4 | regenerated artifacts last, in one pass |
| Y1, Y2 | P1, P2 | one receipt can cover both trees if taken after both land |
| J1 | H1, H2, H3 | released CLI reads `eu-remote` |

Writers of the two plans may share nothing at the same moment. A sibling writer that has landed its boxes on a file releases it. The sibling's Owns stay valid for the sibling only.

## Short summary

This plan turns the existing fast change detection into a declared, alerted protection target. The target is expressed by `--rpo`, rendered with jitter, a real deadline and a machine slot. The server gets the capacity to keep up: only changed cells are asked about, prune and chunk GC stay within budget and survive live leases, and a counted refset gives exact live and waiting bytes, with an independent recount alone allowing deletion. Waiting chunks leave the quota under a churn cap. The hook, adjustable cell size and delayed destruction are the included capabilities, each with plain limits, and a second destination stays out. A week-long metered simulation and a stepped rollout on `mail` prove it.

Five results differ from the brief and should be read first:
- F8: `churn-cells` does not exist, and the probe holds a reflink base.
- F13: `RuntimeMaxSec` cannot apply to a oneshot.
- F15: promotion must regain the full ask.
- F16 and F17: chunk GC wedges on its own, and the sibling's refset would never stay valid at this cadence.
- F20: a hook would inherit the unit's credentials unless its environment is built.

## Writer split and order

- Writer X (scale proof): X1 first and now; X2 and X3 after M1 to M9, Q1 to Q6 and N5.
- Writer Q (account storage and schema): Q1 first after sibling A1; Q2 to Q6 after it, per the table.
- Writer M (account maintenance): M1 to M3 after Q1 and X1's figures; M4 any time; M5 before M6; M7, M8 and M9 after M6. M8 pairs with Q5.
- Writer U (chunkstore): U1 after K1; U2; U3 after K2 and K5.
- Writer W (verbs and functions): W1 first; W2 after W1 and U3; W3 after V1 and V4; W4 after U3 and V4; W5 after V3.
- Writer E (CLI target and units): E1 after S3; E2 after E1 and W3; E3 after E2 and N5; E4 after C2.
- Writer N (CLI restore, retention, usage, estimate): N1 after Q4; N2 after M7's knob shape, which D-wire fixes; N3 after Q3; N4 after Q5; N5 after W5.
- Writer T (artifacts, docs, drills): T1 to T3 after every writer above and sibling D1 to D3; T4 alongside, after sibling D4.
- Lead: Y1 to Y3 before the merge; Z1 and Z2 after the edge deploy; J1 to J6 after the release, sibling H1 to H3, and migration 0074 on stable eu.
