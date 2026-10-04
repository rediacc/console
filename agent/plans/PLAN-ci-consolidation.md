# PLAN: one registration verb, one freshness registry, one hook gh layer, one-call plan verbs, and the pytest-aware gate probe

Status: approved -- operator 2026-10-04 (/ask): candidates 1, 3, 4, 6 and 7 of agent/reports/consolidation-investigation-2026-10-04.md, one plan, one PR, queue position 2
Owner: d778be9d
First-Seen: 2026-10-04
Depends-On: no-dep -- candidate 2 (change scope) was the only part that had to wait for PLAN-gate-drop-receipt-verify.md, and it was not approved. This plan does not touch the receipt, quick-select.ts or run.ts. Both plans edit scripts/ci-runner/manifest.ts and gates.lock.json, but that is a file overlap, and the exclusive Concurrency rule plus queue order (this plan at 2, that one at 3) settle it
Priority: P2 -- operator /ask 2026-10-04, queue position 2. This is tooling cost and nothing is red: one hook env var took three commits on 2026-10-04 (01dc64e36, e72c255c9), and seven judge stops were settled by hand-written rebuttals (#57487768)
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited
Owns: .ci/policy/worklist-env-registry.json, .ci/policy/README.md, .ci/config/env-manifest.json, .ci/config/python-env-registry.json, .ci/config/freshness.json, .ci/config/shards/quality-pytest.json, .ci/config/plan-boxes.json, .ci/rediacc_ci/quality/{env_manifest,worklist_env_registry,env_register}.py, .ci/rediacc_ci/ci/{freshness,gate_costs}.py, .ci/rediacc_ci/tests/{test_quality_env_manifest,test_quality_env_register,test_ci_freshness,test_ci_gate_costs}.py, .ci/rediacc_ci/tests/gates/test_gate_worklist_env_registry.py, .github/workflows/housekeeping.yml, package.json, scripts/ci-runner/{shard-place,manifest}.ts, scripts/ci-runner/gates.lock.json, scripts/gates/check-shard-manifest-coverage.ts, .claude/hooks/stop/{wl_gh,wl_ci,wl_civerdict,wl_schedred,wl_prreview,wl_planrec,wl_reggate,worklist,worklist_messages}.py, .claude/rediacc_hooks/tests/{test_wl_gh,test_wl_plan_verbs,test_wl_message_catalogue,test_wl_regression_gate,test_wl_prreview,test_wl_schedred}.py, docs/agent-reference/{ci-gates,plan-records}.md, scripts/data/doc-registry.md, agent/INDEX.md, agent/plans/QUEUE.md
Worklist: #57487768 (candidate 7), #386292ac (the investigation and planning task)

**Operator request, 2026-10-04:** "investigate consolidation opportunities in the console monorepo's CI and agent tooling, then plan them."

**Operator answers, 2026-10-04 (/ask):** plan candidates 1, 3, 4, 6 and 7 (finding #57487768). One plan, one PR, queue position 2 in `agent/plans/QUEUE.md` Promoted. Drop candidates 5 and 8.

**Dropped.**
- **5 (copied constants).** Every copy is already pinned by test_prsignals_pins.py, and none has drifted. A shared module would need `.ci` on the hooks' sys.path, which is the hop test_canonical_sys_path_hop.py exists to keep explicit.
- **8 (hermetic hook tests).** The only test that ran the real tree was fixed in 52757b7be, so a shared helper would have exactly one caller.

**Rules for the whole PR.**
- Clean break: no compatibility shims, and every existing registry is migrated in this PR.
- Nothing commits on its own. Every verb keeps NEVER COMMITS (`worklist.py:504,742,816,937`).

## Part A: registration fan-out (candidate 1)

**Where the authored data lives.** Each name gets exactly one authored home, and no third file is added.

| Names | Authored home | Why |
|---|---|---|
| `WORKLIST_*` | `.ci/policy/worklist-env-registry.json` | It is already a policy decision (`.ci/policy/README.md:405-416`). It holds the only authored per-name fields: `kind`, `why` and the pinned `defaults` (`worklist_env_registry.py:15-37`). |
| everything else | `.ci/config/env-manifest.json` | It stays hand-authored. |

What changes:
- The WORKLIST registry gains one field, `class` (`harness` or `gate-seam`).
- Every `WORKLIST_*` member of an env-manifest shard list becomes generated output, rendered from the registry's `class`.

Why not a new `env-vars.json` from which both files are generated:
- env-manifest's shard lists are read directly by `scripts/lib/doc-providers.ts:1821,1954`, actions_vars.py, secret_supply.py and four tests.
- Moving the WORKLIST registry would churn the policy inventory's four-way equality (`.ci/rediacc_ci/policy_paths.py:85`, `scripts/lib/policy-paths.ts:96`).
- The overlap is exactly the WORKLIST names, measured today: 135 in env-manifest (133 `harness`, 2 `gate-seam`) and 134 in the registry. The odd one out is `WORKLIST_EPICS_LEDGER`, which is in env-manifest only.

**python-env-registry stays the measured AST read set** (`python_env_registry.py:26-28`). check_env_manifest gains one clause: every literal (non-`*`) name in it is classified in env-manifest. Exactly one name fails that today, `GATE_HARNESS_LEDGER` (read by `.ci/rediacc_ci/tests/gates/harness.py`).

**One verb.**

    npm run env:register -- <module> <NAME> --class <c> [--kind <k> --default <d>... --why <w>]

It runs `.ci/rediacc_ci/quality/env_register.py`, which does this in order:
1. **Validate.** `--class` must be one of `LIVE_SHARDS` (`env_manifest.py:97-106`). `WORKLIST_*` names need `--kind` and `--default`, plus `--why` for flag, handle and corpus, which is the same rule the gate applies. A name already registered under a different class is refused.
2. **Write the authored home.** WORKLIST names go into the registry's `names`; other names go into their env-manifest shard. Both are sorted.
3. **Re-render** the env-manifest WORKLIST members.
4. **Record the read.** For a `.py` module, run `check_python_env_registry.py --write-baseline --allow-new <module>:<NAME>`.
5. **Regenerate docs** with `tsx scripts/gen/gen-docs.ts --write`. It has no `--only`, and it is what feeds the doc-registry env-manifest region.
6. **Check** with the three gates, read-only, and print their verdicts.

It never commits. The env-manifest `_comment` ("There is deliberately no `--write-baseline`") is rewritten: the verb is typed per name, like `--allow-new`, so it is not a blanket reseed.

**ARITY is derived, not hand-written.** Today `test_wl_message_catalogue.py:53-445` is a hand table of 255 entries.
- The test parses each catalogue string's `%` placeholders (`%%` ignored; `(key)` gives a mapping; the conversion letter picks a sample: d/i/x take 1, f takes 1.0, s/r take "x") and renders it.
- It then AST-scans `.claude/hooks/stop/*.py` for `<alias>.NAME % <tuple|dict literal>` and fails when a call site's tuple length or dict keys differ from the derived arity. That is the call-site claim the hand table only asserted.
- The `SAMPLES` overrides are kept only where a sample value matters, for example `SCHED_ROW`.

**A new pytest file is placed automatically.** Today the coverage gate says "Add it to a leg (the lightest one, by the lane-durations estimate)" (`check-shard-manifest-coverage.ts:326-328`), and the file is placed by hand: the last six commits to quality-pytest.json were hand placements.

New `scripts/ci-runner/shard-place.ts`, run as `npm run shard:place -- <lane>`:
- It reads `unitsFrom(lane)` (`unit-enumerators.ts:343-353`) and the committed manifest (`parseShardManifest`).
- A missing unit goes to the leg holding its `mutex` group if it has one (`unit-enumerators.ts:255-272`). Otherwise it goes to the leg with the smallest sum of `units[id]` in lane-durations.json, using `defaultUnitMs[lane]` when a unit has no measurement.
- Phantom ids are removed.
- `generatedAt` moves only when the legs change, as gate-bind already does.
- It refuses lanes that have buckets or `rebalanceConstraints` (test-e2e-workers), so those keep going through gate-bind.

## Part B: freshness contract (candidate 3)

New registry `.ci/config/freshness.json`. It lists exactly the two real artifacts; the debt baselines are a different class (see the investigation, section 3). Each entry has:
- `artifact`
- `producers` (argv lists)
- `check` (argv)
- `network` (bool)
- `cadence`, a subset of `["pr", "nightly"]`

The entries:

| Artifact | Producers | Check |
|---|---|---|
| `.ci/config/lane-durations.json` | `budget_report --refresh`, and `check_job_timeout_headroom.py --refresh` for its `job_max_seconds` half (`.ci/scripts/quality/check_job_timeout_headroom.py:23`) | `budget_report --check` |
| `.ci/config/gate-costs.json` | `gate_costs --refresh` | `gate_costs --check` |

New `.ci/rediacc_ci/ci/freshness.py` has three modes:
- `--check --cadence <c> [--report-to F]` runs every matching check with `PYTHONPATH=.ci` and sums the exit codes. It is the single writer of the report, which becomes per-artifact sections.
- `--list`.
- `--refresh <artifact>`.

It refuses an empty registry, unknown keys, and a missing artifact. Because the report now has one writer, `gate_costs.py` loses `--report-to` (`gate_costs.py:336-338,437-440`).

Consumers:
- `package.json:153` `check:ci-budget-freshness` becomes `freshness --check --cadence pr`. The id is kept, since both artifacts are budget files; rename it when a third artifact arrives.
- In `housekeeping.yml:226-255`, the two check steps become one step, `freshness --check --cadence nightly --report-to /tmp/budget-check.txt`.
- The report and fail steps (`housekeeping.yml:264-276`) key on that one step.
- The manifest entry (`scripts/ci-runner/manifest.ts:1489-1513`) adds `freshness.py` and `freshness.json` to `leaves` and `paths`.

## Part C: the hook gh layer (candidate 4)

New `.claude/hooks/stop/wl_gh.py`. It uses only the standard library and reads no environment variable; it is added to the WORKLIST registry's `sealed_modules`, so a timeout knob would be a red. It has two parts.

**`call(argv, *, cwd, timeout=25)` returns `(data, error)` and never raises.**
- It spawns `["gh", *argv]` with `stdin=subprocess.DEVNULL`.
- It keeps every arm of `wl_ci._gh_json` (`wl_ci.py:183-210`): spawn error, non-zero exit, non-JSON output, and the GraphQL `errors` array returned with exit 0.
- `call_list(argv, ...)` is the `--paginate --slurp` flatten from `wl_prreview.py:168-180`, with the same `(data, error)` contract.
- A `run=` seam takes a raw `(rc, out, err)` runner, so wl_prreview's injected fakes (`wl_prreview.py:133`) keep working.

**`cache_read(path, ttl, error_ttl, now)` and `cache_write(path, doc)`.**
- The write is atomic: mkstemp, then `os.replace`, as in `wl_civerdict.py:62-73` and `wl_schedred.py:120-130`.
- An entry carrying `error` expires after `error_ttl`; any other entry expires after `ttl`, measured from `at`.

Migrated callers:
- **wl_ci.**
  - `_gh_json` sites at `:289, :314, :400, :831, :897, :1083`.
  - The raw `gh api graphql` call at `:77-90`.
  - The `.cistate` cache (`:939`, TTL `:986`) and the `.prlink` cache (`:1102`) move onto `wl_gh`.
  - The `.cimark` marker is not a cache, so it only gets the atomic write (`:1045`).
  - `_gh_json` is deleted.
- **worklist.py:278.**
- **wl_civerdict.** `fetch` (`:115-138`), with its cache on `FETCH_TTL_S` (`:28`).
- **wl_schedred.** `:204, :219, :240, :336`, with its cache on `TTL_S` / `ERROR_TTL_S` (`:32-34`). `WORKLIST_SCHED_RED_TTL_S` stays a read in wl_schedred.
- **wl_prreview.** `run_gh`, `_gh_json` and `_gh_list` (`:141-180`) are replaced. `UnreadableError` is raised in exactly one place, at the CLI boundary: wl_prreview's callers do expect a raise, but that is now one documented conversion rather than a second implementation.
- **Stays CI-side.** `ghx`, `ci_diagnose.GhFetcher` and ci-trace's `_fetcher` (`.ci/scripts/ci/ci-trace.py:247`).

## Part D: plan verbs (candidate 6)

**`worklist.py --plan-new <me> <agent/plans/PLAN-x.md> [--write]`.**
- **Refusals:**
  - the file is missing or is not under `agent/plans/`;
  - any of Status, Owner, First-Seen, Depends-On, Priority, Concurrency or Owns is missing;
  - the plan has no box;
  - the plan already has a ledger row (the refusal points to `--plan-tick`).
- **Steps, in order:**
  1. **Stage the file** with `git add -- <rel>`. This stages and never commits. It is needed because the ledger scan and INDEX read tracked plans only (`check_plan_boxes.py:183-184`, #0b93d454).
  2. **Write the ledger row**, `merge_ledger(doc, rel, ledger_row(root, rel, text))` (`wl_planrec.py:1975,2007`), into `.ci/config/plan-boxes.json`.
  3. **Refresh** with `R.refresh_index` (`wl_planrec.py:1254`), which writes INDEX, its census and the QUEUE generated section through `_refresh_queue` (`:1280`).
- **Untouched:** Promoted, which no tool writes.
- **Output:** it prints the one commit line.

**`--plan-tick <me> <plan> <box> <evidence...> --investigate present <kind>:<tok> <kind>:<tok>... [--write]`.**
- **Order:** it builds the row with `R.plan_investigate` (`wl_planrec.py:2244`), using the tick evidence as the note, which must clear INV_NOTE_MIN. It then passes the row as a new `inv_row=` parameter to `plan_tick` (`:2404`, which today looks it up at `:2453`). Nothing is written until both pass. The writes then go jsonl row, plan, ledger, index (`worklist.py:794-796`).
- **Verdict:** only `present` is accepted, because only `present` licenses an immediate tick. Clause 1 already exempts it (`wl_planrec.py:2340-2341`). `absent` and `partial` are refused with a pointer to `--plan-investigate`.
- **Other changes:** the usage texts at `worklist_messages.py:2414,2455` are updated, and so is the dispatch at `worklist.py:2518-2523`.

## Part E: the gate probe learns pytest testpaths (candidate 7, #57487768)

`prove_new_gate` (`wl_reggate.py:633`) changes in four ways:
1. **Read the testpaths.** `pytest_testpaths(root)` reads `[tool.pytest.ini_options].testpaths` from pyproject.toml (`pyproject.toml:377-381`) with stdlib `tomllib`.
2. **Map a changed test file to `check:ci-pytest`.** If it matches `test_*.py` under a testpath, it maps to that key, but only when `scripts` has the key and `gate_reachable` (`:588`) passes. The probe then runs `python3 -m pytest -q -p no:cacheprovider <rel>` through `wl_proc.run` within `REGGATE_TIMEOUT_S` (`:28`), with the note "collected by check:ci-pytest via pyproject testpaths". This replaces the script-text match at `:669-676` for those files.
3. **Widen the suite exemption** at `:661-668` to `.claude/rediacc_hooks/`.
4. **Widen `CHECK_SCRIPT_GLOBS`** (`:94-107`) with `.ci/rediacc_ci/tests/test_*.py`, `.claude/rediacc_hooks/tests/test_*.py` and `.claude/rediacc_hooks/guards/test-*.py`. The first-sight seeding at `:644-652` keeps untouched files from running.

## Tasks
- [x] T1 Register this plan: `npm run check:ci-plan-boxes -- --update` and `npm run check:ci-plan-record -- --update` (the verb does not exist yet), and insert it by hand at Promoted position 2 in `agent/plans/QUEUE.md`. Proof: `check:ci-plan-boxes` and `check:ci-plan-record` pass. Control: revert the ledger row and plan-boxes reds, naming this plan.
    (ticked) 2026-10-04T07:33:56Z by d778be9d: npm run check:ci-plan-record -- --update rc=0, check:ci-plan-boxes --update rc=0, QUEUE.md:12 Promoted 2
- [ ] T2 The WORKLIST registry gets `class` on all 134 names. `WORKLIST_EPICS_LEDGER` gets registered, or its exclusion is written down with the reason (to be found out in this box). env_manifest.py renders and checks WORKLIST shard membership against the registry. Proof: new cases in `test_quality_env_manifest.py` and `test_gate_worklist_env_registry.py`. Control: a WORKLIST name hand-placed in the wrong shard reds, and the message names `npm run env:register`.
- [ ] T3 check_env_manifest gets the python-env clause, and `GATE_HARNESS_LEDGER` is classified as `gate-seam`. Proof: a `test_quality_env_manifest.py` case. Control: a literal name planted in a copy of python-env-registry.json (through `ENV_MANIFEST_OVERRIDE_FILE`-style seams) reds, and an opaque `*` name does not.
- [ ] T4 `env_register.py` and `npm run env:register`. Proof: `test_quality_env_register.py` against a `REDIACC_CI_ROOT` fixture tree, with a recording runner for the gen-docs and `--allow-new` subprocesses. Controls: a flag with no `--why` is refused and writes nothing; a re-registration under a different class is refused; a non-`.py` module skips `--allow-new`.
- [ ] T5 Rewrite the "how to add" prose: env-manifest `_comment`, the registry `$why`, the env_manifest.py and worklist_env_registry.py docstrings, and `.ci/policy/README.md` §405 (the `class` field). Proof: `check:ci-policy-inventory`, `check:ci-prose-style`.
- [ ] T6 Derived ARITY plus the AST call-site check in `test_wl_message_catalogue.py`; the hand table is deleted. Proof: test_117 passes on the tree. Controls: a planted call site `M.V_IDLE % ("a", "b")` in a tmp copy fails; a catalogue string with a mixed keyed and positional placeholder fails.
- [ ] T7 `scripts/ci-runner/shard-place.ts` with `--selftest`, `npm run shard:place`, and the selftest chained into `check:ci-shard-manifest-coverage` (`package.json:154`). The coverage "missing" message names `npm run shard:place -- <lane>`. Controls: the selftest places a fixture unit on the lightest leg, puts a mutex unit with its group, drops a phantom, refuses test-e2e-workers, and leaves a no-op run byte-identical.
- [ ] T8 `.ci/config/freshness.json` and `freshness.py`, and `gate_costs --report-to` is removed. Proof: `test_ci_freshness.py` with a fixture registry of `python -c` checks, plus updated gate_costs tests. Controls: one failing check makes rc 1 and names its artifact in the report; an empty registry is refused; `--cadence nightly` skips a pr-only entry.
- [ ] T9 Rewire the package.json `check:ci-budget-freshness` script, the manifest.ts entry, and housekeeping's budget-check job. Proof: a `test_ci_freshness.py` pin that parses housekeeping.yml: the budget-check job calls `rediacc_ci.ci.freshness`, and calls neither budget_report nor gate_costs directly. Control: re-add the old step and the pin fails. Plus `check:ci-workflow-invariants`, `actionlint`.
- [ ] T10 `wl_gh.py`. Proof: `test_wl_gh.py`. Cases: non-zero exit, timeout, spawn failure, non-JSON output and GraphQL `errors` each return `(None, str)`; `stdin is subprocess.DEVNULL` (kwargs captured); cache TTL and error TTL; an atomic write leaves no tmp file. Control: drop `stdin=` and the case fails.
- [ ] T11 Migrate wl_ci (6 sites plus `:77`), worklist.py:278, wl_civerdict and wl_schedred, along with their caches; `wl_ci._gh_json` is deleted. Proof: the existing `test_wl_schedred.py` (PATH gh shim), `test_wl_ci_status.py`, `test_wl_ci_verdict_surface.py`, `test_ci_trace_scheduled.py` and `test_wl_ci_queue_and_mail.py` stay green unchanged. Control: a shim exiting 1 still yields `unreadable`, not a raise.
- [ ] T12 Migrate wl_prreview onto `wl_gh.call` and `call_list` through the `run=` seam. Proof: `test_wl_prreview.py` stays green, and its fake runner is untouched.
- [ ] T13 Pin the consolidation. A `test_wl_gh.py` case AST-scans `.claude/hooks/stop/*.py` and refuses any `subprocess.*(["gh", ...])` outside wl_gh.py. wl_gh.py goes into `sealed_modules`. Control: the scanner flags a planted source string. Plus `check:ci-worklist-env-registry`.
- [ ] T14 `--plan-new`. Proof: `test_wl_plan_verbs.py` in a tmp git repo checks that the ledger row equals `ledger_row`, that INDEX lists the plan, and that the QUEUE generated section lists it. Controls: skip the `git add` and INDEX omits the plan (the test fails); a missing Owns header is refused with nothing written.
- [ ] T15 `--plan-tick ... --investigate present ...`. Proof: one call in `test_wl_plan_verbs.py` writes the jsonl row and ticks the box. Controls: `--investigate partial` is refused; an unresolvable pointer is refused; in both cases plan, ledger and jsonl stay byte-identical.
- [ ] T16 wl_reggate: testpaths mapping, exemption and globs. Proof: `test-reggate-ledger.py` and `test_wl_plan_fidelity.py` stay green.
- [ ] T17 Regression test in `test_wl_regression_gate.py`: a fixture root whose pyproject declares testpaths, plus a dirty `.ci/rediacc_ci/tests/gates/test_gate_fixture.py`, must prove via check:ci-pytest. Shown red on the pre-T16 code: the note there reads "no check:* key runs it". Control: remove `testpaths` from the fixture and the note reverts.
- [ ] T18 Place the four new pytest files (test_quality_env_register, test_ci_freshness, test_wl_gh, test_wl_plan_verbs) with `npm run shard:place -- quality-pytest`, using T7's own verb. Proof: `check:ci-shard-manifest-coverage`.
- [ ] T19 Regenerate the lock with `npm run gen:gates-lock`, plus `tsx scripts/gate-bind.ts --write` if a region moved. Proof: `check:ci-gates-lock`, `check:ci-gate-bind`.
- [ ] T20 Docs. `docs/agent-reference/ci-gates.md`: the one-command registration, the freshness registry replacing the prose at `:134`, `wl_gh` as the hook gh layer, and `shard:place`. `docs/agent-reference/plan-records.md`: `--plan-new` and `--investigate`. Then `npm run gen:docs -- --write` for doc-registry.md and the CLAUDE.md regions; CLAUDE.md is changed only by that generator. Proof: `check:ci-doc-region-parity`, `test_gate_docs_gen.py`.
- [ ] T21 Registry gates on the final tree: `check:ci-env-manifest`, `check:ci-worklist-env-registry`, `check:ci-python-env-registry` (pairs moved by T11 drained with `--write-baseline`), `check:ci-policy-inventory`, `check:ci-hook-integrity`.
- [ ] T22 Live checks, read-only. `npm run check:ci-budget-freshness` against GitHub gives the same verdict as the old two commands. `ci-trace.py` and one Stop read CI through `wl_gh` (the `.cistate` file is rewritten atomically).
- [ ] T23 Close #57487768 with tick evidence naming the T16 and T17 commits.
- [ ] T24 Full `npm run check:ci-pytest` with no shard, the hook test-*.py suites, and `npm run ci:quick` on the final tree, with every red fixed in this PR.
