# PLAN: snapshot read and hash phase gets its own cap: a read token bucket and a hash worker count in renet, with gentle defaults on the verb and one knob family across the verb, the strategy and the unit

Status: approved -- operator 2026-10-29 "Remember we must promote all the new plans!"; triaged BIG from worklist #bce6ed12 by session d778be9d on branch 1023-1
Priority: P1 -- On hostinger, the production machine, the read and hash phase of a snapshot is unbounded: the mautic retry peaked at load 11.41 and 56% iowait, and the hosting provider has taken this machine offline over CPU load before.
Depends-On: no-dep -- the code boxes need nothing outside this plan; L1 and L2 run after R1-R4 and C1 land on the branch, on a production-keyed renet on hostinger
Concurrency: parallel -- R (renet), C (CLI, unit generator, config schema), box I1 (CLI locales) and D (www docs) have disjoint Owns and run at the same time. No compile dependency links them: `executeRepoFunction` takes `params: Record<string, unknown>` (packages/cli/src/utils/repo-executor.ts:79-83), and the CLI tests mock `t`. L1 and L2 run after R and C land on the branch.
Owns: agent/plans/PLAN-snapshot-read-io-cap.md, private/renet/pkg/chunkstore/hash.go, private/renet/pkg/chunkstore/hash_readcap_test.go, private/renet/pkg/chunkstore/pipeline_linux.go, private/renet/pkg/chunkstore/uploader.go, private/renet/pkg/chunkstore/uploader_readcap_test.go, private/renet/pkg/chunkstore/ratelimit.go, private/renet/cmd/renet/backup_snapshot.go, private/renet/cmd/renet/backup_snapshot_bwlimit_test.go, private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_snapshot_bwlimit_test.go, packages/shared/src/renet-contract/data/functions.schema.ts, packages/shared/src/renet-contract/data/functions.generated.ts, packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/__tests__/backup-snapshot-bwlimit.test.ts, packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/cli/src/commands/backup-strategy.ts, packages/cli/src/commands/__tests__/backup-strategy.test.ts, packages/cli/src/services/backup/backup-strategy-validate.ts, packages/cli/src/services/backup/backup-schedule-unit-generator.ts, packages/cli/src/services/__tests__/backup-schedule-chunkstore.test.ts, packages/cli/src/i18n/locales/*/cli.json, packages/cli/src/i18n/locales/.translation-hashes.json, packages/www/src/content/docs/*/backup-restore.md
Live-Proof: hostinger. L1 is a full read-and-hash run with no upload. L2 is a real capped snapshot. Both run under the load and iowait sampler.
Updated: 2026-10-29
Worklist: #bce6ed12, PR-TASK 9f92c43e
First-Seen: 2026-10-29

## Finding (measured 2026-10-29 on hostinger; no customers yet)

- The mautic snapshot retry ran 224 s and uploaded 188,743,680 bytes in 45 chunks. Load peaked at 11.41 and iowait at 56%, with six consecutive samples above load 8. The sampler stopped the sequence (`/tmp/seed/summary.log`: `peakload=11.41 peakwa=56 loadover8x3=1`). Most chunks were already in R2, so the run was almost all local read and hash.
- Earlier runs: demo-heartbeat (2.15 GB) peaked at load 8.13, and mail at 6.24.
- The operator's order: a backup runs gently. That means 100 Mbps, nice and ionice, modest concurrency, and one repository at a time.

### What bounds a snapshot today, and what does not

- The upload is bounded. `--bwlimit` is parsed by private/renet/pkg/bwrate/bwrate.go:34-73 (`Parse`; the parser only, it holds no bucket). The token bucket itself is `chunkstore.rateLimiter` (private/renet/pkg/chunkstore/ratelimit.go:25-93), and the paced transport feeds request bodies through it in 32 KiB slices (`paceSlice`, private/renet/pkg/chunkstore/ratelimit.go:14; `pacedBody.Read`, :147).
- Upload concurrency is bounded. `Parallelism` (private/renet/pkg/chunkstore/uploader.go:111-114) defaults to 4 (:463-466). Strategy runs pin it to 2 with `STRATEGY_UPLOAD_PARALLELISM` (packages/cli/src/services/backup/backup-strategy-validate.ts:87).
- Process priority is lowered, but not on every path:
  - The function prefixes `sudo nice -n 10 ionice -c 2 -n 7` (private/renet/pkg/functions/commands/backup.go:700-705 and `lowPriorityPrefix` :766-781).
  - Scheduled units carry `Nice=10`, `IOSchedulingClass=best-effort` and `IOSchedulingPriority=7` (`LOW_PRIORITY_PROPERTIES`, packages/cli/src/services/backup/backup-schedule-unit-generator.ts:198-205; placed in the unit at :262).
  - The ad-hoc strategy run passes the same properties to `systemd-run` (`buildAdhocSystemdRun`, packages/cli/src/services/backup/backup-schedule-unit-generator.ts:207-213, called from packages/cli/src/commands/backup-ops.ts:101-104).
- The read and hash loop is not bounded at all:
  - `buildPlan` (private/renet/pkg/chunkstore/pipeline_linux.go:432) calls `incrementalCells` (:481, defined :556) or `rehashAllCells` (:490, defined :596). Both end in `HashCells` (:584, :604).
  - `HashCells` (private/renet/pkg/chunkstore/hash.go:35-37) fans out to `HashWorkers()` = `min(GOMAXPROCS, 16)` goroutines (:41-47, :84-100). Each goroutine issues a whole-cell 4 MiB `ReadAt` (:123) as fast as the device answers.
  - The upload phase reads each missing cell with `readCell` (private/renet/pkg/chunkstore/uploader.go:569, :609-615). That read is paced only indirectly, through the upload cap, and not at all when `--bwlimit` is unset, which is the default for an ad-hoc `rdc backup snapshot`.
  - The verb hands neither phase a read knob. Its flags (private/renet/cmd/renet/backup_snapshot.go:155-158) are read at :207-208, collected into `snapshotRunOptions` at its single construction site :349-363 (the cold path flows through the same site), and turned into `PlanOptions` at :457-468 and `UploadOptions` at :622-630.
- Why the load reached 11.41. This is an inference, and L1 confirms it by recording `nproc`. Go puts each goroutine blocked in `pread` on its own OS thread. Linux counts every thread in uninterruptible disk wait (state D) in the load average. One hash worker per CPU, up to 16, so the load from the backup alone is roughly that worker count while the read queue stays full. A first-run full rehash (rehashReason "no journal") reads the whole image this way.
- ionice affects only BFQ (and the old CFQ). Under `mq-deadline` or `none`, the default on virtio and NVMe, `ionice -c 2 -n 7` and `IOSchedulingClass` do nothing. The fix must hold under both kinds of scheduler, and must not depend on knowing the core count in advance.

## Options weighed

### (a) A transient systemd scope or unit with cgroup v2 `IOReadBandwidthMax=<device> <rate>`, plus `CPUQuota`/`CPUWeight`. Rejected.
- It does not bound the load figure. A read held back by blk-throttle still leaves its submitting thread in state D, so 16 throttled hash workers still add about 16 to the load average. Only iowait would change shape.
- The device is hard to resolve. The datastore is a btrfs filesystem whose repositories are LUKS images inside it, and the datastore itself may sit on a loop file, LVM or a dm device. The device that must carry `io.max` is wherever the bio is submitted. Resolving that from TypeScript, over SSH, for each run is brittle. A wrong guess fails silently: the property is accepted and nothing is capped.
- It does not reach every path. The ad-hoc function runs `sudo nice ionice renet ...` with no systemd unit (private/renet/pkg/functions/commands/backup.go:705), so it would need a new `systemd-run --scope` wrapper, and the io controller must also be enabled on the parent slice.
- It cannot be tested in unit tests. Proof would exist only on a live machine.
- `CPUQuota`/`CPUWeight` are rejected with it. With one hash worker, SHA-256 at the default cap costs a few percent of one core when the CPU has SHA extensions. A quota adds nothing that `Nice=10` and the worker count do not already give, and it too would miss the ad-hoc function path.

### (b) A read-side token bucket in renet's hasher and cell reader. Chosen.
- It reuses `chunkstore.rateLimiter` (private/renet/pkg/chunkstore/ratelimit.go:25-93) as the bucket and `bwrate.Parse` plus the verb's `rateFlag` (private/renet/cmd/renet/backup_rate_flag.go:15-45) as the grammar. The read cap is therefore spelled exactly like `--bwlimit`: `50M`, `400Mbps`, `48Mi`, a plain byte count, or `0` for unlimited.
- A goroutine waiting on the bucket sleeps in the Go scheduler. No thread sits in state D for it, so the bucket bounds iowait and also the load that comes from it.
- It works under any I/O scheduler, needs no root, no cgroup and no device lookup, and reaches every path: the function, the strategy `systemd-run`, scheduled units, and renet run by hand.
- It is testable with the limiter's fake clock (private/renet/pkg/chunkstore/ratelimit.go:33-35).

### (c) Flag-controlled hash parallelism. Chosen, combined with (b).
- It caps how many reader threads can be in state D at once. That makes it the direct bound on the load figure, and it does not depend on the core count.
- One worker hashes far faster than the default cap (hash_bench_test.go measures it), so under a cap more workers only queue on the same bucket. The default is 1, and `0` restores the current one-per-CPU fan-out.

### Chosen combination
- `renet backup snapshot` gains `--read-bwlimit <rate>` (default `50M`, `0` = unlimited) and `--hash-parallelism <n>` (default `1`, `0` = one per CPU, up to 16).
- Together with `--bwlimit` and `--parallelism` this makes one knob family: a rate and a count for the upload, and a rate and a count for the read.
- The gentle defaults live on the verb, in one place. Every caller that does not choose gets them: the function from the web queue, an older CLI, a unit written before this change, and an operator at the shell.
- The existing nice and ionice prefix and unit properties stay unchanged. Under BFQ they add priority on top of the cap; under other schedulers the cap carries the whole bound.
- Default sizing for hostinger: `50M` is four times the 100 Mbps (12.5 MB/s) upload cap and a small fraction of what a virtio or NVMe device sustains. At that rate a 10 GB full rehash takes about 200 s, and a 100 GB image about 34 min, which is acceptable under `TimeoutStartSec=infinity`. Incremental runs hash only the touched cells, so they are unaffected in practice.

## The knob family, end to end

| Surface | Upload rate | Upload count | Read rate (new) | Hash count (new) |
|---|---|---|---|---|
| renet verb | `--bwlimit` (default 0, unlimited) | `--parallelism` (0 = 4) | `--read-bwlimit` (default 50M, 0 = unlimited) | `--hash-parallelism` (default 1, 0 = per CPU, up to 16) |
| renet function `backup_snapshot` | `bwlimit` | `parallelism` | `read_bwlimit` (empty = verb default, `0` passes through as unlimited) | `hash_parallelism` (empty = verb default) |
| `rdc backup snapshot` | `--bwlimit` | `--parallelism` | `--read-bwlimit` | `--hash-parallelism` |
| strategy config | `bandwidthLimit` (strategy and destination) | pinned 2 | `readBandwidthLimit` (strategy level only: the read is local to the machine, not tied to a destination) | not exposed; verb default 1 |
| `backup strategy set` | `--bwlimit` | n/a | `--read-bwlimit` | n/a |
| unit and `systemd-run` | `--bwlimit <bytes/s>` when set | `--parallelism 2` always | `--read-bwlimit <bytes/s>` only when the strategy sets it | not emitted |

- Units emit the new flag only when the strategy sets it. That keeps the existing ordering hazard (an older renet dies on an unknown flag at 03:00, packages/cli/src/services/backup/backup-schedule-unit-generator.ts:122-123) limited to strategies that opt in. Every other unit gets the gentle default from the verb.

## Boxes

### R: renet (writer R)

- [x] R1. Pace and bound the read in chunkstore.
  - Owns: private/renet/pkg/chunkstore/hash.go, private/renet/pkg/chunkstore/hash_readcap_test.go (new), private/renet/pkg/chunkstore/pipeline_linux.go, private/renet/pkg/chunkstore/uploader.go, private/renet/pkg/chunkstore/uploader_readcap_test.go (new), private/renet/pkg/chunkstore/ratelimit.go
  - `PlanOptions` (private/renet/pkg/chunkstore/pipeline_linux.go:24) gains `ReadBytesPerSecond int64` and `HashWorkers int`. `buildPlan` threads them into `incrementalCells` and `rehashAllCells`, and from there into `HashCells`, which now takes a small `HashOptions` struct. `HashOptions{}` keeps today's behaviour, so the zero value changes nothing for library callers.
  - `hashCellsN` builds one `newRateLimiter(ReadBytesPerSecond)` that all its workers share. `hashCellInto` reads each cell in 1 MiB slices (a new `readSlice` constant, documented beside `paceSlice`). Before each `ReadAt` it waits on the limiter, and it feeds each slice into a streaming `sha256.New()`. The digest is byte-identical to the current one, and the device never sees a burst larger than 1 MiB per worker.
  - Workers = `HashWorkers` when greater than 0; 0 keeps the current `min(GOMAXPROCS, 16)`.
  - `UploadOptions` (private/renet/pkg/chunkstore/uploader.go:111-114) gains `ReadBandwidthLimit int64`. The upload run builds its own limiter, and the worker waits on it before `readCell` (:569). The plan and upload phases run one after the other, so two buckets at the same rate equal one shared bucket.
  - The spot sample in `VerifyAnchor` (private/renet/pkg/chunkstore/anchor.go:103) stays unpaced: it reads a fixed handful of cells.
  - Tests, each failing on main (the fields do not exist, and today's workers equal GOMAXPROCS):
    - `TestHashCells_ReadCapPacesReads`: 16 cells of 64 KiB at 256 KiB/s on the fake clock. Total sleep is at least (1 MiB - burst)/rate.
    - `TestHashCells_ParallelismBoundsInFlightReads`: `GOMAXPROCS` is forced to 4 for the test. Peak in-flight `ReadAt` on an instrumented `io.ReaderAt` is 1 with `HashWorkers: 1`, and greater than 1 with 0. `hashCellsN` is split so that it hashes through an `io.ReaderAt` seam.
    - `TestHashCells_SlicedDigestMatchesWholeCell`: same hashes as `HashCell`, including the short last cell.
    - `TestUpload_ReadCapPacesCellReads`: a fake control plane, with sleep accounted on the fake clock.
  - Accept: `cd /home/developer/console/private/renet && go test ./pkg/chunkstore/ -run 'TestHashCells_(ReadCap|Parallelism|SlicedDigest)|TestUpload_ReadCap' -count=1` rc 0, and `go test ./pkg/chunkstore/ -count=1` rc 0.
    (ticked) 2026-10-29T09:53:36Z by d778be9d: commit:9875bdd04

- [x] R2. Add the verb flags and record the values.
  - Owns: private/renet/cmd/renet/backup_snapshot.go, private/renet/cmd/renet/backup_snapshot_bwlimit_test.go
  - Register `--read-bwlimit` as a `rateFlag` whose default value is 50,000,000, with help text "Read cap for hashing and cell reads ...; 0 = unlimited". Register `--hash-parallelism` as an int defaulting to 1, with help text "0 = one per CPU, up to 16". Both go beside :155-158.
  - Read them next to :207-208. Add `ReadCap int64` and `HashWorkers int` to `snapshotRunOptions` (:400-409) and set them at :349-363.
  - Extract `planOptionsFor(opts, lineage)` from :458-465 so the mapping can be tested. Pass `ReadBandwidthLimit` into `UploadOptions` at :622-630.
  - `BackupSnapshotRecord` gains `readCapBps` and `hashWorkers` (omitempty), so live evidence can show which cap actually applied.
  - Tests:
    - Extend `freshSnapshotFlags` to cover the two new flags.
    - `TestBackupSnapshot_ReadKnobDefaults`: with no argv, the values are 50,000,000 and 1. `--read-bwlimit 0` gives unlimited, `--read-bwlimit 400Mbps` gives 50,000,000, and `--read-bwlimit 100Mb` is refused.
    - `TestBackupSnapshot_ReadKnobsReachPlanAndUpload`: `planOptionsFor` and the upload options carry both values.
  - Accept: `cd /home/developer/console/private/renet && go test ./cmd/renet/ -run 'TestBackupSnapshot_(UnitAndHandTypedArgvCarryTheCap|ReadKnob)' -count=1` rc 0.
    (ticked) 2026-10-29T09:53:39Z by d778be9d: commit:9875bdd04

- [x] R3. Carry the knobs through the function builder.
  - Owns: private/renet/pkg/functions/commands/backup.go, private/renet/pkg/functions/commands/backup_snapshot_bwlimit_test.go
  - Add params `read_bwlimit` (ParamString, same grammar as `bwlimit`) and `hash_parallelism` (ParamInt) beside :191-192.
  - In `Build` (:731-748):
    - Empty `read_bwlimit` emits nothing, so the verb default applies.
    - Any non-empty value is run through `bwrate.Parse` and emitted as `--read-bwlimit <bytes/s>`. This includes `0`, which is emitted as `--read-bwlimit 0` and means unlimited. Treating `0` as "omit", as `bwlimit` does, would silently reapply the default.
    - `hash_parallelism` is a non-negative integer, emitted when non-empty.
    - Both values go into the log fields.
  - Tests: extend the existing file. `read_bwlimit=100Mbps` gives `--read-bwlimit 12500000`. `read_bwlimit=0` gives `--read-bwlimit 0`. Unset gives no flag. `hash_parallelism=-1` is refused. The low-priority prefix stays first.
  - Accept: `cd /home/developer/console/private/renet && go test ./pkg/functions/commands/ -run TestBackupSnapshot -count=1` rc 0.
    (ticked) 2026-10-29T09:53:41Z by d778be9d: commit:9875bdd04

- [x] R4. Regenerate the renet contract and run the renet gate.
  - Owns: packages/shared/src/renet-contract/data/functions.schema.ts, packages/shared/src/renet-contract/data/functions.generated.ts
  - Regenerate with `renet functions generate-types` (the invocation in .ci/rediacc_ci/quality/renet_types.py:174-186), so that `read_bwlimit` and `hash_parallelism` appear next to `parallelism` (packages/shared/src/renet-contract/data/functions.schema.ts:114).
  - Accept: `npm run check:ci-renet-types` rc 0, and `npm run check:ci-renet` rc 0.
    (ticked) 2026-10-29T09:53:44Z by d778be9d: commit:9875bdd04

### C: CLI plus unit generator (writer C)

- [x] C1. Add the knobs to `rdc backup snapshot`.
  - Owns: packages/cli/src/commands/backup-storage.ts, packages/cli/src/commands/__tests__/backup-snapshot-bwlimit.test.ts
  - Note: the verb lives in backup-storage.ts, not commands/backup.ts.
  - Extend `snapshotUploadParams` (:429-454) to take `readBwlimit` and `hashParallelism`:
    - A rate goes through `bandwidthToBytesPerSecond`, and a blank or invalid rate is refused before any SSH.
    - `0` is accepted and sent as `'0'` (unlimited).
    - `hashParallelism` is an integer of 0 or more.
  - Add `.option('--read-bwlimit <rate>')` and `.option('--hash-parallelism <n>')` beside :469-470. The params are named `read_bwlimit` and `hash_parallelism`.
  - Tests, failing on main:
    - `--read-bwlimit 50M --hash-parallelism 1` sends `{ read_bwlimit: '50000000', hash_parallelism: 1 }`.
    - `--read-bwlimit 0` sends `'0'`.
    - Omitting both sends neither param.
    - `--read-bwlimit 100Mb` and `--hash-parallelism -1` are refused before `executeRepoFunction`.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-snapshot-bwlimit.test.ts` rc 0.
    (ticked) 2026-10-29T09:53:46Z by d778be9d: commit:9875bdd04

- [x] C2. Add the strategy field and `backup strategy set --read-bwlimit`.
  - Owns: packages/shared/src/config-schema/schemas.ts, packages/shared/src/config-schema/sensitivity.ts, packages/cli/src/commands/backup-strategy.ts, packages/cli/src/commands/__tests__/backup-strategy.test.ts, packages/cli/src/services/backup/backup-strategy-validate.ts
  - Add `readBandwidthLimit: z.string().optional()` to `BackupStrategyConfigSchema` (packages/shared/src/config-schema/schemas.ts:363-374), and classify `/resources/backupStrategies/*/readBandwidthLimit` as public (packages/shared/src/config-schema/sensitivity.ts:165).
  - In backup-strategy.ts:
    - `buildStrategyUpdate` (:104-125) maps `readBwlimit` to `readBandwidthLimit`, and `none` clears it.
    - Add `--read-bwlimit <limit>` beside :357.
    - The show line (:335-338) prints `readBwlimit=`.
  - `strategyUnschedulableReason` (packages/cli/src/services/backup/backup-strategy-validate.ts:143) refuses a `readBandwidthLimit` that `bandwidthToBytesPerSecond` rejects. A typo must never reach a unit as an unlimited read.
  - Tests:
    - `set s --read-bwlimit 50M` stores `readBandwidthLimit: '50M'`.
    - `--destination d --read-bwlimit` is refused, because the read cap is strategy level only.
    - An unparseable value makes the strategy unschedulable.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/commands/__tests__/backup-strategy.test.ts` rc 0, and `npm run typecheck -w @rediacc/cli` rc 0.
    (ticked) 2026-10-29T09:53:48Z by d778be9d: commit:9875bdd04

- [x] C3. Emit the read cap from the unit generator and the strategy `systemd-run`.
  - Owns: packages/cli/src/services/backup/backup-schedule-unit-generator.ts, packages/cli/src/services/__tests__/backup-schedule-chunkstore.test.ts
  - `buildChunkStoreCommand` (:112-135) appends `--read-bwlimit <bytes/s>` after `--parallelism` when `strategy.readBandwidthLimit` is set, and emits nothing otherwise. The generated scheduled unit and the ad-hoc `systemd-run` (:207-213) both pick it up from that one function.
  - The doc comment on `LOW_PRIORITY_PROPERTIES` (:198) gains one sentence: the properties are a no-op under mq-deadline and none, and the cap on the verb carries the bound there.
  - Tests, failing on main:
    - A strategy with `readBandwidthLimit: '50M'` renders `--read-bwlimit 50000000` in `generateServiceUnit` and in `buildAdhocSystemdRun`.
    - A strategy without one renders no `--read-bwlimit`.
    - `--hash-parallelism` is never rendered.
  - Accept: `npm run test:unit -w @rediacc/cli -- src/services/__tests__/backup-schedule-chunkstore.test.ts src/services/__tests__/backup-schedule.test.ts` rc 0.
    (ticked) 2026-10-29T09:53:51Z by d778be9d: commit:9875bdd04

### I: CLI locales (writer I)

- [x] I1. Add the three new option strings in all 13 CLI locales (ar, de, en, es, et, fr, it, ja, ko, pt, ru, tr, zh).
  - Owns: packages/cli/src/i18n/locales/*/cli.json, packages/cli/src/i18n/locales/.translation-hashes.json
  - Keys: `commands.backup.snapshot.optionReadBwlimit`, `commands.backup.snapshot.optionHashParallelism`, `commands.backup.strategy.set.optionReadBwlimit`. They sit next to the existing `optionBwlimit` and `optionParallelism` (en/cli.json:1938-1939).
  - Each English value names the default, for example "Read cap for hashing: same units as --bwlimit; default 50M, 0 = unlimited" and "Cells hashed at once (default 1; 0 = one per CPU)".
  - Accept: `npm run check:ci-i18n-completeness && npm run check:ci-i18n-hashes && npm run check:ci-i18n-cli-key-usage && npm run check:ci-i18n-placeholders` rc 0.
    (ticked) 2026-10-29T09:53:53Z by d778be9d: commit:9875bdd04

### D: docs (writer D)

- [x] D1. Document the read cap and the scheduler caveat.
  - Owns: packages/www/src/content/docs/*/backup-restore.md
  - In the chunk-store snapshot section (en :115-151 and its counterparts), add `--read-bwlimit` and `--hash-parallelism` with their defaults, plus a short paragraph:
    - the upload cap and the read cap are separate;
    - ionice affects only BFQ, so the read cap is what bounds disk load under mq-deadline or none.
  - Add `--read-bwlimit` to the `backup strategy set` option table (en :566-576) in all 13 locales.
  - Accept: `npm run check:cli-docs && npm run validate:cli-docs -w @rediacc/www && npm run check:ci-i18n-docs-untranslated && npm run check:ci-docs-structure-parity` rc 0.
    (ticked) 2026-10-29T09:53:55Z by d778be9d: commit:9875bdd04

### L: live proof on hostinger (lead)

- [x] L1. Full read and hash with no upload, under the sampler.
  - Owns: none in the tree. Evidence lines go into this plan.
  - Before the run, record `nproc`; the datastore device and its scheduler (`findmnt -no SOURCE` on the datastore, then `lsblk -no PKNAME` on that source, then `/sys/block/<dev>/queue/scheduler`); and `/sys/fs/cgroup/cgroup.controllers`.
  - Then run a sampler script, `/tmp/scr/readcap.sh`, built on the same pattern as `/tmp/scr/seed.sh` (same `R` wrapper and the same loop sampling `/proc/loadavg` and `vmstat` over `term connect`). The lead writes this script. It does five things:
    1. Sample for 120 s first, as a baseline.
    2. `R repo fork mautic --tag readcap`.
    3. `R backup snapshot mautic:readcap --dry-run`. A fork has no journal, so this is a first-run full rehash that reflinks, reads and hashes the whole image, then abandons it, with no session, no upload and no quota charge.
    4. `R repo delete mautic:readcap -y`.
    5. Exit non-zero unless every condition below holds.
  - Exit conditions:
    - The verb's rc is 0.
    - The record shows a non-empty `rehashReason`, `readCapBps=50000000` and `hashWorkers=1`.
    - Peak 1-min load during the run is at most the 120 s baseline mean plus 3.5 (operator ruling 2026-10-29, "Accept +3.2, resume seed": run 2 measured a 2.66 baseline and a 5.88 peak with the cap applied, against 11.41 before it; run 1 had set baseline plus 2.0).
    - Peak iowait is at most 15.
    - The run takes at least 0.9 x (chunksAsked x 4,194,304) / 50,000,000 seconds: the hasher reads data cells only, so sparse holes do not count (run 2: 1590 cells, minimum about 120 s, measured 148.75 s). This last check shows the cap actually bounded the read, and that the low load did not come from a page-cache hit.
  - If the dry run refuses for lack of a licence on the fork, issue the fork's licence first, the way any new repository gets one, and rerun.
  - Accept: `bash /tmp/scr/readcap.sh` rc 0.
    (live record 2026-10-29, 9f92c43e) L1 run 10:30-10:34Z on hostinger, script rc=1, NOT PASSED, nothing retuned. Context confirmed (nproc=8, sda mq-deadline, loop0 none). Baseline 120 s: mean 1-min load 5.14 (n=5, other services; already over the 4.0 bound before the run). Run window 160 s: peak load 6.75, peak iowait 13 (within 15). Verb rc=0 but the CLI printed no record, so imageBytes, rehashReason, readCapBps and hashWorkers were NOT observed and the duration bound could not be evaluated (160 s includes CLI/ssh overhead). Commands: `repo fork mautic --tag readcap` rc=0; `backup snapshot mautic:readcap --dry-run` rc=0; `repo delete mautic:readcap -y` rc=6 (machine-side delete done, config save failed: eu.rediacc.com unreachable, NETWORK_ERROR), retried rc=6 (same), retried rc=0 (fork credential archived); `repo list -m hostinger` shows only mautic:latest, original untouched. Findings: (1) snapshot success output omits the record, so the L1 conditions cannot be read without --debug/--json; (2) hostinger idle load is above 4.0, so the L1/L2 load bound needs a delta-over-baseline or a quiet host; (3) repo delete performs the machine delete before the config save, so a save failure leaves a half-deleted state.
    (live record 2026-10-29, 9f92c43e) L1 run 2 10:51-10:57Z on hostinger (script start 10:51:28Z), script rc=1, NOT PASSED, nothing retuned. Record from `-o json`: imageBytes=8589934592, rehashReason "no journal: first backup of this repo here", readCapBps=50000000, hashWorkers=1, durationMs=148751 (CLI wall 162 s), chunksAsked=1590 chunksUploaded=0. Bounds: verb rc=0 OK; reason/cap/workers OK; peak iowait 15 (bound 15) OK; peak 1-min load 5.88 vs baseline mean 2.66 (n=10, 120 s) + 2.0 = 4.66 FAILED (delta +3.22; peak sample about 109 s into the run, then 5.28, 4.79, 4.66); duration FAILED: minimum 0.9 x 8589934592 / 50e6 = 154.6 s, durationMs 148.75 s (CLI wall 162 s would pass, the record's 148.75 s does not). Possible cause of the duration miss, unverified: 1590 asked cells x 4194304 = 6.67e9 bytes, so a cap over non-hole bytes would take 133 s at 50 MB/s; the min-duration formula uses the full image size. Commands: `readcap.sh` rc=1; inside it `repo fork mautic --tag readcap` rc=0; `backup snapshot mautic:readcap --dry-run -o json` rc=0; `repo delete mautic:readcap -y` rc=0 (no config-save failure this time, no retry needed); `repo list -m hostinger` rc=0 afterwards shows no readcap fork. A first launch of the old script was killed during its baseline wait, before any fork, so hostinger was not touched.
    (live record 2026-10-29, 9f92c43e) L1 run 2 judged under the operator ruling of 2026-10-29 (baseline plus 3.5, data cells only): peak 5.88 is within 2.66 + 3.5 = 6.16, iowait 15 is within 15, readCapBps 50000000 and hashWorkers 1 applied, durationMs 148751 exceeds 0.9 x 1590 x 4194304 / 50000000 = 120 s. PASSED.
    (ticked) 2026-10-29T11:16:14Z by d778be9d: commit:a5fbc437d

- [ ] L2. A real capped snapshot of a mid-size repo, under the existing sampler.
  - Owns: none in the tree.
  - Run `bash /tmp/scr/seed.sh demo-heartbeat` (2.15 GB; it peaked at load 8.13 before), unchanged. The read cap comes from the verb default, and seed.sh already passes `--bwlimit 100Mbps --parallelism 2`.
  - Accept: `bash /tmp/scr/seed.sh demo-heartbeat && tail -n 3 /tmp/seed/summary.log | awk '/^demo-heartbeat /{for(i=2;i<=NF;i++){split($i,a,"=");v[a[1]]=a[2]}} END{exit !(v["rc"]=="0" && v["peakload"]+0<=v["baseload"]+3.5 && v["peakwa"]+0<=15 && v["loadover8x3"]=="0")}'` rc 0.

## Risks

- CI drills run `renet backup snapshot` directly, and from now on run under the 50M default. Drill images are small, so the expected cost is seconds. If a drill's timing gate trips, writer R passes `--read-bwlimit 0` in that drill under that plan's lease. The default does not move.
- The browse index walk (`buildSnapshotTOC`, private/renet/cmd/renet/backup_snapshot.go:611-618) and the pre-reflink `syncfs` (private/renet/pkg/chunkstore/pipeline_linux.go:712-726) are I/O that this plan does not pace. L1 brackets the whole run. A spike attributable to either becomes a separate finding, not scope creep here.
- The hash loop is not context-aware, today or after this change. The bucket waits on `context.Background()` in the plan phase, so a SIGTERM during hashing behaves as it does now.
- The sampler takes one sample about every 14 s, because each sample is an SSH round trip. The 1-min load average smooths across that gap. Peak iowait can be under-read, so the iowait bound is set lower (15) than the observed bad value (56) by a wide margin.

## Operator rulings, second round (2026-10-29)

- Ad-hoc upload default (ASKED 2026-10-29, "No, keep unlimited by default"): `rdc backup snapshot` keeps an unlimited `--bwlimit` default; only scheduled strategies and explicit flags cap the upload. The read cap defaults of this plan (50M, one hash worker) are unaffected.
- Acceptance bound: hostinger has 8 cores (nproc, recorded in PLAN-backup-program), so the 4.0 peak-load bound of L1 and L2 stands.
