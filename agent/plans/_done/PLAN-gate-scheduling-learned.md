# PLAN: pre-push and CI gate scheduling that learns from recorded outcomes

Status: done -- 2026-10-08, every box ticked (T12's live triage run stopped at its first RED by design, so the plan shows the early-red path and not a green receipt; the 12 reds it found are tracked as separate pre-push work); was approved -- operator 2026-10-08: implement now, in this session, with no deferral; the brief makes it the first plan of the branch after PR #599, started the moment #599 merges
Depends-On: no-dep -- builds on the ci-runner, receipt and push guard already on main; no open plan has to finish first
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P0 -- operator 2026-10-08: "start now"
Concurrency: parallel -- four writers with disjoint files (section 9); the lead owns run.ts integration review, prepush.sh and the agent docs
Owns: .ci/rediacc_ci/ci/gate_ledger.py, .ci/rediacc_ci/ci/gate_model.py, .ci/rediacc_ci/core/jsonl_append.py, .ci/rediacc_ci/tests/test_gate_ledger.py, .ci/rediacc_ci/tests/test_gate_model.py, .ci/rediacc_ci/tests/test_gate_model_replay.py, .ci/rediacc_ci/tests/fixtures/gate_model/**, .claude/hooks/stop/wl_store.py, scripts/ci-runner/ledger.ts, scripts/ci-runner/rank.ts, scripts/ci-runner/run.ts, scripts/ci-runner/pool.ts, scripts/ci-runner/sim.ts, scripts/ci-runner/report.ts, .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py, scripts/gates/check-deps.ts, .ci/scripts/ci/ci-trace.py, .claude/agents/pr-babysitter.md
Worklist: #288838a4

## Why (2026-10-08, branch 1007-1, PR #599)

Six full pre-push runs ran back to back, at 957-1002 s each, and each one found a single new red. Because of the queue order, the cheap reds were found last:
- `check:version` takes 1 s and was ready at 0.011 s, but it started at 975 s.
- `check:ci-pytest` held 17 cores for 945 s (receipt timelines under `.ci/cache/receipts/`).

The brief's evidence (agent brief, 2026-10-08) is a REPLAY FIXTURE the learned model must reproduce, never configuration.

## Principle

Nothing in the scheduler is a static list. Clock gates, clusters, change associations, flakes and the order are all derived from the outcome ledger plus `scripts/ci-runner/gates.lock.json`, and recomputed as data arrives.

The only hand-written inputs are the tunables in section 8. Each has a stated reason.

The source of the scheduler, model and ledger must name no gate id. A test (T9) plants one and must go red.

## What exists (investigated 2026-10-08, file:line in the agent reports)

**Ordering.** `planAdmission` returns a single `rank` comparator (`scripts/ci-runner/pool.ts:777-940`). `runPool` sorts the ready set by it (`scripts/ci-runner/pool.ts:1157`).
- slots mode: longest wall first (`scripts/ci-runner/pool.ts:823`).
- cores mode: max(bottom level, mutex chain, cpu) (`scripts/ci-runner/pool.ts:926-936`).
- `sim.ts` drives the same `admit`/`planAdmission` (`scripts/ci-runner/sim.ts:1-25`), so an order can be checked by simulation.

**Receipt.**
- Built only under `--quick`, at `scripts/ci-runner/run.ts:4043-4107`. `whole = narrowedBy.length === 0` (`scripts/ci-runner/run.ts:4087`).
- 50 archived copies are kept under `.ci/cache/receipts/` (`scripts/ci-runner/run.ts:2970-2985`).
- Per-gate `inputHash` is null for 306 of 352 gates: only 46 declare `paths` (`scripts/ci-runner/input-hash.ts:207-244`).
- `filesHash` is not a sound input key for path-less gates. `check:version` went green, red, then green with the same `filesHash`, because the fix was in package.json.

**Streaming.** FAIL blocks already print the moment a gate fails (`scripts/ci-runner/report.ts:281-287`). But the operator's `prepush.sh` redirects everything to a log, so nothing is seen until the end.

**Stopping.** SIGTERM/SIGINT stops new launches and kills the gates, and the run exits with no receipt (`scripts/ci-runner/run.ts:3795-3830`).

**Existing data.** None of it is a cross-run pass/fail history:
- `lane-durations.json`, `gate-costs.json` and `gate-durations.json` hold timing only.
- `agent/reggate/*.jsonl` is the Stop hook's effort ledger, not gate outcomes.
- The ci-trace log cache (`~/.cache/ci-trace/logs/`) and `ci_diagnose` categories (`.ci/rediacc_ci/ci/ci_diagnose.py:58-71`) are the CI side.

**Locked append.** `.claude/hooks/stop/wl_store.py:649-667` `_append_lines`: blocking flock, one O_APPEND write per batch, torn-tail heal.

**PUSH-GUARD HOLE (found on the way).** `--fail-fast` is not a narrowing flag (`scripts/ci-runner/run.ts:2830-2837`). Gates it skips are written as `blocked` (`scripts/ci-runner/run.ts:3121`), which the guard accepts as a verdict (`.claude/rediacc_hooks/guards/block_unverified_push.py:1332`, `:1502`). So a `--quick --fail-fast` run whose only red is carried may produce a `whole: true` receipt with unjudged gates. This is verified first in T1, then fixed.

## 1. Outcome ledger (piece 1)

**Location.** `$REDIACC_GATE_LEDGER_DIR`, else `${XDG_STATE_HOME:-~/.local/state}/rediacc-gate-ledger/<origin-slug>/`.
- It is per machine and shared by every worktree, session and the push clone. It is not keyed per checkout the way the typecheck cache is.
- It is state rather than cache, because receipts rotate at 50 and history past that cannot be backfilled.

**Files.**
- `outcomes-YYYY-MM.jsonl`
- `ledger.lock`
- `seen.idx`, which makes folds idempotent
- `model.json`
- `reports/`
- `claims/`

**Rows (v1).**
- `run`: id, src (prepush, quick, ci-step, ci-nightly, probe or backfill), at, branch, head, tree, salt, clean, base tree, changed paths (capped), lock sha, derived classes, and the ci block (run, attempt, job, ci_diagnose category).
- `g`: run, gate, outcome (pass, fail, timeout, skip, cancel or blocked), wall ms, input key and its kind, finding keys, and attribution (own, shared-step or test).
- `end`: run, wall, exit, and whether the run was cut short.

**Input key.** `inputHash` when non-null. Otherwise:
- `sha(defHash, filesHash, salt)` for a gate with declared paths;
- the head tree for a path-less gate;
- tree + dirty digest outside a clean checkout.

Carried verdicts are never written, because a carried gate did not run.

**Writer.**
- ci-runner's `onFinish` (`scripts/ci-runner/run.ts:3561`) feeds `scripts/ci-runner/ledger.ts`. That module streams rows to a long-lived `python3 -m rediacc_ci.ci.gate_ledger append` child, copying the lease-broker pattern including its loud degradation.
- `_append_lines` moves to `.ci/rediacc_ci/core/jsonl_append.py`, and `wl_store` imports it from there. There is one implementation, not two copies.
- Off when `CI=true` unless the env var is set.

**CI fold-in.** `gate_ledger fold-ci` runs on demand at the end of `ci-trace.py`'s trace and in the daily refresh.
- Runs and jobs come from `budget_report.fetch_runs`/`fetch_jobs`.
- Gates map to steps through `load_gate_ci_steps`. A step shared by several gates gives weak `shared-step` rows.
- `ci.kind: test` gates take their outcome from `pytest-fail:` keys.
- Failed jobs get their category from `ci_diagnose.diagnose`.
- The nightly `gate-costs-*` artifact (3-day retention) is pulled daily.

**Backfill.** Every `receipts/*.json` across `git worktree list` and the push clone, plus CI jobs from the last 90 days.

**Rotation.** Monthly segments, `LEDGER_RETENTION_DAYS` and `LEDGER_MAX_BYTES`.

## 2. Path classes (derived)

The anchors are:
- every declared `paths` glob (a trailing `/**` reduced to its directory);
- every repo-file leaf;
- every `ci.test` path;
- `GLOBAL_INPUTS`.

A changed file's class is the longest anchor that matches it, using the input-hash glob grammar's Python twin (`v2_match_glob`, `.claude/rediacc_hooks/guards/block_unverified_push.py:1354`). An unmatched file is `~<first two segments>`.

Classes are recomputed from the stored paths against the current lock at model time, so they never go stale.

## 3. Red classification (piece 2)

Episodes are tracked per (gate, local|CI), from onset to recovery. Rules apply in this order:
1. **infrastructure:** the ci_diagnose category is infra-likely, watchdog-cancel, timeout-cancel or manual-cancel, or the outcome is `blocked`. These are excluded from every rate.
2. **flaky:** green again at the same input key and salt.
3. **clock:** red with the input key unchanged since the last green. That means one of:
   - a strong key is equal at onset; or
   - a probe reruns the gate at the last green head in a disposable clone within `PROBE_BUDGET_S` and it is red there; or
   - passively, at least `CLOCK_MIN_ONSETS` onsets bracket the same UTC boundary.

   A green probe proves the red real.
4. **real:** green again only after the inputs changed.
5. **chronic** (inferred): never green in the window. The classification then descends to finding keys, and each finding (for example one pytest node) gets its own episode.

Recency weight is 2^(-age/half-life).

Flaky gates and tests open or refresh a worklist item automatically (section 6). The clock set feeds preflight.

## 4. Learned relationships (pieces 3 and 6)

**Co-failure clusters.**
- Weighted lift over real onsets. Same run counts 1; consecutive runs on one branch count `CONSECUTIVE_WEIGHT`.
- An edge needs support ≥ `MIN_SUPPORT`, lift ≥ `MIN_LIFT` and Jaccard ≥ `MIN_JACCARD`.
- These are unioned with structural edges from gates.lock: shared paths glob, shared leaf, `needs`, or shared (job, step).
- Union-find gives the clusters. Every edge records where it came from.

**Change-to-red associations.** For each (class, gate), P(real onset | class in diff) divided by the gate's base rate. When an associated class is not among the gate's declared paths, a `paths-gap` item opens.

**Upgrade companions.** Gate A red at run r and green at r+1, while gate B is green at r and has a real red at r+1 on the same branch. B is a candidate at support 1 and reliable at `COMPANION_MIN_SUPPORT`. No flag knowledge is needed.

## 5. Scheduler and runner (pieces 4 and 5)

**Ranking.** `scripts/ci-runner/rank.ts` is pure and names no gate id. It builds `order = {pinned, preflight, value}` from `model.json` and the diff's classes. Both `rank` closures in `pool.ts` (`:823`, `:936`) take two keys:
1. pinned gates first, by today's priority. A gate is pinned when its planned wall is ≥ `LONG_FRACTION` × T* (T* is today's simulated makespan), or it sits on a `needs`/mutex chain that long;
2. then preflight;
3. then the rest by p_red / max(wall, 1 s), with today's priority breaking ties.

**Wall is never lengthened, checked on every run.** `sim.ts` exports `predictMakespan`, and the runner simulates both today's order and the proposed one.
- If the proposed order is more than `WALL_SLACK_MS` slower, the runner pins the gate whose start moved latest and simulates again, up to `PIN_ITERATIONS` times.
- If it is still slower, it uses today's order and prints `ranking: OFF for this run (simulated +Ns)`.

**Preflight.** The learned clock set plus the change-associated gates (≥ `ASSOC_MIN_P`). They are admitted greedily by value while the LPT makespan on the cores free at t=0 stays ≤ `PREFLIGHT_TARGET_S`.
- A gate with no wall estimate, or longer than `PREFLIGHT_MAX_GATE_S`, is never preflight.
- Preflight shares the pool rather than running first, so it adds no wall time.
- **Stage 1:** the next value-ranked gates up to `STAGE1_MASS` of the total p_red.
- Both stages print a line when they finish (`PREFLIGHT done at 41s: 6 gates, 2 red`).

**Early stop.** `--stop-on-stage-red[=preflight|1]`. When a named stage has finished with a red not covered by carried-reds keys, the run:
- stops new launches;
- kills the live gates;
- prints the reds and the `--narrow` command;
- exits 3 and writes **no receipt**.

There is no sentinel file, because the cache is shared across sessions. For an ad-hoc stop the runner prints its pid ("SIGTERM stops without a receipt").

**Streaming.** In `onFinish`, one line per red:
`RED <id> <wall>s at <t>s [preflight|stage1|tail] <first error> rerun: <cmd>`
The first error is the first `::finding::` key, else the first error-looking line.

There is also a machine stream, `--events <abs>` (default `<receipt dir>/ci-quick-events/<runId>.jsonl`), with these events: run-start (the plan, ranking on/off and why), gate-red, stage-done, run-end (`receipt: written|none`).

**Cold start.** Ranking is off when the ledger has fewer than `MIN_LEDGER_RUNS` whole runs, or fewer than `MIN_COVERAGE` of the selected gates have ≥ `MIN_GATE_OBS` observations. The run then uses today's order with no preflight and prints why. Gates thin on data take a Beta prior at the global red rate.

**Narrow re-run.**
- `npm run ci:quick -- --narrow [--print]` runs the union of:
  - F: the last receipt's non-carried fails;
  - C: their learned clusters;
  - T: the gates whose inputs the fix touched (`touchedSlow` rules 1-3 against receipt.head..worktree; rule 4, "no paths means touched", is excluded on purpose);
  - A: the gates associated with the changed classes.
- `--narrow` is a narrowing flag. It never writes a receipt, and a full receipt is built only when a push is due.

**Guard (the hole above).** `--fail-fast`, `--stop-on-stage-red` and `--narrow` join `narrowingFlags`. This is part (a) only. Writing skipped gates as their own verdict, part (b), would also refuse pushes where a carried prerequisite skipped its dependents, which changes accepted behaviour, so it is NOT taken.

**Wrapper and docs.**
- The operator's `prepush.sh` streams through `tee` plus a line-buffered filter for `RED|PREFLIGHT|STAGE|ranking`.
- It gains a `TRIAGE=1` mode that passes `--stop-on-stage-red`.
- On exit 3 it says `no receipt (stopped)` instead of parsing a stale receipt.
- `.claude/agents/pr-babysitter.md:100-102` gains the loop: red, `--narrow` until green, one full receipt when a push is due.

## 6. Self-improvement loop (piece 7)

`python3 -m rediacc_ci.ci.gate_model refresh` uses a TTL stamp (`MODEL_TTL_H`). It is started detached after a whole receipt when stale, and by `ci-trace --model`. Each run:
- folds in CI results and backfill, and runs the probes;
- rewrites `model.json`;
- writes `reports/<date>.md`.

Worklist items carry the token `[gate-model:<kind>:<key>]`. An open item with the token is refreshed with `--update`; otherwise one is added. Ownership uses an O_EXCL claim, as in `.claude/hooks/stop/wl_schedred.py:540,605`. The kinds:
- `flaky-test:<node>` (from the brief)
- `flaky-gate:<id>`
- `chronic:<id>`
- `companion:<A>-><B>` (reliable only)
- `paths-gap:<id>:<class>`
- `infra:<cat>:<job>`
- `clock-set` (one item)
- `wall-drift:<id>`
- `ledger-health`
- `model-quality`: the share of reds preflight or stage 1 caught

Every kind after `flaky-test` is INFERRED; the brief's own list was truncated after "new flaky tests;".

## 7. Upgrade companion fix (piece 6, #3b831146)

After `executeInstalls` succeeds (`scripts/gates/check-deps.ts:2240`), `check-deps.ts --upgrade` rewrites the `pinVersion` of every `.syncpackrc.json` group whose `dependencies` it moved. It uses the exact-form, byte-stable write of `applyOverrideBump` (`:1525-1565`).
- A lockstep group moves only when all of its members moved.
- Labels stay unchanged, because `check-syncpack-reasons.ts` keys on them.
- A selftest fixture covers this. Control: without the rewrite, `check:version` is red on the fixture.

## 8. Tunables

| Name | Value | Reason |
|---|---|---|
| HALF_LIFE_REAL_DAYS | 7 | branches live 1-2 days and deps drift weekly; a fixed red fades within about a week |
| HALF_LIFE_FLAKY_DAYS | 21 | flakes are rare, so they need longer memory |
| CLOCK_MIN_ONSETS / CLOCK_PERSIST | 2 / 2 | one onset or one rerun cannot separate clock from coincidence or flake |
| MIN_SUPPORT / MIN_LIFT / MIN_JACCARD | 3 / 2.0 / 0.3 | about 25 runs a day; rules out pairs that co-occur once |
| CONSECUTIVE_WEIGHT | 0.5 | a next-run red is weaker evidence than a same-run red |
| COMPANION_MIN_SUPPORT | 2 | one occurrence is only a candidate |
| PROBE_BUDGET_S | 120 | matches the preflight target |
| LEDGER_RETENTION_DAYS / LEDGER_MAX_BYTES | 120 / 256 MiB | about 32 KB per run × 25 runs a day |
| COLD_START_RUNS = MIN_LEDGER_RUNS | 8 | about one working day of pre-push runs (10-08 had 11) |
| MIN_GATE_OBS / MIN_COVERAGE | 5 / 0.5 | below these, recency weighting is noise |
| PREFLIGHT_TARGET_S | 120 | the brief's 2-minute cap |
| PREFLIGHT_MAX_GATE_S | 90 | admits check:deps (63 s); a gate longer than this cannot share the cap |
| LONG_FRACTION | 0.25 | 10-08's long gates were ≥0.30 of T*, the next tier 0.14 |
| WALL_SLACK_MS / PIN_ITERATIONS | 1000 / 5 | the simulation is deterministic; this bounds the safety search |
| STAGE1_MASS | 0.9 | stage 1 should hold most expected reds |
| ASSOC_MIN_P | 0.2 | a one-in-five association is worth a preflight slot under the cap |
| MODEL_TTL_H | 24 | the nightly artifact cadence |

## 9. Writers (≤4, disjoint)

- **W1, opus, gate-author: ledger and model.**
  - Owns: `.ci/rediacc_ci/ci/gate_ledger.py`, `gate_model.py`, `.ci/rediacc_ci/core/jsonl_append.py`, `.claude/hooks/stop/wl_store.py` (import only), the `test_gate_ledger.py`, `test_gate_model.py` and `test_gate_model_replay.py` tests, and `fixtures/gate_model/**`.
  - Defines the `model.json` contract below.
- **W2, opus, gate-author: runner.**
  - Owns: `scripts/ci-runner/ledger.ts`, `rank.ts`, `run.ts`, `pool.ts`, `sim.ts`, `report.ts`.
  - Codes against the contract, with a fixture `model.json`.
- **W3, opus, gate-author: push-guard hole.**
  - Owns: `block_unverified_push.py` and `test-block_unverified_push.py`.
  - Reproduces the hole first. `narrowingFlags` itself is W2's, in run.ts; W3 adds the guard-side fixture that refuses a `--fail-fast` receipt.
- **W4, sonnet: upgrade companion.**
  - Owns: `scripts/gates/check-deps.ts` (section 7).
- **The lead:** `ci-trace.py` fold hook, `prepush.sh`, `pr-babysitter.md`, integration runs and the replay.

**`model.json` contract (v1):**
`{v, built_at, cold_start:{on,reason}, runs, gates:{<id>:{obs, p_red, p_red_by_class:{<class>:p}, wall_ms, class:"real|flaky|clock|chronic|infra|none", findings:{<key>:class}}}, clock_set:[ids], clusters:[[ids]], associations:{<class>:{<id>:p}}, companions:[{from,to,support,reliable}]}`

## Boxes

- [x] T1 W3: reproduce the fail-fast receipt hole (the guard accepts a `--quick --fail-fast` receipt with a carried red), fixture plus control; W2 adds the flags to `narrowingFlags`
    (ticked) 2026-10-08T08:54:33Z by d778be9d: commit:903de767c guard unjudged_blocked (143 cases rc0) and commit:73eb13b08 runner flags (run.ts --selftest 369 assertions ok)
- [x] T2 W1: `jsonl_append.py` lifted from wl_store, with wl_store importing it; concurrency and torn-tail tests with controls
    (ticked) 2026-10-08T08:54:34Z by d778be9d: commit:73eb13b08 jsonl_append.py loaded by .claude/hooks/stop/wl_store.py:649; concurrency and torn-tail tests pass (test_gate_ledger.py)
- [x] T3 W1: `gate_ledger` append/backfill/fold-ci/rotation; backfill of the 50+ receipts here and in the push clone
    (ticked) 2026-10-08T08:54:35Z by d778be9d: commit:73eb13b08 gate_ledger append/backfill/fold-ci/rotation with tests; live ledger 357 rows
- [x] T4 W1: path classes and the classification (real/flaky/clock/infra/chronic, per-finding descent); the replay fixture from 2026-10-08 passes with its controls
    (ticked) 2026-10-08T08:54:37Z by d778be9d: commit:73eb13b08 test_gate_model_replay.py replays the 2026-10-08 receipts with controls (59 passed)
- [x] T5 W1: clusters, associations, companions; `model.json` v1; `refresh` with TTL, report, worklist items with token dedup
    (ticked) 2026-10-08T08:54:38Z by d778be9d: commit:73eb13b08 clusters/associations/companions, model.json v1, refresh TTL (.ci/rediacc_ci/ci/gate_model.py:86); tests pass
- [x] T6 W2: `ledger.ts` writing rows from `onFinish`; loud degradation
    (ticked) 2026-10-08T08:54:39Z by d778be9d: commit:73eb13b08 ledger.ts writes rows from onFinish; runner and learned selftests rc0
- [x] T7 W2: `rank.ts` plus the `pool.ts` two-key rank, the `sim.ts` `predictMakespan` safety check, preflight/stage 1 and the cold-start fallback; property test over the archived timelines with a control
    (ticked) 2026-10-08T08:54:40Z by d778be9d: commit:73eb13b08 rank.ts + pool two-key rank + sim predictMakespan; 15/15 mixes ranked, control 10 slower unpinned
- [x] T8 W2: RED streaming, the `--events` stream, `--stop-on-stage-red` (exit 3, no receipt), `--narrow [--print]`
    (ticked) 2026-10-08T08:54:41Z by d778be9d: commit:73eb13b08 RED lines scripts/ci-runner/report.ts:475, --events, --stop-on-stage-red (scripts/ci-runner/run.ts:352), --narrow --print live rc0
- [x] T9: no gate id in gate_model.py, gate_ledger.py, ledger.ts or rank.ts; a test with a planted control
    (ticked) 2026-10-08T08:54:43Z by d778be9d: commit:73eb13b08 T9 scan .ci/rediacc_ci/tests/test_gate_model.py:530 with planted-id control :563
- [x] T10 W4: check-deps `--upgrade` moves the syncpack pinVersion groups (#3b831146); selftest plus control
    (ticked) 2026-10-08T08:54:44Z by d778be9d: commit:a15f054ce planPinSync/syncPinGroups in check-deps.ts, selftest section 13 with the skip-pin-sync mutant
- [x] T11 lead: the ci-trace fold-in hook, `prepush.sh` streaming plus `TRIAGE=1`, the pr-babysitter loop docs
    (ticked) 2026-10-08T09:12:23Z by d778be9d: commit:94414782f ci-trace folds a final verdict into the gate ledger (detached gate_model refresh; selftest probes) and commit:cc82d9f2a pr-babysitter narrow-then-full loop; the scratchpad pre-push wrapper streams RED/STAGE lines and TRIAGE=1 exits 3 with no receipt
- [x] T12 lead: a live run on the real tree. Backfill, refresh, then one triage pre-push. Record time-to-first-red against 10-08 (459-975 s) and confirm the receipt and guard behaviour
    (ticked) 2026-10-08T10:17:44Z by d778be9d: commit:4e7ad3c8b made the refresh finish (3m51s; model.json 12 clusters, 158 runs); then a TRIAGE=1 pre-push at 2026-10-08T12:08Z: ranking ON, first RED check:ci-pr-task-trailers at 7.0s into ci:quick (10-08 baseline 459-975 s); stopped rc=3, prepush-receipt.json mtime unchanged (no receipt written)

## Record corrections

- The T12 tick cites a pre-push at "2026-10-08T12:08Z". That clock reading is local time (+0200, commit 4e7ad3c8b is dated 12:08:25 +0200), so the run was at 10:08Z, before the 10:17:44Z tick.

## Risks

- `scripts/ci-runner/**` is a global input (`scripts/ci-runner/input-hash.ts:24`), so landing it voids every carried gate once.
- `check:ci-pytest` (about 945 s) stays the critical path of a full receipt. This plan shortens the triage cycles, not the full run.
- Elastic-gate wall estimates can be stale, and the safety check uses the same estimates. Each run records simulated against actual wall in its events.
- The UTC-boundary clock rule is a heuristic; probes are the decisive check and cost a clone checkout.
- Lifting `_append_lines` touches the Stop hook's store; T2 runs the store's full suite.
