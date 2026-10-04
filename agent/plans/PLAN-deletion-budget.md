# PLAN: a per-PR deletion budget (deletions >= 0.33 x additions over all tracked lines), per-PR coverage, and a mutation-judged prune of the pytest corpus, bash-twin parity tests and duplicate tests and gates
Status: draft -- operator /ask 2026-10-04, two rounds plus the coverage addition, all binding; round two overrides round one wherever they conflict; one operator addition is still pending (DB29)
Owner: d778be9d
First-Seen: 2026-10-04
Depends-On: no-dep -- builds only on shipped modules (plan_gate, wl_prscope, wl_prsignals, review_table, shrink_only, check_pytest, differential.py, mutate-check.sh, the shape index). The file overlaps with live plans are listed under Concurrency and not as prerequisites, because a Depends-On edge would pull those plans into this PR's plan set (`plan_gate.pr_plan_set`, `.claude/rediacc_hooks/plan_gate.py:216`)
Priority: P1 -- operator order 2026-10-04: every PR deletes at least a third as many lines as it adds, every PR shows what its tests run, and the suite keeps only tests a planted defect proves are needed
Concurrency: parallel -- at most 6 writers, disjoint file ownership per box (see "Ownership"). Shared with live plans: scripts/ci-runner/{manifest.ts,gates.lock.json} and .claude/rediacc_hooks/guards/block_unverified_push.py (PLAN-gate-drop-receipt-verify); .claude/hooks/stop/{wl_prscope,wl_checks,worklist_messages}.py and .claude/rediacc_hooks/tests/test_plan_gate.py (PLAN-stop-hook-one-plan-scope); .claude/rediacc_hooks/guards/block_admin_merge.py (PLAN-plan-per-pr-loop); package.json, .ci/config/shards/quality-pytest.json and docs/agent-reference/ci-gates.md (PLAN-ci-consolidation, PLAN-clean-review-ledger); scripts/gates/*.ts and .ci/cache/shape-index (PLAN-stop-hook-refactor-enforcement); the twin test files, .ci/rediacc_ci/tests/goldens/** and .ci/shadow/** (PLAN-retire-bash-oracles, 9 open boxes). Owns: decides overlaps (block_plan_concurrency).
Owns: .ci/config/deletion-budget.json, .claude/rediacc_hooks/deletion_budget.py, .claude/rediacc_hooks/tests/test_deletion_budget.py, .ci/scripts/quality/{check_deletion_budget,check_test_deletion_provenance,check_uncovered_lines}.py, .ci/rediacc_ci/quality/{test_value,test_line_map,test_mutation,test_failure_history,test_keep_bar,test_deletion_provenance,twin_inventory,clone_families,coverage_combine,uncovered_lines}.py, .ci/rediacc_ci/review/coverage_summary.py, .ci/rediacc_ci/tests/test_quality_{deletion_budget,test_value,test_line_map,test_mutation,test_failure_history,test_keep_bar,test_deletion_provenance,twin_inventory,clone_families,coverage_combine,uncovered_lines}.py, .ci/rediacc_ci/tests/test_review_coverage_summary.py, .ci/rediacc_ci/tests/test_prsignals_pins.py, .ci/rediacc_ci/tests/fixtures/{test_value,test_line_map,test_mutation,test_keep_bar,twin_inventory,clone_families,coverage}/**, .ci/config/test-value.json, .ci/config/test-prune-ledger.json, .ci/config/uncovered-lines-baseline.json, .claude/rediacc_hooks/plan_gate.py, .claude/rediacc_hooks/tests/test_plan_gate.py, .claude/rediacc_hooks/guards/{block_admin_merge,test-block_admin_merge,block_unverified_push,test-block_unverified_push}.py, .claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl, .claude/hooks/stop/{wl_prscope,wl_checks,worklist_messages,wl_reggate,wl_prsignals}.py, .claude/rediacc_hooks/tests/{test_wl_prscope,test_wl_loop_next,test_wl_message_catalogue}.py, package.json, scripts/ci-runner/{manifest.ts,gates.lock.json}, .github/workflows/ci-quality.yml, .ci/config/shards/quality-pytest.json, .ci/config/python-env-registry.json, .ci/config/{lane-durations,gate-costs}.json, .ci/rediacc_ci/check_pytest.py, scripts/gates/check-{i18n,locale,translation,docs}-*.ts and their .ci/rediacc_ci/tests/gates/test_gate_*.py (DB19, DB20), twin-retired and pruned test files under .ci/rediacc_ci/tests and .claude/rediacc_hooks/tests (DB16, DB18, DB21), .ci/rediacc_ci/tests/goldens/twins/**, .claude/rediacc_hooks/tests/goldens/** (twin rows only), .ci/shadow/**, agent/reports/{test-value,twin-inventory,clone-families}-2026-10.{md,json}, agent/plans/PLAN-test-prune-batches.md, agent/plans/QUEUE.md, docs/agent-reference/ci-gates.md, CLAUDE.md

**Operator prompt, 2026-10-04 (summarised):** a LinkedIn post on Sazabi deleting 811,883 lines of unit tests. Its hypotheses: agent-written unit tests lock in sloppy code, slow agents and CI, and waste tokens and CI minutes. Its counterweight: when agents write everything, the suite is the only signal that something broke. Its five questions: behaviour or implementation detail; would anyone notice it gone; is it a copy; does it protect something that hurts in production; how long does it run.

**Operator caution, round two, verbatim:** "be careful about 90 days. we may introduced them in last 90 days." <!-- style-ok -->

**Operator on coverage, verbatim:** "we change a lot per PR, so nightly cannot be the option." The design is "close to" what is wanted, and "there is something else we need", which is not yet known (DB29). <!-- style-ok -->

## What was true when this was written

- **No deletion rule existed.** `agent/plans/PLAN-stop-hook-refactor-enforcement.md:14-25` records that a remembered "40% threshold" never existed. The ratio is a new decision: 0.33, set by the operator on 2026-10-04.
- **Round two overrides round one on counting.** Round one excluded generated files (lockfiles, goldens, i18n bundles, gen-docs regions and the like) and excluded drained shrink-only baselines from the deletion side. Round two chose "All tracked lines": plain numstat over every tracked file, with no exclusion list, no generated-region splitting and no whitespace or reflow layer. Every round-one exclusion is gone, including the baseline-drain one. Binary rows count 0, and gitlinks are measured per submodule.
- **The rule will rarely bite in bulk.** Bulk numbers ran about 0.60 over the last 60 days (operator figure). This checkout measures 0.58: `git log origin/main --since=60.days --no-merges --numstat -M` sums to 1,673,022 added and 968,640 deleted. The rule binds per PR, so it bites on the add-only PR.
- **Nothing caps pytest time** (round two, decision 2). The p90 sum, 91.2 minutes over 566 `pytest:` units in `.ci/config/lane-durations.json`, is reported, not budgeted, and only orders the prune.
- **The merge gate.** `plan_merge_refusal` (`.claude/rediacc_hooks/plan_gate.py:430`) returns "" as soon as the body carries an `Operational-Reason:` line (:437). It is called by `block_admin_merge.py:307` (console only, behind `if repo == GH_REPO:` at :301) and `block_push_to_protected_branch.py:361`. In CI, `check_plan_implementation.py:179` (`pr_event_body`) reads the body from the Actions event.
- **The quick lane.** `quick-select.ts:7` admits a slow gate with no `paths` whenever the change set is non-empty, and a non-slow gate always runs. `block_unverified_push` refuses a push without a green receipt.
- **The pytest legs.** The `quality-pytest` job (`.github/workflows/ci-quality.yml:2346`, "Pytest (N/3)", `timeout-minutes: 15` at :2348) runs `npm run check:ci-pytest -- --shard-manifest .ci/config/shards/quality-pytest.json --shard N/3`. It checks out submodules at `fetch-depth: 0` with a read-only app token for all five repos. It uploads `reports/quality-pytest/` as `unit-durations-quality-pytest-s<N>-<sha>` with `retention-days: 3` (:2370). The `quality-branch` job checks out `head_ref` at `fetch-depth: 0` without submodules (:529-565), and its steps are hand-written (:596).
- **Posting to the PR.** The review table (`.ci/rediacc_ci/review/review_table.py`) upserts one comment whose body starts `<!-- per-commit-reviews: <head40> -->`, from the `pr-labels` job. That job holds `pull-requests: write` and runs only after `ci-complete` succeeds (`.github/workflows/ci.yml:1891-1897`). The table is advisory end to end. `.claude/hooks/stop/wl_prsignals.py` keeps a by-value copy of each bot marker, pinned by `.ci/rediacc_ci/tests/test_prsignals_pins.py`.
- **Shrink-only, in Python.** `.ci/rediacc_ci/quality/shrink_only.py` holds the decision (`baseline_additions` :22, `write_verdict` :31) for Python gates. `scripts/lib/shrink-only-baseline.ts` is the TS original.
- **Coverage tooling.** Neither coverage.py nor mutmut is installed, and pytest and xdist come from `uv` via `.ci/bootstrap.sh`. Python is 3.14, so `sys.monitoring` (3.12+) supplies LINE events and the `DISABLE`/`restart_events` pair without a dependency.
- **check_pytest floors.** `check_pytest.py:69` sets `MIN_TESTS = 150` against about 8,920 tests on disk. Floor 2 re-keys itself.
- **Corpus.** `.ci/rediacc_ci/tests` holds 491 files and 7,680 tests, of which `tests/gates/` holds 166 control-first files with 1,695 tests. `.claude/rediacc_hooks/tests` holds 78 files and 1,240 tests. There are 46 control-style `test-*.py` files under `.claude/hooks/stop` and `.claude/rediacc_hooks/guards`.
- **Mutation targets.** 388 non-test modules under `.ci/rediacc_ci` (172,366 lines) and 154 under `.claude` (72,871 lines).
- **Twins.** The operator counts 278 test files that mention a "twin". `grep -rlw twin --include='test_*.py'` over the two roots returns 414 here. `.ci/rediacc_ci/tests/differential.py` runs bash against the port. There are 65 files in `.ci/rediacc_ci/tests/goldens/twins/` and 285 entries under `.ci/shadow/`, including `twin-parity.ledger.jsonl`. Docstrings cite those files as retirement records (`check_hook_integrity.py:69`, `assert_job_succeeded.py:6`). `.ci/scripts/release/` holds 15 `*.sh` files (the operator's count is 14).
- **Gate clusters.** `scripts/gates/` holds 130 TS gates: an i18n family of 18 and a docs family of 10. `check:ci-parity` and `check:ci-gate-reachability-coverage` keep the gate-id sets consistent.
- **The reggate.** `REGGATE_PROMPT` (`worklist_messages.py:1818`) is hashed in `.ci/config/rubric-calibration.json`. `R_REGGATE_BLOCK` (used at `wl_reggate.py:812`) is not.

## Design

### D1. One rule, one constant

`.ci/config/deletion-budget.json` holds `"ratio": "0.33"` and the submodule map (D5), nothing else. The engine parses the ratio as `fractions.Fraction`, so the comparison is exact integer arithmetic: `deletions * den >= additions * num`, with 0.33 = 33/100. Zero additions passes. The shortfall is `ceil(additions * num / den) - deletions`. A later change of target is a one-line edit, and a test proves the ratio has no second copy. The protected-suite list lives in `.ci/config/test-value.json`, a separate file.

### D2. How the ratio is computed

The engine runs `git -c diff.renameLimit=0 diff --numstat -z --no-ext-diff --no-textconv --find-renames=50% <base>...<head>`, where base is `git merge-base origin/main <head>`.

- **Source: git, not gh.** gh needs the network, so the Stop hook and push guard could not reproduce it offline, and it cannot separate gitlink rows. Every rename setting is pinned on the command line.
- **Line rules:** every tracked file counts. A pure rename is 0/0, and an edited rename counts only its changed lines. Copies count in full as additions. Binary rows count 0. A gitlink row is replaced by that submodule's own range (D5).
- **Base locally:** the Stop hook prefers the PR's `baseRefOid` when that object exists locally. Otherwise it says "local base may be stale" and uses `origin/main`.
- **Which tree is judged:** the PR head. The merge guard measures `refs/remotes/origin/<head>`, else `HEAD`, never the working tree. The protected-branch push measures the pushed sha. CI measures `head_ref`. The Stop hook and push guard measure `HEAD`.
- **Output:** a `Measurement` (`additions`, `deletions`, `ratio`, `needed`, `base`, `head`, `binary`, `per_repo`, `problems`). A measurement with problems is not a pass anywhere. `refusal(root, rev, body)` returns "" or a reason with the four numbers and the rule.

The same module exports `added_lines(root, base, head, path)`: head line numbers from a `-U0` hunk walk. D12's gate uses it, so "what the PR changed" has one definition.

### D3. Where it runs, and why the surfaces agree

Every surface calls one engine, `.claude/rediacc_hooks/deletion_budget.py`. It sits in the hooks package because plan_gate and the Stop hook already import it, and CI reaches it the way `check_plan_implementation.load_plan_gate` (:169) reaches plan_gate.

| Surface | Short, no `Operational-Reason:` |
|---|---|
| `plan_merge_refusal` (merge, fast-forward fallback) | refuses |
| `check:ci-deletion-budget` on a pull_request run (`quality-branch`) | red |
| Stop hook, PR open, boxes open | one advisory line with the shortfall and the top three DELETE-CANDIDATEs |
| Stop hook, PR open, every box ticked | a blocking shortfall text in place of the merge offer |
| `block_unverified_push`, MMDD-N branch | one WARN line, never a refusal |
| `ci:quick` | not selected; the push guard line is the local agreement point; no receipt field, so `run.ts` stays out of this plan |

Without a pull_request event, the gate measures, prints "NOT JUDGED: no PR event", and exits 0 only after its `--selftest` controls ran in the same invocation.

### D4. Exceptions and the bootstrap

One `Operational-Reason:` line admits open boxes, a short ratio and new uncovered lines (D12), through plan_gate's `has_operational_reason`. The cost is stated: a PR admitted for one reason is admitted for all three. Every admission prints its measured numbers.

**Bootstrap:** no date-keyed grace window. This plan's PR carries the twin retirement (DB16), the clone merges (DB18-DB20) and keep-bar batch 1 (DB21), and is expected to meet the ratio on those deletions. The D12 baseline seed adds lines too, which is why its writer emits one JSON line per file, not per id.

The fallback is a one-time `Operational-Reason: deletion-budget bootstrap -- <measured numbers>` line, written only if the measured head is short after DB21. CI's deletion gate is red from DB13 until those deletions land, so DB13 is pushed together with DB16 at the earliest.

### D5. Submodule PRs

`"submodules"` maps `private/account`, `private/renet`, `private/elite` and `private/homebrew-tap` to their slugs. Each is judged on its own over the range from its gitlink at the console merge-base to its gitlink at the console head.

- **Locally:** `git -C private/<x> diff --numstat` with the D2 flags.
- **In CI**, where `quality-branch` has no submodules: `gh api repos/<slug>/compare/<old>...<new>`, through the same row function. A listing at the file cap fails closed.
- **Merging a submodule PR:** `block_admin_merge` gains an arm for those slugs that measures the local `private/<x>` range after a fetch. An `Operational-Reason:` line in that PR's body, or in the console PR of the same head branch, admits it.

### D6. The keep bar: a test stays only if it kills a mutant no other surviving test kills

**Never judged, kept regardless:**

- control-first gate tests: `.ci/rediacc_ci/tests/gates/**`, every `test-*.py` under `.claude/hooks/stop` and `.claude/rediacc_hooks/guards`, and any test calling `controls.plant` or building `Controls(`;
- the protected suites in `test-value.json` `"protected"`, each with a reason: licensing (`*licen*`, `.ci/rediacc_ci/{drills,proxies}/*license*`), payments and Stripe (a body naming `stripe`, or an account billing target), config-storage crypto (`encrypt|decrypt|kdf|passkey|vault` targets), and release/CD (`test_deploy_*`, `test_gate_release*`, `test_ci_*tag*`, `test_core_release_*`, `test_ops_scrub_sentinel`, targets under `.ci/rediacc_ci/{release,deploy,version}/**`).

Each protected glob must match at least one test.

**The decision.** Mutation (S6) is the only signal that removes a test. The others order the work and explain each verdict:

- S1, private-name assertions;
- S2, mock density;
- S3, normalised-AST copies;
- S4, run time;
- S7, regression-born (`wl_reggate.py:24` `FIX_SUBJECT` on the `def` line's introducing commit);
- S9, failure history (D9);
- S10, coverage redundancy (D12).

**The line map (DB8), shared with D12.** A pytest plugin on `sys.monitoring` LINE events records, per test id, the target-module lines it executes. Each line is recorded once per test: the callback returns `DISABLE`, and `restart_events()` runs at each test boundary, which keeps the overhead to one callback per line per test. Each xdist worker writes its own file, and `merge()` joins workers, legs and runs.

Child processes are covered by a `.pth` hook placed in the interpreter's site-packages (CI leg only; locally a sandbox). It records into the same directory. It finds its test id from the env var, or, when a harness scrubbed the env, by walking the parent-pid chain to a `worker-<pid>.current` file the plugin keeps. Lines a child ran with no resolvable test id go to an `unattributed` bucket. They count as executed for D12's gate, which prevents false reds, but are attributed to no test, so they make no redundancy or mutation claim.

The map is cached by the sha of every target module and test file. Once DB25 lands, CI's combined map for a head replaces the local full run.

**The mutants (DB9).** One mutant per mutable line covered by at least one judgeable test. The operators are tried in a fixed priority:

1. negate a comparison;
2. swap `and`/`or`;
3. replace a return value with `None`;
4. drop a call statement;
5. change a string literal;
6. shift an integer constant by one.

Mutants are compiled into a sandbox copy as trampolines, selected by `TESTVALUE_MUTANT=<id>`, so a warm worker runs many mutants and a subprocess inherits the selection. The live tree is never written, and the baseline is run green twice first. A test red in either baseline is flaky and kept.

**The kill matrix, at bounded cost.** For each mutant, the tests covering its line run in this order: protected and control-first first, then coverage-redundant tests, then the fastest. A timeout (5x baseline) counts as a kill. The run stops at the second kill. Unknown killers are treated as absent, which errs toward keeping.

**Cost.** DB14's pilot over three modules (pure, subprocess-heavy, hook) fixes the per-mutant cost before the full run. The run is sharded `--shard i/N` by module, resumable, and cached in `.ci/cache/test-value/kills/<module-sha>-<tests-sha>.jsonl`. No time cap applies. The report states the CPU-hours spent.

**Incremental re-runs.** Deleting tests never invalidates a survivor's KEEP. Re-runs are needed only for modules whose source changed or whose covering tests were rewritten (DB16, DB18), and the cache key catches exactly those.

**The solver (DB11).** Candidates (judgeable, not protected, not control-first, not flaky) are visited slowest first, with coverage-redundant tests (S10) ahead of others at equal speed, and S7 and S9 tests at the back. Candidate T is deleted when two things hold:

- every mutant T kills has another killer that is still surviving;
- at least `min_observable` (default 1) of the mutants on T's lines were killed by some test.

Otherwise T stays, with its unique kill recorded. Deleting T removes it from the surviving set before the next candidate is visited, so two sharers of a mutant's only kill can never both go.

**How equivalent mutants are kept from condemning a test.** A mutant no test kills is discarded. It is never anyone's unique kill and never makes anyone non-unique. A test is judged only on mutants another test proved observable. A test whose lines produced only surviving mutants, or whose target is not Python, is UNJUDGEABLE and stays.

### D7. Angle a: retire bash-twin parity tests

DB15 classifies every test file in the two roots that names a twin:

- **twin-live:** a `TWIN_REL`-style constant, a `differential.py` call, or a `twin-parity.ledger.jsonl` row names a bash path that exists. Kept.
- **twin-retired:** the named path is gone at HEAD. Retired.
- **comment-only:** prose only. Left alone.

Twins under `.ci/scripts/release/` are outside this angle until the operator's real cd-v2, promote-stable and backfill-release-sentinel runs.

**Retiring a twin-retired file (DB16):**

1. **Salvage.** A case that asserts the port's own observable behaviour (exit code, a stdout or stderr fact, a written file) becomes a plain assertion, with the expected value inlined from the golden. A case that only asserts "port bytes == twin bytes" is deleted.
2. **Control-first files.** A `tests/gates/` file is never deleted whole: its differential-only cases go, and its CONTROL cases stay byte for byte.
3. **Matching artifacts.** The test's goldens (`.ci/rediacc_ci/tests/goldens/twins/<subject>.jsonl`, its rows in `.claude/rediacc_hooks/tests/goldens/**`), its `.ci/shadow/**` file and its `twin-parity.ledger.jsonl` rows go in the same commit.
4. **Citations.** Docstrings citing a deleted path are re-pointed to `commit:<sha>` of the deleting commit.
5. **The bar.** Salvaged cases then face the D6 bar.

### D8. Angle b: merge duplicate tests and gates

DB17 runs clone detection over two surfaces:

- **The pytest roots:** S3's literal-abstracted hash. A group of 2 or more bodies is a parametrize candidate.
- **`scripts/gates/*.ts`:** token windows from `.ci/cache/shape-index/probe.mjs`. It finds families that differ only by a pattern, a path set or a message.

Its output is `agent/reports/clone-families-2026-10.json`.

**Tests (DB18).** Each group becomes one `@pytest.mark.parametrize` test, with case ids carrying the old names. A group holding a protected or control-first test keeps every case.

**Gates (DB19 i18n, DB20 docs).** A pattern-only family becomes one gate with an `{arm, pattern, message}` table. The rules:

- Every member's control survives as an arm. The `CONTROL` count before equals the count after.
- Retired ids leave all four registrations and every textual reference, with no alias.
- Every surviving id stays reachable: `check:ci-parity` and `check:ci-gate-reachability-coverage` are green.
- A member DB17 does not list as pattern-only stays separate.

### D9. Angle c: failure history ranks, never condemns

**Source.** S9 reads per-test failures from the junit artifacts CI uploads (`unit-durations-quality-pytest-s<N>-<sha>`, already parsed by `budget_report.py`). Those artifacts are kept for 3 days (`ci-quality.yml:2370`), so the window W is measured from the oldest artifact actually present: about 3 days today. Lengthening that retention is a storage-cost decision this plan does not take. It is listed for the operator in DB23.

**Age.** A test's age comes from `git blame` of its `def` line. A test introduced inside W has its history ignored, and the D6 bar alone judges it. With W this short, that is almost every test, which matches the operator's caution.

**Use.** For older tests, a real failure in W (red, then green after a code change, not a flaky re-run) moves the test to the back of the solver's order and is shown in the report. "Never failed" is never evidence against a test.

### D10. The prune and check_pytest, the shard manifest, the cost refresh

**The provenance gate (DB12).** `check:ci-test-deletion-provenance` requires every removed test id to be one of:

- **moved:** the same literals-kept hash exists at head;
- **parametrized:** it is a case id at head;
- **target-deleted:** its imported module is gone;
- **ledgered:** a row in `.ci/config/test-prune-ledger.json` with class `keep-bar`, `twin-retired` or `clone-merged`, plus evidence.

A protected or control-first id is refused even when ledgered.

**Floors.** Floor 2 re-keys itself. After DB21, `MIN_TESTS` becomes two thirds of the post-prune corpus (DB22).

**Shard manifest and costs.** Every deleting box regenerates `.ci/config/shards/quality-pytest.json` with `npx tsx scripts/gates/check-lane-budget.ts --rebalance quality-pytest --write`. `lane-durations.json` and `gate-costs.json` are refreshed by `budget_report --refresh` after a green CI run (DB24).

### D11. Reconciling the regression gate and the deletion budget

1. **Correctness wins the conflict.** A reggate demand is never answered by skipping the test. The budget is answered by deleting elsewhere, or by `Operational-Reason:`.
2. **Different units.** The reggate judges a fix-set and the budget judges a PR, so a fix PR pays for its test out of the same PR's deletions.
3. **The payment has a source.** On a short branch, the reggate block gains a line (a new constant, never `REGGATE_PROMPT`) naming the top three solver DELETE-CANDIDATEs, same package first.
4. **Extension before addition.** The same line points at a parametrize case in an existing test as the cheaper settle.
5. **A regression test faces the bar like any other.** It kills the mutant that re-creates its fix's defect. S7 only moves it to the back of the order.
6. **Coverage pulls the same way as the reggate.** D12's gate asks the regression test to execute the fixed lines, which is what a regression test does anyway.

### D12. Per-PR coverage, on every PR

The operator rejected a nightly run, so coverage is collected by the existing pytest legs on every PR run. It answers three questions on the PR page and enforces one rule.

**Collection (DB25).** `check_pytest.py` gains `--line-map <dir>`, which loads DB8's plugin (`-p rediacc_ci.quality.test_line_map`) and installs the `.pth` child hook for the run. The three legs pass it. Each leg uploads `line-map-quality-pytest-s<N>-<sha>` (retention 3 days, read only within the run).

**The combine job.** A new `coverage-combine` job (`needs: quality-pytest`, `if: !cancelled()`) checks out `head_ref` at `fetch-depth: 0` with `filter: blob:none`. It downloads the three maps, runs `coverage_combine.merge` into one `test -> file -> lines` map plus the `unattributed` bucket, and uploads the result. A leg whose map is missing makes the job red as "coverage incomplete", never green over two thirds of the suite. The job's two steps are the PR summary and the gate.

**The PR summary (DB26).** `.ci/rediacc_ci/review/coverage_summary.py` upserts one comment that starts `<!-- coverage-summary: <head40> -->`, the review table's shape. It is posted from the combine job itself, which holds `pull-requests: write`, rather than from `pr-labels`, which runs only after `ci-complete` succeeds and so would never show the summary of a red head. It is advisory end to end: a posting failure logs and exits 0. `wl_prsignals.py` gains the marker as a by-value copy (pinned in `test_prsignals_pins.py`), so `ci-trace.py` and the Stop hook can read it. Three sections, each capped at 30 rows with the full list in the uploaded artifact:

- **Redundant tests:** among the tests the PR adds or changes, and the tests that run lines in files the PR changes, every test for which each line it runs is also run by at least one other surviving test. This is a cheap first filter. The full-suite list feeds D6 as S10, and mutation stays the deciding bar.
- **Lines run by many tests:** the changed files' lines with the highest covering-test counts, as function ranges.
- **Changed lines no test runs:** the executable lines (D12 gate rule) among `added_lines` that the combined map never saw.

**The gate (DB27): `check:ci-uncovered-lines`, shrink-only.**

- **Scope:** Python files the PR changed, under the line map's target roots (`.ci/`, `.claude/`). TS, Go and bash are out of scope, stated in the gate's success line, and named in DB23.
- **Executable lines:** the lines in `co_lines()` of every code object compiled from the head blob. Comments, blank lines and docstrings are never executable, so they never red.
- **Finding ids:** `path:<sha1 of the stripped line text>[:12]:<occurrence>`, stable across line shifts.
- **The finding:** an added executable line with no record in the combined map. The `unattributed` bucket counts as a record.
- **The baseline:** `.ci/config/uncovered-lines-baseline.json` is seeded with every currently uncovered executable line in the target roots, written one JSON line per file. A new finding not in the baseline fails. A baselined id that is now covered also fails, until drained with `--drain`. `--write-baseline` goes through `shrink_only.write_verdict` and refuses growth, the `prose-style` discipline.
- **The exception:** an `Operational-Reason:` line in the event body, read with plan_gate's parser.
- **Without a pull_request event**, the gate judges against `.ci/cache/line-map/combined.json` when its recorded tree equals `HEAD^{tree}`, else prints "NOT JUDGED: no line map for this tree". It is never in ci:quick, because it needs the whole suite.

This reinstates the dropped dead-code-via-coverage angle as a per-PR signal on changed lines, not as a one-off deletion sweep.

**Overhead and the lane budget (DB24).** The overhead is measured, not assumed. The first green run with `--line-map` is compared leg by leg against the preceding green run of the same shard plan without it, from each leg's own `unit-durations` artifact. The per-leg minutes are recorded in `docs/agent-reference/ci-gates.md`.

The lane budget absorbs the overhead in three steps:

1. `budget_report --refresh` prices the inflated units into `lane-durations.json`.
2. `check-lane-budget.ts --rebalance quality-pytest --write` re-packs the legs.
3. If the worst leg still exceeds the 15-minute job ceiling (`ci-quality.yml:2348`, operator spec W), the lane grows to four legs: `"of": 4` in the manifest, `shard: [1, 2, 3, 4]` in the matrix. `shard_min_tests` re-derives its floor from `of` (`check_pytest.py:72`).

The combine job adds its own wall time after the legs. The pipeline's 20-minute ceiling is checked by `check:ci-lane-budget` in the same box.

## Ownership

A file under two boxes is written by the later box only after the earlier one is ticked.

| Box | Owns | After |
|---|---|---|
| DB1 | deletion_budget.py, test_deletion_budget.py, deletion-budget.json | -- |
| DB2 | check_deletion_budget.py, test_quality_deletion_budget.py | DB1 |
| DB3 | plan_gate.py, test_plan_gate.py, block_admin_merge.py, test-block_admin_merge.py | DB1 |
| DB4 | block_unverified_push.py, test-block_unverified_push.py, goldens/block_unverified_push.jsonl | DB1 |
| DB5 | wl_prscope.py, wl_checks.py, worklist_messages.py, test_wl_prscope.py, test_wl_loop_next.py, test_wl_message_catalogue.py | DB1 |
| DB6 | wl_reggate.py | DB5, DB14 |
| DB7 | quality/test_value.py, test-value.json, test_quality_test_value.py, fixtures/test_value/** | -- |
| DB8 | quality/test_line_map.py (plugin, `.pth` child hook, per-worker files, `merge`), test_quality_test_line_map.py, fixtures/test_line_map/** | -- |
| DB9 | quality/test_mutation.py, its test, fixtures/test_mutation/** | DB8 |
| DB10 | quality/test_failure_history.py, its test | -- |
| DB11 | quality/test_keep_bar.py, its test, fixtures/test_keep_bar/** | DB7 |
| DB12 | check_test_deletion_provenance.py, quality/test_deletion_provenance.py, its test, test-prune-ledger.json | DB7 |
| DB13 | package.json, manifest.ts, gates.lock.json, ci-quality.yml, shards/quality-pytest.json, python-env-registry.json, docs/agent-reference/ci-gates.md, CLAUDE.md | DB2, DB7-DB12, DB15, DB17, DB26, DB27 |
| DB14 | agent/reports/test-value-2026-10.{md,json} | DB7-DB11 |
| DB15 | quality/twin_inventory.py, its test, fixtures/twin_inventory/**, agent/reports/twin-inventory-2026-10.{md,json} | -- |
| DB16 | twin-retired test files, goldens/twins/**, hook goldens (twin rows), .ci/shadow/**, citing docstring lines; then shards and ledger | DB13, DB15 |
| DB17 | quality/clone_families.py, its test, fixtures/clone_families/**, agent/reports/clone-families-2026-10.{md,json} | DB7 |
| DB18 | parametrized test files; then shards and ledger | DB16, DB17 |
| DB19 | i18n family gates and their gate tests; then registration files | DB25, DB17 |
| DB20 | docs family gates and their gate tests; then registration files | DB19 |
| DB21 | keep-bar test deletions; then shards and ledger | DB14, DB18 |
| DB22 | check_pytest.py (MIN_TESTS) | DB21, DB25 |
| DB23 | agent/plans/PLAN-test-prune-batches.md, agent/plans/QUEUE.md | DB21 |
| DB24 | lane-durations.json, gate-costs.json; then shards/quality-pytest.json and the ci-quality.yml matrix if a fourth leg is needed | DB21, DB25, a green CI run on the head |
| DB25 | check_pytest.py (`--line-map`), then ci-quality.yml (leg flag, uploads, `coverage-combine` job), package.json, manifest.ts, gates.lock.json (`check:ci-uncovered-lines`), the D12 section of docs/agent-reference/ci-gates.md | DB8, DB13, DB26, DB27 |
| DB26 | quality/coverage_combine.py, review/coverage_summary.py, wl_prsignals.py, test_prsignals_pins.py, test_quality_coverage_combine.py, test_review_coverage_summary.py, fixtures/coverage/** | DB8 |
| DB27 | check_uncovered_lines.py, quality/uncovered_lines.py, uncovered-lines-baseline.json, test_quality_uncovered_lines.py | DB1, DB8 |
| DB29 | to be named when the operator's addition is known | DB25 |

DB28 is not used, so DB29's ID stays stable whatever its scope turns out to be.

Parallel waves:

1. {DB1, DB7, DB8, DB10, DB15}
2. {DB2, DB3, DB4, DB5, DB9, DB11, DB12, DB17, DB26, DB27}
3. {DB13, DB14}
4. {DB6, DB16, DB25}
5. {DB18, DB19}
6. {DB20, DB21}
7. {DB22, DB23, DB24}

DB29 waits for the operator.

## Tasks

- [ ] DB1 The engine and its config: `.ci/config/deletion-budget.json:1` (new; `"ratio": "0.33"`, `"submodules"`) and `.claude/rediacc_hooks/deletion_budget.py:1` (new; `measure`, `added_lines`, `rows_from_numstat`, `rows_from_compare`, `judge`, `refusal`), per D1, D2 and D5. Proof: `python3 -m pytest .claude/rediacc_hooks/tests/test_deletion_budget.py -q`. The cases build a temp repo and cover:
  - (100,33) passes; (100,32) fails needing 1; (3,1) passes; (4,1) fails; (0,0) passes;
  - a lockfile edit counts;
  - a pure rename is 0/0, and an edited rename counts only its edits;
  - a binary file is 0/0;
  - a gitlink bump becomes a submodule row;
  - `added_lines` returns head line numbers across two hunks;
  - an unresolvable base yields `problems` and a refusal.
  
  Control: a config copy with `"ratio": "0.40"` flips (100,33) to fail.
- [ ] DB2 The rule gate `check:ci-deletion-budget`: `.ci/scripts/quality/check_deletion_budget.py:1` (new; header `step: Deletion budget`, `lane: quality-branch`; the body via the `check_plan_implementation.py:179` shape; submodules via gh compare; INFO on admission; NOT JUDGED without an event). Proof: `.ci/scripts/quality/check_deletion_budget.py --selftest && PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_deletion_budget.py`. Cases: a short event is rc 1 with the numbers; with `Operational-Reason:` it is rc 0 with INFO; a compare response at the cap is rc 1 "unmeasurable". Control: an always-pass engine stub reds the selftest.
- [ ] DB3 The merge gate: `.claude/rediacc_hooks/plan_gate.py:458` (after the open-box loop, `deletion_budget.refusal(root, rev or "HEAD", pr_body)`) and `.claude/rediacc_hooks/guards/block_admin_merge.py:301` (the submodule arm). Proof: `python3 -m pytest .claude/rediacc_hooks/tests/test_plan_gate.py -q && python3 .claude/rediacc_hooks/guards/test-block_admin_merge.py`. Cases: a ticked plan on a short repo is refused with the numbers; with `Operational-Reason:` it is admitted; an unmeasurable head is refused; a short submodule merge admitted by the console PR body passes. Control: `refusal` returning "" reds the short case.
- [ ] DB4 The push guard's agreement line: `.claude/rediacc_hooks/guards/block_unverified_push.py:810` (one WARN line from `deletion_budget.measure(root, "HEAD")` on an allowed MMDD-N push, never a deny). Proof: `python3 .claude/rediacc_hooks/guards/test-block_unverified_push.py` with short and passing worlds, plus the golden re-recorded in `.claude/rediacc_hooks/tests/goldens/block_unverified_push.jsonl`. Control: a guard that denies on short flips the short world and reds.
- [ ] DB5 The Stop hook:
  - `.claude/hooks/stop/wl_prscope.py:46` (a `deletion` field on `LoopState`, filled in `done(LIVE, ...)` at :174, cached per head and base sha);
  - `.claude/hooks/stop/wl_checks.py:2534` (`pr_scope_line` advisory);
  - `.claude/hooks/stop/wl_checks.py:2623` (`V_LOOP_NEXT_DELETION_SHORT` in place of `V_LOOP_NEXT_MERGE` when ticked, short and unadmitted);
  - `.claude/hooks/stop/worklist_messages.py:2725` (`V_LOOP_NEXT_DELETION_SHORT`, `PR_SCOPE_DELETION`, `R_REGGATE_PAY_FOR`).
  
  Proof: `python3 -m pytest .claude/rediacc_hooks/tests/test_wl_prscope.py .claude/rediacc_hooks/tests/test_wl_loop_next.py .claude/rediacc_hooks/tests/test_wl_message_catalogue.py -q`. Cases: open plus short is advisory only; ticked plus short blocks; ticked plus short plus `Operational-Reason:` gives the merge offer. Control: dropping the LIVE-arm check restores the merge offer in the second case.
- [ ] DB6 The reggate payment line: `.claude/hooks/stop/wl_reggate.py:812` (`R_REGGATE_PAY_FOR` appended on a short branch with three DELETE-CANDIDATEs and the parametrize-first hint; `REGGATE_PROMPT` untouched). Proof: `python3 -m pytest .claude/rediacc_hooks/tests/test_wl_message_catalogue.py -q && python3 .claude/hooks/stop/test-reggate-ledger.py && npm run check:ci-rubric-calibration`. Control: a passing measurement prints no payment line.
- [ ] DB7 The static signals and the protected list: `.ci/rediacc_ci/quality/test_value.py:1` (new; S1-S4 and S7, `body_hash(node, literals=True|False)`, target resolution from imports) and `.ci/config/test-value.json:1` (new; `protected`, `control_first`, `min_observable`, the operator priority). Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_test_value.py`. Cases: local renames hash equal; a literal difference hashes equal only when abstracted; `mod._x` sets S1; a `fix(...)` def sets S7; every protected glob matches a real test. Control: emptying `protected` reds the non-vacuity case.
- [ ] DB8 The line map, shared by D6 and D12: `.ci/rediacc_ci/quality/test_line_map.py:1` (new; `sys.monitoring` LINE events with `DISABLE` and per-test `restart_events`; per-xdist-worker files; the `.pth` child hook with env-var and parent-pid-chain test-id lookup; the `unattributed` bucket; `merge(paths)`). Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_test_line_map.py` over `fixtures/test_line_map/`. Cases:
  - an in-process test and a `python3 -m` subprocess test both map to the target's executed lines;
  - a subprocess launched with an emptied env still maps, through the pid chain;
  - a child with no resolvable test lands in `unattributed`;
  - two worker files merge to their union;
  - a line run twice in one test is recorded once.
  
  Control: with the `.pth` hook absent, the subprocess case maps to none and reds.
- [ ] DB9 The mutation runner: `.ci/rediacc_ci/quality/test_mutation.py:1` (new; the six operators in priority order; trampolines in a sandbox copy; `TESTVALUE_MUTANT`; a double green baseline; protected-first, then redundant, then fastest; stop at the second kill; 5x timeout as a kill; `--shard i/N`; the resumable cache). Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_test_mutation.py` over `fixtures/test_mutation/`. Cases: an asserting test kills and an assertion-free one does not; a string-literal mutant lets an output test kill; a run stops after two kills; the live fixture bytes are unchanged; an unchanged-sha re-run runs zero mutants. Control: a red-baseline fixture is skipped and listed, never scored.
- [ ] DB10 Failure history: `.ci/rediacc_ci/quality/test_failure_history.py:1` (new; failures from the junit artifacts; W measured from the oldest artifact present; age from `git blame`; real failure = red then green across a code change). Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_test_failure_history.py`. Cases: a test younger than W yields `history: none`; an older red-then-green yields `failed: <run>`; a same-head flake yields nothing; with no artifacts W is 0, recorded rather than defaulted to 90. Control: forcing W to 90 days with 3 days of artifacts reds the "measured, not assumed" case.
- [ ] DB11 The keep-bar solver: `.ci/rediacc_ci/quality/test_keep_bar.py:1` (new; the D6 greedy, slowest first, S10 ahead at equal speed, S7 and S9 at the back, UNJUDGEABLE and flaky kept, unique kills recorded). Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_test_keep_bar.py` over `fixtures/test_keep_bar/`:
  - two sharers of an only kill: exactly one deleted;
  - kills shared with a protected test: deleted;
  - only surviving mutants on its lines: UNJUDGEABLE, kept;
  - the matrix minus a deleted test re-solves with no new deletions among former KEEPs.
  
  Control: a solver that skips the surviving-set update deletes both sharers and reds.
- [ ] DB12 The ledger and `check:ci-test-deletion-provenance`: `.ci/config/test-prune-ledger.json:1` (new) and `.ci/scripts/quality/check_test_deletion_provenance.py:1` + `.ci/rediacc_ci/quality/test_deletion_provenance.py:1` (new; `lane: quality-branch`; the D10 classes). Proof: `--selftest && <check>` rc 0, plus `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_test_deletion_provenance.py`. Controls: an unledgered deletion reds; a move stays green; a parametrize under its own case id stays green; a ledgered `test_deploy_*` deletion still reds.
- [ ] DB13 Registration of the rule and provenance gates, by hand where `quality-branch` requires it (`ci-quality.yml:596`):
  - `package.json:191`;
  - `scripts/ci-runner/manifest.ts` and `scripts/ci-runner/gates.lock.json:2086`;
  - `.github/workflows/ci-quality.yml:590` (two steps after "Plan implementation clock", with the gh token for compare);
  - `.ci/config/shards/quality-pytest.json` (the new test files, via `--rebalance quality-pytest --write`);
  - `.ci/config/python-env-registry.json`;
  - a "Deletion budget and keep bar" section in `docs/agent-reference/ci-gates.md` and one line in `CLAUDE.md`.
  
  Proof: `npm run check:ci-gate-bind && npm run check:ci-parity && npm run check:ci-gate-reachability-coverage && npm run check:ci-shard-manifest-coverage && npm run check:ci-python-env-registry && npm run ci -- --quick --list`, with the new gates absent from the quick plan. Control: dropping one manifest entry reds `check:ci-gate-bind`. Pushed together with DB16.
- [ ] DB14 The pilot, the full run and the report: `agent/reports/test-value-2026-10.json:1` and `.md:1` (new; generated by `PYTHONPATH=.ci python3 -m rediacc_ci.quality.test_keep_bar --report`). The pilot over three modules is recorded first with its per-mutant cost and the projected total. Its report holds:
  - per-class counts, and mutants generated, killed and discarded;
  - CPU-hours, and the measured W;
  - the S10 redundancy count.
  
  Proof: the command rc 0, and a `python3 -c` over the json asserting every DELETE-CANDIDATE carries a solver trace. Control: the report refuses to write while any judgeable test's target lacks a kill file.
- [ ] DB15 The twin inventory: `.ci/rediacc_ci/quality/twin_inventory.py:1` (new; the D7 classifier; release twins forced out of scope) and `agent/reports/twin-inventory-2026-10.json:1` (new). Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_twin_inventory.py`. Cases: an existing twin is twin-live; an absent one is twin-retired; prose only is comment-only; a release twin is out of scope even when absent. Control: classifying by the word alone puts the prose fixture in twin-retired and reds.
- [ ] DB16 Twin retirement, one commit per twin family, per D7 (salvage, control cases kept, goldens and `.ci/shadow/**` deleted with the test, docstrings re-pointed, `twin-retired` ledger rows, shards regenerated). Proof per commit: `npm run check:ci-pytest && npm run check:ci-test-deletion-provenance && npm run check:ci-shard-manifest-coverage && npm run check:ci-stale-plan-citations`, plus `git grep -n` over the deleted golden and shadow paths returning nothing. Control: restoring one deleted path in a docstring reds the citation check.
- [ ] DB17 Clone families: `.ci/rediacc_ci/quality/clone_families.py:1` (new; test groups from DB7's literal-abstracted hash, gate families from the shape-index windows, each member marked pattern-only or not) and `agent/reports/clone-families-2026-10.json:1` (new). Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_clone_families.py`. Cases: three tests differing in one literal form one group; two gates differing in a regex and a message form one pattern-only family; a third with different control flow is listed but not pattern-only. Control: a literals-kept hash forms no group and reds.
- [ ] DB18 Test parametrize merges, one commit per suite area, per D8 (case ids carry the old names; protected and control groups keep every case; `clone-merged` rows; shards regenerated). Proof per commit: `npm run check:ci-pytest && npm run check:ci-test-deletion-provenance && npm run check:ci-shard-manifest-coverage`, with the collected count unchanged for the merged groups. Control: dropping one case id reds provenance.
- [ ] DB19 The i18n gate family merged, per D8, over the pattern-only members among `scripts/gates/check-{i18n,locale,translation}-*.ts`, `check-dead-translation-keys.ts` and `check-cli-i18n-key-usage.ts`, plus their `.ci/rediacc_ci/tests/gates/test_gate_*.py` and the registration files. Proof: `npm run check:ci-gate-bind && npm run check:ci-parity && npm run check:ci-gate-reachability-coverage && npm run check:ci-<merged-id>`, plus the before and after `CONTROL` counts printed equal and `git grep -n` over the retired ids returning nothing. Control: deleting one arm's control reds the count check.
- [ ] DB20 The docs gate family merged, by the DB19 procedure, over the pattern-only members among `scripts/gates/check-docs-*.ts`, `check-doc-region-parity.ts` and `check-cli-docs.ts`. Proof and control as in DB19.
- [ ] DB21 Keep-bar batch 1, in this PR: DB14's DELETE-CANDIDATEs after an incremental re-run over the modules DB16 and DB18 changed, using CI's combined line map for the head once DB25 is green. At most 400 tests per commit, slowest first, `keep-bar` rows, a clean per-commit review, shards regenerated. Proof per commit: `npm run check:ci-pytest && npm run check:ci-test-deletion-provenance && npm run check:ci-shard-manifest-coverage && npm run check:ci-lane-budget && npm run check:ci-deletion-budget` (the last against a local event fixture with this PR's body). Control: deleting one KEEP test with a recorded unique kill, without a row, reds provenance.
- [ ] DB22 Floor 1 re-sized: `.ci/rediacc_ci/check_pytest.py:69` (`MIN_TESTS` to two thirds of the post-DB21 corpus, rounded down to a multiple of 50; docstring :23 updated). Proof: `.ci/rediacc_ci/check_pytest.py --selftest && npm run check:ci-pytest`. Control: the case at :526 holds, and a half-size fixture corpus reds floor 1.
- [ ] DB23 The follow-up plan: `agent/plans/PLAN-test-prune-batches.md:1` (new). It holds:
  - the remaining keep-bar batches and the UNJUDGEABLE list;
  - coverage and mutation for the vitest, account and renet suites;
  - D12's TS, Go and bash scope;
  - the release twins after the operator's real runs;
  - the junit-retention question from D9 as an operator decision.
  
  Queued via `npm run check:ci-plan-record -- --update`. Proof: `npm run check:ci-plan-record` rc 0. Control: with the plan file absent, the gate reports the entry as dangling.
- [ ] DB24 Overhead and cost refresh after the first green CI run with `--line-map` on the DB21 head. It records each leg's minutes with and without the map (from the `unit-durations` artifacts of that run and the preceding green run) in the D12 section of `docs/agent-reference/ci-gates.md`. It then refreshes `.ci/config/lane-durations.json` and `.ci/config/gate-costs.json` via `PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --refresh`, and runs `--rebalance quality-pytest --write`. Only if a leg still exceeds 15 minutes does it grow to four legs (`.ci/config/shards/quality-pytest.json` `"of": 4`, `.github/workflows/ci-quality.yml:2363` `shard: [1, 2, 3, 4]`). Proof: `PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --check && npm run check:ci-lane-budget && npm run check:ci-shard-manifest-coverage` rc 0. Control: a hand-added stale unit id reds `check:ci-lane-budget`.
- [ ] DB25 Coverage wiring on every PR, per D12:
  - `.ci/rediacc_ci/check_pytest.py:1043` (`--line-map <dir>` beside `parse_shard_args`, loading DB8's plugin and installing the `.pth` hook);
  - `.github/workflows/ci-quality.yml:2363` (the legs pass `--line-map reports/line-map/` and upload `line-map-quality-pytest-s<N>-<sha>`);
  - a new `coverage-combine` job after `quality-pytest` (`pull-requests: write`, `fetch-depth: 0`, steps "Coverage summary" and "Uncovered lines");
  - `check:ci-uncovered-lines` registered in `package.json`, `scripts/ci-runner/manifest.ts` and `scripts/ci-runner/gates.lock.json`;
  - the D12 section of `docs/agent-reference/ci-gates.md`.
  
  Proof: `.ci/rediacc_ci/check_pytest.py --selftest && npm run check:ci-gate-bind && npm run check:ci-parity && npm run check:ci-gate-reachability-coverage`, plus one CI run on the branch showing the three map artifacts, the combined map and the summary comment at the head sha (read with `.ci/scripts/ci/ci-trace.py`). Control: a leg run with `--line-map` withheld leaves one artifact missing, and the combine job goes red "coverage incomplete" rather than green.
- [ ] DB26 Combine and summary: `.ci/rediacc_ci/quality/coverage_combine.py:1` (new; merge, missing-leg refusal, the redundancy, hotspot and uncovered-changed computations) and `.ci/rediacc_ci/review/coverage_summary.py:1` (new; the upserted `<!-- coverage-summary: <head40> -->` comment, 30-row caps, advisory exit 0 on a posting failure, a `--render-only` local mode). It also adds `COVERAGE_PREFIX` beside `TABLE_PREFIX` at `.claude/hooks/stop/wl_prsignals.py:30`, and its pin in `.ci/rediacc_ci/tests/test_prsignals_pins.py`. Proof: `PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_coverage_combine.py .ci/rediacc_ci/tests/test_review_coverage_summary.py .ci/rediacc_ci/tests/test_prsignals_pins.py` over `fixtures/coverage/`. Cases:
  - a test whose every line is also run by another is listed redundant, and one with a sole line is not;
  - a line run by five tests heads the hotspot list;
  - an added executable line absent from the map is listed uncovered;
  - two runs upsert one comment.
  
  Control: changing the marker in one copy only reds the pin test.
- [ ] DB27 The shrink-only gate `check:ci-uncovered-lines`: `.ci/scripts/quality/check_uncovered_lines.py:1` + `.ci/rediacc_ci/quality/uncovered_lines.py:1` (new; scope, executable lines from `co_lines()`, content-hash ids, `unattributed` counted as run, `Operational-Reason:` through plan_gate's parser, `--drain` and `--write-baseline` through `shrink_only.write_verdict` at `.ci/rediacc_ci/quality/shrink_only.py:31`), and `.ci/config/uncovered-lines-baseline.json:1` (new; seeded, one line per file). Proof: `.ci/scripts/quality/check_uncovered_lines.py --selftest && PYTHONPATH=.ci python3 -m pytest -q .ci/rediacc_ci/tests/test_quality_uncovered_lines.py`. Cases:
  - a new uncovered added line reds;
  - the same with `Operational-Reason:` passes with INFO;
  - an added comment or docstring line never reds;
  - a baselined line now covered reds until `--drain`;
  - a `--write-baseline` that adds an id is refused;
  - an unchanged line shifted down by an insert keeps its id.
  
  Control: removing the baseline file makes `--write-baseline` refuse rather than reseed (the `write_verdict` missing-baseline arm).
- [ ] DB29 OPERATOR ADDITION PENDING (coverage). The operator called D12 "close to" right and said "there is something else we need". The scope, files and proof are not known, and this box is filled in place when the operator names the addition. It stays open until then, so the plan gate holds this PR's merge for it unless an `Operational-Reason:` line says why it merges without it.
