# PLAN: CPU-aware scheduling for ci:quick
Status: active -- operator-approved direction 2026-09-30 (worklist #4f56fcee); designed by a Plan agent, verified figures below
Depends-On: no-dep -- the runner, its duration cache and the lane-durations refresh pattern all exist today
Owner: d778be9d
First-Seen: 2026-09-30
Date: 2026-09-30
Priority: P2 -- local feedback speed; nothing in CI depends on it
Concurrency: exclusive -- it rewrites the pool every local gate run goes through
Owns: scripts/ci-runner/pool.ts, scripts/ci-runner/exec.ts, scripts/ci-runner/run.ts, scripts/ci-runner/report.ts, scripts/ci-runner/sim.ts, scripts/ci-runner/manifest.ts, .ci/rediacc_ci/ci/gate_costs.py, .ci/config/gate-costs.json

## 1. Problem, measured

- The operator watches Task Manager (WSL2, 24 logical cores) during `npm run ci:quick`: every core busy early, then fewer.
- Last run: 286 gates, wall 41.0 s, serial 818.5 s, 20.0x on 22 slots (scripts/ci-runner/run.ts:1199 sets `availableParallelism() - 2`); longest gate 18.3 s. No CPU time is measured; the per-gate /proc sampler (scripts/ci-runner/exec.ts:96-124) is the only CPU evidence.
- From the push-clone resource capture (285 gates, 47.0 s span): gates' CPU is at least 813.7 core-seconds, so the CPU floor on 24 cores is at least 33.9 s; busy cores by 4 s bucket run 18.3-19.8, then 18.1, 17.2, 16.0, 12.1, 6.5. About 80% while the pool is full, then a tail.
- The tail is ordering: `expected()` ranks by wall only (scripts/ci-runner/pool.ts:232-238). `check:test-shared` uses 32.8 cpu-s over 4.7 s wall (6.9 cores) and started at 42.2 s, last. 46 gates run under 0.5 cores yet cost a full slot; 6 gates at 1.5+ cores cost one slot unless someone hand-wrote `weight` (35 declarations in scripts/ci-runner/manifest.ts).
- The push recipe runs `npm run -s build` (8 s warm) and doc-region parity (14 s) serially before ci:quick: 63 s end to end. Parity stays out of `--quick` only through `slow: true` (scripts/ci-runner/manifest.ts:2150); its CI step p90 is 8.0 s.
- Ceiling: the pool from 41 s to about 36 s (floor max(CP 18.3 s, CPU 34 s)); the push recipe from 63 s to about 40 s once the pre-steps join the pool, the larger win.

## 2. Design

### 2.1 Measure CPU per gate
- scripts/ci-runner/exec.ts:83-87 spawns `bash -c 'trap "times >&3" EXIT; eval "$1" 3>&-' _ <run>`; bash's `times` second line is the user+sys of every reaped descendant (RUSAGE_CHILDREN). fd 3 is closed for the gate's descendants so a daemon holding it cannot delay `close` (scripts/ci-runner/exec.ts:151). `cpuMs` joins ExecOutcome (scripts/ci-runner/exec.ts:17-28) and GateResult (scripts/ci-runner/pool.ts:91-106).
- The EXIT trap disables bash's exec-last-command, so a signal-killed gate exits 128+n: scripts/ci-runner/exec.ts:151-153 maps code > 128 to the existing signal message (selftest control: `kill -9 $$`). Exit 77 (scripts/ci-runner/pool.ts:89) is unaffected.
- Peak memory from the sampler's own per-gate jsonl (max over ticks of summed rss_kb; double-counts shared pages, which errs conservative).
- A sampler CPU total above `times` by more than 20% flags `undercount` (unreaped descendants) and the larger value is used.
- Linux/WSL2 exact; macOS has `times` but no RSS; Windows-native Git Bash uses wall only.
- DurationRecord (scripts/ci-runner/run.ts:479-483) gains `cpu` and `rssMb` (last 5 passing runs), carried by loadDurationRecords and saveDurations (scripts/ci-runner/run.ts:485-538), which today would drop them.

### 2.2 Pack against a core budget (`--sched cores|slots`, `slots` kept for A/B and rollback)
- C = `availableParallelism() - 1`; epsilon 10%; K = 2C concurrent processes; M = 0.75 x MemAvailable at start.
- A gate's cores d(g) = clamp(median cpu_s / min recent wall, 0.25, C) (least-contended wall, the floor rule scripts/ci-runner/run.ts:473-477 already uses). Unmeasured: `weight ?? 1`; memory 4 GB if `heavy`, else 0.5 GB. Source order: local, then baseline x speed factor (2.5), then hand weight.
- Priority key = max(bottom level over `needs`, cpu_s): 1-core gates reduce to today's longest-first; a wide gate like check:test-shared moves to the first wave.
- Admit g if needs and claims pass (scripts/ci-runner/pool.ts:241-243), sum(d) + d(g) <= C(1+epsilon), running < K, sum(m) + m(g) <= M, and no reservation is delayed. EASY backfill: a head gate that does not fit reserves its predicted start; later gates run only if they fit beside it or finish first. The idle branch (scripts/ci-runner/pool.ts:310-318) still admits the head on an empty pool. `heavyLimit` only for unmeasured heavy gates.

### 2.3 Report utilisation
- /proc/stat every 500 ms (os.cpus() off Linux); per-gate readyAt/startAt/endAt and `blockedBy` (cpu, mem, count, claim, reservation).
- Footer lines (scripts/ci-runner/report.ts:100-176): busy %, idle and iowait core-seconds, gates' own CPU; a per-5 s busy-cores strip; `floor max(CP, cpu) ... wall = N x floor`; the top 5 queue delays with their reason. The same fields in `--json` and the receipt.

### 2.4 Fold the push pre-steps into the pool
- Drop `slow: true` from check:ci-doc-region-parity (8.0 s CI step, under the tier line per scripts/gates/check-gate-manifest.ts:73-77, 157-172).
- A `build:cli` node (`needs: ['build:packages']`, `mutex: ['build-artifacts']`, shaped like scripts/ci-runner/manifest.ts:4738-4749) and `needs` edges on each quick gate that reads a dist tree, found empirically: a clean clone with every packages/*/dist removed runs ci:quick, each failing gate gets an edge, the rerun is green.
- The push recipe becomes fetch, submodule update, `ci:quick --receipt-out`; the receipt then vouches for build and parity.

### 2.5 Committed baseline .ci/config/gate-costs.json
- CI runs each gate as its own step, not through the runner, so no CPU exists there today (per-gate wall does: `gate_step_p90_seconds`, .ci/rediacc_ci/ci/budget_report.py:994). A nightly housekeeping job `gate-costs-capture` runs `run.ts --quick --jobs 1 --sched slots --json` (serial, so uncontended) and uploads it.
- Schema: `refreshed_at`, `source`, and per gate `{cpu_s, wall_s, eff_cores, capped, peak_rss_mb, rank}`; `capped` when eff_cores >= 0.9 x runner cores (width not portable).
- `.ci/rediacc_ci/ci/gate_costs.py --refresh|--check` reuses budget_report's fetch_runs/fetch_artifacts (.ci/rediacc_ci/ci/budget_report.py:275, :826), median of the last 5 captures; `--check` reds on more than 25% drift like DRIFT_THRESHOLD (.ci/rediacc_ci/ci/budget_report.py:130), wired beside .github/workflows/housekeeping.yml:224 with its @mention path.
- Blend at load: speed factor s = median of local_cpu_s / base_cpu_s over at least 20 shared gates (else 1.0); est = w x local + (1 - w) x s x base with w = n/(n+2).

### 2.6 Retire hand-written weight and heavy
- scripts/ci-runner/lanes.ts:555-577, 700-702, 730 falls back to `weight` and counts `heavy`: switch its unit-cost fallback to baseline cpu_s first, then delete weight/heavy from measured gates in manifest.ts, trim HAND_ONLY (scripts/gen/gen-manifest.ts:65-72), regenerate gates.lock, and refuse a new `weight` on a measured gate. check:ci-pytest's `weight: 8` stays until measured locally.

## 3. Tests, each with a control
- A pure `admit()` shared by runPool and a new scripts/ci-runner/sim.ts (discrete events, processor sharing when sum(d) > C). Synthetic mix (60 I/O gates d 0.2, 8 wide d 6, 120 one-core, an 18 s chain behind an 8 s build): `cores` cuts idle core-seconds by at least 30% against `slots` with no worse makespan. Controls: all-one-core within 1%; epsilon infinite fires the cap assertion; no reservation starves a d-8 gate; d > C still admitted on an idle pool; two 20 GB gates with M 32 GB never overlap; replaying the measured capture under `slots` lands within 15% of 47.0 s before the simulator is trusted.
- Wrapper: busy `yes` gives cpuMs > 500, `sleep 1` < 100, `kill -9 $$` still a signal, 77 still blocked.
- gate_costs pytest: 24% drift passes, 26% reds, a capped gate's eff_cores drift ignored.
- Folding: the no-dist clean clone is green with the edges and red on the named gates without them.

## 4. Success on this machine
- 5 alternating pairs of `--sched slots` / `--sched cores` in the push clone: busy at least 90% between the first and last 10% of the run (80% today), wall at most 1.10 x floor (about 37-38 s, 41.0 today), check:test-shared in the first wave; the push recipe at 45 s or less (63 s today).

## 5. Open questions (defaults execute)
- Core budget: C = availableParallelism() - 1. Epsilon 10%, K = 2C. Memory 0.75 x MemAvailable; unmeasured heavy 4 GB, else 0.5 GB. Baseline CPU from a nightly serial capture job. Priority max(bottom level, cpu_s), pure bottom level kept as a flag. Parity joins `--quick` for everyone. Laptops: same algorithm, speed factor on baseline-seeded gates only.

## Tasks

- [x] P0 measure only: the rusage wrapper, cpu/rss in the duration cache, the utilisation footer; collect 5 runs
    (ticked) 2026-10-05T09:55:46Z by d778be9d: commit:0564f8067 the rusage wrapper, cpu/rss in the duration cache and the utilisation footer shipped; reconciled by PLAN-prepush-full-cpu PF0
- [x] P1 `--sched cores` behind a flag: admit(), sim.ts, the scheduler tests with controls, the A/B of section 4
    (ticked) 2026-10-05T09:55:48Z by d778be9d: commit:0fdca103a --sched cores with admit(), sim.ts and controls shipped, and is the default since 2026-09-30 (scripts/ci-runner/run.ts:36); reconciled by PLAN-prepush-full-cpu PF0
- [ ] P2 default `cores`; parity leaves `slow`; `build:cli` and the empirical dist edges; the push recipe drops its pre-steps
    (2026-10-05, PLAN-prepush-full-cpu PF0) SHIPPED HALF: `cores` is the default since 2026-09-30 (scripts/ci-runner/run.ts:36). Still open: parity leaving `slow`, the `build:cli` and dist edges, and the push recipe dropping its pre-steps.
- [ ] P3 the nightly gate-costs capture, .ci/config/gate-costs.json from the first --refresh, gate_costs --check in housekeeping
- [ ] P4 lanes.ts on baseline cost, then weight/heavy retired from measured gates
    (2026-10-05, PLAN-prepush-full-cpu PF0) The `weight` half is SUPERSEDED by PLAN-prepush-full-cpu PF1, which replaces `weight` with elastic `cores: {min, max}` granted at admit; lanes.ts balancing without `weight` is that plan's writer F. `heavy` and the baseline-cost balancing stay here.
