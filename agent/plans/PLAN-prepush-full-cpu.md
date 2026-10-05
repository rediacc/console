# PLAN: one-pass pre-push on every core, sized at launch, with no self-contention and no pointless restarts

Status: approved -- operator ruling 2026-10-05: "Shortest possible pre-push cycle with full CPU utilization. A complete change, not easy fixes."; rides PR #595
Owner: d778be9d
First-Seen: 2026-10-05
Depends-On: no-dep -- builds on the shipped cores scheduler (scripts/ci-runner/run.ts:36, the default since 2026-09-30) and the shipped droppedTouched receipt; PLAN-ci-quick-cpu-scheduling.md overlaps in Owns and is reconciled by PF0 rather than awaited
Priority: P0 -- operator order 2026-10-05: pre-push wall close to the critical path, near-zero idle core-seconds, no static worker counts in any local or CI lane (the `(operator)` marker is the operator's to add; the pre-edit guard refuses it from the AI)
Concurrency: parallel -- four writers with disjoint file sets (## Writer split); the overlap with PLAN-ci-quick-cpu-scheduling.md (exclusive, queued, not live) is settled by PF0
Owns: scripts/ci-runner/{pool,run,exec,quick-select,sim,report,gate-spec,typecheck-incremental,lease-client,manifest}.ts, scripts/ci-runner/gates.lock.json, scripts/gen/gen-manifest.ts, package.json, pyproject.toml, conftest.py, .ci/rediacc_ci/{check_pytest,battery,xdist_groups,core_lease,runtmp}.py, .ci/rediacc_ci/quality/{pool_writer_safety,literal_sources}.py, .ci/rediacc_ci/tests/gates/{test_gate_ci_runner,test_gate_shrink_only_composition,test_gate_docs_gen,test_gate_paths_exist,test_gate_gate_anti_vacuity,test_gate_record_paths}.py, .ci/rediacc_ci/tests/{test_canonical_sys_path_hop,test_core_ports,test_core_account,test_testrun_start_account,test_testrun_account_e2e,test_xdist_groups,test_check_pytest_jobs,test_core_lease,test_proxies_go_unit,test_tree_tripwire}.py, .claude/rediacc_hooks/tests/{test_guards_differential,test_guards_process_table,test_hooks_procs,test_settings_collapse}.py, .claude/rediacc_hooks/guards/{block_unverified_push,test-block_unverified_push}.py, .claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl, .ci/policy/{record-paths,fixed-widths}.json, .ci/scripts/quality/check_record_paths.py, .ci/bootstrap.sh, .ci/config/lane-durations.json, .ci/config/shards/quality-pytest.json, scripts/gates/check-lane-budget.ts, docs/agent-reference/ci-gates.md, .claude/skills/testing/hooks.md, agent/plans/PLAN-ci-quick-cpu-scheduling.md
Worklist: (lead adds the epic and item ids when the plan enters the PR)

**Operator rulings, 2026-10-05 (effective now, verbatim where quoted).**
- No static worker counts anywhere in the local or CI lanes. Every parallel tool sizes itself from the cores actually available at launch. This supersedes the "STOP AT 2.08x" ruling recorded on check:ci-pytest in scripts/ci-runner/manifest.ts:5019 (pytest fixed at `-n 8`, `weight: 8` at scripts/ci-runner/manifest.ts:5019); that comment is rewritten to cite this ruling (PF8).
- Target: pre-push wall time close to the longest single gate (the critical path), with near-zero idle core-seconds.
- "Shortest possible pre-push cycle with full CPU utilization. A complete change, not easy fixes." <!-- style-ok -->

## What was true before this plan (HEAD e3005c26d, read for this plan)

This section is the starting point as read at e3005c26d, kept as written; the boxes below record what changed and the After table what it measured.

**The pre-push is two scheduler passes.** The session driver (scratchpad `prepush.sh`) syncs a push clone, runs `npm run ci:quick -- --receipt-out <R>`, reads `droppedTouched` out of the receipt, then runs `run.ts --only <ids> --receipt-out <R>` as a second pass. The first pass cannot start the slow gates because `quickDiffAdmit` (scripts/ci-runner/run.ts:710-784) admits a touched slow gate only inside `QUICK_BUDGET_MS = 90_000` (scripts/ci-runner/quick-select.ts:6). Everything over budget becomes a `droppedTouched` entry with an `--only` command (scripts/ci-runner/run.ts:753-759, 787-789). The second pass merges into `droppedVerified` (scripts/ci-runner/run.ts:2288-2339, `mergeDroppedVerified` at scripts/ci-runner/run.ts:2290).

**The scheduler fixes each gate's width before the run.** `planAdmission` derives one `cores` number per gate (scripts/ci-runner/pool.ts:587: measured cpu/wall clamped to [0.25, C], else `weight ?? 1`), and `admit` packs against it (scripts/ci-runner/pool.ts:317-513). Nothing tells a gate how many cores it was budgeted: `execGate` passes `process.env` plus the gate's declared `env` and nothing else (scripts/ci-runner/exec.ts:89). C is `availableParallelism() - 1` (scripts/ci-runner/run.ts:901).

**Static worker counts in gate tooling, found by grep (the sweep in PF9 is the complete list).**
- `PYTEST_JOBS_CAP = 8` and `jobs() = min(8, os.cpu_count())` (.ci/rediacc_ci/check_pytest.py:139, :148-154), passed as `-n` at .ci/rediacc_ci/check_pytest.py:1232 and :1290; the manifest mirrors it as `weight: 8` (scripts/ci-runner/manifest.ts:5019).
- `battery._default_jobs() = min(8, os.cpu_count())` (.ci/rediacc_ci/battery.py:448-450).
- `literal_sources.classify_all` workers `min(8, os.cpu_count())` (.ci/rediacc_ci/quality/literal_sources.py:533).
- `typecheck-incremental` width `min(8, availableParallelism() - 1)` (scripts/ci-runner/typecheck-incremental.ts:795).
- Thirteen hand-written `weight: 2` declarations (scripts/ci-runner/manifest.ts:87, 105, 120, 135, 150, 708, 727, 744, 3469, 3534, 3552, 5297, 5311) on gates whose tools pick their own width: no vitest config under packages/ or private/ sets a worker count (grep of every `vitest.config.ts` for maxWorkers/maxForks/maxThreads finds none), so each vitest gate is believed to use every core while the pool budgets it at 2 (hypothesis: vitest's default width, confirmed by PF9's measurement).
- `unitParallelism: {"quality-pytest": 4}` in .ci/config/lane-durations.json is hand-authored (its own `$comment`, lines 55-61) and read by scripts/gates/check-lane-budget.ts:60.
- I/O fan-out widths (`xargs -P 8` at .ci/scripts/deploy/simulate-promotion.sh:218, `FETCH_PARALLELISM` at .ci/rediacc_ci/security/audit.py:847, `ARTIFACT_DOWNLOAD_WORKERS` at .ci/rediacc_ci/ci/budget_report.py:924, `COPY_WIDTH` at .ci/rediacc_ci/deploy/r2_promote.py:263) bound concurrent requests against a remote API, not cores. PF9 decides them explicitly.

**What serialises check:ci-pytest.** Measured from the local junit of 2026-10-03 (reports/quality-pytest/junit.xml, `-n 8`, wall 1111.7 s, 20,777 items, 7,607 test-seconds):
- The `hooks-guards` xdist group holds all of test_guards_differential.py (461.0 s, `XDIST_GROUP` at .claude/rediacc_hooks/tests/test_guards_differential.py:633) plus test_hooks_procs.py's marked cases (:40, :93). One group runs on one worker, so 470 s is a floor no core count moves. The reason is narrow: three guards read the real process table (`PROCESS_TABLE_READERS`, .claude/rediacc_hooks/tests/test_guards_differential.py:634-641), but conftest groups whole modules (conftest.py:74).
- The longest single item is test_settings_collapse.py `test_verdict_set_is_unchanged[pre-bash]` at 220.8 s, ungrouped; no worker count splits one item.
- Other groups: `hooks-delegates` 242.2 s, `ports` 214.9 s (.ci/rediacc_ci/tests/test_core_account.py:33, .ci/rediacc_ci/tests/test_testrun_account_e2e.py:3, .ci/rediacc_ci/tests/test_testrun_start_account.py:3, .ci/rediacc_ci/tests/test_core_ports.py:43; the reason is `find_consecutive_free_ports` returning the first free run, .ci/rediacc_ci/xdist_groups.py:37), `housekeeping-cleanup-versions` 205.7 s (.ci/rediacc_ci/tests/test_housekeeping_cleanup_versions.py:71), `real-tree` 197.2 s.
- The `real-tree` group members and their stated reasons: .ci/rediacc_ci/tests/gates/test_gate_shrink_only_composition.py:15 (four controls plant a probe in the scanned tree), .ci/rediacc_ci/tests/gates/test_gate_docs_gen.py:32 (case B perturbs a tracked file, case C runs `--write`), .ci/rediacc_ci/tests/gates/test_gate_paths_exist.py:22 (plants a file under `.ci/scripts/`), .ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py:26 (a reader: its plants moved into copies, docstring :23-27), .ci/rediacc_ci/tests/test_canonical_sys_path_hop.py:49 (a reader of `git ls-files --others`).
- The `tree:repo` exclusive claim on check:ci-pytest (scripts/ci-runner/manifest.ts:5026, `writesTree` at :5026) excludes six other gates for the whole pytest wall: check:ci-guard-mutations, check:test:tutorial-player, check:ci-security-audit, check:ci-proxy-image-smoke (slow), and check:ci-renet-types and check:ci-search-index, which are in the quick lane (gates.lock.json, `mutex` contains `tree:repo`). In a one-pass run those two quick gates would wait out pytest.
- check:ci-pool-writer-safety enforces the claim: any module declaring the real-tree group obliges the pytest lane to hold an exclusive `tree:` claim (.ci/rediacc_ci/quality/pool_writer_safety.py:418-456).

**What voids a receipt.** block_unverified_push demands `receipt.headTree == pushed tree` (.claude/rediacc_hooks/guards/block_unverified_push.py:885), and each `droppedVerified` entry must name the same tree (:688). `worklist.py --review-commit` commits `agent/reviews/<branch>/` after every reviewed commit, so the receipt dies on a commit that changes no code.

**Premise checks (facts that contradict or narrow the order).**
- test_gate_generate_tag_inputs.py no longer writes the tree and declares no group (its docstring at :14-19, comment at :38). test_gate_gate_anti_vacuity.py no longer writes either; it stays in the group as a reader. The manifest's `writesTree` text (scripts/ci-runner/manifest.ts:5026) and pool_writer_safety's docstring (:421) still name both as writers, so both are stale. The live writers are shrink_only_composition, docs_gen and paths_exist.
- `agent/reviews/**` is not ungated: check_plan_implementation.py maps rebased commits through review records (:444, :573, :1105), check_agent_session_archival.py prunes by them (:31-34), and check_durable_paths_tracked.py probes the directory (:38-41). `agent/worklist/` is read by .ci/scripts/quality/check_durable_paths_tracked.py:42, .ci/scripts/quality/check_tree_shape.py:71 and scripts/gates/check-pr-task-trailers.ts (reads `agent/worklist/epics.jsonl`). `agent/reggate/` is read by .ci/scripts/quality/check_tree_shape.py:72 and .ci/scripts/quality/check_plan_record.py:180. So a record-only commit can change a gate's verdict, and part 5 has to re-judge those readers rather than skip them.
- The driver exports `PUBLIC_VIDEO_CDN_BASE_URL` by hand for the `--only` pass although scripts/ci-runner/exec.ts:89 applies a gate's declared `env`. Hypothesis: a `gate: false` prerequisite pulled in by `needs` lacks the env its dependents declare. PF7 verifies it, and the one-pass design must not need the export.
- PLAN-ci-quick-cpu-scheduling.md shows five unticked boxes and agent/plans/QUEUE.md:76 says "not started", yet P0 and P1 shipped (commits 0564f8067, 0fdca103a) and `cores` is the default (scripts/ci-runner/run.ts:36, :2444). PF0 reconciles that record.

## Baseline (measured)

Filled by the lead from a parallel measurement on this host (24 logical cores, WSL2) before any writer lands. Each row names the command that produced it.

| # | Metric | Source | Baseline |
|---|---|---|---|
| B1 | Pre-push end to end, push-clone sync to last receipt write | `prepush.sh` wall | at least about 18 min per run (pass 1 93 s + pass 2 pytest 972-1328 s); 27-34 min between runs including review-commit waits. Tonight's driver overwrote its logs per run, so no exact end-to-end figure exists; the driver now records one (scratchpad prepush2.sh) |
| B2 | Pass 1 wall (`ci:quick --receipt-out`) | receipt `wallMs` | 93.0 s at e3005c26d (114.0 s on 2026-10-04); quick-walls.json history: 30 green runs, 65-97 s, median about 74 s |
| B3 | Pass 2 wall (`run.ts --only <dropped>`) | `only*.log` footer | pass 2 is bounded by check:ci-pytest: 972.5, 1095.7, 1079.3, 1056.1, 1328.1, 1085.6 s across six runs; 949.3 s with only two gates |
| B4 | Critical path: longest gate id and its wall | report.ts footer `floor` line | pass 1: build:packages > build:cli > check:ci-proxy-rdc-update, 82.7 s; pass 2: check:ci-pytest in every run |
| B5 | Floor max(CP, gate CPU / C) and wall / floor | report.ts footer | pass 1: floor 82.7 s, wall 93.0 s = 1.12x; pass 2 (two-gate run): wall 949.3 s = 1.00x floor, pytest alone |
| B6 | Idle core-seconds and busy % over the whole pre-push | receipt `utilisation` (both passes) | pass 1: 676.7 idle core-s, 69.7% busy (320.3, 88.2% on 2026-10-04); pass 2 (two-gate run): 12,788.7 idle core-s, 43.8% busy |
| B7 | check:ci-pytest wall at today's `-n 8` | `--only check:ci-pytest` footer | 1085.6 s in the e3005c26d pre-push (972-1328 s across tonight's six); the manifest's 396 s (scripts/ci-runner/manifest.ts:5019) was measured on 2026-09-07 |
| B8 | pytest test-seconds, largest xdist group, longest item | junit.xml | 21,449 tests, 7,865.9 test-seconds, wall 1,070.0 s (junit 2026-10-05T08:16); longest item test_settings_collapse::test_verdict_set_is_unchanged[pre-bash] 203.5 s, then test_guards_differential::test_every_guard_discriminates 187.9 s; heaviest files test_guards_differential 458.4 s, test_hooks_delegates 358.3 s, test_housekeeping_cleanup_versions 312.5 s, test_settings_collapse 253.6 s. Ideal at 23 cores: 7,865.9 / 23 = 342 s |
| B9 | check:ci-pytest wall at `-n 23`, groups unchanged | `PYTEST_JOBS=23` | TBD-baseline |
| B10 | Receipts voided by a record-only commit, last 10 pushes | git log of agent/reviews commits between receipt and push | 9 restarts on 2026-10-05; every restart's HEAD was a fresh chore(reviews) commit from --review-commit before the clone sync, and 3 more were voided by a review ruling committed mid-run |
| B11 | Concurrent pytest from another session during a pre-push: both walls | two runs started together | TBD-baseline |

## 1. Dynamic sizing

**The contract.**
- The ci-runner grants each gate a core count at launch and exports it as `CI_RUNNER_CORES=<k>` in the gate's environment (scripts/ci-runner/exec.ts:91 gains it beside the declared `env`). It also exports `CI_CORE_LEASE_HELD=1` when the grant is backed by the machine-wide lease (part 4), so a child never leases the same cores twice.
- A gate reads its width through one helper per language: Python `core_lease.granted_cores()` (.ci/rediacc_ci/core_lease.py), TypeScript `grantedCores()` (scripts/ci-runner/lease-client.ts). Both return `CI_RUNNER_CORES` when it is a positive integer, else the cores this process may run on (`len(os.sched_getaffinity(0))`, `os.availableParallelism()` in node). The fallback is what CI uses: CI runs each gate as its own workflow step (.ci/rediacc_ci/ci/gate_costs.py:4), so a CI leg sizes to its runner's real CPU count with no setting.
- No tool keeps a cap. A tool that needs a floor below which parallelism is pointless declares it as the manifest `min`, never as a constant in its own code.

**Elastic declarations.** `GateSpec` (scripts/ci-runner/gate-spec.ts:68) replaces `weight?: number` with `cores?: { min: number; max: number | 'all' }`. A gate with a width knob declares it and passes `$CI_RUNNER_CORES` to that knob in its `run`. A gate without a knob declares nothing and keeps the measured d(g) of the cores rule.

**Admission of an elastic gate.** `Candidate` (scripts/ci-runner/pool.ts:229) gains `elastic?: {min, max}`; `admit()` (scripts/ci-runner/pool.ts:317) computes the grant at the moment it admits:
- `free` = min(cap - cores in use, lease free tokens from part 4).
- `area` = the predicted CPU of every other gate still unstarted or running, in core-ms, divided by the elastic gate's predicted wall at the candidate grant. This is the share of the machine the rest of the pass needs while the elastic gate runs.
- grant = clamp(floor(C - area), min, min(max, free)). With a 23-core budget and a fast lane of about 818 cpu-s (PLAN-ci-quick-cpu-scheduling.md section 1) beside a pytest of several hundred seconds, the area term is two or three cores, so pytest starts near 20 workers and the fast gates fill the rest.
- If free < min, the gate is held with a new `HoldReason` `lease`, and EASY backfill reserves its start exactly as it does for `cpu` (scripts/ci-runner/pool.ts:405-440). The progress guarantee (scripts/ci-runner/pool.ts:483-495) grants `max(min, free)` on an empty pool.
- The grant is recorded on `GateResult` (`grantedCores`) and in the receipt, so the after table can show it.

**Weight follows the grant.** The candidate's `cores` for budgeting is the grant, not a hand number, and the measured d(g) of an elastic gate is stored per core (cpu / wall / grant), so a run at 20 workers does not teach the scheduler a gate is 20 wide forever.

- [x] PF1 `cores: {min, max}` replaces `weight` in gate-spec.ts and gen-manifest's HAND_ONLY list (scripts/gen/gen-manifest.ts:72); `weight` is refused by the manifest check, clean break
    (ticked) 2026-10-05T11:55:32Z by d778be9d: commit:00fa66691 gate-spec carries cores {min,max}, a manifest still carrying weight is refused, gen-manifest lists cores
- [x] PF2 `admit()` grants elastic gates by the area rule, `lease` hold reason, `grantedCores` on GateResult and the receipt; exec.ts exports `CI_RUNNER_CORES` and `CI_CORE_LEASE_HELD`
    (ticked) 2026-10-05T11:55:33Z by d778be9d: commit:00fa66691 pool.ts admit grants elastic gates by the area rule with a lease hold reason, exec.ts exports CI_RUNNER_CORES and CI_CORE_LEASE_HELD
- [x] PF3 `grantedCores()` in lease-client.ts; `scripts/ci-runner/typecheck-incremental.ts:795` reads it; sim.ts models elastic gates (processor sharing above C, as today)
    (ticked) 2026-10-05T11:55:35Z by d778be9d: commit:00fa66691 grantedCores in lease-client.ts, read by typecheck-incremental.ts, sim.ts models elastic gates (case 7)
- [x] PF4 check_pytest.py: `PYTEST_JOBS_CAP` deleted, `jobs()` = `PYTEST_JOBS` if set, else `granted_cores()`; the `-n 2` at :877 stays because it is a header-parse fixture that needs exactly two workers, and its comment says so
    (ticked) 2026-10-05T11:55:36Z by d778be9d: commit:00fa66691 PYTEST_JOBS_CAP deleted; jobs() is PYTEST_JOBS else core_lease.granted_cores(); test_check_pytest_jobs plants the cap
- [x] PF5 manifest: check:ci-pytest `cores: {min: 2, max: 'all'}`; each vitest gate passes `--maxWorkers=$CI_RUNNER_CORES` and declares `cores: {min: 1, max: 'all'}`; each biome gate likewise through its thread knob (hypothesis: `RAYON_NUM_THREADS`, verified before use); every remaining `weight: 2` is replaced by an elastic declaration or deleted in favour of measured d(g)
    (ticked) 2026-10-05T11:55:37Z by d778be9d: commit:00fa66691 pytest cores {min 2, max all}; 7 vitest gates via VITEST_MAX_WORKERS; check:format via RAYON_NUM_THREADS; eslint gates cores {1,4} via eslint-heap --concurrency; no weight left
- [x] PF6 .ci/rediacc_ci/battery.py:450 and .ci/rediacc_ci/quality/literal_sources.py:533 read `granted_cores()`; lane-durations.json `unitParallelism` is derived from the runner's core count by budget_report rather than hand-authored, and scripts/gates/check-lane-budget.ts:60 reads the derived value
    (ticked) 2026-10-05T12:27:02Z by d778be9d: commit:e791f7c6d battery and literal_sources read granted_cores (00fa66691); budget_report derives unitParallelism from the lane runner label, prior kept when underivable

## 2. One scheduler pass

**Decision: the new meaning of `--quick`, not a new flag.** One receipt-producing lane keeps the guard's contract single, and the repo's clean-break rule forbids a second mode beside it. The one other consumer, the nightly gate-costs capture (`run.ts --quick --jobs 1 --sched slots --json`, .ci/scripts/ci/scope-map.cjs:158), is unaffected: a CI checkout has no last push, so `quickDiffAdmit` admits no slow gate there (scripts/ci-runner/run.ts:726-737).

**The pass.**
- `select()` (scripts/ci-runner/run.ts:600-692) admits every touched slow gate. `QUICK_BUDGET_MS`, `admitWithinBudget`'s budget arm and the `budget` and `unpriced` `DropKind`s (scripts/ci-runner/quick-select.ts:6, :229) are deleted.
- A touched slow gate is still dropped in exactly one case: a tree writer outside a disposable clone (`treeWriteRefusal`, scripts/ci-runner/run.ts:583-587). That drop keeps `kind: 'tree'` and its `--only` command, and the `--only` merge (scripts/ci-runner/run.ts:2288-2339) stays for it alone.
- Ordering stays the cores rule's priority, max(bottom level, cpu) (scripts/ci-runner/pool.ts:613-632), fed by lane-durations `gate_step_p90_seconds` and the local cache, so pytest and the other long gates start at t=0 and the fast gates fill around them.
- The push recipe becomes: sync the push clone, `npm run ci:quick -- --receipt-out <R>`. The driver's second phase and its hand-exported env are deleted.

**The receipt.** Field set unchanged. `droppedTouched` lists only gates this pass could not run (tree writers outside a disposable clone), so in the push clone it is `[]`. A touched slow gate that ran is in the run like any other gate: a failure lands in `failed`, `findings` and `exitCode`, and `carried_verdict` judges it (.claude/rediacc_hooks/guards/block_unverified_push.py:1049). A new diagnostic field `slowAdmitted` names the touched slow gates the pass ran (the guard does not read it).

- [x] PF7 one-pass `--quick`: budget deleted, every touched slow gate admitted, `slowAdmitted` in the receipt, `PUBLIC_VIDEO_CDN_BASE_URL` hypothesis verified and fixed at its root (a missing `env` on the prerequisite, or the gate's own declaration)
    (ticked) 2026-10-05T11:55:39Z by d778be9d: commit:00fa66691 the 90 s budget and its budget/unpriced drops are deleted; the first one-pass run admitted 63 slow gates and dropped none
- [x] PF8 scripts/ci-runner/manifest.ts:5019 comment rewritten to cite the 2026-10-05 ruling and the elastic declaration; .ci/rediacc_ci/check_pytest.py:139-147 comment block rewritten to match
    (ticked) 2026-10-05T11:55:40Z by d778be9d: commit:00fa66691 the STOP AT 2.08x comment and check_pytest's cap comment both cite the 2026-10-05 ruling
- [x] PF10 gate test (test_gate_ci_runner.py): a synthetic manifest with one slow gate whose leaf the diff touches; one `--quick --receipt-out` in a clean clone runs it, writes `droppedTouched: []` and the gate in `slowAdmitted`; a failing slow gate gives `exitCode: 1` and `failed` naming it; in a dirty shared checkout a touched tree writer still lands in `droppedTouched` with its `--only` command, and that `--only` run merges into `droppedVerified`. Control: restoring the 90 s budget makes the first case report the slow gate as dropped, and the test reds
    (ticked) 2026-10-05T11:55:41Z by d778be9d: commit:00fa66691 test_elastic_gate_is_told_its_grant and test_quick_is_one_pass, each with its plant red then green

## 3. Shrink the critical path

The pytest floor today is the 470 s `hooks-guards` group, then the 220.8 s single item, then the 215-242 s groups. Each fix below removes one serial chain; the order follows its size.

**hooks-guards (470 s on one worker).**
- Move the cases that read the process table (the `PROCESS_TABLE_READERS` golden cases and the two anti-vacuity controls named at .claude/rediacc_hooks/tests/test_guards_differential.py:633) into a new module test_guards_process_table.py that keeps `XDIST_GROUP = "hooks-guards"` with test_hooks_procs.py. Everything else in test_guards_differential.py loses the group and distributes per item.
- The session fixture (.claude/rediacc_hooks/tests/test_guards_differential.py:788) builds a world of about 17,000 inodes per worker (pyproject.toml:406-407 records /tmp hitting its inode cap at 24 workers). It becomes build-once: the first worker builds into a content-addressed directory under the run's runtmp dir behind an `fcntl` lock, and the others reuse it read-only. Hypothesis: nothing in the golden cases writes into that world; PF12 proves it with a read-only bind (chmod -R a-w) before relying on it.

**The 220.8 s item.** test_settings_collapse.py `test_verdict_set_is_unchanged[pre-bash]` is parametrised per chain. It is split one level finer (per guard, or per case chunk, whichever the test's own loop iterates; hypothesis until read), so no item exceeds about 20 s.

**ports (215 s).** `find_consecutive_free_ports` returns the first free run (.ci/rediacc_ci/xdist_groups.py:37). Each worker gets a disjoint slice of 20000-30000 keyed on `PYTEST_XDIST_WORKER`, sized from the worker count at startup; the `ports` group is deleted from all four modules.

**real-tree (197 s) and the `tree:repo` mutex.**
- shrink_only_composition, docs_gen and paths_exist plant into a copy of the directories they scan, the way test_gate_gate_anti_vacuity.py already does with `empty_tree_fixture` (its docstring :23, :165). docs_gen's `--write` case runs against a copy of the files it writes.
- With no writer left, the two readers (anti_vacuity, canonical_sys_path_hop) leave the group too, and `REAL_TREE_GROUP` has no member.
- A new session tripwire (test_tree_tripwire.py plus a conftest hook) records `git status --porcelain --untracked-files=all` before collection and after the session. Any difference that a test made fails the session and names the paths. Concurrent edits by other sessions are excluded by comparing only paths under the testpaths roots and the directories the gate tests scan, and by running the tripwire in the push clone, where the tree is still.
- check:ci-pytest drops `mutex: ['tree:repo']` and `writesTree` (scripts/ci-runner/manifest.ts:5026). pool_writer_safety.py flips its rule: zero modules may declare the real-tree group, and the pytest lane must not claim `tree:` exclusively (its claim text at :438-456 and docstring :418-430 rewritten).

**Other groups.** `hooks-delegates` (242 s) and `housekeeping-cleanup-versions` (206 s) each get the same treatment: read the reason, isolate the shared resource per worker (a per-worker temp root or port slice), delete the group. Where a group guards a genuinely machine-wide resource (a fixed /tmp path, a docker daemon), the fixed path is made per-worker instead.

**The slow files and the order.**
- test_proxies_go_unit.py (248.9 s locally, 356.4 s in CI per .ci/config/lane-durations.json:436): its longest item `test_real_tree_agrees_byte_for_byte` (68.4 s) is split per Go package. Hypothesis until read: the test runs one `go test` over every package.
- `pytest_collection_modifyitems` in conftest.py sorts items by measured duration, longest first, from the local junit and lane-durations `units` (per-file, .ci/config/lane-durations.json:105-917). `loadgroup` hands out pending items in that order, so the longest start first.
- Target: no serial chain above about 60 s, so check:ci-pytest's wall approaches test-seconds / grant.

- [x] PF11 hooks-guards: the process-table cases move to test_guards_process_table.py with the group; test_guards_differential.py ungrouped
    (ticked) 2026-10-05T11:55:43Z by d778be9d: commit:00fa66691 the process-table cases moved out; the grouped half fell from about 460 s to 18 s
- [x] PF12 the guards world: sharing one build across workers is measured before it is built, and kept per worker when the saving is under about 10 s of check:ci-pytest wall
    (ticked) 2026-10-05T12:27:04Z by d778be9d: commit:00fa66691 measured 2026-10-05: 41 worlds in 1.27 s per worker, built in parallel, about 1.3 s of a 500 s wall; five worlds take warn_remote_drift FETCH_HEAD writes, so they stay per worker
- [x] PF13 test_settings_collapse split so no item exceeds about 20 s; test_proxies_go_unit split per package
    (ticked) 2026-10-05T12:27:13Z by d778be9d: commit:00fa66691 settings_collapse chunked with a partition control (slowest 17.0 s); go_unit slowest 23.0 s, go test already GOMAXPROCS wide
- [x] PF14 per-worker port slices; the `ports` group deleted from its four modules
    (ticked) 2026-10-05T11:55:44Z by d778be9d: commit:00fa66691 worker_port_range and free_port_in_range give each worker a slice; the ports group is gone
- [x] PF15 shrink_only_composition, docs_gen and paths_exist plant into copies; the real-tree group has no member; the tree tripwire lands with a planted control
    (ticked) 2026-10-05T11:55:45Z by d778be9d: commit:00fa66691 the three plant into copies or verify-only; the session tripwire in conftest fails a run that changes a tracked path
- [x] PF16 check:ci-pytest drops `tree:repo` and `writesTree`; pool_writer_safety's rule and docstring flipped; xdist_groups.py docstring and test_xdist_groups.py updated for an empty real-tree group
    (ticked) 2026-10-05T11:55:47Z by d778be9d: commit:00fa66691 tree:repo and writesTree dropped; pool_writer_safety refuses any real-tree declaration; gate_tree_writes REAL control pins it
- [x] PF17 hooks-delegates and housekeeping-cleanup-versions groups resolved per worker, or kept with a measured reason in the module
    (ticked) 2026-10-05T11:55:48Z by d778be9d: commit:00fa66691 both groups removed: the floor test reads its cases by ast, hooks-delegates ran clean three times at -n 8
- [x] PF18 duration-ordered collection in conftest.py; .ci/config/shards/quality-pytest.json rebalanced for the split files
    (ticked) 2026-10-05T12:27:05Z by d778be9d: commit:610f3b57c longest-first ordering from 00fa66691 with a silent fallback on malformed lane-durations; quality-pytest legs rebalanced, worst 10.09 to 9.21 min

## 4. No self-contention

**One machine-wide lease.** .ci/rediacc_ci/core_lease.py owns a token pool of N = `len(os.sched_getaffinity(0))` tokens.
- Location: `$REDIACC_CORE_LEASE_DIR`, else `$XDG_RUNTIME_DIR/rediacc-cores`, else `${TMPDIR:-/tmp}/rediacc-cores-<uid>`. Not `.ci/cache`, which is per checkout, while the contention is per machine across worktrees and push clones. Hypothesis: the devbox container sees the host's cores and needs the host directory bind-mounted to share the pool; PF22 checks and either mounts it or records why the devbox stays separate.
- A token is a file `<i>.lock` held by `fcntl.flock(LOCK_EX | LOCK_NB)` on an open descriptor. A sidecar `<i>.json` names pid, command and start time for `core_lease.py status`.
- **Reaping is the kernel's.** A flock is released when the last descriptor on it closes, which includes the holder's death by any signal. A stale lease cannot exist; the sidecar of a free token is stale by definition and is overwritten at the next acquire. `status` also reports a live holder that has used no CPU for 10 minutes, as a report, never a kill.

**Verbs.** `acquire --min a --max b [--wait]` returns the grant k (a ≤ k ≤ b, as many as are free); `run --min a --max b -- <cmd>` acquires, exports `CI_RUNNER_CORES=k` and `CI_CORE_LEASE_HELD=1`, and execs the command with the descriptors inherited, so the lease lives exactly as long as the command's process tree holds them; `broker` speaks JSON lines on stdin and stdout (`{"op":"free"}`, `{"op":"acquire","min":a,"max":b}`, `{"op":"release","ids":[...]}`) and exits on EOF, releasing everything.

**Who draws from it.**
- The ci-runner spawns one broker per run (lease-client.ts). Before each `admit()` pass it reads `free`, and on launch it acquires the gate's grant; a short grant is used as is, and a grant below `min` returns the tokens and holds the gate with `lease`. Gates inherit nothing from the broker; they learn their width from `CI_RUNNER_CORES` alone.
- Session-launched pytest: `.ci/cache/toolchain/uv-tools/bin/pytest` (today a symlink to the uv tool's binary, the documented session entry in .claude/skills/testing/hooks.md:25) becomes a wrapper written by .ci/bootstrap.sh. Without `CI_CORE_LEASE_HELD` it calls `core_lease.py run`: `-n auto`, `-n logical` and a bare `-n N` request `--min 1 --max N` (or all), rewrite `-n` to the grant, and a serial run takes one token. With `CI_CORE_LEASE_HELD` set it execs the real binary untouched.
- check_pytest.py run standalone (no `CI_RUNNER_CORES`) leases through the same module, so `npm run check:ci-pytest` from a session cannot take every core under a running pre-push.
- Writer agents' test runs go through the same wrapper because it is the path they are told to use; their prompts name it.

- [x] PF19 core_lease.py: tokens, acquire, run, broker, status; `granted_cores()` helper (lands first: B and C import it)
    (ticked) 2026-10-05T11:55:50Z by d778be9d: commit:7bee521ca flock tokens, acquire/run/pytest/broker/free/status, pool mutex; 21 tests and three plants red then green
- [x] PF20 lease-client.ts and the runner's use of it: `free` before each pass, acquire at launch, release at settle, the broker killed with the runner
    (ticked) 2026-10-05T11:55:51Z by d778be9d: commit:00fa66691 openLease reads free before each pass, takes and releases tokens per gate, falls back to the whole machine saying why
- [x] PF21 bootstrap.sh writes the pytest wrapper in place of the symlink; check_pytest.py leases when run standalone; .claude/skills/testing/hooks.md names the wrapper
    (ticked) 2026-10-05T11:55:52Z by d778be9d: commit:7bee521ca bootstrap writes the lease-aware pytest wrapper idempotently and doctor reports a lease row
- [x] PF22 devbox lease-directory check (mount or recorded reason)
    (ticked) 2026-10-05T11:55:54Z by d778be9d: commit:606f7daac the devbox binds /run/user/<uid>/rediacc-cores with REDIACC_CORE_LEASE_DIR, and devbox.py matches (d3508efb0)

## 5. No pointless restarts

**The record set.** .ci/policy/record-paths.json lists the globs a commit may touch without voiding a receipt, each with its `readers`: the gate ids whose verdict depends on those files, with file:line evidence. Starting set from the reads found above:

| Glob | Readers (evidence) |
|---|---|
| `agent/reviews/**` | check:ci-plan-implementation (.ci/scripts/quality/check_plan_implementation.py:444, :1105), check:ci-agent-session-archival (.ci/scripts/quality/check_agent_session_archival.py:31), check:ci-durable-paths-tracked (.ci/scripts/quality/check_durable_paths_tracked.py:38-41) |
| `agent/worklist/*.jsonl` except `epics.jsonl` | check:ci-durable-paths-tracked (:42), check:ci-tree-shape (.ci/scripts/quality/check_tree_shape.py:71) |
| `agent/reggate/*.jsonl` | check:ci-tree-shape (:72), check:ci-plan-record (.ci/scripts/quality/check_plan_record.py:180) |

`agent/worklist/epics.jsonl` stays out: check-pr-task-trailers.ts reads it and its verdict is a commit-range judgement. Whole-tree scanners (prose style, formatters, secret scans) are checked for these globs by the gate below and added as readers where they read them.

**The gate.** check:ci-record-paths (.ci/scripts/quality/check_record_paths.py) derives the readers by scanning every gate's leaves for each glob's literal prefix and reds when the policy's list differs. Control first: a planted gate leaf citing `agent/reviews/` must appear as an undeclared reader.

**The advance.** When HEAD has moved since the receipt and `git diff --name-only <receipt tree> HEAD^{tree}` lies inside the record set, `npm run ci:quick` does not re-run the lane. It runs the selftest and then only the readers of the touched globs at HEAD, and appends to the receipt `advances: [{from, to, paths, gates: {id: exitCode}, finishedAt}]`. A touched glob with no readers advances with `gates: {}`. Any path outside the set runs the whole pass as today.

**The guard.** .claude/rediacc_hooks/guards/block_unverified_push.py:885 accepts `r_tree != tree` only when the receipt's `advances` form a chain from `headTree` to the pushed tree and, for every step, the guard recomputes `git diff --name-only from to` itself (never trusting `paths`), finds it inside the record set read from HEAD's copy of the policy, and finds every reader of the touched globs in `gates` at exit 0 or carried. `dropped_verdict` (:994) and the carried-reds read take the chain's end as the tree. The extra git call runs only on the branch that refuses today, so the common path stays one `rev-parse` and one file read. The existing refusal texts are unchanged, so the frozen golden (.claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl) keeps its rows and gains rows only for the new refusals.

- [x] PF23 record-paths.json and check:ci-record-paths with its planted-reader control, wired through package.json, the manifest and its CI step
    (ticked) 2026-10-05T11:55:55Z by d778be9d: commit:aedf9a278 record-paths.json with 62 readers and the control-first gate, wired in 00fa66691 and 633a458bf
- [x] PF24 the advance in run.ts: diff against the receipt tree, readers only, `advances` appended
    (ticked) 2026-10-05T11:55:56Z by d778be9d: commit:00fa66691 planAdvance/runAdvance re-run only the record readers and append an advances step, diffed with --no-renames
- [x] PF25 the guard's chain rule with the diff recomputed, `dropped_verdict` and carried reds on the chain's end
    (ticked) 2026-10-05T11:55:58Z by d778be9d: commit:aedf9a278 the guard follows advances, recomputes each diff with --no-renames, admits only record-only steps whose readers passed
- [x] PF26 guard gate tests (test-block_unverified_push.py): a reviews-only commit with its readers green in `advances` is allowed; a reviews-only commit with no advance is refused; a commit touching agent/reviews and one code file is refused; an advance whose `paths` claims only records while the real diff holds code is refused; two chained advances are allowed; a reader red in `advances` is refused unless carried. Control: replacing the confinement check with `True` (the guard's own DEFECT seam, .claude/rediacc_hooks/guards/block_unverified_push.py:46) makes the code-commit case pass, and the suite reds
    (ticked) 2026-10-05T11:55:59Z by d778be9d: commit:aedf9a278 16 advance worlds, 100 cases; the confinement plant through the DEFECT seam fails the 4 confinement cases

## 6. Records

- [x] PF0 PLAN-ci-quick-cpu-scheduling.md: P0 and P1 ticked with commits 0564f8067 and 0fdca103a, P2's shipped half named, P4's weight retirement marked superseded by this plan's PF1; QUEUE.md line corrected
    (ticked) 2026-10-05T11:55:31Z by d778be9d: commit:8913d62ab P0 and P1 ticked with their commits, P2's shipped half named, P4's weight half marked superseded, QUEUE.md line corrected
- [x] PF9 the static-width sweep: every `-n`, `-j`, `-P`, `max_workers`, `maxWorkers`, `cpu_count()` and `availableParallelism()` in a gate's reach is either sized by the grant or listed in `.ci/policy/fixed-widths.json` as an I/O fan-out with its remote limit; check_record_paths.py's second mode reds on a new literal width outside the list (operator decision point: I/O widths are request concurrency, not cores; DEFAULT: they stay fixed and listed)
    (ticked) 2026-10-05T11:56:00Z by d778be9d: commit:aedf9a278 fixed-widths.json lists the network fan-outs (operator: keep fixed, listed); check:ci-record-paths refuses an unlisted width or a core cap; embed-asset probe now granted (00fa66691)
- [x] PF27 docs/agent-reference/ci-gates.md: the one-pass pre-push, `CI_RUNNER_CORES`, the lease, the record set
    (ticked) 2026-10-05T12:16:14Z by d778be9d: commit:2432a731a one-pass lane, CI_RUNNER_CORES, the lease and the record set documented

## Writer split

Four writers, disjoint ownership, each forbidden every other path, `git checkout/restore/stash`, and any sync or regenerate script (the lead regenerates gates.lock.json and the docs tables). Order: C's PF19 helper lands first (one small commit), then A, B and D in parallel; the lead integrates and runs the end-to-end pre-push.

**(A) runner: elastic admission, lease client, one pass, advance.** Owns scripts/ci-runner/{pool,run,exec,quick-select,sim,report,gate-spec,typecheck-incremental,lease-client}.ts, scripts/gen/gen-manifest.ts, package.json, .ci/rediacc_ci/tests/gates/test_gate_ci_runner.py. Boxes PF1 (schema half), PF2, PF3, PF7, PF10, PF20, PF24.
- Control-first test: test_gate_ci_runner.py `test_elastic_gate_is_told_its_grant`, a synthetic manifest gate writing `$CI_RUNNER_CORES` to a file under `cores: {min: 2, max: 'all'}` beside four one-core gates; asserts 2 ≤ grant ≤ C and the area rule's value. Planted defect: exec.ts without the export (the file reads empty) must red it. Second: PF10's one-pass case, with the 90 s budget restored as its planted defect.

**(B) pytest: dynamic -n and the critical path.** Owns scripts/ci-runner/manifest.ts, .ci/rediacc_ci/{check_pytest,xdist_groups,battery}.py, .ci/rediacc_ci/quality/{pool_writer_safety,literal_sources}.py, pyproject.toml, conftest.py, the test modules of PF11-PF18 (test_guards_differential, test_guards_process_table, test_hooks_procs, test_settings_collapse, test_proxies_go_unit, test_core_ports, test_core_account, test_testrun_start_account, test_testrun_account_e2e, test_gate_shrink_only_composition, test_gate_docs_gen, test_gate_paths_exist, test_gate_gate_anti_vacuity, test_canonical_sys_path_hop, test_xdist_groups, test_check_pytest_jobs, test_tree_tripwire), .ci/config/shards/quality-pytest.json, .ci/config/lane-durations.json, scripts/gates/check-lane-budget.ts. Boxes PF4, PF5, PF6, PF8, PF11-PF18, PF1's manifest half.
- Control-first test: test_check_pytest_jobs.py, `CI_RUNNER_CORES=12` gives `-n 12` and an unset variable gives the affinity count. Planted defect: `PYTEST_JOBS_CAP = 8` restored gives 8 and must red. Second: test_tree_tripwire.py, a planted test that appends to a tracked file under a fixture root must fail the session naming that path, and the clean run must pass.

**(C) the machine-wide lease and its wrappers.** Owns .ci/rediacc_ci/{core_lease,runtmp}.py, .ci/rediacc_ci/tests/test_core_lease.py, .ci/bootstrap.sh, .claude/skills/testing/hooks.md. Boxes PF19, PF21, PF22.
- Control-first test: test_core_lease.py over a 4-token pool in a temp directory: two `acquire --max 3` calls get 3 and 1; a third `--min 1 --wait` blocks until `kill -9` of the first holder frees its tokens, then gets them; a `broker` that sees EOF frees all. Planted defects: counting sidecar files instead of holding flocks (the kill case then never frees) and acquiring without `LOCK_NB` (the over-grant case then hangs to its timeout) must each red.

**(D) the receipt rule for record-only commits.** Owns .claude/rediacc_hooks/guards/{block_unverified_push,test-block_unverified_push}.py, .claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl, .ci/policy/{record-paths,fixed-widths}.json, .ci/scripts/quality/check_record_paths.py, .ci/rediacc_ci/tests/gates/test_gate_record_paths.py. Boxes PF9, PF23, PF25, PF26.
- Control-first test: PF26's cases, with the confinement check replaced by `True` through the guard's DEFECT seam as the planted defect. Second: check_record_paths.py `--selftest`, a planted leaf citing `agent/reviews/` must be reported as an undeclared reader.

The lead keeps PF0, PF27, the gates.lock.json regeneration, the manifest wiring of check:ci-record-paths (B's file, one entry handed over as text), and the integration run.

## After (measured)

Same rows as the baseline, from the same commands after the last writer lands.

| # | Metric | Source | After |
|---|---|---|---|
| B1 | Pre-push end to end | `ci:quick --receipt-out` wall | TBD-after |
| B2 | The one pass's wall | receipt `wallMs` | TBD-after |
| B3 | Second pass | none by construction | TBD-after |
| B4 | Critical path gate and wall | report.ts footer | TBD-after |
| B5 | Floor and wall / floor | report.ts footer | TBD-after |
| B6 | Idle core-seconds and busy % | receipt `utilisation` | TBD-after |
| B7 | check:ci-pytest wall at its grant (grant recorded) | receipt `grantedCores` | TBD-after |
| B8 | pytest test-seconds, largest group, longest item | junit.xml | TBD-after |
| B9 | check:ci-pytest wall standalone at full grant | `npm run check:ci-pytest` | TBD-after |
| B10 | Receipts voided by a record-only commit | the advance count in receipts | TBD-after |
| B11 | Concurrent session pytest during a pre-push: both walls and the grants | two runs started together | TBD-after |

- [ ] PF-final: the before/after table is filled from real runs
