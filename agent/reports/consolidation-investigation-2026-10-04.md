# Consolidation investigation, 2026-10-04

Operator task, 2026-10-04: "investigate consolidation opportunities in the console monorepo's CI and agent tooling, then plan them. Do not implement anything in this task." The eight candidates came from that task. Four read-only Explore agents (haiku) each covered two of them, and the lead spot-checked every load-bearing claim against the tree. Where an agent was wrong, the corrected fact is stated and the agent's claim is marked as refuted.

## Summary

| # | Candidate | Verdict | Size | Risk |
|---|---|---|---|---|
| 1 | Registration fan-out | **Worth planning.** The three env registries carry the same 134 WORKLIST names, and 585 names are shared between env-manifest and python-env. | M | low |
| 2 | Change scope | **Worth planning, after PLAN-gate-drop-receipt-verify.** Three encodings of path-to-gate knowledge exist, and the CI scope map is separate from the manifest. | L | medium |
| 3 | Freshness contract | **Small.** Only two artifacts have a live producer, and both became PR-bound in 7c845cf3b. A generic contract buys little today. | S | low |
| 4 | GitHub read layers | **Worth planning (hooks side).** Six gh call paths have two opposite error contracts, and the hooks cannot use ghx. | M | medium |
| 5 | Copied constants | **Drop.** Twelve values are copied in two hook files, every copy is pinned, and none has drifted. A shared module would hide the sys.path hop the repo deliberately states. | - | - |
| 6 | Plan-state verbs | **Smaller than stated.** `--plan-tick` already writes plan-boxes.json and INDEX.md. The fan-out happens at plan CREATION: plan-boxes `--update`, plan-record `--update` and QUEUE.md. | S | low |
| 7 | Regression-judge round trips | **Worth fixing, as a defect and not a consolidation.** The gate probe cannot map a pytest file to `check:ci-pytest`. Tracked as finding #57487768. | S | low |
| 8 | Hermetic hook tests | **Drop as a consolidation.** The only real-tree Stop-hook test was test_gate_stop_hook_stdin.py, fixed in 52757b7be. One other test drives dispatch.py, and guards never call the judge. | XS | - |

## 1. Registration fan-out

**Current state.** Each registry, what it holds, how it is written, and the gate that checks it:

| Registry | Holds | Written by | Checked by |
|---|---|---|---|
| `.ci/config/env-manifest.json` | 1080 names across 9 shards | hand | `check:ci-env-manifest` |
| `.ci/config/python-env-registry.json` | 596 distinct names in 463 module entries | `check_python_env_registry.py --write-baseline --allow-new <module>:<NAME>` (`.ci/rediacc_ci/quality/python_env_registry.py:26-28`) | its own gate |
| `.ci/policy/worklist-env-registry.json` | 134 WORKLIST names with kind, defaults and why | hand | `check:ci-worklist-env-registry` |
| `.ci/config/shards/quality-pytest.json` | 3 legs, 560 ids | `gate-bind --write`, per the `scripts/ci-runner/shard-manifest.ts:6` header. A new test is placed by hand: the coverage gate says "Add it to a leg", but nothing rebalances | `scripts/gates/check-shard-manifest-coverage.ts` |
| `scripts/ci-runner/gates.lock.json` | gate lock | `gen-gates-lock` | `check:ci-gates-lock` |
| `scripts/data/doc-registry.md` | doc regions | `scripts/gen/gen-docs.ts --write` | `check:ci-doc-region-parity` |

The message-catalogue ARITY table in `.claude/rediacc_hooks/tests/test_wl_message_catalogue.py` is hand-written per message.

**Duplication, measured by the lead.**
- env-manifest and python-env share 585 names. 11 python-env names are absent from env-manifest.
- All 134 WORKLIST names are in all three env registries.
- A new hook env var therefore takes three hand edits plus a gen-docs run, because env-manifest feeds a doc-registry region. On 2026-10-04 that cost three commits: 01dc64e36, then e72c255c9 for the missed doc region.

**Breakage history.** These commits fixed a missed registry: 01dc64e36, e72c255c9, 091c67391 (WORKLIST_DEAD_HOURS), 1ed8f824c, 32865d7cb, 20382976d, eb932d04d. The agent counted 21 matching subjects in 30 days. Only these seven were checked.

**Partial solutions.**
- gen-gates-lock is a working single-source generator.
- python-env-registry is already AST-measured and typed, and its `--allow-new` registers a read in one command.

**Shape of a fix.** One authored source per env var (name, class, kind, default, why), from which env-manifest and worklist-env-registry are generated. python-env-registry stays as the measured read set, checked against that source. The plan should also cover gen-docs triggered by the same verb, and an ARITY table derived by counting placeholders, with the test keeping only the sample arguments.

## 2. Change scope

**Current state.** Three places encode path-to-gate knowledge, and `check:ci-parity` cross-checks none of them against each other:
- **CI.** `.ci/scripts/ci/scope-map.cjs` (19 rules, KNOWN_MODULES, JOB_SURFACES) is run by `scope_shadow.py` in ci.yml's initialize job and produces the `run_<key>` outputs. Pointer-bump detection is separate, in `.ci/scripts/ci/detect-pointer-bump.sh`.
- **npm run ci --changed.** `scripts/ci-runner/select.ts` reads the manifest's `paths`, which 45 of 363 gates declare (lead count). Gates without `paths` fail open.
- **ci:quick.** `scripts/ci-runner/quick-select.ts` applies four rules: paths, transitive leaves imports, package.json script diffs, and a no-paths fail-open. It also excludes tree writers and admits gates only within a 90 s budget.

**Divergence.** ci:quick drops a touched slow gate for budget without recording the drop. That is #74f48292 and PLAN-gate-drop-receipt-verify, and it let a stale agent/INDEX.md reach CI (run 37129843955). The scope map and the manifest are independent: a new top-level path has to be added to scope-map.cjs by hand, or it routes wherever the map's default sends it.

**Shape of a fix.** The manifest stays the single source. A generated scope table, built from manifest `paths` and leaves plus the module list, feeds scope-map.cjs and quick-select. PLAN-gate-drop-receipt-verify (queue position 3) has to land first, because it changes what the receipt records.

**Risk.** Medium. CI routing errors are expensive, so this needs a shadow-mode period, which `scope_shadow.py` already provides.

## 3. Freshness contract

**Current state, corrected by the lead.**
- `.ci/config/lane-durations.json`: producer `budget_report --refresh`, check `budget_report --check`. Since 7c845cf3b the check runs on every PR as `check:ci-budget-freshness`.
- `.ci/config/gate-costs.json`: producer `gate_costs --refresh`, check `gate_costs --check`. Bound to the PR in the same commit. Before that the file did not exist and housekeeping mapped NO_BASELINE to a pass.
- `check_job_timeout_headroom.py --refresh` writes `job_max_seconds` into the same lane-durations.json (`.ci/scripts/quality/check_job_timeout_headroom.py:23`, "RETIRED INTO lane-durations.json"). Its gate reads only the committed numbers.
- **Refuted:** the agent said `check:ci-lane-budget` compares against fresh measurements. It is offline and judges committed numbers (`scripts/gates/check-lane-budget.ts` header).
- **Refuted:** the agent listed `job-timeout-baseline.json`. The file no longer exists.
- **Different class:** docker-image, devcontainer, embed and search-index freshness are shrink-only debt baselines, not live-producer caches.

**Verdict.** Two artifacts, both already bound per PR. A generic contract can wait for a third.

## 4. GitHub read layers

**Current state. Six gh call paths:**

| Path | Location | Failure contract | Timeout |
|---|---|---|---|
| `wl_ci._gh_json` | `.claude/hooks/stop/wl_ci.py:183` | returns `(None, error)` | 25 s |
| `wl_prreview.run_gh` | `wl_prreview.py:141` | returns an rc tuple; stdin DEVNULL | 120 s |
| `wl_prreview._gh_list` | `wl_prreview.py:168` | raises | 120 s |
| `ghx.api_json` | `.ci/rediacc_ci/core/ghx.py:377` | raises typed errors | 30 s, retries |
| `ghx.gh` | `ghx.py:315` | raises typed errors | 30 s, retries |
| `ci_diagnose.GhFetcher` | `.ci/rediacc_ci/ci/ci_diagnose.py:167` | custom per method | per call |

ci-trace's `_fetcher` adds a seventh path, and `wl_schedred` reuses `_gh_json`.

**Caches.** Six cache files with five TTLs: `.cistate` 180/900 s, `.ciqueue` 180 s, `.civerdict` 300 s, `.prlink`, `.schedred` 900/300 s, and `.cimark`.

**Why hooks cannot use ghx.** ghx imports `rediacc_ci.proc`, and a hook has no path to `rediacc_ci` (`wl_prreview.py:18-19`, `wl_prsignals.py:6`).

**Breakage history.** In 52757b7be's investigation the lead first suspected inherited stdin in `_gh_json`, which passes no `stdin`. It was not the cause, but `run_gh` closes stdin and `_gh_json` does not: one contract, implemented twice.

**Shape of a fix.** A stdlib-only `.claude/hooks/stop/wl_gh.py` with one call (argv, timeout, stdin DEVNULL, returning `(data, error)`) and one cache helper (path, TTL, error TTL, atomic write). wl_ci, wl_civerdict, wl_prreview and wl_schedred move onto it. ghx stays the CI-side layer.

## 5. Copied constants: recommend drop

**Copies.** Eight constant groups are copied in `wl_prsignals.py:17-42`, all pinned by `.ci/rediacc_ci/tests/test_prsignals_pins.py`. A further four review-comment values are copied in `wl_prreview.py:43-83`. No drift has been recorded.

**Why not a shared module.** A shared importable module needs `.ci` on sys.path inside hooks, which is exactly the hop `test_canonical_sys_path_hop.py` exists to keep stated. Copying and pinning costs one test per copy, and a drift fails loudly.

**Recommendation.** Leave as is. A follow-up would only pin the four `wl_prreview` values by name instead of by behaviour.

## 6. Plan-state verbs

**Corrected by the lead.**
- `--plan-tick --write` writes the plan file, then `.ci/config/plan-boxes.json` (`wl_planrec.py:140`, LEDGER_REL), then `agent/INDEX.md` (`R.refresh_index`, `worklist.py:796`, added in 7fc26359f).
- **Refuted:** the agent said `--plan-investigate` writes plan-boxes.json. It appends to `agent/ledgers/plan-investigation.jsonl` (`wl_planrec.py:2050`).
- The manual `check:ci-plan-boxes -- --update` today was needed because a NEW plan had no ledger entry. `check:ci-plan-record -- --update` regenerated the QUEUE.md backlog and the census.

**Shape of a fix.**
- A `--plan-new` verb, or a plan-file creation hook, that writes the ledger entry, INDEX, QUEUE and census in one step.
- `--plan-tick` could accept the investigation pointers inline (`--investigate present <ptr> <ptr>`), turning two calls into one.

**Size.** Small.

## 7. Regression-judge round trips: a defect

**Cause, found by the lead.** `wl_reggate.py:670-676` maps a changed test file to a gate only when package.json script TEXT names its path. Every pytest file under `.ci/rediacc_ci/tests` or `.claude/rediacc_hooks/tests` runs through pyproject `testpaths` under `check:ci-pytest`, so it always reads "no check:* key runs it". The suite-gate exception at `:661` covers `.claude/hooks/` and `.ci/scripts/test/gates/`, but not `.claude/rediacc_hooks/`.

**Refuted.** The agent said the fix-set omits test files. `fixset_files` lists every changed file, tests included (`wl_reggate.py:373-406`).

**Cost.** Today, seven stops settled as covered or one-off after a rebut that named check:ci-pytest by hand.

**Shape of a fix.** Teach the probe the pytest testpaths, which pyproject.toml already declares, and add `.claude/rediacc_hooks/` to the suite exception. Tracked as #57487768.

## 8. Hermetic hook tests: recommend drop as a consolidation

**Current state.** Tests that run real hooks outside wlfix:
- `.ci/rediacc_ci/tests/gates/test_gate_stop_hook_stdin.py` is the only one that ran the Stop hook against the real tree. It was fixed in 52757b7be (WORKLIST_JUDGE=off).
- `test_gate_untagged_commit_branch.py` drives `dispatch.py`. Guards make no judge or network call.
- `test_review_standing_orders_brief.py` uses a canned worklist.

**Recommendation.** A shared helper would have one caller. Fold the lesson into wlfix's docstring instead.

## Findings put on the worklist during this investigation

- **#57487768:** the gate-probe defect (candidate 7).
- **#137bd4d3:** `wl_wake.py` silently accepts an unknown flag (`--status` armed a timer).
