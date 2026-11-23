# PLAN: Tooling speed -- a fast Stop hook, trustworthy profiler data, fewer processes per tool call, no blind CI retries
Status: approved -- operator /ask 2026-11-22: two plans with speed first; profiler fixes and per-check timing live here; wrangler-dev-e2e gets a native-Linux CI lane; the reggate debt fold is redesigned off the stop path
Owner: fee07197
First-Seen: 2026-11-22
Depends-On: no-dep -- builds on the Stop hook, lifecycle runner and profiler at the 1121-1 tip; ordering against other live plans is box-level and named under Ordering
Priority: P1 -- every stop costs 15-40 s and every Bash call starts about 16 Python processes, which slows every session and every writer
Concurrency: parallel -- the box groups below edit separate files; SP3 edits wl_checks.py, which several live plans also edit, so SP3 lands after the boxes named under Ordering
Owns: agent/plans/PLAN-tooling-speed.md, .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_core.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_cli.py, .claude/hooks/stop/wl_stopregistry.py, .claude/hooks/stop/wl_review.py, .claude/hooks/stop/wl_schedred.py, .claude/hooks/stop/wl_loopspeed.py, .claude/hooks/stop/wl_uncommitted.py, .claude/hooks/stop/wl_histfirst.py, .claude/hooks/stop/wl_resprofile.py, .claude/hooks/stop/wl_ressample.py, .claude/hooks/stop/wl_reggate.py, .claude/hooks/profile/**, .claude/rediacc_hooks/lifecycle.py, .claude/hooks/post-bash/**, .claude/hooks/post-tool/**, .ci/policy/hook-exec-baseline.json, .claude/rediacc_hooks/tests/test_wl_stop_speed*.py, .claude/rediacc_hooks/tests/test_lifecycle_inprocess*.py, .claude/rediacc_hooks/tests/test_resprofile*.py, .ci/scripts/ci/watchdog-monitor.cjs, .github/workflows/ops-watchdog-monitor.yml, .ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py, .github/workflows/ci-quality.yml

## Ask

Operator, 2026-11-22, after a read-only investigation of where local CI and hook CPU goes: "I want to convert the current hook system into an auto maintain machine. So, even we have crazy plans in the future, everything should be clean, fast, organized and less code for the same work." <!-- style-ok -->

The follow-up /ask split the work into two plans, speed first. PLAN-tooling-code-reduction.md is the second.

## Context, measured 2026-11-21 and 2026-11-22

1. **The Stop hook costs 15-40 s per stop**, about half of it CPU (resprofile, Nov 21: 144 real stops, wall p50 15.7 s, p90 42.5 s, CPU p50 7.7 s). The LLM judge and GitHub calls are not the cost.
2. **The event log is parsed about 10 times per stop.** `S.load` (.claude/hooks/stop/wl_store.py:1292) re-reads `agent/worklist/<session>.jsonl` (9.1 MB) from .claude/hooks/stop/wl_checks.py:3455, 3480, 3550 and 3657, wl_roster, wl_planqueue, wl_schedred, wl_prreview and wl_retro, with no per-process memo.
3. **The transcript tail is read about 12 times per stop**, from .claude/hooks/stop/wl_core.py:745 and 898, wl_admit and wl_liveness.
4. **About 15-25 git processes start per stop** for answers that change only when HEAD or refs move (wl_review.branch_state, wl_schedred, wl_loopspeed, wl_uncommitted, wl_histfirst, the rev-parse at .claude/hooks/stop/wl_checks.py:2784).
5. **State is saved up to 19 times per stop** (`S.save_state`).
6. **Three stop-path steps do heavy work every time:** the resprofile fold reads all of today's exit.jsonl (8-25 MB) and rewrites rollup.json; backup_lag starts a Python subprocess (.claude/hooks/stop/wl_checks.py:121); the reggate proof runs an npm gate (.claude/hooks/stop/wl_reggate.py:754, 120 s timeout).
7. **run_stop is one function of 3,720 lines** (.claude/hooks/stop/wl_checks.py:3439-7158) holding 78 check keys, with no per-check timing.
8. **Every Bash call starts about 16 Python and 2 bash processes.** lifecycle.run_pattern (.claude/rediacc_hooks/lifecycle.py:384, subprocess at :410) starts each post-bash (8) and post-tool (4) member as its own process. The harness-level baseline (`.ci/policy/hook-exec-baseline.json`) counts 3.
9. **The profiler cannot drive retirement decisions yet.** The inherited `_WL_SITEPROFILE` marker makes every child of a profiled Python skip recording; `PYTHONPATH=.ci` replaces the path that loads sitecustomize; test fixtures are folded into the rollup; the rollup has no per-day counts or last-seen date; `~/.claude/resprofile` holds 25 GB in 35,378 directories, 19 GB of it in two clone directories that prune never visits.
10. **The CI watchdog retries deterministic failures.** Its classifier answers HTTP 402, and the fallback retries anything matching the E2E, OPS or Fork Isolation allowlist, so the same job fails on every attempt (nightly 44882769573: Renet BPF rebuild check red on attempts 1, 2 and 3).
11. **check:ci-proxy-wrangler-dev-e2e runs nowhere.** `cannot_run()` in proxy_wrangler_dev_e2e.py refuses Docker Desktop (this host), and its CI kind is `local-only`: 98 of 100 local receipts record it blocked with exit 77.

## Design

D1. **One read per stop.** A per-process memo keyed on (path, mtime, size) serves the event-log fold and the transcript tail to every caller in one Stop run. State writes collect in memory and flush once at the end, plus once on an exception path.

D2. **Git answers keyed on HEAD.** A small cache keyed on the `HEAD` sha, the index mtime and the `packed-refs` mtime answers branch state, merge-base, unpushed counts and freshness. A miss runs git once.

D3. **Heavy steps leave the stop path.** The resprofile fold seeks to its stored byte cursor and runs from the sampler or a timer, never from run_stop. backup_lag is cached by HEAD. The reggate npm proof runs from the CLI or a gate, and the Stop hook reads its last verdict.

D4. **run_stop becomes a registry.** Each check is `(key, tier, fn)` in wl_stopregistry.py; the runner times each one with `time.monotonic` and writes the duration with the existing blocklog row. The floor set in wl_floor.py stays fixed, and every key appears exactly once, as `check_plan_record --effort-table` requires. The worklist CLI verbs move to wl_cli.py, so worklist.py is the Stop hook only.

D5. **Advisory lifecycle members run in-process.** Post-bash and post-tool members that only print advice run in the lifecycle process with a per-member timeout and crash isolation (an exception is caught, named on stderr and counted, as dispatch.run_chain already does). Members that must stay separate (a blocking member, one that forks long work) keep their own process and say why in PATTERNS.

D6. **Profiler data a machine can act on.** The marker carries the recorder's pid, so a child records unless the marker equals its own pid. A `.pth` file in the user site directory loads the recorder even when `PYTHONPATH` is replaced. Prune walks every resprofile directory by age and deletes pytest and tmp directories outright. The fold skips `fixture: true` records and strips worktree prefixes from shapes. The rollup gains per-day counts and `last_seen`.

D7. **The watchdog retries only what can pass.** A job that failed on the same step with the same first error line on the previous attempt is not retried, whatever the classifier says. An HTTP 402 from the classifier is logged as a classifier outage and falls back to no retry for a repeat failure.

D8. **wrangler-dev-e2e runs in CI.** A native-Linux job in ci-quality.yml (ubuntu-latest has a real docker daemon) runs the gate. Its CI kind changes from `local-only` to that step, and the local lane keeps it blocked on Docker Desktop with a message naming the CI job.

## Ordering against other live plans

- SP3 (the run_stop registry) lands after the small wl_checks.py removals that are ready now: PLAN-stop-hook-store-status.md J1 and R1, PLAN-stop-hook-retro-20261117.md .2-.6, PLAN-stop-hook-retro-20261122.md .1, PLAN-simple-two-tree-loop.md B4, PLAN-weekly-lessons.md W5 and PLAN-push-decoupling.md R7. Checks those plans add later (weekly-lessons W4, simple-two-tree-loop B7, retro-20261117 .7) arrive as registry entries with a tier and timing.
- PLAN-reggate-debt-collection.md is redesigned before approval (operator /ask 2026-11-22) so its debt fold runs from the CLI, a gate, or a cache keyed on ledger mtime and HEAD, never per stop. SP2 provides the stop-path side.
- SP6 (watchdog) and SP7 (wrangler lane) land before PLAN-console-private.md S2, which sweeps every workflow.

## Tasks

- [x] SP1 [writer] One event-log fold and one transcript tail per Stop run (D1): a memo in wl_store.py keyed on (path, mtime, size) behind `S.load`, the same for the transcript tail in wl_core.py, every caller served from it, and `S.save_state` collecting writes that flush once at the end and once on an exception.
  Owns: .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_core.py, .claude/rediacc_hooks/tests/test_wl_stop_speed_reads.py
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_stop_speed_reads.py` rc 0, with a test that counts opens of the event log and of the transcript during one fixture Stop run (1 each) and a control where touching the event log between two loads re-reads it; the whole `test_wl_*` family passes unchanged.
    (ticked) 2026-11-23T06:57:50Z by ace763dd: commit:8cadbea570 fileline:.claude/rediacc_hooks/tests/test_wl_stop_speed_reads.py:1 -- one event-log fold and one transcript tail per stop; test_wl_stop_speed_reads 11 passed, test_wl_* 2453 passed; events 3 to 1, transcript 6 to 1
- [ ] SP2 [writer] Git answers keyed on HEAD, and the three heavy steps off the stop path (D2, D3): a cache keyed on HEAD sha, index mtime and packed-refs mtime for wl_review.branch_state, wl_schedred, wl_loopspeed, wl_uncommitted and wl_histfirst; the resprofile fold seeks to its cursor and runs from wl_ressample; backup_lag cached by HEAD; the reggate npm proof read from its last recorded verdict.
  Owns: .claude/hooks/stop/wl_review.py, .claude/hooks/stop/wl_schedred.py, .claude/hooks/stop/wl_loopspeed.py, .claude/hooks/stop/wl_uncommitted.py, .claude/hooks/stop/wl_histfirst.py, .claude/hooks/stop/wl_resprofile.py, .claude/hooks/stop/wl_ressample.py, .claude/hooks/stop/wl_reggate.py, .claude/rediacc_hooks/tests/test_wl_stop_speed_git.py
  Depends on: SP1.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_stop_speed_git.py` rc 0, counting git process starts in a fixture Stop run (at most 3 on an unchanged HEAD, with a control where a new commit refreshes the cache) and asserting that no npm or `python3 -m` child starts from run_stop.
- [ ] SP3 [writer] run_stop as a registry with per-check timing, and the CLI out of worklist.py (D4): wl_stopregistry.py holds `(key, tier, fn)` for every check of run_stop, the runner writes each duration into the blocklog row, the floor set stays as wl_floor.py defines it, and the worklist verbs move to wl_cli.py with worklist.py delegating to it.
  Owns: .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_stopregistry.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_cli.py, .claude/rediacc_hooks/tests/test_wl_stop_speed_registry.py
  Depends on: SP1, and the wl_checks.py boxes named under Ordering.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_stop_speed_registry.py` rc 0 and `npm run check:ci-plan-record` rc 0 (the effort-table rule still sees every key once); a test asserts every registry entry writes a duration and that a fixture Stop run gives byte-identical stop text before and after the split; `python3 .claude/hooks/stop/worklist.py --list --open fee07197` still answers through wl_cli.py.
- [x] SP4 [writer] Advisory lifecycle members in-process (D5): lifecycle.run_pattern imports and calls the post-bash and post-tool members that only advise, with a per-member timeout and caught exceptions; members that must stay a process are marked in PATTERNS with the reason; `.ci/policy/hook-exec-baseline.json` gains the true per-call process count including the lifecycle fan-out.
  Owns: .claude/rediacc_hooks/lifecycle.py, .claude/hooks/post-bash/**, .claude/hooks/post-tool/**, .ci/policy/hook-exec-baseline.json, .claude/rediacc_hooks/tests/test_lifecycle_inprocess.py
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_lifecycle_inprocess.py` rc 0 with a test that counts processes started for one fixture Bash call (at most 4, against about 16 before), a control where a member that raises is named on stderr while the others still run, and `npm run check:ci-hook-exec-baseline` rc 0 with the new count.
    (ticked) 2026-11-23T06:57:51Z by ace763dd: commit:2101cdbc71 fileline:.claude/rediacc_hooks/lifecycle.py:1 -- advisory lifecycle members in-process; test_lifecycle_inprocess 13 passed, check:ci-hook-exec-baseline rc 0; python processes per Bash call 16 to 4
- [ ] SP5 [writer] Profiler fixes (D6): a pid-keyed marker in sitecustomize.py, a `.pth` loader written by the bash_env.sh setup, prune over every resprofile directory by age with pytest and tmp directories removed, fixture records skipped in the fold, worktree prefixes stripped from shapes, and per-day counts and `last_seen` in the rollup.
  Owns: .claude/hooks/profile/**, .claude/hooks/stop/wl_resprofile.py, .claude/rediacc_hooks/tests/test_resprofile_trust.py
  Depends on: SP2 (the fold moves first).
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_resprofile_trust.py` rc 0, with tests that a child of a profiled Python records its own row, that `PYTHONPATH=.ci python3 -m <module>` records, that a fixture record is not folded, that a 20-day-old pytest directory is pruned, and that the rollup carries `last_seen`; `du -sh ~/.claude/resprofile` after one prune is quoted in the tick evidence.
- [x] SP6 [writer] The watchdog retries only what can pass (D7): watchdog-monitor.cjs compares the failed step and first error line against the previous attempt and does not retry a repeat; a classifier HTTP 402 is logged as an outage and does not widen the retry allowlist for a repeat failure.
  Owns: .ci/scripts/ci/watchdog-monitor.cjs, .github/workflows/ops-watchdog-monitor.yml
  Depends on: none.
  Accept: `node .ci/scripts/ci/watchdog-monitor.cjs --selftest` (added by this box if absent) rc 0 with a fixture of two attempts failing on the same step and line (no retry) and a control of a first-attempt E2E timeout (retried); `npm run check:ci-workflows` rc 0.
    (ticked) 2026-11-23T06:57:52Z by ace763dd: commit:5a6449ca86 fileline:.ci/scripts/ci/watchdog-monitor.cjs:1 -- watchdog skips repeat failures and logs classifier 402 as outage; selftest 16 checks rc 0, check:ci-workflows rc 0 (8c3d02faa8 5a6449ca86)
- [ ] SP7 [writer] wrangler-dev-e2e gets a native-Linux CI lane (D8): a ci-quality.yml job on ubuntu-latest runs `npm run check:ci-proxy-wrangler-dev-e2e`, the manifest entry's CI kind becomes that step, and the local refusal on Docker Desktop names the CI job. GitHub-only: native-runner -- the gate needs a native Linux docker daemon, and this host runs Docker Desktop on WSL2, which cannot_run() refuses.
  Owns: .ci/rediacc_ci/quality/proxy_wrangler_dev_e2e.py, .github/workflows/ci-quality.yml
  Depends on: PLAN-tooling-code-reduction.md CR2 when the gate generator has landed, so the manifest entry is written through the gate header; before that, the manifest and lock edit goes through the current generator.
  Accept: `npm run check:ci-parity` and `npm run check:ci-workflows` rc 0; one CI run on the branch shows the new job green, read with `.ci/scripts/ci/ci-trace.py`.
- [ ] SP8 [live] Measure after SP1-SP4: wall p50 and p90 of real stops over one working day from the resprofile rollup, and processes per Bash call. Accept: Stop wall p50 under 5 s and p90 under 12 s, at most 4 processes per Bash call, both quoted with the rollup path in the tick evidence.

## Risks

- **A memo serving a stale read.** D1 keys on mtime and size, and the SP1 control proves a write between two loads is seen.
- **In-process members leaking state.** SP4 keeps a member a process when it holds module state or forks; the crash-isolation control proves one member cannot take the others down.
- **Watchdog under-retrying a real flake.** D7 skips a retry only when the step and the first error line repeat exactly; a different failure is still retried.
