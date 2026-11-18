# PLAN: ci:quick CPU -- sound gate reuse, pytest by impact locally, faster slow tests
Status: approved -- operator ruling ASKED:2026-11-16T11:35Z chose fixes A+B+C in one plan; rejected: a pre-commit instant tier
Owner: d778be9d
First-Seen: 2026-11-16
Depends-On: no-dep -- the schema 2 receipt, the carry logic, quick-select and the pytest gate are all in the tree now
Priority: P1 -- every push costs about 21k core-s and 1409-1886 s of wall time on 24 cores, and that cost delays every PR
Concurrency: parallel -- the writer groups below edit separate files; scripts/ci-runner/manifest.ts is also owned by PLAN-ci-quick-cpu-scheduling.md, so W2 lands only when that plan has no open edit there
Owns: agent/plans/PLAN-ciquick-cpu.md, scripts/ci-runner/input-hash.ts, scripts/ci-runner/run.ts, scripts/ci-runner/quick-select.ts, scripts/ci-runner/typecheck-incremental.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/path-trace.ts, .claude/rediacc_hooks/**/block_unverified_push*.py, .ci/rediacc_ci/check_pytest.py, .ci/rediacc_ci/pytest_impact.py, .ci/policy/pytest-smoke.json, .ci/policy/pytest-impact.json, .ci/policy/pytest-slow-allow.json, .ci/scripts/quality/check_gate_paths_honest.py, .ci/rediacc_ci/tests/**
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

### W2 path declarations -- scripts/ci-runner/path-trace.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json
- [x] W2.1 [writer] path-trace.ts with `--gate`, `--write` and directory-listing folding (A2). Accept: a fixture gate reading two files gets exactly those two plus its listed directory.
    (ticked) 2026-11-17T14:08:18Z by d778be9d: commit:988ca9561b c64047e813 52e05ba9f2 fe5b4c2b5b 4936a0f350 7a9a97bac4; path-trace selftest 48/48 rc=0, trace-honest selftest 24/24 rc=0, pytest 13 passed, tsc rc=0 (writer report); check:ci-paths-origin rc=0 on the landed tree
- [ ] W2.2 [writer] Trace the 349 whole-tree gates in the clone and write their `paths`; gates over 30% of the tree or reading `.git` stay whole-tree with a named reason. Accept: whole-tree count ≤ 80 in gates.lock.json, and `npm run ci` green on an unchanged tree.

### W3 honesty gate -- .ci/scripts/quality/check_gate_paths_honest.py, its manifest row through W2's lock regeneration, .ci/rediacc_ci/tests/test_gate_paths_honest.py
- [ ] W3.1 [writer] Trace mode and sparse-clone mode, diff-scoped in quick, with the rotation flag (A3). Accept: the undeclared-read fixture fails both modes; the declared fixture passes.

### W4 pytest impact -- .ci/rediacc_ci/pytest_impact.py, .ci/rediacc_ci/check_pytest.py, .ci/policy/pytest-smoke.json, .ci/policy/pytest-impact.json, .ci/rediacc_ci/tests/test_pytest_impact.py
- [ ] W4.1 [writer] The map, selection, smoke floor and every B4 fallback, each with a test. Accept: one test per fallback reason, and a control where a leaf-module edit selects only its importers plus smoke.
- [ ] W4.2 [writer] check_pytest impact/full switch, receipt fields `pytestScope`, selected count and map digest, and guard acceptance (B5). Accept: `CI=true` runs the full suite, asserted on the collected count.
- [ ] W4.3 [writer] Derive `reads` with the tracer and declare check:ci-pytest `paths` (B2, B6). Accept: a docs-only diff carries check:ci-pytest.

### W5 typecheck skip -- scripts/ci-runner/typecheck-incremental.ts and its test
- [x] W5.1 [writer] Find the volatile skip-key field and hash content instead (A6). Accept: the two-run test and its touched-file control.
    (ticked) 2026-11-18T12:32:50Z by d778be9d: commit:859d10c020 -- box Accept re-run 2026-11-18 by a lease writer, rc 0

### W6-W10 slow tests, one writer per file
- [x] W6 [writer] test_ops_mirror_config_store: module-scoped store and injected clock. Accept: same test count, ≤ 300 s in junit.
    (ticked) 2026-11-18T12:32:38Z by d778be9d: commit:7a21752ae9 -- box Accept re-run 2026-11-18 by a lease writer, rc 0
- [ ] W7 [writer] test_hooks_delegates and the check_pytest.py triple run (coordinate the check_pytest.py hunk with W4): controls run once. Accept: same test count, ≤ 600 s.
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
- [ ] W2.5 [writer] Fold to names, after W2.3 in the same file: a listed directory goes to `lists` (root included), the parent of a missed lookup inside a tracked directory goes to `lists`, `ls-files` with only name-shaping flags gives `names: ['**']`, and the 30% line is measured on content globs only; trace-honest accepts `lists` and `names` and flags an undeclared listing or index read. Owns: scripts/ci-runner/path-trace.ts, scripts/ci-runner/trace-honest.ts. Accept: `npx tsx scripts/ci-runner/path-trace.ts --selftest` and `npx tsx scripts/ci-runner/trace-honest.ts --selftest` exit 0, with a fixture where `python3 -m` run from the root reading 2 files gives paths of those 2 plus `lists: ['', '.ci']`, and the same fixture without `lists` fails trace-honest.
- [ ] W2.6 [writer] Re-trace in the kept clone: the gates that exited non-zero under the trace run untraced first (red on the tree is named, not traced); heavy gates trace with `--jobs 1` and a timeout of 4x their average; needs edges guard-mutations to build:packages and trap-registry to build:cli; carry-exempt rows with a kind for network (deps, devcontainer-pins, bws-map-live, pr-epic-block, i18n-www-translation-freshness), clock (resprofile, go-deps, security-audit), history (renet-types, docker-image-freshness) and cache (aws-resolver); `refs` on the remaining history gates. Owns: scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/trace-ledger.ts, .ci/policy/carry-exempt.json. Accept: `node -e 'const g=require("./scripts/ci-runner/gates.lock.json");const n=g.filter(e=>e.gate&&!(e.paths||[]).length).length;console.log(n);process.exit(n<=80?0:1)'`, `npx tsx scripts/gates/check-paths-origin.ts` and `npm run ci` green on an unchanged tree; a count between 81 and 85 goes to the operator (count only carriable gates, or accept 85 with the named stays) instead of loosening a rule.
- [ ] W3.2 [writer] The declared path sets made honest, after W2.5: `npx tsx scripts/ci-runner/trace-honest.ts --origin declared --mode trace --jobs 4`, then each set becomes traced with `path-trace --gate <id> --replace-declared --write` unless it is small and exact, in which case it is widened. Owns: scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, scripts/ci-runner/trace-ledger.ts. Accept: `npx tsx scripts/ci-runner/trace-honest.ts --origin declared --mode both --sparse-top 36` exits 0, and `--origin traced --rotation 1/3`, `2/3`, `3/3` each exit 0 once.
- [ ] W3.3 [writer] Wire check:ci-gate-paths-honest: the gate header in trace-honest.ts; a manifest row running `npx tsx scripts/ci-runner/trace-honest.ts --quick --mode trace`, heavy, writesTree, needs build:packages and build:cli, carry-exempt with kind history; a quality-job step that installs strace and passes `--base origin/${GITHUB_BASE_REF:-main}`; the full rotation `--rotation auto --mode both --sparse-top 10` as a scheduled ci-drift.yml step; no new package.json key. Owns: scripts/ci-runner/trace-honest.ts, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json, .ci/policy/carry-exempt.json, .github/workflows/ci-quality.yml, .github/workflows/ci-drift.yml, docs/agent-reference/ci-gates.md. Accept (local): `npm run ci -- --only check:ci-gate-paths-honest` green on an unchanged tree in 10 s or less; a plant adding one undeclared read to a traced gate's leaf turns it red naming the path; `npm run ci -- --only check:ci-gate-bind --only check:ci-parity --only check:ci-test-gate-wiring --only check:ci-package-key-budget` green.

### Live measurement
- [ ] M0 [live] Baseline before any W lands: core-s for the one-file `.py`, one-file `.ts`, red-rerun and unchanged-tree scenarios on the kept clone. Accept: four receipt paths and their core-s in the tick evidence.
- [ ] M1 [live] After W1, W2, W3 and W5: the same four scenarios. Accept: the unchanged-tree and red-rerun targets met.
- [ ] M2 [live] After W4: the one-file `.py` and `.ts` scenarios. Accept: ≤ 4,000 and ≤ 3,000 core-s; the receipt shows `pytestScope: impact` with the selected count.
- [ ] M3 [live] After W6-W9: a full local `npm run ci -- --only check:ci-pytest` against the 18,377 core-s median. Accept: ≥ 35% lower, junit totals in the tick evidence.

## Risks

- **Missed `reads`** let a red reach CI. B4's fallbacks and A3's rotation make it rare; each miss adds an edge and a regression test.
- **strace in the devcontainer** may need `CAP_SYS_PTRACE`; if refused, path-trace falls back to the sparse-clone proof and says so.
- **Frozen hash contract:** W1.2 changes input-hash.ts, the Python guard and the parity test in one commit.
