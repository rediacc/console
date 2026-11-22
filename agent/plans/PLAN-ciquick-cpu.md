# PLAN: ci:quick CPU -- sound gate reuse, pytest by impact locally, faster slow tests
Status: approved -- operator ruling ASKED:2026-11-16T11:35Z chose fixes A+B+C in one plan; rejected: a pre-commit instant tier
Owner: d778be9d
First-Seen: 2026-11-16
Depends-On: no-dep -- the schema 2 receipt, the carry logic, quick-select and the pytest gate are all in the tree now
Priority: P1 -- every push costs about 21k core-s and 1409-1886 s of wall time on 24 cores, and that cost delays every PR
Concurrency: parallel -- the writer groups below edit separate files; scripts/ci-runner/manifest.ts is also owned by PLAN-ci-quick-cpu-scheduling.md, so W2 lands only when that plan has no open edit there
Owns: agent/plans/PLAN-ciquick-cpu.md, scripts/ci-runner/input-hash.ts, scripts/ci-runner/run.ts, scripts/ci-runner/quick-select.ts, scripts/ci-runner/typecheck-incremental.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/path-trace.ts, .claude/rediacc_hooks/**/block_unverified_push*.py, .ci/rediacc_ci/check_pytest.py, .ci/rediacc_ci/pytest_impact.py, .ci/policy/pytest-smoke.json, .ci/policy/pytest-impact.json, .ci/policy/pytest-slow-allow.json, .ci/scripts/quality/check_gate_paths_honest.py, .ci/rediacc_ci/tests/**, scripts/ci-runner/pool.ts, scripts/ci-runner/lanes.ts, scripts/gates/check-guard-mutations.ts, .claude/rediacc_hooks/tests/**, .claude/rediacc_hooks/guards/test-*.py
Worklist: PR-TASK 79b7e92e

## Problem, measured

- One ci:quick run costs about 21k core-s and 1409-1886 s of wall time, with all 24 cores busy. check:ci-pytest is 69.8% of gate CPU (median 18,377 core-s, .ci/cache/gate-durations.json).
- The suite has 36,212 tests. The 594 tests over 5 s take 68% of pytest time (.ci/cache/quality-pytest/junit.xml).
- Carry is nearly dead. The receipt at 2026-11-16T11:17Z carried 23 gates and ran 290. Typical runs carry 0-32 of about 380 gates.
- check:types:incremental used 79 cpu-s on an unchanged tree, although it claims to skip when nothing changed.
- Linting only changed files would save seconds: biome lint 3.3 s, biome format 0.9 s, ruff 1.7 s and the warm incremental typecheck 6.4 s run over the whole repo.

## Root cause

1. **Most gates hash the whole tree.** 349 of 397 gates.lock.json entries declare no `paths`, so their input glob is `**` (scripts/ci-runner/input-hash.ts `computeGateHashes`, `WHOLE_TREE_GLOB`). Any commit changes their hash, so they carry only across a byte-identical tree.
2. **Rule 4 drags in the slow gates.** quick-select rule 4 (scripts/ci-runner/quick-select.ts:8-14) selects every slow gate with no `paths` on any non-empty diff. check:ci-pytest is one of them, so a one-line doc fix runs all 36k tests.
3. **Null hashes cascade.** A gate whose `needs` hash is null (exempt, `env`, or whole-tree-null) becomes `needs-null` and always runs (input-hash.ts `compute`). 42-51 carry-exempt rows (.ci/policy/carry-exempt.json) feed this cascade.
4. **One prior receipt.** `planCarry(prior, ...)` takes a single prior receipt, so a red run followed by a fix discards verdicts that `.ci/cache/receipts/<tree>.json` still holds.
5. **Pytest runs everything** locally, the same as CI. A few files dominate (Fix C).
6. **The incremental typecheck re-runs** on an unchanged tree: its skip key holds something that changes between two runs (suspects: mtimes rewritten by the clone refresh, hard-linked node_modules).

## Fix A: gate reuse

**A1. Carry by hash across receipts.** Index every whole receipt under `.ci/cache/receipts/` by `(gate id, inputHash)` and carry from any receipt with an `ok` verdict at that hash. The guard already re-hashes each carried gate against its origin receipt (docs/agent-reference/ci-gates.md:25-26), so the hash contract is unchanged. Keep the last 200 receipts.

**A2. Derive `paths` from a trace.** New `scripts/ci-runner/path-trace.ts` runs one gate in the kept clean clone under `strace -f -e trace=openat,open,stat,newfstatat,readlink,execve,getdents64`, keeps the tracked paths it opened, stat'ed or listed, and folds them into globs (a directory more than 50% read, or listed, becomes `dir/**`). `--write` merges them into the manifest entry, then `gen-manifest` regenerates gates.lock.json. A gate reading more than 30% of the tree, or `.git/`, stays whole-tree or goes carry-exempt with a named reason. Linux-only; elsewhere it refuses.

**A3. Fail a gate that reads an undeclared path.** This is what makes carry sound. New gate `ci-gate-paths-honest`, to be registered as a `check:` script (.ci/scripts/quality/check_gate_paths_honest.py) re-traces each gate with `paths` and fails on a tracked path read outside `paths ∪ GLOBAL_INPUTS ∪ leaf closure`, naming the path and the `path-trace --write` fix. The quick lane traces only gates whose lock entry, leaves or `paths` changed; a nightly rotation traces a third of the gates. A second, independent check: a sparse clone holding only the declared inputs must give the same verdict, for the 10 costliest gates each rotation. A fixture gate reading one undeclared file must fail both checks.

**A4. Stop the null cascade.** Each carry-exempt row records why (`clock|history|network|cache`). A gate whose `needs` edge only orders an artifact hashes through the producer's `filesHash`, not its nullable `inputHash`. TS hasher, Python twin and parity test move in one commit.

**A5. Rule 4 narrows by itself** once slow gates declare `paths`.

**A6. Fix check:types:incremental.** Log the skip key on two runs at one tree, find the field that differs, hash content instead. Test: the second of two runs reports `skipped` under 5 cpu-s; touching one .ts file makes it run tsc.

## Fix B: pytest by impact locally, full suite in CI

**B1. The map.** New `.ci/rediacc_ci/pytest_impact.py` builds `test file -> import closure` with quick-select's resolver rules (`resolvePy`) plus each test's `conftest.py` chain, from `git ls-tree` and an AST parse (no imports executed), cached by the tree's Python blob digest.

**B2. Data reads.** Non-Python files a test reads (fixtures, JSON policy, shell hooks) go in a per-directory `reads` table in `.ci/policy/pytest-impact.json`, derived with the A2 tracer attributed per test file through `PYTEST_CURRENT_TEST`, and re-traced by A3's rotation.

**B3. Selection.** The smoke floor (`.ci/policy/pytest-smoke.json`, about 300 tests under 1 s covering every top-level package), plus every test file whose closure or `reads` meets the change set since the last push, plus every changed test file.
(corrected 2026-11-22, operator /ask) "Since the last push" reads "since the last green receipt head": W11's last-green record is the base, and the push base applies only when no green record exists. Measured 2026-11-21: check_pytest.py:1422 deletes scope.json at every run start and only a green run rewrites it, so after any red run (48 of the last 100 receipts) the base fell back to origin/main and every such run printed `pytest-impact: FULL`.

**B4. Fall back to the full suite** when `conftest.py`, `pyproject.toml`, `uv.lock`, pytest config, check_pytest.py or pytest_impact.py changed; on an unresolved import; on a changed tracked file under `.ci/` or `.claude/` that neither the graph nor `reads` covers; above 40% of test files; or on a missing map. Each prints `pytest-impact: FULL (<reason>)`.

**B5. CI stays full.** Under `CI=true` or `--full`, check_pytest runs the whole sharded suite. The receipt records `pytestScope: impact|full`, the selected count and the map digest, and `block_unverified_push` accepts `impact`, since the ruling makes CI the full-suite backstop. A red on main from an impact miss adds the missed edge to `reads` with a regression test.

**B6. Carry.** check:ci-pytest declares `paths` (Python trees, `reads` roots, test roots), so TypeScript-only and docs-only pushes carry it.

## Fix C: the slow tests

Every assertion stays, and each box records the test count before and after.

- **test_ops_mirror_config_store** (105 tests, 3,412 s): a module-scoped store with per-test reset, an injected clock instead of real sleeps. Target under 300 s.
- **test_hooks_delegates** (1,858 s; orphan-control suites up to 299 s): read .ci/rediacc_ci/check_pytest.py:84 (the hook twin suite reportedly runs three times) before editing; run the controls once per session and parametrize the twin in one process. Target under 600 s.
- **test_guards_differential** (1,370 s): cache the reference side's verdicts per input digest; one subprocess per guard instead of per case. Target under 450 s.
- **test_quality_plan_implementation::test_main_with_merge\*** (425 s): build the merge-history repo once per session, `git clone --local --shared` per test. Target under 60 s.
- **Ratchet:** a new test over 10 s (median of 3 junit runs) fails CI unless `.ci/policy/pytest-slow-allow.json` lists it with a reason.

## Measurement acceptance

Core-s is the sum of per-gate `cpuMs` in the receipt plus the runner's own CPU (receipt `utilisation` block).

| Scenario | Today | Target |
|---|---|---|
| ci:quick after a one-file `.ci/rediacc_ci/*.py` docstring change | about 21k core-s | ≤ 4,000 core-s |
| One-file TypeScript change | about 21k core-s | ≤ 3,000 core-s |
| Red rerun: a red receipt, then a one-line fix | full cost | ≤ 2,500 core-s, every gate the fix misses carried |
| Rerun on an unchanged tree | not measured | ≤ 200 core-s; check:types:incremental ≤ 5 cpu-s |
| Full pytest | 18,377 core-s | ≥ 35% lower |

## Boxes

### W1 carry lookup and null cascade -- scripts/ci-runner/input-hash.ts, scripts/ci-runner/run.ts, .claude/rediacc_hooks/**/block_unverified_push*.py and its parity test
- [x] W1.1 [writer] Confirm whether run.ts reads only the last receipt as prior; if so add carry by `(id, inputHash)` across `.ci/cache/receipts/` (A1), keeping 200. Accept: a test carrying from a receipt two runs back, and a control where a changed hash does not carry.
    (ticked) 2026-11-18T12:32:45Z by d778be9d: commit:182b846803 -- box Accept re-run 2026-11-18 by a lease writer, rc 0
- [x] W1.2 [writer] Artifact `needs` hash through the producer's `filesHash`, plus the exempt-reason field (A4), TS hasher and Python twin together. Accept: hash parity test passes; the `needs-null` count in `--quick --list --json` falls.
    (ticked) 2026-11-18T12:32:48Z by d778be9d: commit:182b846803 -- box Accept re-run 2026-11-18 by a lease writer, rc 0
    Note (2026-11-19): W1.2 landed the `needs` edge through the producer's `artifactHash`, which folds the producer's `filesHash` with its `defHash` and `needs` (scripts/ci-runner/input-hash.ts:266), so the producer's `filesHash` is what the edge hashes. The tick did not record the before and after `needs-null` count of `--quick --list --json`; the Accept's count clause rests on the hash parity test and the rc 0 re-run alone.

### W2 path declarations -- scripts/ci-runner/path-trace.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json
- [x] W2.1 [writer] path-trace.ts with `--gate`, `--write` and directory-listing folding (A2). Accept: a fixture gate reading two files gets exactly those two plus its listed directory.
    (ticked) 2026-11-17T14:08:18Z by d778be9d: commit:988ca9561b c64047e813 52e05ba9f2 fe5b4c2b5b 4936a0f350 7a9a97bac4; path-trace selftest 48/48 rc=0, trace-honest selftest 24/24 rc=0, pytest 13 passed, tsc rc=0 (writer report); check:ci-paths-origin rc=0 on the landed tree
- [ ] W2.2 [writer] Trace the 349 whole-tree gates in the clone and write their `paths`; gates over 30% of the tree or reading `.git` stay whole-tree with a named reason. Accept: whole-tree count ≤ 80 in gates.lock.json, and `npm run ci` green on an unchanged tree.

### W3 honesty gate -- .ci/scripts/quality/check_gate_paths_honest.py, its manifest row through W2's lock regeneration, .ci/rediacc_ci/tests/test_gate_paths_honest.py
- [x] W3.1 [writer] Trace mode and sparse-clone mode, diff-scoped in quick, with the rotation flag (A3). Accept: the undeclared-read fixture fails both modes; the declared fixture passes.
    (ticked) 2026-11-21T14:12:34Z by d778be9d: present: scripts/ci-runner/trace-honest.ts:9 (commit bf3461577); trace-honest --selftest 66/66 rc 0

### W4 pytest impact -- .ci/rediacc_ci/pytest_impact.py, .ci/rediacc_ci/check_pytest.py, .ci/policy/pytest-smoke.json, .ci/policy/pytest-impact.json, .ci/rediacc_ci/tests/test_pytest_impact.py
- [x] W4.1 [writer] The map, selection, smoke floor and every B4 fallback, each with a test. Accept: one test per fallback reason, and a control where a leaf-module edit selects only its importers plus smoke.
    (ticked) 2026-11-19T02:13:32Z by d778be9d: commit:c1a3d736 map, selection, smoke floor and every B4 fallback, 12 tests rc 0
- [x] W4.2 [writer] check_pytest impact/full switch, receipt fields `pytestScope`, selected count and map digest, and guard acceptance (B5). Accept: `CI=true` runs the full suite, asserted on the collected count.
    (ticked) 2026-11-22T15:47:55Z by ace763dd: present: .ci/rediacc_ci/check_pytest.py:1313 pytestScope full/impact (755fd65e0 a3548fda6); check_pytest --selftest rc 0, 94 controls incl wants_full
- [x] W4.3 [writer] Derive `reads` with the tracer and declare check:ci-pytest `paths` (B2, B6). Accept: a docs-only diff carries check:ci-pytest.
    (corrected ASKED:2026-11-18T14:50Z) The traced union reads all 11,668 tracked files, so no narrower `paths` is honest: check:ci-pytest is whole-tree and pytest_impact selects the tests whose traced reads cover the change. Accept: a docs-only diff RUNS check:ci-pytest and selects only its traced readers plus smoke.
    Note (2026-11-19): the W4.3 box line keeps the superseded Accept so its signature holds; the tick below certifies the corrected Accept on the line above, not the box line's.
    (ticked) 2026-11-18T15:40:35Z by d778be9d: commit:5e5d1c0f1c commit:bc22fff052 -- check:ci-pytest whole-tree (docs edit probe CARRY before, RUN after), select() judges every changed file through the reads table (738 test files, 16,928 entries); docs/playbook 30, hook guard 71 of 936; pytest_impact tests 141 passed, run.ts --selftest rc 0. DEPS-WAIVED: W4.3 code and tests stand on their own

### W5 typecheck skip -- scripts/ci-runner/typecheck-incremental.ts and its test
- [x] W5.1 [writer] Find the volatile skip-key field and hash content instead (A6). Accept: the two-run test and its touched-file control.
    (ticked) 2026-11-18T12:32:50Z by d778be9d: commit:859d10c020 -- box Accept re-run 2026-11-18 by a lease writer, rc 0

### W6-W10 slow tests, one writer per file
- [x] W6 [writer] test_ops_mirror_config_store: module-scoped store and injected clock. Accept: same test count, ≤ 300 s in junit.
    (ticked) 2026-11-18T12:32:38Z by d778be9d: commit:7a21752ae9 -- box Accept re-run 2026-11-18 by a lease writer, rc 0
- [x] W7 [writer] test_hooks_delegates and the check_pytest.py triple run (coordinate the check_pytest.py hunk with W4): controls run once. Accept: same test count, ≤ 600 s.
    (ticked) 2026-11-19T02:13:12Z by d778be9d: commit:3828d77f20 test_hooks_delegates 962 s -> 477 s wall, 95 passed rc 0; guard harnesses rc 0 on the landed tree
- [x] W8 [writer] test_guards_differential: reference cache and batched subprocesses. Accept: same case count, ≤ 450 s; a deliberately broken guard still fails the differential.
    (ticked) 2026-11-18T12:32:41Z by d778be9d: commit:a20a16ab88 -- box Accept re-run 2026-11-18 by a lease writer, rc 0
- [x] W9 [writer] test_quality_plan_implementation merge fixtures: session template and local clones. Accept: same test count, ≤ 60 s.
    (ticked) 2026-11-18T12:32:43Z by d778be9d: commit:1a8401480d -- box Accept re-run 2026-11-18 by a lease writer, rc 0
- [x] W10 [writer] Slow-test ratchet and `.ci/policy/pytest-slow-allow.json`. Accept: a fixture test sleeping 11 s fails the check.
    (ticked) 2026-11-18T01:29:22Z by d778be9d: commit:e3e12fc949 ce2d2e9e31 7d7ecd770a slow-test ratchet in check_pytest, serial re-time and own-phase judgment; ratchet tests 85 passed, check_pytest --selftest 94 rc 0

### W2b broad-gate reduction and the honesty gate (2026-11-17, worklist #f0da7369)

Measured after the re-trace landed in 4d95ef719d: gates.lock.json holds 159 whole-tree gates (154 traced whole-tree plus 5 carry-exempt never traced). A design read of path-trace.ts found most of them are classifier false positives: git's own repository check (`access(".git/objects")`, `access(".git/refs")`) is read as history for 61 gates that only run `git ls-files`, and Python's `-m` listing of the cwd turns into `.ci/**` 49 times. The realistic outcome is 65 to 82 whole-tree gates; 80 is reachable on the middle estimate, not guaranteed. The 30% line is not lowered and `refs` keys are not skipped to reach it.

- [x] W2.3 [writer] Classifier truth in path-trace: bare `objects`/`refs` existence checks and `objects/info/alternates` are discovery; `remote -v|get-url` and `rev-list --max-parents=0 HEAD` are discovery; `diff` with no revisions and only paths is the index plus those files; `status` is history; `.git/modules/*/(refs|packed-refs|logs)` is history; `ls-files` with `-s|--stage|--eol|--format|-m|-d` is content; trace `connect`, and a connection that is not loopback or a unix socket gives a whole-tree verdict with reason "network"; strace's own `strace:` lines are kept apart from gate output; a `--no-seccomp` retry; `--replace-declared`. Owns: scripts/ci-runner/path-trace.ts, .ci/rediacc_ci/tests/test_path_trace*.py. Accept: `npx tsx scripts/ci-runner/path-trace.ts --selftest` exits 0 with new controls (a trace of `git ls-files` plus access(.git/objects) is not history; `git log` still is; a submodule refs read is history; a fixture `connect` to 1.1.1.1 is "network", loopback is not), and `npx tsx scripts/ci-runner/path-trace.ts --gate check:ci-dead-bash --gate check:deps` gives reasons naming the git index and the network, not `.git/objects`.
    (ticked) 2026-11-18T01:29:19Z by d778be9d: commit:3a4a8513d3 bab2c5c804 path-trace classifier truth and list/name folding; review fixes 0cccf731 090f8602; path-trace --selftest 90/90 rc 0
- [x] W2.4 [writer] The hash contract gains `lists` (tracked children of a directory, no content), `names` (tracked paths matching globs) and `refs` (the sha a named ref resolves to), in one commit with the Python twin and after or inside W1.2; a gate with none of the three keeps a byte-identical inputHash. Owns: scripts/ci-runner/input-hash.ts, scripts/ci-runner/gate-spec.ts, scripts/ci-runner/quick-select.ts, scripts/gates/check-paths-origin.ts, .claude/rediacc_hooks/guards/block_unverified_push.py, .claude/rediacc_hooks/guards/test-block_unverified_push.py, .claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl, .ci/rediacc_ci/tests/test_input_hash_names_parity.py. Accept: `npx tsx scripts/ci-runner/run.ts --selftest`, `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_input_hash_names_parity.py .ci/rediacc_ci/tests/test_input_hash_exempt_parity.py` and `python3 .claude/rediacc_hooks/guards/test-block_unverified_push.py` exit 0, with controls: a new file in a listed directory moves the hash, an edit to an unread file there does not, a new HEAD sha moves a `refs: ['HEAD']` gate, and an unchanged lock entry keeps its earlier hash.
    (ticked) 2026-11-18T01:29:20Z by d778be9d: commit:2fff2da3b2 bf9ab97090 524ef7de4a lists/names/refs as gate inputs with --changed and advance accounting; review fix 65ac06bf; run.ts --selftest 634 rc 0
- [x] W2.5 [writer] Fold to names, after W2.3 in the same file: a listed directory goes to `lists` (root included), the parent of a missed lookup inside a tracked directory goes to `lists`, `ls-files` with only name-shaping flags gives `names: ['**']`, and the 30% line is measured on content globs only; trace-honest accepts `lists` and `names` and flags an undeclared listing or index read. Owns: scripts/ci-runner/path-trace.ts, scripts/ci-runner/trace-honest.ts. Accept: `npx tsx scripts/ci-runner/path-trace.ts --selftest` and `npx tsx scripts/ci-runner/trace-honest.ts --selftest` exit 0, with a fixture where `python3 -m` run from the root reading 2 files gives paths of those 2 plus `lists: ['', '.ci']`, and the same fixture without `lists` fails trace-honest.
    (ticked) 2026-11-22T15:47:58Z by ace763dd: present: scripts/ci-runner/path-trace.ts:9 lists/names fold (bab2c5c80); path-trace --selftest 159/159 rc 0, trace-honest --selftest 66/66 rc 0
- [ ] W2.6 [writer] Re-trace in the kept clone: the gates that exited non-zero under the trace run untraced first (red on the tree is named, not traced); heavy gates trace with `--jobs 1` and a timeout of 4x their average; needs edges guard-mutations to build:packages and trap-registry to build:cli; carry-exempt rows with a kind for network (deps, devcontainer-pins, bws-map-live, pr-epic-block, i18n-www-translation-freshness), clock (resprofile, go-deps, security-audit), history (renet-types, docker-image-freshness) and cache (aws-resolver); `refs` on the remaining history gates. Owns: scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/trace-ledger.ts, .ci/policy/carry-exempt.json. Accept: `node -e 'const g=require("./scripts/ci-runner/gates.lock.json");const n=g.filter(e=>e.gate&&!(e.paths||[]).length).length;console.log(n);process.exit(n<=80?0:1)'`, `npx tsx scripts/gates/check-paths-origin.ts` and `npm run ci` green on an unchanged tree; a count between 81 and 85 goes to the operator (count only carriable gates, or accept 85 with the named stays) instead of loosening a rule.
- [ ] W3.2 [writer] The declared path sets made honest, after W2.5: `npx tsx scripts/ci-runner/trace-honest.ts --origin declared --mode trace --jobs 4`, then each set becomes traced with `path-trace --gate <id> --replace-declared --write` unless it is small and exact, in which case it is widened. Owns: scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/trace-ledger.ts. Accept: `npx tsx scripts/ci-runner/trace-honest.ts --origin declared --mode both --sparse-top 36` exits 0, and `--origin traced --rotation 1/3`, `2/3`, `3/3` each exit 0 once.
- [ ] W3.3 [writer] Wire check:ci-gate-paths-honest: the gate header in trace-honest.ts; a manifest row running `npx tsx scripts/ci-runner/trace-honest.ts --quick --mode trace`, heavy, writesTree, needs build:packages and build:cli, carry-exempt with kind history; a quality-job step that installs strace and passes `--base origin/${GITHUB_BASE_REF:-main}`; the full rotation `--rotation auto --mode both --sparse-top 10` as a scheduled ci-drift.yml step; no new package.json key. Owns: scripts/ci-runner/trace-honest.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .ci/policy/carry-exempt.json, .github/workflows/ci-quality.yml, .github/workflows/ci-drift.yml, docs/agent-reference/ci-gates.md. Accept (local): `npm run ci -- --only check:ci-gate-paths-honest` green on an unchanged tree in 10 s or less; a plant adding one undeclared read to a traced gate's leaf turns it red naming the path; `npm run ci -- --only check:ci-gate-bind --only check:ci-parity --only check:ci-test-gate-wiring --only check:ci-package-key-budget` green.

### L machine load across trees (2026-11-21, worklist #b095886f)

Context: operator ruling 2026-11-21 (worklist #b095886f) folds four machine-load boxes into this plan. Read-only evidence the same day: the landing and development trees each run ci:quick in their own clone and the quick-clone lock is per checkout (scripts/ci-runner/quick-clone.ts:209, lock at :755); a machine-wide core lease exists (.ci/rediacc_ci/core_lease.py, run.ts coreBudget about 1288-1291, openLease about 4748) but reads no /proc/loadavg or RAM and ignores writers and processes outside the lease; vm:check takes only its own flock (.ci/rediacc_ci/drills/vm_check.py about :17 and :1415) and not the lease; on 2026-11-21 a landing ci:quick with writers active reached load about 22, check:deps, check:ci-account-server and build:www timed out, and load peaked at 39 on 24 cores.

- [ ] L0 [lead] Diagnose the 2026-11-21 landing ci:quick run: whether the core lease degraded ("lease unavailable" or "degraded" in the run header or the broker log) or processes outside the lease caused the load. Owns: none. Accept: the tick evidence names the run, quotes the header or broker line (or its absence), and names the uncounted process classes with their share of the load.
- [ ] L1 [writer] Load-aware gate admission in scripts/ci-runner/pool.ts and scripts/ci-runner/run.ts: a gate start waits, bounded and with a visible message, while the 1-minute load exceeds the core count by a margin; the loadavg reader is a fake-able seam. Depends on: PLAN-ci-quick-cpu-scheduling.md, which owns run.ts exclusively, so this box lands only when that plan has no open edit there. Owns: scripts/ci-runner/pool.ts, scripts/ci-runner/run.ts. Accept: `npx tsx scripts/ci-runner/run.ts --selftest` exits 0 with a fake load of 2C (no gate starts, the wait message prints, the bound ends the wait) and a 0.5C control (gates start at once).
- [ ] L2 [writer] vm:check holds core-lease tokens for its battery and drills. Depends on: L0 (the diagnosis names whether the lease is the right instrument). Owns: .ci/rediacc_ci/drills/vm_check.py, .ci/rediacc_ci/tests/test_vm_check_core_lease.py. Accept: a test with `REDIACC_CORE_LEASE_TOKENS=4` where, while vm_check holds its tokens, a second lease client sees fewer free, and a control without vm_check sees all 4.
- [ ] L3 [writer] One machine-wide lock serializes check:deps, check:ci-account-server and build:www across trees. Depends on: PLAN-ci-quick-cpu-scheduling.md for manifest.ts, as W2 does. Owns: scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .ci/rediacc_ci/core_lease.py, .ci/rediacc_ci/tests/test_core_lease_heavy_lock.py. Accept: a test where two heavy gates started together run one after the other, and a control where a single heavy gate does not wait; `npx tsx scripts/gates/check-paths-origin.ts` and `npm run ci -- --only check:ci-parity` exit 0 after the lock regeneration.

### W11-W19 impact baseline, core release, carried scheduling work, hook-test speed (2026-11-22, operator /ask)

Context: a read-only investigation on 2026-11-21 and 2026-11-22 (junit of 2026-11-20: 38,984 cases, about 21,000 test-seconds; 100 local receipts) found impact selection falling back to FULL after every red run, pytest holding 18 of 24 cores to its end while account-server and lint queued behind it (about 130 s of tail), and most hook-test time going to a process start per case. Operator /ask 2026-11-22: these fixes join this plan; the core release lands before L1; PLAN-ci-quick-cpu-scheduling.md P2 and P4 are carried here so that plan can close. Session ace763dd confirmed P2 is not done (pool.ts:190 still says "Default `slots`") and supersedes P2 and P4 citing W13 and W14 once they are committed.

- [ ] W11 [writer] Last-green record: check_pytest.py writes `.ci/cache/quality-pytest/last-green.json` (head, Python version, map digest) only on a green run and never deletes it at run start; scope.json stays the per-run receipt; `last_green_base` reads the new record; with no record, the base is the clone's newest green receipt head, then the push base.
  Owns: .ci/rediacc_ci/check_pytest.py, .ci/rediacc_ci/tests/test_check_pytest_last_green.py
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_check_pytest_last_green.py` and `.ci/rediacc_ci/check_pytest.py --selftest` rc 0, with tests that a green run writes the record, that a red run after it keeps the record and the next run's impact base is that head (no FULL line), and a control that scope.json is still removed at run start.
- [ ] W12 [writer] Core release before L1: pool.ts re-evaluates an elastic gate's grant while it runs, so cores its workers no longer use return to the pool and a queued gate starts before the elastic gate ends; two-track C1's critical and nice priority stays as it is.
  Owns: scripts/ci-runner/pool.ts, scripts/ci-runner/run.ts
  Depends on: none (operator /ask 2026-11-22: before L1).
  Accept: `npx tsx scripts/ci-runner/run.ts --selftest` rc 0 with a fixture where an elastic gate granted 18 of 24 cores drops to 4 busy workers and a queued 15-core gate starts before it ends, and a control where a gate whose workers stay busy keeps its grant.
- [ ] W13 [writer] Carry PLAN-ci-quick-cpu-scheduling.md P2's open half: `cores` confirmed as the default in both pool.ts and run.ts, check:ci-parity leaves `slow`, the `build:cli` and empirical dist `needs` edges, and the push recipe drops its pre-steps.
  Owns: scripts/ci-runner/pool.ts, scripts/ci-runner/run.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, docs/agent-reference/ci-gates.md
  Depends on: W12.
  Accept: `npx tsx scripts/ci-runner/run.ts --selftest` rc 0; `npm run ci -- --quick --list --json` shows check:ci-parity without `slow` and the new edges; `grep -n "Default" scripts/ci-runner/pool.ts` names `cores`.
- [ ] W14 [writer] Carry PLAN-ci-quick-cpu-scheduling.md P4's live half: lanes.ts balances on the baseline cost in `.ci/config/gate-costs.json`, and `heavy` is retired from gates whose cost is measured.
  Owns: scripts/ci-runner/lanes.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json
  Depends on: W13.
  Accept: `npm run check:ci-lane-budget` rc 0, and a lanes test where two lanes balance on measured cost with a control where an unmeasured gate keeps its `heavy` flag.
- [ ] W15 [writer] Guard suites run their cases in-process: hookcases and the guard `test-*.py` harnesses call `dispatch.run_one` with the whole `os.environ` swapped, `tzset()` called and import-frozen guard modules reloaded, as test_guards_differential.py:690-702 does; the boundary set keeps one real `dispatch.py <stem>` run per guard and one deny plus one allow per chain compared byte for byte with `run_chain`.
  Owns: .claude/rediacc_hooks/tests/hookcases.py, .claude/rediacc_hooks/tests/test_hooks_delegates.py, .claude/rediacc_hooks/tests/test_hooks_static.py, .claude/rediacc_hooks/tests/test_hooks_boundary.py, .claude/rediacc_hooks/guards/test-*.py
  Depends on: none; lands before PLAN-tooling-code-reduction.md CR5 edits the same guard suites.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_hooks_delegates.py .claude/rediacc_hooks/tests/test_hooks_static.py .claude/rediacc_hooks/tests/test_hooks_boundary.py` rc 0 with the same case count, `npm run check:ci-guard-mutations` rc 0, and junit seconds of the two modules quoted before and after (target: under half).
- [ ] W16 [writer] Duplicate runs removed: check-guard-mutations.ts also asserts no TMPDIR leftovers and non-empty output, and test_hooks_delegates skips suites that declare DEFECT or MUTANTS; the "real tree is green" tests leave the tests/gates modules whose gate already runs on its own; the per-mutant selftest reruns leave test_gate_pin_cli.py and test_gate_pin_drivers.py; test_guards_differential caches `python_fields` per input for the session.
  Owns: scripts/gates/check-guard-mutations.ts, .claude/rediacc_hooks/tests/test_hooks_delegates.py, .claude/rediacc_hooks/tests/test_guards_differential.py, .ci/rediacc_ci/tests/gates/test_gate_*.py
  Depends on: W15.
  Accept: `npm run check:ci-guard-mutations` rc 0 with a planted TMPDIR leftover turning it red; `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_guards_differential.py .ci/rediacc_ci/tests/gates/test_gate_pin_cli.py .ci/rediacc_ci/tests/gates/test_gate_pin_drivers.py` rc 0; a deliberately broken guard still fails the differential.
- [ ] W17 [writer] Real-tree gate scans once per session: a session fixture runs each real-tree gate once and the test-only path skips the repeated `controls_first` selftest, for env_manifest, worklist_env_registry, python_env_registry, dead_python, plan_live_proof, plan_folders, gh_retry_reads and gh_retry_shell, record_paths and shfmt.
  Owns: .ci/rediacc_ci/tests/**
  Depends on: none; PLAN-tooling-code-reduction.md CR3 later merges the three env gates and keeps this fixture.
  Accept: the named test modules rc 0 with the same test count, and their junit seconds quoted before and after (target: under half).
- [ ] W18 [writer] Shared fixtures and cheaper fakes: xdist_group plus session scope for the test_d1_shard_move template, the githook World (shared by test_githook_gen_docs and test_githook_generated_artifacts), test_dev_worktree_lease's `kept` and the docker scenarios; Stop-hook tests fork per case from a pre-imported parent in wlfix.py instead of a fresh `python3 worklist.py`; shell fakes for gh, curl, aws, sleep, go and sudo; one shared GOCACHE in test_proxies_go_unit.py.
  Owns: .ci/rediacc_ci/tests/**, .claude/rediacc_hooks/tests/wlfix.py, .claude/rediacc_hooks/tests/test_githook_*.py
  Depends on: none.
  Accept: every touched module rc 0 with the same test count, and junit seconds of the touched modules quoted before and after (target: a third lower in total).
- [ ] W19 [writer] test_settings_collapse sampled: the old side runs in-process through `run_one`; the real chain-head.sh side runs on a stratified sample of one payload per guard per verdict; clause 1 (one command per pattern) and the why-on-edit control stay whole.
  Owns: .claude/rediacc_hooks/tests/test_settings_collapse.py, .claude/rediacc_hooks/tests/guardcorpus.py
  Depends on: W15.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_settings_collapse.py` rc 0 with a control where dropping one lifecycle member still turns the collapse test red, and its junit seconds quoted before and after (target: under 200 s from 910 s).
- [ ] M4 [live] After W11 and W15-W19: one ci:quick run right after a red receipt, and one full local `npm run ci -- --only check:ci-pytest`. Accept: the post-red run's receipt shows `pytestScope: impact` with under 20% of test files selected; the full run's junit total is at most 13,000 test-seconds (about 21,000 on 2026-11-20); both quoted in the tick evidence.

### Live measurement
- [ ] M0 [live] Baseline before any W lands: core-s for the one-file `.py`, one-file `.ts`, red-rerun and unchanged-tree scenarios on the kept clone. Accept: four receipt paths and their core-s in the tick evidence.
- [ ] M1 [live] After W1, W2, W3 and W5: the same four scenarios. Accept: the unchanged-tree and red-rerun targets met.
- [ ] M2 [live] After W4: the one-file `.py` and `.ts` scenarios. Accept: ≤ 4,000 and ≤ 3,000 core-s; the receipt shows `pytestScope: impact` with the selected count.
- [ ] M3 [live] After W6-W9: a full local `npm run ci -- --only check:ci-pytest` against the 18,377 core-s median. Accept: ≥ 35% lower, junit totals in the tick evidence.

## Risks

- **Missed `reads`** let a red reach CI. B4's fallbacks and A3's rotation make it rare; each miss adds an edge and a regression test.
- **strace in the devcontainer** may need `CAP_SYS_PTRACE`; if refused, path-trace falls back to the sparse-clone proof and says so.
- **Frozen hash contract:** W1.2 changes input-hash.ts, the Python guard and the parity test in one commit.
