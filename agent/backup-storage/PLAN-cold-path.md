# PLAN: the cold backup path for the chunk store

Status: executing

**2026-08-15 (later): THE QUIESCE VERIFICATION WAS WRONG, AND THE DESIGN CHANGED.**
This is the correction that matters most in this file, because the first version of the
fix was worse than the bug it replaced.

T1's rule -- refuse a repo that did not actually quiesce -- was implemented by re-running
`discoverRunningRepos` after the stop. That predicate means *the per-network DOCKER DAEMON
is up or its socket answers* (`pkg/daemon/discovery.go:50`). The barrier stops services
with `Unmount: false`, and the only code that stops the daemon sits behind `if
opts.Unmount` (`pkg/orchestration/up_down_workflows.go:385`). So the daemon was ALWAYS
still up after a *successful* quiesce, and the verify refused every repository it had just
selected. `--cold` could not store a snapshot at all: three live runs, three refusals,
`cold_stage=0ms`. The refusal blamed a missing Rediaccfile, which is a plausible-sounding
diagnosis pointing at entirely the wrong thing.

**The predicate must be CONTAINERS, not the daemon** (`containersStillUp`, opening the
repo's own socket via `router.ListContainers`), and it fails CLOSED -- an unreachable
socket counts as still-running and therefore refused, because an unverifiable quiesce is
exactly what must not be labelled cold.

**The lesson for anyone extending this barrier: a seam can hide a predicate.** No unit
test could see this, because the fixture stubbed the very function whose meaning was
wrong, and an earlier live run misread the refusal as the fix working rather than as the
fix being unconditional. Only a full round trip with a real container caught it.

**Also unreachable until this was fixed:** the refusal branch drops `ColdWindowMs` and
`ColdSteps`, so a record carrying `cold: true` WITH a phase breakdown could not exist and a
real 400 ms outage left no machine-readable trace.

**2026-08-15: BUILT AND LIVE-PROVEN.** Steps 1-9 are done. The barrier, the cold lock,
the quiesce verification, the refusal-costs-no-outage path and the per-phase StepTimer
all ran on ops VM 192.168.111.11; the live run found three defects no unit test could
see (staging validated against fields it never reads, an unlicensed repo stopped before
being refused, and a repo reporting "quiesced" whose containers never stopped). ONE HALF
REMAINS: T3's round trip, where the restored file must show no gap and the live file
must show one. That now runs against a LOCAL S3 rather than waiting on operator
credentials.

Operator's constraint, verbatim intent: *"for the cold backup, we tend to keep the
down-time minimal with snapshoting"*. So: containers DOWN, take the CoW snapshot,
containers UP, and only THEN upload. The outage is the snapshot window, never the
transfer window. Any design that holds containers down across an upload is wrong.

---

## The headline: this is ~120 lines of orchestration, not a new engine

**Nothing in the existing cold machinery is rclone-specific.**
`private/renet/cmd/renet/backup_sync_cold.go` contains zero rclone references.
`discoverRunningRepos` (`:37`), `filterReposByName` (`:97`), `stopColdBackupRepos`
(`:179`), `startColdBackupRepos` (`:310`), `coldBackupRestartConcurrency` (`:236-243`)
and `pkg/coldbackup/sidecar.go` all survive the decommission verbatim.

What dies lives in `backup_sync.go`: the whole-datastore btrfs subvolume snapshot
(`:448`) and its GC flock (`:367`), and the fact that `--rclone-backend` is a
REQUIRED persistent flag (`:113-115`), which makes `backup sync push --mode cold`
not merely deprecated but unrunnable without rclone credentials.

**The chunk store already only ever reads a snapshot.** `PlanSnapshot` takes the
reflink at `pkg/chunkstore/pipeline_linux.go:156` and the uploader opens that path,
never the live image (`uploader.go:57-58`, `:216`). So cold is orchestration plus
ONE API split, because `PlanSnapshot` bundles two operations of wildly different
cost:

- `reflinkSnapshot` (`:156`) — metadata-only, the constant-time part;
- `buildPlan` (`:163`) — `rehashAllCells` reads the ENTIRE image on a first run
  (`:336-352`).

**The barrier goes between `:156` and `:163`.** Holding containers down across
`buildPlan` would make the outage O(image), hours on a first seed.

---

## THREE BLOCKERS IN EXISTING CODE. One is live today.

### BLOCKER 1 — the cold path would deadlock against itself

`TransientReason` skips any repo with `coldbackup.RunningPath(guid)` present
(`pipeline_linux.go:90`), and `stopOneRepo` writes exactly that file BEFORE
`DownServices` (`backup_sync_cold.go:142`, `:367-374`). A naive "stop, then
`PlanSnapshot`" therefore stops every container and then skips every repo:
**a full outage that backs up nothing.** Pinned by
`pipeline_integration_test.go:422-429`.

Fix: `PlanOptions.OwnsColdBackup bool` + `TransientReasonForOwner(...)`; keep the
exported `TransientReason` signature delegating with `false` so
`transient_restore_linux_test.go:34,42,50` is untouched. Only the in-process cold
orchestrator sets it, and only for repos it stopped itself.

### BLOCKER 2 — SIGTERM already leaves containers down. THIS IS LIVE.

`backup_sync.go:451` and `:466` pass the **SIGTERM-cancelled** context
(`setupSyncPushInterrupt`, `:290-307`) into `startColdBackupRepos`. Downstream
`orch.UpServices(ctx,…)` (`backup_sync_cold.go:278`) and
`context.WithTimeout(ctx, 30s)` (`:400`) both fail instantly on a dead context, so
**the restart is a no-op and the containers stay down.**

The snapshot-delete defer two lines below already does it correctly, with a fresh
`context.Background()` and its own timeout (`backup_sync.go:472-482`). The restart
does not. This is exactly the dangerous case, and it exists now.

### BLOCKER 3 — the watchdog cannot recover the common template, and erases the evidence

Rediaccfile `down()` is conventionally `renet compose -- down -v`
(`packages/json/templates/databases/mysql/Rediaccfile:8-10`), which REMOVES
containers. The sidecar records container IDs (`backup_sync_cold.go:362-374`). On
the crash path `decideSidecarActions` sees `!st.Exists`, treats it as resolved
(`pkg/router/watchdog.go:221-222`) and calls `DeleteRunning` (`:290-294`): no
restart, and the only crash record is destroyed.

Real crash timeline today: ~3s watchdog no-op, then ~3 min reconcile recovery via
`repoHealthy` (`repository_reconcile.go:302-305`) — **and only for repos with an
autostart keyfile.** Non-autostart repos stay down until a human notices.

---

## What quiescing actually buys, honestly

The reflink freezes the LUKS image file. btrfs waits on ordered extents, so the
image's own dirty page cache is captured — but the INNER filesystem's page cache
and journal, above dm-crypt, are not. **A hot chunk-store snapshot is
crash-consistent**: equivalent to pulling the power on the guest.

Note `reflinkSnapshot` (`pipeline_linux.go:396-406`) does **no flush at all**,
unlike the fork primitive which syncfs's the inner mount then the datastore
(`repository_fork.go:326-337`). The hot chunk path is missing that; adding it is a
hot-path fix too.

Cold is GENUINELY REQUIRED for: workloads that do not fsync honestly (Redis with
AOF off, MongoDB `j:false`, Elasticsearch async translog); **cross-repo**
consistency as one point in time; and avoiding recovery cost on restore. The real
value is not the snapshot, it is `down()` giving the container SIGTERM and a
graceful shutdown, so Postgres writes a shutdown checkpoint.

Cold is CEREMONY for a single-repo Postgres/MySQL/etcd at default durability:
crash-consistent is exactly what their recovery is designed for. Say so in `--help`
and price cold honestly, because the operator pays a real outage for it.

Hazard worth naming: cold runs the operator's REAL `down()`, including `-v`, which
removes anonymous volumes.

---

## The design

**Surface: `renet backup snapshot --cold`.** A flag on the existing verb, not a new
one: a separate verb would have to re-implement licence resolution, session URL
derivation, machine-id, session mint, quota refusal, stream mint, `DeclaredBytes`
and exit code 16 — the entire file — and a second copy is how the two silently
diverge. Cold changes exactly WHEN the reflink happens relative to container state.

`--cold` (bool) rather than `--mode cold`: it leaves the existing guard at
`backup-schedule.test.ts:277` (`not.toContain('--mode')`) live.

`rdc backup strategy set` needs NOTHING new: `--mode cold` already validates,
persists and is schema-legal. The only change is that `buildChunkStoreCommand`
stops throwing at `backup-schedule-unit-generator.ts:130-140` and appends `--cold`.

**Datastore-wide barrier, not per-repo.** Per-repo gives a shorter outage each but
destroys cross-repo consistency, which is the main thing cold is for.

```
1. acquire cold lock (exclusive, non-blocking, datastore-wide) — REFUSE if busy
2. discover running repos ∩ selected guids
3. arm the restart guarantee (defer + signal handler, FRESH ctx)
   ── DOWNTIME WINDOW OPENS ──
4. stopColdBackupRepos (concurrent, existing knob)
5. targeted syncfs per mount, then the datastore
6. per guid: chunkstore.StageSnapshot(...)   ← constant-time reflink only
7. startColdBackupRepos (concurrent, FRESH ctx)
   ── DOWNTIME WINDOW CLOSES ──
8. per guid: PlanFromStaging → mint → Upload → Commit   (unchanged)
9. release cold lock
```

Engine split in `pkg/chunkstore/pipeline_linux.go`:
`StageSnapshot` (transient check + repo flock + reflink), `PlanFromStaging`
(buildPlan), and `PlanSnapshot` = the two composed, so the hot path is unchanged.

## Refusals, following the file's own `exclude`/`mode` precedent

Overlapping cold runs; `--cold --dry-run` (a dry run that stops containers is not
dry, one that does not is not cold); `--cold` on a non-Linux build (today
`backup_sync_cold_other.go:34-39` makes stop/start silent no-ops, i.e. a "cold"
backup that is hot); and snapshotting a repo whose quiesce FAILED — today that path
is `Warnf` + continue (`backup_sync_cold.go:150-155`), which under cold silently
produces a hot snapshot.

NOT refused: a cold run where nothing was running. That is a legitimate no-op.

## Proving the downtime claim

Instrument `cold_down`, `cold_sync`, `cold_stage`, `cold_up` with `output.StepTimer`,
and add `cold`, `quiesced`, `quiesceMs`, `coldWindowMs` to `BackupSnapshotRecord`.

**The proof:** on a run with large `bytesUploaded`, `coldWindowMs` must be a small
fraction of `durationMs` and must NOT scale with `bytesUploaded`. Run twice, once
after light churn and once after heavy, and show `coldWindowMs` flat while
`durationMs` and `bytesUploaded` move. That comparison is the whole claim.

## Tests that are evidence, not "the command ran"

- **T1 ordering barrier** (unit, no docker): via the existing `stopOneRepoFn` /
  `restartOneRepoFn` seams plus a new `stageSnapshotFn`, assert per repo
  `idx(down) < idx(stage) < idx(up)` AND `idx(last down) < idx(first stage)`.
  A test that only asserts the command ran passes both orderings; this cannot.
- **T2 content freeze**: write marker A, `StageSnapshot`, write marker B to the live
  image, `PlanFromStaging`; the manifest must reflect A and not B.
- **T3 the real evidence** (ops VM): a container appending a monotonic counter every
  200 ms inside the repo. After `--cold` + restore, the restored file has NO gap and
  ends at k, while the LIVE file has a gap starting at k of width ≈ `coldWindowMs`.
  **The control is the identical fixture under a hot run, which shows no gap.** The
  differential is what makes it evidence that containers were stopped.
- **T4 the dangerous path**: fault injection after down/stage; SIGTERM inside the
  window asserting `UpServices` received a LIVE context (the direct regression test
  for BLOCKER 2); SIGKILL then one watchdog tick and one reconcile tick against a
  `compose down -v`'d repo (the direct test for BLOCKER 3, which fails today).
- **T5 overlap**: the second concurrent run exits non-zero AND stopped nothing.

## Order, and the one sequencing rule that matters

1. Engine split + `OwnsColdBackup` + staging flock + pre-reflink syncfs (T2)
2. Point anchor GC at the new staging flock (`pkg/prune/datastore.go:343-351`,
   `:1094-1112`) — closes a pre-existing hot-path window too
3. **The cold orchestrator — inline, do not delegate. Every failure mode lives here**
4. Verb wiring (`--cold`, refusals, record fields)
5. Crash-recovery fixes (BLOCKER 3)
6. Generator: `mode:'cold'` → `--cold`, raise `TimeoutStopSec` (T6)
7. Contract param + regenerate
8. T1, T4, T5
9. T3 on the ops VM, capturing `coldWindowMs` vs `durationMs` at two churn levels

**Deploy renet BEFORE the generator.** A generator emitting `--cold` against a renet
without the flag dies at cobra flag parse inside a timer at 03:00 — the exact
failure mode already documented at `backup-schedule-unit-generator.ts:156-166`.

i18n cost is zero if the new code follows the file it lives beside:
`backup_snapshot.go` uses no `i18n.T` at all. Keep operator strings plain English.
