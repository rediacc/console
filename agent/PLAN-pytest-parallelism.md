# PLAN: parallelise check:ci-pytest with pytest-xdist
Status: done Owner: 8f55d4f0 Updated: 2026-09-07

Operator order 2026-09-07, verbatim: "let's employ a planning agent and implement then validate then optimize again then validate." Worklist #d76fa6de.

## Why

`check:ci-pytest` IS the local wall clock. The receipt records `wallMs: 675256` for a `--quick` run of 357 gates; the 356 others all finished inside that one gate. A full run measured `1 failed, 8944 passed in 810.16s`. It runs serially: `pyproject.toml:266` is `addopts = "-ra --strict-markers --strict-config"` with no `-n`, and `import xdist` is a `ModuleNotFoundError`. `nproc` is
24.

Three measured facts, each verified against this tree:

**It is 45x the next gate.** Taking the FLOOR of `recent` per gate from `.ci/cache/gate-durations.json` -- the statistic `scripts/gates/check-gate-manifest.ts:503` uses -- no other quick-lane gate has a floor above 17.0s, and the sum of all 357 floors is 1227.2s against a 22-slot pool. The lane's throughput-bound wall is about 56s. Everything above that is this one gate.

**It is about to crash rather than report.** `.ci/rediacc_ci/check_pytest.py:277` passes `timeout=900` and `main()` has no `except subprocess.TimeoutExpired`, so at 810.16s measured there are 90 seconds of margin before the gate raises a traceback instead of returning a verdict. The corpus grows about 200 tests per W7 P3 batch.

**It is about to be retiered against its will.** Its duration window is exactly `[18132, 27488, 658870, 661530, 675251]`, so the judged floor is 18.1s only because two stale small samples survive. Two more runs roll them out, the floor becomes ~658s, `BUDGET_MS * SLACK` is 20s, and the oracle demands `slow: true` -- which `scripts/ci-runner/run.ts:384` uses to drop all 8945 tests
out of the pre-push lane.

## What the design refuted, and it changed the shape of the work

**The hazard I briefed does not exist.** I told the planner that the ported gate tests plant a defect in the REAL subject file and restore it, so `-n auto` would corrupt the tree. An AST sweep of all 132 Python files under both test roots -- resolving names bound to `paths.from_root(...)` / `paths.repo_root()` and looking for
`write_text`/`write_bytes`/`unlink`/`rename`/`chmod`/`mkdir` against them -- finds ZERO writes to a real-tree path. The plants are in-memory: read the real file, edit the string, write the result into `tmp_path`. The `shutil.copy` calls copy FROM the real tree INTO a tmp root.

It is enforced, not lucky: `.ci/rediacc_ci/tests/gates/test_twin_parity.py:187-213` already computes the lock join and FAILS the port if any ported module's `BASH_TWIN` is in the `mutex | reads` set, with its own anti-vacuity refusal for an empty union. Measured: 29 of 29 ported modules resolve against the lock, and ZERO are in either claim.

So the lock join is the right derivation and it is sound -- but it yields zero groups today, and an anti-vacuity floor asserting "at least one group exists" would be red on day one and would get suppressed. That is the design-changing fact.

## The real hazards, with counts

| Class | Count | Verdict under xdist |
|---|---|---|
| Writes outside `tmp_path` into the real tree | 0 | not a hazard |
| `os.chdir` | 2 (save/restore pair) | not a hazard: workers are PROCESSES |
| `os.environ` mutation without monkeypatch | 35 | not a hazard, same reason; pre-existing fragility |
| Deterministic port allocation | 1 (`.ci/rediacc_ci/tests/test_core_ports.py:209`, first free run in 20000-30000) | REAL: two workers pick 20000 |
| The gate drives 29 real bash twins against the real tree while declaring NO isolation to the pool | 29 | REAL and pre-existing |

## The design

**`-n` does NOT go in `addopts`, and this is load-bearing.** `.ci/rediacc_ci/tests/gates/test_twin_parity.py:154` runs a NESTED `python -m pytest` per module, which reads the same ini. With `-n auto` in `addopts`, 24 outer workers each spawning 24 inner workers is 576 processes. `-n` goes on the gate's argv instead, so nested parity runs stay serial and a hand-typed `pytest` stays
serial.

**Worker count is `min(8, os.cpu_count())`, not `auto`.** `auto` oversubscribes against the runner's own 22-slot pool. The shape and the reason are already written down at `.ci/rediacc_ci/battery.py:480-484`: several tests shell out to npx/tsx, and 20 concurrent node startups cost more in contention than they buy. Override with `PYTEST_JOBS`. Pair with `weight: 8` on the manifest
entry; `scripts/ci-runner/pool.ts:242` caps effective weight at the pool size, so a 2-slot CI pool reads it as "the whole pool".

**`--dist loadgroup`, with the group DERIVED from the lock.** the installed pytest-xdist package, remote.py lines 236-254 (third-party, not in this repo) reads `xdist_group` in the worker and `continue`s on items without it, so ungrouped tests distribute freely. A new `.ci/rediacc_ci/xdist_groups.py` exposes `group_for(module)`, using `battery.classify_from_lock` verbatim -- no
fourth copy -- plus a module-level `XDIST_GROUP` escape for the one genuine shared resource no registry knows about (the port scan). The hook lives in a repo-root `conftest.py` because it must reach all three `testpaths` roots.

**Provisioning, with three corrections to my brief.** The pins file is `.devcontainer/toolchain.env`, NOT `.ci/config/toolchain.env`, which has never existed -- the devcontainer build context cannot reach outside `.devcontainer/`. The convention for a uv-installed Python package is a BARE version (`RUFF_VERSION=0.16.1`, `PYTEST_VERSION=9.1.1`); the `UV_SHA256_*` constants exist
only because those are tarballs fetched by URL. And `.ci/bootstrap.sh`'s install arm is idempotent by resolution, so it needs a SEPARATE xdist check rather than a change to the pytest one.

## What is NOT being changed

- `addopts`, for the fork-bomb reason above.
- `filterwarnings = ["error"]`. If xdist trips a pytest 9 deprecation that is a failure,
which is the point of the setting. Do NOT add an `ignore::` to get past it.
- `testpaths`, `pythonpath`, `cache_dir`, `MIN_TESTS`, the `77` semantics.
- `test_twin_parity.py`'s nested invocation, which stays serial deliberately.
- The 35 env sites and 2 chdir sites: real pre-existing fragility, not made worse here.
- No gate suppressed, allowlisted, or given a BLOCKER to get past this.

## Boxes

Ordered so no half-done state is corrupting: through box 4 the suite runs as it does today.

- [x] 1. **CLOSED BY OPERATOR RULING, not by completion, and that distinction is the point.** The three-run FLOOR and the `--durations` long pole were never taken, because the operator ruled STOP AT 2.08x before box 10's re-measure needed them; box 10 was satisfied instead by the tier oracle's own floor (367.9s over five samples), which is the same statistic taken by the instrument that judges it. Original text: the serial baseline is recorded (8945 tests, exit 0, stderr empty, ~617-660s
      with only a read-only agent in the tree). The three-run FLOOR and the --durations long pole
      are NOT yet taken, and box 10 needs them. Measure the before HONESTLY on a quiesced tree, three runs, keep the FLOOR, and
      record the 40 slowest tests. The 675.3s receipt is NOT the before -- it was measured
      inside a 22-way contended pool, and invariant 14 forbids it.
- [x] 2. Fix the imminent crash: catch `TimeoutExpired`, return a verdict, raise the
      timeout against box 1's floor. Independent of everything else; land it regardless.
- [x] 3. Declare the isolation the gate ALREADY needs: `reads: ['tree:repo']` on
      `check:ci-pytest`, and extend `paths` to cover `.claude/rediacc_hooks/**` and
      `.ci/scripts/test/gates/**`, neither of which the current filter can see.
- [x] 4. Pin and provision xdist: `PYTEST_XDIST_VERSION=3.8.0`, a `resolve_xdist` rung,
      a `setup/tools.py` row NOT added to `TOOL_KEYS`. Suite still serial after this box.
- [x] 5. Prove xdist works here at all: one hand run of `-n 2 --dist loadgroup`, and
      capture the exact header bytes.
- [x] 6. Teach the gate to read the parallel header. WITHOUT this, `-n` makes
      `COLLECTED_RE` return None and the gate fails naming the WRONG problem.
- [x] 7. Land the group derivation, still with no `-n`. Markers are inert without
      `--dist loadgroup`, so the suite must still pass serially.
- [x] 8. Turn it on: `-n`, `--dist loadgroup`, `weight: 8`.
- [x] 9. Add the four controls below, each with a planted-defect demonstration.
- [x] 10. Re-measure and retier on a quiesced tree.

## The control that proves the parallelism is real

My framing was inverted: a derivation returning nothing produces MAXIMUM spread, not minimum, because ungrouped items distribute freely. The collapses that actually exist are all green-and-slow, so four controls, none hand-typed:

- **C1** the run was actually parallel: asked for `-n N` (N>=2) but the header reports
fewer than 2 workers, refuse. Catches xdist missing, `-p no:xdist`, autoload disabled.
- **C2** the join still resolves: every module declaring `BASH_TWIN` must have its
basename in the lock's gate-test set. 29/29 today, both sides derived.
- **C3** enough scheduling units to fill the workers: distinct groups plus ungrouped
items must not fall below the worker count. Corpus-derived, set-based.
- **C4** planted both-directions in `--selftest`: 8 tests recording
`PYTEST_XDIST_WORKER` under `-n 4` must show >=2 distinct workers; the same 8 sharing one `xdist_group` must show exactly 1.

## What could still go wrong

- **xdist 3.8.0 against pytest 9.1.1 is unproven upstream.** Its two private imports
resolve, but a private BEHAVIOUR change would not show up that way. Box 5 finds out. Fallback is a `PYTEST_VERSION` downgrade, which is an operator decision, not a quiet fix.
- **The long pole may cap the win.** `test_port_and_twin_agree` is parametrized over 29
modules, each running a real bash twin AND a nested pytest. If one costs 60s, no worker count goes below 60s. Box 1 measures it before any promise.
- **Retiering is a genuine fork.** A realistic post-change figure is 60-140s against a 20s
budget. `slow: true` loses pre-push pytest entirely. DEFAULT IF UNANSWERED: split the gate by cost (mark the twin-parity half `slow`, keep ~8900 unit tests quick). Do NOT raise `BUDGET_MS` -- that is a lane-wide policy change to accommodate one gate.
- **`weight: 8` costs the lane 8 of 22 slots.** `-n` and `weight` must move together; an
`-n` exceeding `weight` is an undeclared claim on the machine.

## The second pass

The prediction I gave the planner was WRONG in a useful way. I named `check:ci-trap-registry` 33.5s and `check:ci-guard-mention-anchoring` 30.6s from run 3 -- but those are CONTENDED numbers, inflated about 2x because pytest was eating the box. Their floors are 15.3s and 14.7s. Invariant 13 demonstrating itself.

**There is no next single bottleneck.** After pytest, the highest floor is 17.0s and the sum of all 357 floors is 1227.2s across 22 slots. The lane stops being latency-bound and becomes THROUGHPUT-bound, so the second pass targets total CPU mass:

| Runtime | Gates | Serial mass | Mean |
|---|---|---|---|
| bash | 184 | 749.5s (61%) | 4.07s |
| tsx/node | 115 | 313.3s (26%) | 2.72s |
| python | 41 | 124.4s (10%) | 3.03s |

1. Split `check:ci-pytest` by cost, not subject: mark the twin-parity half `slow`, keep
the unit tests quick. Resolves the retiering fork with no coverage loss.
2. **Watch the concentration the port itself creates.** Those 184 bash gates are what W7
P3 is porting. Today they are 184 independently schedulable units across 22 slots; ported, they become ONE unit. `-n` and `weight` must be re-derived at the end of every batch or the port makes the lane worse.
3. Only then per-gate work, which is a process-startup batching question and must be
measured before it is designed.

## What VALIDATE found, and it beat the plan's own hypothesis

`-n 8` measured **1.64x SLOWER** than serial on a quiesced box (unit half, same tests: 619.17s vs 1013.59s). The operator ruled "confirm the cause first" and "investigate more, it seems like we're missing something", so box 8 was NOT applied.

**The cause is session-fixture duplication, and neither the plan nor I predicted it.** Two `scope="session"` fixtures serve **6446 of 8968 tests (72 percent)**: `.claude/rediacc_hooks/tests/test_guards_differential.py` forks `env -i bash` once per case across 6017 cases (~18k processes), and `test_shellscan_differential.py` forks ~12k subshells across 416 files. A session fixture
is scoped to a PROCESS and xdist workers ARE processes, so EVERY worker rebuilds ~30k processes of setup -- about 240,000 at `-n 8`, before any of those 6446 tests does useful work. They are otherwise pure in-process comparison, which is exactly why the suite looks cheap at 71ms/test and collapses under workers.

**My own hypothesis was refuted: collection is 0.53s, not a cost at all.** I had briefed the investigator that per-worker collection of 1377 files would explain the gap.

**The mechanism this plan built was right but UNPOINTED.** The conftest groups by module for `--dist loadgroup`, but neither differential module declared an `xdist_group`, so their 6446 tests scattered across every worker and each paid the full driver.

FIXED 2026-09-07: both modules now declare a group, and deliberately SEPARATE ones (`hooks-guards`, `hooks-shellscan`). A single shared group would have pinned all 6446 tests to ONE worker -- trading 8x duplication for serialising 72 percent of the corpus onto one core, the same mistake inverted. Verified inert: 6446 still collect, ruff clean, no `-n` applied. The before/after
measurement is deliberately NOT taken yet, because the measurement agent was mid-matrix and invariant 14 forbids a contended number.

## Record

Triaged: worklist #d76fa6de, under the operator's ordered sequence.

## Outcome, 2026-09-07: DONE at 2.08x, stopped there by operator ruling

**823.93s to 396s, exit 0, 8968 tests.** The operator's four-step order (plan, implement, validate, optimise again, validate) ran to completion and the ruling on the second optimisation round was **"Stop at 2.08x"**.

### The two root causes, both fixed BEFORE `-n` was turned on

Turning on `-n 8` first made pytest **1.64x SLOWER**, and the reason is the part worth keeping:

1. **The group derivation was INERT.** `pytest_collection_modifyitems` in the root
`conftest.py` had no `@pytest.hookimpl(tryfirst=True)`, and xdist's own undecorated hook wins under pluggy's ordering. The whole derivation ran and changed nothing. This is the defect that makes a parallel run look like a parallelism problem when it is a hook-ordering problem.
2. **Session-scoped fixtures duplicate per WORKER.** A session fixture is
per-PROCESS and xdist workers ARE processes, so every worker paid the full session cost.

**A hypothesis of mine was REFUTED rather than quietly dropped:** I proposed per-worker collection as the cause. Collection is 0.53s. It was not that.

### What landed

`.ci/rediacc_ci/check_pytest.py` puts `-n <jobs> --dist loadgroup` on ARGV, not in `addopts`, with `PYTEST_JOBS_CAP = 8`, a `RUN_TIMEOUT_S` with a real `TimeoutExpired` verdict arm, and a `COLLECTED_RE` union covering both header spellings. The hooks corpora carry SEPARATE `xdist_group` values (`hooks-guards`, `hooks-shellscan`): one shared group would have pinned 72% of the corpus
to a single worker, which is the trap that makes `loadgroup` look useless.

### Not done, deliberately, and still measured

The operator ruled OUT the guards-driver `xargs -P` work (**275.59s to 52.65s, measured**) and the flock fix. Both remain recorded here so the numbers are not lost, and neither is to be started without a new instruction.

### Correction to this plan's own premise

The "Why" section above says `pyproject.toml:266` carries no `-n`. That is still true and is now correct BY DESIGN, not by omission: the flag lives on argv so that a direct `pytest` invocation stays serial and only the gate parallelises.
