# PLAN: drain every inline lint and type suppression into code fixes or BLOCKER-carrying linter config

Status: done -- 2026-10-15, every box ticked (11 of 11); closed when check:ci-plan-record RF refused the open Status (operator order 2026-10-15, #1201d7b9). Was: approved -- operator ruling 2026-10-08T10:48Z: cleanup = "Fix code + central config"; scope = noqa, type: ignore, pylint disable, biome-ignore, eslint-disable*, @ts-*, nolint in console, private/renet and private/account
Depends-On: no-dep -- part 1 (check:ci-inline-suppressions, .ci/config/inline-suppressions-baseline.json and the pre-edit guard, writer a96aa631) has no plan file yet; box P0 refuses to start until that gate is on the branch. Replace this line with `Depends-On: PLAN-<part-1 slug>.md` once that plan exists.
Owner: d778be9d
First-Seen: 2026-10-08
Priority: P2 -- operator ruling; the shrink-only gate from part 1 already stops growth, so this is the drain, not the fence
Concurrency: parallel -- the lead runs P0 serially first; then four writers with disjoint Owns (WA .claude Python, WB .ci/root Python, WC TypeScript plus account, WD renet Go); P2 and F are the lead's, serial, at the end
Owns: pyproject.toml, conftest.py, .claude/hooks/**, .claude/rediacc_hooks/**, .ci/rediacc_ci/**, .ci/scripts/**, packages/locales/site_locales.py, packages/e2e-tests/**, private/account/web/src/pages/**, private/account/web/src/i18n/**, private/renet/**, biome.json, docs/agent-reference/suppressions.md, scripts/lib/suppression-liveness.ts, scripts/gates/check-suppression-liveness.ts, scripts/data/doc-registry.md, .ci/config/inline-suppressions-baseline.json
Worklist: #575d2992

## Why

On 2026-10-08 the operator banned inline suppressions and chose "Fix code + central config":
- Fix the code wherever that is possible.
- A pattern that is deliberate moves into per-file linter config. Each entry carries a `BLOCKER:` reason (docs/agent-reference/suppressions.md, "Format" and "Quality rules") that a liveness check can re-prove.
- The end state is zero inline markers.

Part 1 adds the shrink-only gate and the edit guard. This plan drains the baseline to zero, then switches the gate to "no baseline allowed".

### Measured 2026-10-08 on 43f0e6358 (renet 1dbe423)

- **Python `# noqa`:** 1983 by `git grep`, in 471 files.
  - Tokenized, 1961 are COMMENT tokens. The other 16 sit inside string literals: planted source in tests, for example `.ci/rediacc_ci/tests/gates/test_gate_ci_trace_branch.py:304,344,345,792`, plus docstrings.
  - By tree: `.claude/rediacc_hooks` 1040, `.claude/hooks` 438, `.ci/rediacc_ci` 299, `.ci/scripts` 198, `/home/developer/console/conftest.py` 2.
  - `ruff check --ignore-noqa --statistics` over `git ls-files '*.py' ':!private/**'` reports 1984 suppressed findings. The per-code numbers in the table below are those findings.
- **`# type: ignore`:** 139 (138 are comments). 13 are under `.claude`, 126 elsewhere.
  - By code: arg-type 48, call-overload 38, attr-defined 19, assignment 11, union-attr 7, method-assign 6, misc 4, override 2, and one each of list-item, index, import-untyped and func-returns-value.
- **TypeScript in console:** 148 markers in 15 files, all under `/home/developer/console/packages/e2e-tests`.
  - no-console 123, require-await 17, no-restricted-syntax 6, no-deprecated 2.
  - There is no real `@ts-*` or `biome-ignore` in console source. Those grep hits are fixture text (`.claude/rediacc_hooks/tests/hookcases.py:1364,2122-2137`, `.claude/rediacc_hooks/tests/goldens/block_suppressions.jsonl`, `.ci/rediacc_ci/tests/goldens/claude-hooks/test-hooks.sh.golden:2064-2069`) and gate prose in `scripts/gates/check-source-rules.ts`.
- **private/account:** 6 markers.
  - 5 file-header `/* eslint-disable custom/no-hardcoded-text */` in `private/account/web/src/pages/ConfigMemberAccept.tsx:1`, `private/account/web/src/pages/ConfigMembers.tsx:1`, `private/account/web/src/pages/ConfigSetup.tsx:1`, `private/account/web/src/pages/ConfigStorage.tsx:1`, `private/account/web/src/pages/admin/ConfigAdmin.tsx:1`.
  - 1 `biome-ignore` at `private/account/web/src/pages/ConfigMembers.tsx:95`.
- **private/renet:** 161 `//nolint` lines.
  - One of them is the generator string at `private/renet/_scripts/i18n/gen-locales.py:87`, which emits 13 more into `pkg/i18n/locales/*.go`.
  - By linter: gosec 70, nilerr 22, funlen,gocyclo 14, contextcheck 14, funlen 5, unparam 4, nestif 4, gocritic 4, gocognit 4, and smaller groups.
- **`pylint: disable` and file-level `# ruff: noqa`:** none.
- **The 20 files with eslint-disable:** the 15 e2e files plus the 5 account pages make exactly the "20 files still carry eslint-disable tokens" in the BLOCKER that keeps the stale-directive half of `scripts/gates/check-source-rules.ts` running only by hand. WC makes that BLOCKER false.

### Facts the design rests on (each probed with ruff 0.16.1 through `--stdin-filename`)

1. **RUF100 is already on** (`/home/developer/console/pyproject.toml:44-47`). An inline `# noqa: X` where X is per-file-ignored is reported as `RUF100 ... (non-enabled: X)`.
   - So adding a per-file entry turns the tree red until the inline markers are stripped. Entry and strip must land in ONE commit.
2. **`ruff check --select RUF100 --fix` deletes the whole comment**, including the trailing `-- reason`. Probe: `import json  # noqa: PLC0415 -- lazy for budget` became `import json`.
   - The reasons must be harvested BEFORE the strip.
3. **`lint.pyflakes.allowed-unused-imports = ["_cipath"]` makes `import _cipath` clean**, and makes an existing `# noqa: F401` on it RUF100. This is a central key, not a per-file ignore.
4. **E402 is not raised by `sys.path.insert(...)` or `os.environ[...] = ...` before an import.** It IS raised by any other statement, for example `HERE = ...`, `atexit.register(...)` or `_SYSPATH = _load_syspath()`.
5. **Other exemptions ruff honours:**
   - DTZ005 accepts `datetime.datetime.now().astimezone()`.
   - ARG002 skips a method decorated `@typing.override`.
   - N818 does not fire on a `BaseException` subclass. That route is NOT taken, because it changes which `except Exception` handlers catch the class.
6. **`ruff` has no "unused per-file-ignore" detection.** RUF100 covers inline markers only.
7. **golangci-lint v2 already has `linters.exclusions.warn-unused: true`** (`private/renet/.golangci.yml:477`), but it only warns. `nolintlint` is disabled (`private/renet/.golangci.yml:75`), and dead `//nolint` comments survive as a result:
   - `errchkjson` and `containedctx` are in the disable list (`private/renet/.golangci.yml:68-69`), yet each still has a `//nolint` in the tree.
   - The 13 locale directives are dead because `generated: lax` already skips files headed `// Code generated ... DO NOT EDIT.` (`private/renet/pkg/i18n/locales/en.go:1`).
8. **`check:ci-suppression-liveness` cannot see linter config today.** Its probes are deps, go-deps, embed-assets, devcontainer-pins, unverified-downloads, actions, templates-skiplist, overrides, dead-bash, ci-parity and pr-conditions (`scripts/gates/check-suppression-liveness.ts:332-420`). `BLOCKER_FILES` (`scripts/lib/suppression-liveness.ts:313-334`) names neither `pyproject.toml` nor `.golangci.yml`.
   - The design follows the documented in-gate precedent (`.runner-advice-allowlist`, `syncpack-source-exclusions.json`, docs/agent-reference/suppressions.md:42-43): the oracle is the linter run the gate already does.
9. **The mypy gate is shrink-only over a baseline.** `.ci/config/python-types-baseline.json` is read by `.ci/scripts/quality/check_python_types.py`. Removing a `type: ignore` without fixing the code creates a NEW finding and turns the gate red. Every `type: ignore` therefore has to be fixed for real, and this plan adds no mypy per-module overrides.

### Contract this plan needs from part 1 (confirm with writer a96aa631 before P0)

- **(a)** The gate counts COMMENT tokens only: Python `tokenize`, plus a comment lexer for TS and Go. The fixture strings listed above are not markers and are not drained here.
- **(b)** It can report counts per pathspec, which each box's acceptance below uses: `npm run check:ci-inline-suppressions -- --count <pathspec>`, or whatever spelling part 1 chooses.
- **(c)** `--write-baseline` refuses to add rows.
- **(d)** The pre-edit guard allows an Edit whose result has FEWER markers than the original, because every box here is a removal.

## Per-class decisions (Python)

"Real" is the count of ruff findings with `--ignore-noqa`. Writer columns: P0 means the config lands in P0 and the RUF100 sweep strips the markers.

| Class | Real | Decision | Mechanism | Where / writer |
|---|---|---|---|---|
| F811 | 797 + 1 | fix | `wl` and `sc` are pytest fixtures imported into 55 test modules and then shadowed by the parameter. Create `.claude/rediacc_hooks/tests/conftest.py` defining `wl` (moved from `.claude/rediacc_hooks/tests/wlfix.py:635-640`) and `sc` (moved from `.claude/rediacc_hooks/tests/test_wl_report_inbox.py:152-160`). Delete the 53 `from rediacc_hooks.tests.wlfix import wl  # noqa: F401` lines (for example `.claude/rediacc_hooks/tests/test_wl_cadence.py:21`), the `sc` import at `.claude/rediacc_hooks/tests/test_wl_interim_reports.py:12`, and every parameter-level `# noqa: F811` (for example `.claude/rediacc_hooks/tests/test_wl_cadence.py:164`). Not the root `pytest_plugins`: `/home/developer/console/conftest.py` runs with only `.ci` on the path (its own docstring). A second collector for the same directory is already handled by `.ci/rediacc_ci/pytest_conftest_rebind.py`. `.ci/rediacc_ci/tests/test_version_bump.py:623` (the plant): define it under another name and monkeypatch it in. | WA (797), WB (1) |
| PLC0415 | 436 | 281 deliberate, 155 fix | Deliberate: `.claude/hooks/**` (the 50+ `wl_*` modules import each other lazily because the graph is cyclic, for example `.claude/hooks/stop/wl_liveness.py:194` "wl_roster imports this module", and optional sibling modules, for example `.claude/hooks/stop/wl_checks.py:1802`) and the runtime half of `.claude/rediacc_hooks` (guards loaded on every tool call). Fix: hoist every stdlib lazy import under `.ci` (28 + 9 + 22 test sites, for example `.ci/rediacc_ci/quality/secret_supply.py:823-825` `copy, shutil, tempfile`), every test-file lazy import, and first-party lazy imports under `.ci` unless hoisting provably cycles (`python3 -c 'import <mod>'` fails) or the import is optional third-party (`yaml`). Those leftovers go to P2. | P0 / WA 32 / WB 123 |
| BLE001 | 243 | 207 + about 22 deliberate, about 14 fix | Deliberate: hooks fail open by contract ("FAILS OPEN, LOUDLY" in `.claude/rediacc_hooks/guards/block_plan_without_depends.py` docstring; `.claude/rediacc_hooks/guards/block_focus_spawn.py:174`), and the `.ci` verdict publishers whose job is "never crash, post unknown" (`.ci/rediacc_ci/ci/publish_ci_verdict.py:356,367`, `.ci/rediacc_ci/ci/github_status.py:361,391,480,644`, `.ci/scripts/ci/ci-trace.py` 10 sites, `.ci/rediacc_ci/review/pr_labels.py:355`, `.ci/rediacc_ci/review/review_table.py:664`, `.ci/rediacc_ci/security/workflow_gates.py:1124`, `.ci/rediacc_ci/security/ci_workflow_invariants.py:628`, `.ci/rediacc_ci/testrun/install_methods.py:251`, `.ci/rediacc_ci/testrun/install_methods.py:667`, `.ci/rediacc_ci/testrun/linux_packages.py:141`, `.ci/rediacc_ci/drills/lib.py:232`, `/home/developer/console/conftest.py:209`). Fix by narrowing to the real exception tuple: `.ci/rediacc_ci/ci/gate_ledger.py:939,970`, `.ci/scripts/quality/check_plan_implementation.py:108,177,239,250`, `.ci/scripts/quality/check_plan_record.py:1129`, `.ci/rediacc_ci/deploy/turnstile_drift.py:326`, `.ci/rediacc_ci/quality/ci_watch_recipe.py:193`, `.ci/rediacc_ci/security/rdc_sh_env_check.py:304`, `.ci/rediacc_ci/tests/gates/test_twin_parity.py:542`. Any of these that cannot be narrowed goes to P2. | P0 / WB |
| F401 | 196 | 139 central, 57 fix | `import _cipath` (139 entry points) goes to `allowed-unused-imports`. The `wl` imports disappear with F811. `.claude/rediacc_hooks/hookio.py:51` re-export gets `__all__`. `.ci/rediacc_ci/tests/test_workflows.py:140` probe becomes `importlib.util.find_spec("yaml")`. `.claude/hooks/stop/wl_loopspeed.py:32` side-effect import becomes an explicit hop call. Delete `from rediacc_ci import paths  # noqa: F401 (kept for parity ...)`. | P0 / WA / WB |
| E402 | 63 | fix | (a) Tests under `.ci/rediacc_ci/tests` that import stop modules (for example `.ci/rediacc_ci/tests/test_review_clean_ledger.py:14`): add `.claude/hooks/stop` to `[tool.pytest.ini_options].pythonpath` in P0 and delete each file's hop. This follows the "THE IMPORT PATH, IN ONE PLACE" comment in pyproject.toml, and it also shrinks the hand-hop baseline in `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py`. (b) `.claude/hooks/stop/test-*.py` scripts already get their own directory as `sys.path[0]`, so `HERE=` plus insert is redundant: delete it, and keep `os.environ[...]=` lines, which are exempt (for example `.claude/hooks/stop/test-ci-carried.py:26-28`). (c) `.claude/hooks/post-bash/arm_ci_watch.py:43-48`, `.claude/hooks/post-bash/review_commit.py:34-39`: a side-effect `.claude/hooks/post-bash/_hookpath.py`, the `_cipath` pattern. (d) `.claude/rediacc_hooks/guards/test-block_*.py` (for example `.claude/rediacc_hooks/guards/test-block_missing_npm_script.py:82-87`): a side-effect `.claude/rediacc_hooks/guards/_hookpath.py`. (e) `.ci/scripts/ci/ci-trace.py:44` and `.ci/scripts/quality/check_resprofile.py:46`: a side-effect `_stoppath.py` beside each. Both `_hookpath` and `_stoppath` go into `allowed-unused-imports` in P0. | WA 55 / WB 8 |
| S105/S106 | 27+2 | split | Rename where the name lies, on the precedent at `.claude/hooks/stop/wl_checklist.py:42-44` (for example `.ci/rediacc_ci/ci/gate_model.py:54` `TOKEN_PREFIX`, `.ci/rediacc_ci/deploy/deploy_proxy.py:66`, a message). Real dev credentials (`.ci/rediacc_ci/drills/backup.py:60`, `.ci/rediacc_ci/core/account_lifecycle.py:73`) go to P2 file entries. Never rename a real credential to dodge the rule. Test fixtures are covered by the tests glob. | P0 / WB |
| S102 | 22 | 21 deliberate, 1 fix | The guard harnesses exec the guard's own literal to prove it (`.claude/rediacc_hooks/guards/test-block_plan_box_rewrite.py:435,484`). `.ci/scripts/quality/check_bws_map.py:229` becomes `ast.literal_eval`. | P0 / WB |
| N818 | 25 | fix | Rename to an `...Error` suffix (`Refusal` becomes `RefusalError`, as at `.ci/rediacc_ci/build/build_pkg_repo.py:199,1089`). All references are module-local or in tests. | WB |
| ARG001/ARG002 | 25+10 | fix | `main(argv)` that ignores argv becomes `main(_argv)` (`.ci/rediacc_ci/release/install_script_check.py:445`). Stub overrides get `@typing.override` (`.ci/rediacc_ci/tests/test_drills_backup_license.py:714,717`; `.ci/rediacc_ci/ci/ci_diagnose.py:320`). | WA 5 / WB 30 |
| E731 | 22 | fix | Lambda assignments become `def`. | WA 7 / WB 15 |
| PLW0603 | 17 | fix | A module-level dict cache, on the precedent at `/home/developer/console/conftest.py:25-31` ("so no `global` statement is needed"), or `functools.cache`. | WA 2 / WB 15 |
| S101 | 17 | fix | Non-test asserts become `if x is None: raise RuntimeError(...)`. pyproject.toml:163-168 states why an assert outside tests is a real finding. | WB |
| S310 / S606 / S314 | 15 / 12 / 5 | funnel, then 3 entries | One helper each, as the single site: `rediacc_ci.core.https.urlopen_https` (refuses a non-https scheme), `rediacc_ci.proc.exec_replace`, `rediacc_ci.core.xml_trusted.parse`. WB leaves one inline marker per helper, and P2 moves those to config. | WB, then P2 |
| SIM115 | 8 | fix | `contextlib.ExitStack` (for example `.ci/rediacc_ci/ci/profiler_sampler_linux.py:875,984`). | WB |
| DTZ005/006/011 | 11 | fix | Use `datetime.now().astimezone()` for the local-date branch stamps (`.claude/rediacc_hooks/guards/block_second_branch.py:185`, `.claude/hooks/stop/wl_prscope.py:179`). Use `datetime.now(datetime.UTC)` elsewhere. | WA / WB |
| B010 | 7 | fix | Type the path-loaded module as `Any` and assign the attribute. `.claude/rediacc_hooks/tests/test_guards_differential.py:326-546` becomes `monkeypatch.setattr` where a fixture is available. | WA 6 / WB 1 |
| N802 | 7 | fix | Rename to lowercase. No lock or ledger references these names (grep is empty outside `*.py`). | WB |
| S104 | 2 | deliberate | `.ci/rediacc_ci/core/account.py:804,829` binds drizzle studio on all interfaces as its contract. | P2 |
| A002, B023, S112, singles | 13 | fix | Rename parameters (`.ci/rediacc_ci/tests/test_security_audit.py:439`); bind loop variables through a default argument; narrow `except` (S112 at `.claude/hooks/context/ctx_budget.py:122,248`); apply ruff's own suggestion for FLY002, UP020, PERF401 and PLW0108. | WA / WB |
| `type: ignore` | 138 | fix (no overrides) | `subprocess.run(**kwargs)` call-overload/arg-type (34 in `.ci/rediacc_ci/tests/test_proxies_*.py`, for example `.ci/rediacc_ci/tests/test_proxies_go_unit.py:142-153`): pass the keywords explicitly. Path-loaded modules get a `mod: Any` binding. Method-assign in tests becomes `monkeypatch.setattr` (`.ci/rediacc_ci/tests/test_drills_lib.py:373-428`). An optional module becomes `fcntl: ModuleType \| None` (`.ci/rediacc_ci/core/jsonl_append.py:22`). `cast` is the last resort. | WA 13 / WB 126 |

## Per-class decisions (TypeScript and Go)

| Class | Count | Decision | Mechanism | Writer |
|---|---|---|---|---|
| e2e `no-console` | 123 | fix | Add `packages/e2e-tests/src/utils/log.ts`, which writes through `process.stdout.write` and `process.stderr.write` (no-console does not apply), and route all 15 files through it. Then delete the now-dead e2e paths from biome.json override #18 (noConsole off). | WC |
| e2e `require-await` | 17 | fix | Drop `async` and return `Promise.resolve(...)`, or actually await. Then delete the e2e paths from biome.json override #19 (useAwait off). | WC |
| e2e `no-restricted-syntax` | 6 | fix | `packages/e2e-tests/src/constants.ts:15-62` re-exports `TEST_ENV` properties. Callers read `TEST_ENV.x` directly, and the aliases go. | WC |
| e2e `no-deprecated` | 2 | fix | `packages/e2e-tests/src/utils/bridge/BridgeTestRunner.ts:1306,1331`: migrate the callers and delete the deprecated members. | WC |
| account `no-hardcoded-text` | 5 | fix | Move the strings into `private/account/web/src/i18n/locales/*` with the account translation tooling. Then the `ACCOUNT_NO_HARDCODED_TEXT_DISABLE_FILES` exception (`scripts/gates/check-source-rules.ts:744-760`) and the rule-141 ignores in `scripts/data/source-rules.ts` are dead (box F). | WC |
| account `biome-ignore` | 1 | fix | `private/account/web/src/pages/ConfigMembers.tsx:95` "load on mount only": use a stable callback with `useCallback`, or move the loader into `web/src/hooks/`, where override #2 already decides the rule. | WC |
| renet generated `//nolint` | 13 + 1 | fix (dead) | Stop emitting the directive at `private/renet/_scripts/i18n/gen-locales.py:87` and regenerate. `generated: lax` already skips these files. | WD |
| renet dead `//nolint:errchkjson`, `//nolint:containedctx` | 2 | fix (dead) | Delete: both linters are disabled (`private/renet/.golangci.yml:68-69`). | WD |
| gosec | 70 | split | G304 and G306: fix with `filepath.Clean` / `os.Root` / 0o600 where the call allows. G204 (argv exec, for example `private/renet/cmd/renet/backup_delete.go:159`, `private/renet/pkg/infra/vm/kvm/driver.go:698`): add `exclusions.rules` with `path:` + `text: "G204"` per file, each with a `# BLOCKER:`. For `_test\.go$` and `pkg/testutil/`: one rule with `linters: [gosec]` and `text: "G204\|G304\|G306"`. | WD |
| nilerr | 22 | fix | Replace `if err != nil { return nil }` with the positive branch or an `errors.Is` classification (for example `private/renet/pkg/infra/vm/kvm/driver.go:487`, `private/renet/pkg/compose/exec.go:192`). Leftovers get path+text rules. | WD |
| contextcheck | 14 | fix | Thread `ctx` and detach with `context.WithoutCancel(ctx)` (Go 1.26.6 per `private/renet/go.mod:3`), for example `private/renet/pkg/hub/containers.go:347,498` and `private/renet/pkg/hub/proxy.go:48,56`. Leftovers join the existing path rules (`private/renet/.golangci.yml:546-566`). | WD |
| funlen / gocyclo / gocognit / nestif / maintidx / cyclop | about 17 | split | Extract a function where it is cheap. Otherwise add a path rule, following the existing `cmd/renet/(backup_pull\|backup_push\|checkpoint_commands)\.go$` rule. | WD |
| unparam, gocritic, singles | about 20 | fix | Remove always-nil error returns (`private/renet/pkg/ps/ps.go:111,281`, `private/renet/pkg/rbd/cowclone.go:290`, `private/renet/pkg/repository/lifecycle.go:434`). Use `slices.Concat` for appendAssign (`private/renet/pkg/proxy/compose.go:91,120`). The rest one by one. | WD |

## Config entries to add

### P0, `/home/developer/console/pyproject.toml`

Every key gets a `# BLOCKER:` comment block. One BLOCKER covers the codes after it until a blank line, the same group semantics as docs/agent-reference/suppressions.md:57. The three existing entries (`pyproject.toml:162-225`) are retrofitted with a `BLOCKER:` prefix on their existing reasons.

```toml
[tool.ruff.lint.pyflakes]
# BLOCKER: these modules are imported only for their sys.path side effect; a function call would be a statement and make every later import E402 (measured, .ci/scripts/quality/_cipath.py docstring)
allowed-unused-imports = ["_cipath", "_hookpath", "_stoppath"]

[tool.ruff.lint.per-file-ignores]
".claude/hooks/**/*.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
".claude/rediacc_hooks/commit_policy.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
".claude/rediacc_hooks/dispatch.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
".claude/rediacc_hooks/plan_gate.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
".claude/rediacc_hooks/hookio.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
".claude/rediacc_hooks/guards/block_*.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
".claude/rediacc_hooks/guards/warn_*.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
".claude/rediacc_hooks/guards/require_*.py" = [
  # BLOCKER: the Stop-hook modules import each other lazily because their import graph is cyclic (wl_liveness <-> wl_roster, wl_checks <-> its callers) and every hook invocation pays for what it imports at top level; P0 records the -X importtime cost of worklist.py beside this entry
  "PLC0415",
  # BLOCKER: a hook that raises bricks the agent's turn, so every hook in this tree fails open on an unexpected exception and reports it; a narrowed except would turn an unknown failure into a crash
  "BLE001",
]
"**/rediacc_hooks/guards/test-*.py" = ["N999",
  # BLOCKER: a guard harness execs the guard's own literal source to prove the deployed text, not a copy, behaves as claimed
  "S102"]
"**/tests/**/test_*.py" = ["S101", "S311",
  # BLOCKER: test fixtures carry fake credentials that the code under test must handle; no real secret can reach a pytest tree
  "S105", "S106", "S102"]
".ci/rediacc_ci/ci/publish_ci_verdict.py" = [
  # BLOCKER: a verdict or status publisher must post `unknown` rather than crash, because a crash loses the verdict the run produced
  "BLE001"]
".ci/rediacc_ci/ci/github_status.py" = [
  # BLOCKER: a verdict or status publisher must post `unknown` rather than crash, because a crash loses the verdict the run produced
  "BLE001"]
".ci/scripts/ci/ci-trace.py" = ["BLE001"]  # BLOCKER: a verdict or status publisher must post `unknown` rather than crash, because a crash loses the verdict the run produced
".ci/rediacc_ci/review/pr_labels.py" = ["BLE001"]  # BLOCKER: advisory output never fails CI
".ci/rediacc_ci/review/review_table.py" = ["BLE001"]  # BLOCKER: advisory output never fails CI
".ci/rediacc_ci/security/workflow_gates.py" = ["BLE001"]  # BLOCKER: a heredoc's traceback is exit 1; BaseException is caught to translate it
".ci/rediacc_ci/security/ci_workflow_invariants.py" = ["BLE001"]  # BLOCKER: a heredoc's traceback is exit 1; BaseException is caught to translate it
".ci/rediacc_ci/testrun/install_methods.py" = ["BLE001"]  # BLOCKER: a test that raises is a failed test, not an aborted run
".ci/rediacc_ci/testrun/linux_packages.py" = ["BLE001"]  # BLOCKER: a test that raises is a failed test, not an aborted run
".ci/rediacc_ci/drills/lib.py" = ["BLE001"]  # BLOCKER: teardown must finish
"conftest.py" = ["BLE001"]  # BLOCKER: an audit hook that raises aborts the audited operation

[tool.pytest.ini_options]
pythonpath = [".ci", ".claude/hooks/stop"]
```

### P2, residual entries

Only what WB proves cannot be fixed:
- S310, S606 and S314, one file each: the three funnel helpers.
- S104: `.ci/rediacc_ci/core/account.py`.
- S105: the dev-credential files.
- PLC0415: each `.ci` file with a proved cycle or an optional third-party import.
- BLE001: any of the narrowing candidates that would not narrow.

### WD, `private/renet/.golangci.yml`

- Every existing and new `linters.exclusions.rules` item gets a `# BLOCKER:` comment.
- New G204 rules are per file with a `text:` regex.
- The `_test\.go$` gosec rule is restricted by `text:`.

### Not planned

- No new biome or eslint config entries. WC's design needs none, and it removes the dead e2e paths from biome.json overrides #18 and #19.
- No mypy overrides (fact 9).

## Liveness: the box that teaches it (part of P0)

- **Where:** in-gate, in `.ci/rediacc_ci/quality/python_lint.py`, following the `.runner-advice-allowlist` precedent: the oracle is the ruff run the gate already makes.
- **BLOCKER check:**
  1. Parse the `[tool.ruff.lint.per-file-ignores]` and `[tool.ruff.lint.pyflakes]` regions of pyproject.toml line by line. `tomllib` drops comments, so it is used only to cross-check the parsed keys.
  2. Require a `# BLOCKER:` group over every (glob, code) pair and every allowed-unused-imports name.
  3. Validate each reason with `rediacc_ci.core.allowlist.validate_reason`.
- **Liveness check:**
  1. One extra run: `ruff check --no-cache --ignore-noqa --output-format json --config 'lint.per-file-ignores = {}' --config 'lint.pyflakes.allowed-unused-imports = []' --select <union of codes> -- <files>`.
  2. A pair is live if at least one finding of that code is in a file its glob matches. The matcher supports `**` and `{a,b}`, and a selftest cross-checks it against ruff on a planted file.
  3. A name in allowed-unused-imports is live if at least one F401 on it remains.
- **Verdicts:**
  - A dead entry fails with the line number.
  - Zero findings across the whole universe is "CANNOT VERIFY", never a pass.
- **Controls:** a planted dead entry and a planted reasonless entry, both required to go red.
- **Registration:**
  - Add `pyproject.toml` and `private/renet/.golangci.yml` to `BLOCKER_FILES` in `scripts/lib/suppression-liveness.ts`, so the pr-conditions clause check reads them.
  - Add rows to the mechanism table in `docs/agent-reference/suppressions.md`, marked "liveness in-gate".
  - Run `npx tsx scripts/gen/gen-docs.ts --write` for the derived suppressions region in `scripts/data/doc-registry.md`.
- **Known trade-off, written into the doc:** a directory-wide glob such as `.claude/hooks/**` proves only that at least one site exists, and it admits new deliberate sites without an inline marker. A per-entry count ratchet was considered and rejected as a second baseline. The BLOCKER text names the contract instead, so a site outside it is a review finding.

The golangci half belongs to WD:
- `private/renet/.ci/scripts/quality/lint.sh` captures the `warn-unused` output of all three runs (linux, darwin, windows; lines 29-48).
- It fails on a rule that is unused in all three. A rule live only on darwin is live.
- `.ci/rediacc_ci/private/run_renet.py` validates the BLOCKER comments with `validate_reason`.

## Writers (four concurrent after P0, disjoint)

- **Lead.** Owns `/home/developer/console/pyproject.toml`, `.ci/rediacc_ci/quality/python_lint.py`, `.ci/rediacc_ci/tests/test_quality_python_lint.py`, `scripts/lib/suppression-liveness.ts`, `scripts/gates/check-suppression-liveness.ts`, `docs/agent-reference/suppressions.md`, `scripts/data/doc-registry.md`, `.ci/config/inline-suppressions-baseline.json`. Runs P0, P2 and F. Every other writer requests pyproject entries through the lead.
- **WA (.claude Python).** Owns `.claude/hooks/**/*.py` and `.claude/rediacc_hooks/**/*.py`, except the part-1 guard file. Drains about 977 noqa and 13 type: ignore.
- **WB (.ci and root Python).** Owns `.ci/rediacc_ci/**` and `.ci/scripts/**` (except the lead's two files and `.ci/rediacc_ci/private/run_renet.py`), plus `/home/developer/console/conftest.py` and `packages/locales/site_locales.py`. Drains about 345 noqa and 126 type: ignore.
- **WC (TypeScript plus account).** Owns `packages/e2e-tests/**`, `/home/developer/console/biome.json`, `private/account/web/src/pages/**` and `private/account/web/src/i18n/**`. Drains 148 + 6.
  - Overlaps the Owns of the draft `agent/plans/PLAN-biome-only-lint.md`. If that plan is in flight, the lead serialises the two.
- **WD (renet Go).** Owns `private/renet/**` and `.ci/rediacc_ci/private/run_renet.py`. Drains 161.

## Tasks

- [x] P0 lead: precondition and config sweep.
  - Precondition: part 1's gate and baseline are on the branch, and the contract (a)-(d) is confirmed.
  - Harvest every inline `-- reason` for the config-covered classes into the BLOCKER text before stripping (fact 2).
  - Write the pyproject block above, the pytest `pythonpath` and allowed-unused-imports, and create `.claude/hooks/post-bash/_hookpath.py`, `.claude/rediacc_hooks/guards/_hookpath.py` and `.ci/scripts/ci/_stoppath.py`, `.ci/scripts/quality/_stoppath.py` (empty of callers for now).
  - Run `ruff check --select RUF100 --fix` over the tracked .py files in the SAME commit. Simulated, this drains 657.
  - Update `.ci/rediacc_ci/tests/test_canonical_sys_path_hop.py:426` to `import _cipath`.
  - Land the liveness and BLOCKER validation in `.ci/rediacc_ci/quality/python_lint.py` with its controls, `BLOCKER_FILES`, the suppressions.md rows and gen-docs.
  - Record the `-X importtime` cost of `.claude/hooks/stop/worklist.py` in the BLOCKER.
  - Acceptance: `npm run check:ci-python-lint` rc 0; `npm run check:ci-python-types` rc 0; `npm run check:ci-pytest` green with a collected count at least the pre-change count; `npm run check:ci-suppression-liveness` rc 0; `npm run check:ci-inline-suppressions -- --write-baseline` shrinks by about 657 and the gate is rc 0.
    (ticked) 2026-10-14T11:00:20Z by d778be9d: commit:69dcbc031 through commit:843681b63 (suprb5 03-18) with commit:8661b6e5d (liveness and BLOCKER validation): ruff check . rc=0, check:ci-python-lint, check:ci-python-types (0 new), check:ci-suppression-liveness and check:ci-inline-suppressions rc=0 on the landed tree
- [x] WA1: F811/F401 fixture move.
  - New `.claude/rediacc_hooks/tests/conftest.py` with `wl` and `sc`; 55 test modules lose their import and parameter markers.
  - Acceptance: `ruff check --no-cache .claude/rediacc_hooks/tests` rc 0; `python3 -m pytest .claude/rediacc_hooks/tests -q` green, with the same count as before; a hand-picked file-order run (the #6b5becd7 shape) is green.
    (ticked) 2026-10-14T11:00:22Z by d778be9d: commit:acbfa7820 through commit:44dc25f91: conftest.py carries wl and sc; ruff check rc=0; the moved modules run 398 and 490 passed in their two batches
- [x] WA2: the rest of `.claude`.
  - E402 hops (stop test scripts, post-bash and guard harnesses through `_hookpath`), PLC0415 in tests and harnesses, DTZ, E731, B010, ARG, S112, A002, PLW0603, and the 13 `type: ignore`.
  - Acceptance: `npm run check:ci-python-lint` and `npm run check:ci-python-types` rc 0; `npm run check:ci-pytest` green; `npm run check:ci-hook-integrity` rc 0; `npm run check:ci-inline-suppressions -- --count .claude` reports 0.
    (ticked) 2026-10-14T11:00:24Z by d778be9d: commit:a494c7afc commit:13fc2c349 commit:727f46339 commit:622d3d8e1: check_inline_suppressions.py --count .claude reports 0 markers in 350 files; python-lint, python-types and hook-integrity rc=0
- [x] WB1: `.ci` mechanical fixes.
  - F811 plant, F401, E402 (pythonpath and `_stoppath`), N818, N802, E731, ARG001/002, PLW0603, S101, SIM115, DTZ, B010, B023, A002, singles, and the S105 renames.
  - Acceptance: python-lint and python-types rc 0; `npm run check:ci-pytest` green.
    (ticked) 2026-10-14T12:08:45Z by d778be9d: commit:de78b5174 through commit:dbc2463f4 with the suprb5 28-41 series: python-lint and python-types rc=0 (0 new), check_inline_suppressions.py --count .ci reports 0 markers in 1255 files
- [x] WB2: `.ci` judgement work.
  - Hoist PLC0415, proving each kept-lazy import with a failing `python3 -c 'import X'` or an optional dependency.
  - Narrow BLE001.
  - Add the three funnel helpers (S310, S606, S314), with one inline marker each.
  - Fix the 126 `type: ignore`; the types baseline must not grow.
  - Hand the lead a list of every leftover (file, code, verified reason).
  - Acceptance: `npm run check:ci-python-types` rc 0 with the baseline unchanged or smaller; `npm run check:ci-pytest` green; the per-path count over `.ci` and `conftest.py` is no more than the handed-over list.
    (ticked) 2026-10-14T12:08:48Z by d778be9d: commit:42aaed77c (exec_replace), commit:78d4464d5 (https funnel, redirect check in fbaeeb596), commit:61b2c30fe (xml funnel), commit:dbc2463f4 (hoists, BLE001): python-types baseline 648 findings, 0 new, 0 grown; the touched modules tests 521 and 148 passed
- [x] WC1: e2e.
  - Add the `log.ts` logger; fix require-await, constants.ts and the deprecated members; remove the dead e2e paths from biome.json overrides #18 and #19.
  - Acceptance: `npm run check:lint` (the tooling shard then) rc 0; `npx biome lint packages/e2e-tests --error-on-warnings` rc 0; `npx tsc --noEmit -p packages/e2e-tests` rc 0; `--count packages/e2e-tests` reports 0.
    (ticked) 2026-10-13T19:40:08Z by d778be9d: commit:24700adad e2e markers drained (6ac6f1ca0 2b58ed344 2f24c5053 24700adad); grep finds 0 marker-bearing files under packages/e2e-tests; the tooling lint shard rc=0 in pre-push run 27
- [x] WC2: account.
  - i18n the 5 pages across every locale in `private/account/web/src/i18n/locales/`, and fix `private/account/web/src/pages/ConfigMembers.tsx:95`.
  - Acceptance: `npm run check:lint` (the account shard then) rc 0; `cd private/account && npm run typecheck:web` rc 0; the account i18n gate rc 0; `--count private/account` reports 0. This is an account submodule PR.
    (ticked) 2026-10-13T19:40:10Z by d778be9d: commit:4f0063f11 account c6ec4ac and 3145dbe; grep finds 0 marker-bearing files under private/account; the account lint shard rc=0
- [x] WD1: renet dead and mechanical.
  - Generator line and regeneration, the dead errchkjson/containedctx directives, unparam, gocritic, nilerr, contextcheck, and the singles.
  - Acceptance: `npm run check:ci-renet` rc 0 (golangci on linux, darwin and windows); `cd private/renet && go test ./...` green for the touched packages.
    (ticked) 2026-10-13T19:40:12Z by d778be9d: commit:814f23f77 renet bb9c148; zero nolint; check:ci-renet rc=0 (golangci 0 issues on three GOOS)
- [x] WD2: renet deliberate.
  - gosec split and complexity rules, each with a `# BLOCKER:`.
  - `lint.sh` fails on a rule unused in all three GOOS runs; `run_renet.py` validates BLOCKER comments; a planted dead rule and a reasonless rule both go red.
  - Acceptance: `npm run check:ci-renet` rc 0; `--count private/renet` reports 0. This is a renet submodule PR.
    (ticked) 2026-10-14T16:27:24Z by d778be9d: renet be1d639 and console a7b511201: bash .ci/scripts/quality/lint.sh rc=0 with rules=43 entries=66 and dead on all 0, a planted dead rule and a planted dead linter go rc=1, a reasonless rule fails run_renet.py at private/renet/.golangci.yml:799; check_inline_suppressions.py --count private/renet reports 0; pytest test_private_run_renet.py 70 passed
    (evidence) 2026-10-14 by d778be9d: npm run check:ci-renet rc=0 at f56153c61 (Renet CI completed successfully), the acceptance command the tick did not show (review 88e73c4f.1); the ledger row records the gate exists, this line records that it passed (88e73c4f.2)
- [x] P2 lead: residual config.
  - Add WB's handed-over entries and the three helper entries with BLOCKERs, and strip the last inline markers through RUF100 in the same commit.
  - Acceptance: python-lint rc 0, including liveness; `npm run check:ci-suppression-liveness` rc 0; `npm run check:ci-inline-suppressions -- --count .ci` and `-- --count conftest.py` report 0.
    (ticked) 2026-10-14T12:08:51Z by d778be9d: commit:de78b5174 and commit:a82f2fb5c: the leftovers are pyproject per-file-ignores with BLOCKER reasons, check:ci-python-lint (liveness) and check:ci-suppression-liveness rc=0, --count .ci and --count conftest.py both 0
- [x] F lead: close the gate.
  - Write `.ci/config/inline-suppressions-baseline.json` at zero, and switch `check:ci-inline-suppressions` to "no baseline allowed": a present baseline file is itself a failure.
  - Lift the "20 files still carry eslint-disable tokens" BLOCKER on the stale-directive gate (`scripts/ci-runner/manifest.ts`, `scripts/ci-runner/gates.lock.json`), since its reason is now false. Delete `ACCOUNT_NO_HARDCODED_TEXT_DISABLE_FILES` and the rule-141 ignores. These files are in `PLAN-biome-only-lint` Owns, so coordinate.
  - Acceptance: `npm run check:ci-inline-suppressions` rc 0 with "0 markers, no baseline"; `npm run check:ci-source-rules` rc 0; `npm run check:ci-suppression-liveness` rc 0; a planted `# noqa: F401` in a scratch copy is refused by both the gate and the pre-edit guard.
    (ticked) 2026-10-14T15:33:03Z by d778be9d: commit:f320d07d5 and commit:3bbecab99 with commit:0cd8b76b6: check:ci-inline-suppressions rc=0 with 0 markers and no baseline (a baseline file or a planted noqa F401 is refused), check:ci-source-rules rc=0 with the rule-141 ignores and ACCOUNT_NO_HARDCODED_TEXT_DISABLE_FILES gone, check:ci-suppression-liveness rc=0

## Risks

- **The P0 sweep touches about 400 files in one commit.** It is mechanical (RUF100 `--fix`), and the reasons are harvested first. No writer starts before it lands.
- **pytest pythonpath gains `.claude/hooks/stop`.** A test that relies on a stop module NOT being importable would change. Acceptance requires the same collected count and a green suite; `import_wl` reloads explicitly, so it is unaffected.
- **Renaming test functions (N802)** changes pytest node ids. grep found no lock or ledger reference, but WB re-checks `scripts/ci-runner/gates.lock.json` and `.ci/config/*` before landing.
- **WC2 needs translations for every account locale.** If the account translation tooling cannot produce them, the box stays open as `[?]` for the operator. It does not fall back to an inline marker or a config entry.
