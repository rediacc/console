# PLAN: port test-agent-session-archival.sh to a pytest gate test, retire the bash gate-test entry
Status: done
First-Seen: 2026-09-23
Summary: the 306-line bash gate-test is now 15 pytest cases in `.ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py` (15 passed, and a planted `dead=True` in `move()` red exactly the one live-target case), the bash file and its manifest entry are gone, and `check:ci-language-policy` is green at 38 controls with no NEW bash finding.
Owner: d778be9d
Updated: 2026-09-23

## The live finding

`npm run check:ci-language-policy` (`.ci/scripts/quality/check_language_policy.py`) is red with exactly one finding:

```
✗ 1 NEW bash file(s) under .ci, .claude, scripts/ops, scripts/drills, scripts/dev. Ruling 7 (2026-09-06) makes these trees
  Python; the surface may shrink and may never grow:
    .ci/scripts/test/gates/test-agent-session-archival.sh

  Write it in Python instead. If it genuinely must stay bash forever, add it
  to /home/developer/console/.ci/policy/.language-policy-allowlist with a BLOCKER reason
  that says why. Do NOT add it to .ci/config/language-policy-baseline.json -- that file is the port's backlog and it
  only shrinks.
```

`.ci/scripts/test/gates/test-agent-session-archival.sh` (306 lines) is staged this session but was never committed: `git show HEAD:.ci/scripts/test/gates/test-agent-session-archival.sh` fails with "path does not exist in 'HEAD'", and `git log --all --oneline -- .ci/scripts/test/gates/test-agent-session-archival.sh` returns nothing. It has no history to protect.

Confirmed absent from both grandfather lists, so there is nothing to edit there and nothing to add:
- `.ci/config/language-policy-baseline.json` -- no match for `agent-session-archival`
- `.ci/policy/.language-policy-allowlist` -- no match for `agent-session-archival`

## What the bash file tests, and what it does not need to bring with it

`.ci/scripts/test/gates/test-agent-session-archival.sh` is a gate-test (a test file, `qualityGateTest: true`), not an operator-facing tool.
It drives `.ci/scripts/quality/check_agent_session_archival.py`, which is already Python (`.ci/scripts/quality/check_agent_session_archival.py:1`, entry point) sitting on top of the already-Python library `.ci/rediacc_ci/quality/agent_session_archival.py`. There is no bash production subject to port -- only the test.

That distinguishes this from the `bws-rotate` precedent this session already completed: there, `scripts/dev/bws-rotate.sh` (an operator tool) had to become `scripts/dev/bws-rotate.py` *and* its gate-test had to be ported. Here the production side is a non-issue; only the bash gate-test needs a home in Python.

The already-staged `.ci/rediacc_ci/tests/test_quality_agent_session_archival.py` does NOT make the bash file redundant.
It is the port of the *library's* own reasoning (`agent_session_archival.py`'s pure functions: `idle_hours`, `classify_due`, `vacuity_reason`, `label_for`, `move_refusal`, etc.), driven by direct import (`.ci/rediacc_ci/tests/test_quality_agent_session_archival.py:1-9,264-288`).
Its own docstring says exactly this: it drives "the individual functions directly," and it imports `check_agent_session_archival` only "for its constants only; nothing here calls `main`" (`.ci/rediacc_ci/tests/test_quality_agent_session_archival.py:27-34`).

The bash file's own header states what it adds on top of that (`.ci/scripts/test/gates/test-agent-session-archival.sh (retired at 1ad63b448, ported to .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py; the site was lines 11-34)`): its own `--selftest` (34 controls) proves `move_refusal()`'s DECISION as a pure function and nothing else.
The bash file exists to drive the CLI entry point as a real subprocess against a real git repository, and specifically to prove:

1. `--move` really performs `git mv`, the old path is really empty afterwards, and `git status --porcelain` reports it as a rename (`test-agent-session-archival.sh (retired at 1ad63b448, ported to .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py; the site was lines 98-114)`).
2. The reserved-name rail, the live/`--force` rail, the dirty-tree rail, and the occupied-archive-path rail, each refused as a process exit code (1, or 2 for a bad invocation) and each mirrored by the same fixture succeeding once the one blocking fact is fixed (`:127-222`).
3. `--check`, `--status` and `--selftest` write nothing at all to `agent/` or the git index, driven as three real invocations (`:226-238`).
4. The gate reds on a real backlog and goes green once the fix it names is applied (`:240-254`).
5. The three CANNOT-RUN (exit 77) cases -- empty `agent/`, missing `agent/archive/`, and a `.claude/` that cannot be reached -- each refuse rather than silently passing (`:256-287`).
6. The fixture symlinks the real `.claude/` (`ln -s "$REPO_ROOT/.claude" "$root/.claude"`, `:65`) so the gate's derivation of `wl_store` (`.ci/scripts/quality/check_agent_session_archival.py:262-277`, `paths.hooks_stop_dir` + `paths.on_sys_path`) is exercised against the live oracle, not a copy that could drift.
   This is exactly why the manifest entry declares `reads: ['tree:repo']` (`scripts/ci-runner/manifest.ts:4840-4841`).

None of that -- the CLI as a process, the real `git mv`, the exit codes, the read-only guarantee, the symlinked live oracle -- is covered by the existing `test_quality_agent_session_archival.py`. So this is a genuine port, not a deletion.
It lands as a new "gates" pytest module beside the existing one, following the naming convention `check_<name>.py` -> `test_gate_<name>.py` already used across `.ci/rediacc_ci/tests/gates/` (e.g. `check_plan_folders.py` -> `test_gate_plan_folders.py`).

## Where it lands, and why no BASH_TWIN

Target: `.ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py` (not `.ci/rediacc_ci/tests/test_quality_agent_session_archival.py` -- that name is taken by the pure-function port already staged, and mixing the two kinds of test into one file would blur the "what this adds to the gate's own selftest" framing both files rely on).

`.ci/rediacc_ci/tests/gates/` is already a real pytest root (`pyproject.toml:377-379`, `testpaths`), auto-collected by `check:ci-pytest` (`.ci/rediacc_ci/check_pytest.py:780-802`, `testpath_dirs()` reads `testpaths` rather than a hardcoded list) and by the shared `gate` fixture in `.ci/rediacc_ci/tests/gates/conftest.py:1-45` (anti-vacuity: a test that records zero `gate.log_pass()`/`gate.assert_*` calls but exits green is itself a failure).

No `BASH_TWIN` module attribute is declared, and this follows the `bws-rotate` precedent directly: `test_twin_parity.py` (`.ci/rediacc_ci/tests/gates/test_twin_parity.py:1-30`) exists to compare a port against a committed bash original ("invariant 5 forbids deleting a twin in the change that ports it").
That invariant protects twins with real git history -- `check-python-lint.sh` (`.ci/rediacc_ci/tests/test_quality_python_lint.py:260-262`), `run-all.sh` (`.ci/rediacc_ci/battery.py:4`), etc. `test-agent-session-archival.sh` has none: it was never in a commit.
`test_gate_bws_rotate.py` set the exact precedent for this same situation this session (`.ci/rediacc_ci/tests/gates/test_gate_bws_rotate.py:1` -- "retired 2026-09-23", no `BASH_TWIN` anywhere in that file, confirmed by grep).
`ported_modules()` (`.ci/rediacc_ci/tests/gates/test_twin_parity.py:59-65`) only compares modules that declare `BASH_TWIN`; a module that does not simply isn't part of that comparison, which is correct here because there is no committed original left to diff against.

## The template

`.ci/rediacc_ci/tests/gates/test_gate_plan_folders.py` is the closest existing shape: a CLI gate script (`check_plan_folders.py`, which -- like this one -- has a read verb and a writing verb, `--move`/`--sweep`) driven as a subprocess against real git repositories built in `tmp_path`, using:
- `harness.run([sys.executable, str(GATE), *argv], cwd=paths.repo_root(), env={...})` (no pty needed -- this subject takes no TTY-gated input, unlike `bws-rotate.py`)
- a `_seed(tmp_path, extra=...)` fixture builder that inits, configures and commits a git repo
- the `gate` fixture's vocabulary: `gate.assert_exit_code`, `gate.assert_contains`, `gate.assert_vacuous_tree_fails`, `gate.log_pass`, `gate.log_fail`

`test_gate_bws_rotate.py`'s pty machinery (`run_full`, `_read_pty`) is not needed here: `check_agent_session_archival.py` takes no TTY-gated stdin, so `harness.run` (plain `subprocess.run`) is sufficient for every case, exactly as `test_gate_plan_folders.py` already does for its own `--move`/`--sweep`.

## Confirmed seams available on the subject (no production code changes needed)

- `AGENT_SESSION_ARCHIVAL_ROOT` env var seam: `.ci/rediacc_ci/quality/agent_session_archival.py:54` (`ROOT_ENV`), read by `repo_root()` at `:276-278`. This is exactly what the bash fixture already uses (`test-agent-session-archival.sh (retired at 1ad63b448, ported to .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py; the site was line 83)`, `run_gate()`).
- `.ci/config/agent-session-archival.json` must exist under the fixture root with a numeric `grace_days` (`.ci/scripts/quality/check_agent_session_archival.py:304-311`, `_config()`); the bash fixture copies the real file (`test-agent-session-archival.sh (retired at 1ad63b448, ported to .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py; the site was line 66)`) -- the port does the same, from `paths.from_root(".ci", "config", "agent-session-archival.json")`.
- The oracle derivation: `.ci/scripts/quality/check_agent_session_archival.py:262-277` (`_wl_store`), using `paths.hooks_stop_dir(root)` + `paths.on_sys_path`. A fixture with no `.claude/` at all makes this raise `CannotRunError` -> exit 77 with "cannot import wl_store" in the message (`:273-276`, `main()`'s `except CannotRunError` at `:486-488`).
- `move()`'s full rail set lives at `.ci/scripts/quality/check_agent_session_archival.py:402-452`; `run()`'s vacuity/backlog behaviour at `:327-369`; `main()`'s argv handling (including the `--move` with no target -> exit 2 case) at `:455-489`.

## Tasks

- [x] T1. Re-run `npm run check:ci-language-policy` and confirm the live finding text still names exactly `.ci/scripts/test/gates/test-agent-session-archival.sh` and nothing else, so the fix is scoped correctly before touching anything.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Done, in progress 2026-09-23: writer a6fb2bd0c76e5508e dispatched and mid-implementation.

- [x] T2. Write `.ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py`.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Written, staged, confirmed on disk 2026-09-23. Port every one of the 15 bash functions listed below to a `def test_...(gate, tmp_path)` function, preserving the case each one proves (not just its name) and every "mirror" assertion (a refusal proven beside the same fixture succeeding once the blocking fact is fixed):

  1. `test_the_subject_and_its_tools_are_present` (`:89-94`) -- `GATE.is_file()`, git and python3 on PATH (git/python3 checks can drop: the harness itself needs both to run at all, so `shutil.which` guards read like `.ci/rediacc_ci/tests/gates/test_gate_plan_folders.py:73-76`'s `test_git_is_available_or_this_file_asserts_nothing`).
  2. `test_an_abandoned_directory_moves_and_leaves_nothing_behind` (`:98-114`) -- `--move deadbeef --label test-label` exits 0, prints `agent/deadbeef -> agent/archive/test-label/deadbeef`, old path gone, new `STATE.md` content intact, `git status --porcelain` shows `R  agent/deadbeef/STATE.md`.
  3. `test_the_promotion_reminder_is_printed_before_it_acts` (`:116-123`) -- output contains `promote anything in agent/RULES.md`.
  4. `test_a_reserved_name_is_refused_outright` (`:127-140`) -- `--move archive` exits 1, "reserved directory", `agent/archive` untouched; MIRROR: `--move deadbeef` on the same tree still succeeds.
  5. `test_every_reserved_name_is_refused_not_just_the_first` (`:142-152`) -- loop over `archive programs worklist reggate plans ledgers pr legacy`, each exits 1 with "reserved directory".
  6. `test_a_live_target_is_refused_without_force_and_moves_with_it` (`:154-168`) -- `--move live5678` exits 1, "still LIVE", directory untouched; MIRROR: `--move live5678 --force` succeeds and removes it.
  7. `test_a_dirty_target_is_refused_because_a_peer_may_be_writing` (`:170-187`) -- an uncommitted `NOTE.md` inside the target makes `--move` exit 1 with "race a live writer" and leaves the note; MIRROR: commit the note, the same directory now moves and the note travels with it.
  8. `test_an_occupied_archive_path_is_refused` (`:189-202`) -- pre-existing `agent/archive/test-label/deadbeef/` makes `--move` exit 1 with "already exists" and the occupant's content is untouched.
  9. `test_a_missing_directory_is_refused` (`:204-212`) -- `--move nosuchxx` exits 1, "does not exist".
  10. `test_move_without_a_target_is_a_setup_error_not_a_verdict` (`:214-222`) -- bare `--move` exits 2 (not 1) with "needs a session directory name".
  11. `test_check_and_status_write_nothing_at_all` (`:226-238`) -- run with no args, `--status`, `--selftest` in sequence; `agent/` file listing (name + size) and `git status --porcelain` are byte-identical before and after all three.
  12. `test_the_gate_fires_on_the_backlog_and_goes_green_once_it_is_archived` (`:240-254`) -- default run exits 1 naming `agent/deadbeef/ has been idle` and `--move deadbeef`; after that move, the same invocation exits 0 and reports `1 session director(ies)`.
  13. `test_an_empty_agent_tree_refuses_rather_than_passing` (`:256-265`) -- delete both session dirs, default run exits 77, "CANNOT RUN".
  14. `test_a_missing_archive_directory_refuses_rather_than_passing` (`:267-276`) -- delete `agent/archive`, default run exits 77, "nowhere to archive".
  15. `test_a_missing_oracle_refuses_rather_than_inventing_one` (`:278-287`) -- delete the `.claude` symlink, default run exits 77, "cannot import wl_store".

  Shared fixture helper `seed(root)` ports `test-agent-session-archival.sh (retired at 1ad63b448, ported to .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py; the site was lines 61-77)`: creates `agent/archive/`, `.ci/config/`, `agent/deadbeef/` (a `## SESSION deadbeef <34-days-ago ISO8601Z>` heading, well past 24h dead-horizon + 14-day grace), `agent/live5678/` (a `## SESSION live5678 <60s-ago>` heading), symlinks `.claude` to `paths.repo_root() / ".claude"` (the REAL one, not a copy -- this is the one property this port must not weaken), copies the real `.ci/config/agent-session-archival.json`, then `git init`/`config`/`add -A`/`commit`.
  Use `tmp_path` per pytest test rather than the bash file's `with_temp_dir`; pytest already isolates each test function.

  Use `harness.run([sys.executable, str(GATE), *argv], cwd=paths.repo_root(), env={"AGENT_SESSION_ARCHIVAL_ROOT": str(root)})` for every invocation (`GATE = paths.from_root(".ci", "scripts", "quality", "check_agent_session_archival.py")`).

  Header docstring should state, in this file's own words, what it adds beyond `agent_session_archival.py`'s pure-function port and beyond the gate's own `--selftest` -- i.e. restate the "WHAT THIS ADDS" section of the bash original's header (`test-agent-session-archival.sh (retired at 1ad63b448, ported to .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py; the site was lines 11-34)`) in the repo's own prose style, and note explicitly that it drives the CLI as a process against a real git tree with the REAL `.claude/` reachable, which is why it (like `gate-test:agent-session-archival` before it) is the one case in this file's family that needs a real filesystem and a real oracle rather than a fixture record.

- [x] T3. Confirmed independently 2026-09-23: `pytest .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py -q` -- 15 passed in 3.91s. Run the new file standalone and confirm all 15+ cases pass:
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
  ```
  PYTHONPATH=.ci python3 -m pytest .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py -v
  ```
  Done looks like: every `test_*` passes, and each prints at least one `gate.log_pass(...)`/assertion (the `gate` fixture's teardown in `conftest.py` raises on a green test with zero recorded controls, so a silently-vacuous port fails this step on its own).

- [x] T4. Done 2026-09-23. `dead=bool(known and known.dead)` at `.ci/scripts/quality/check_agent_session_archival.py:426` was replaced with `dead=True` for one run; the suite went `1 failed, 14 passed`, and the one failure was `test_a_live_target_is_refused_without_force_and_moves_with_it` ("expected 1, got 0"). The suite reds on a real regression and is not vacuous.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      NOTE ON STEP 3: `git checkout -- <path>` is refused by `.claude/hooks/chain-head.sh` (pre-bash) in this tree, so the plant was reverted by editing the line back, which is the repair-forward form and is safer here because that file carries another session's staged work.
      `git diff` against the index is empty afterwards and `git status` reports the file as `A ` again, so the revert is byte-exact; the re-run is 15 passed.
      Prove the suite can fail (a control, not a courtesy). Temporarily edit the real subject for one throwaway run and revert immediately:
  1. Make a one-line edit to `.ci/scripts/quality/check_agent_session_archival.py`'s `move()` (e.g. temporarily hardcode `dead=True` at `:426` regardless of `known`), or comment out the `if why:` refusal block at `:432-434`.
  2. Re-run T3's pytest command and confirm exactly the case(s) that rail protects now fail (e.g. `test_a_live_target_is_refused_without_force_and_moves_with_it`), and only those.
  3. `git diff -- .ci/scripts/quality/check_agent_session_archival.py` to confirm the only difference is the throwaway edit, then `git checkout -- .ci/scripts/quality/check_agent_session_archival.py` to discard it (this file is not part of this plan's scope; do not commit the plant).
  4. Re-run T3 and confirm green again.
  Done looks like: a recorded observation (in the plan's own closing note, not a committed file) that the new suite reds on a real regression and is not vacuous.

- [x] T5. Delete `.ci/scripts/test/gates/test-agent-session-archival.sh` from the tree and from the index
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Confirmed gone 2026-09-23 (`ls`: No such file or directory, neither staged nor untracked). (`git rm .ci/scripts/test/gates/test-agent-session-archival.sh` -- it is currently staged as a new file this session, so this both unstages and removes it). Confirm with `git status` that it no longer appears at all (neither staged nor untracked).

- [x] T6. Done 2026-09-23: the 15-line object plus its two comment lines removed, `git diff --stat` on `manifest.ts` reads `16 deletions(-)` and nothing else. The only `agent-session-archival` strings left in the file are `check:ci-agent-session-archival`'s own `id` and `run` at `:2026-2027`.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Remove the `gate-test:agent-session-archival` entry from `scripts/ci-runner/manifest.ts` (the whole object at `scripts/ci-runner/manifest.ts:4840-4854`, comment included, from the opening `{` through its matching `},`).
  Do not rewire it onto `check:ci-pytest` -- `check:ci-pytest`'s `paths:` already carries `.ci/rediacc_ci/**` (`scripts/ci-runner/manifest.ts:4783-4791`), the same retirement shape used for `gate-test:bws-rotate` (confirmed: no `bws-rotate` string appears anywhere in `manifest.ts`, `gates.lock.json`, `package.json` or `ci-quality.yml` after that retirement) and documented in `agent/plans/PLAN-plyr-css-on-demand-loading.md:117` ("a Python port does not get one: `scripts/ci-runner/manifest.ts` records that the standalone `gate-test:` entries for ported modules were RETIRED into `check:ci-pytest`... a second entry would schedule the same work twice").
  Leave `check:ci-agent-session-archival` (`scripts/ci-runner/manifest.ts:2026-2029`, `package.json:185`) completely untouched -- that is the still-bash-free production gate, unaffected by this change.

- [x] T7. Done 2026-09-23: `gen-gates-lock: wrote scripts/ci-runner/gates.lock.json (347 gate(s) in manifest file order)`, then `✓ scripts/ci-runner/gates.lock.json matches the manifest: 347 gate(s), same order.` The lock diff is `18 deletions(-)` and is exactly the removed block.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Regenerate the committed lock and verify it:
  ```
  npm run gen:gates-lock
  npm run check:ci-gates-lock
  ```
  Done looks like: `scripts/ci-runner/gates.lock.json`'s `gate-test:agent-session-archival` block (currently at `scripts/ci-runner/gates.lock.json:5113-5129`) is gone, and no other entries changed except whatever the generator normally touches. Do not hand-edit the lock file.

- [x] T8. Done 2026-09-23: `38 control(s) passed` and `✓ language policy: 267 bash file(s) ... 139 frozen (shrink-only, none added), 128 exempt by name across 18 allowlist entr(ies).` No NEW bash finding.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Re-run the language policy gate and confirm green:
  ```
  npm run check:ci-language-policy
  ```
  Done looks like: `38 control(s) passed` (or more) and no `NEW bash file(s)` finding.

- [x] T9. Done 2026-09-23: `34 control(s) passed`, against `CONTROL_FLOOR = 26`. The subject is untouched by this plan, so this is the no-op confirmation it was meant to be.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Run the gate's own selftest directly, to confirm nothing about the production subject moved:
  ```
  python3 .ci/scripts/quality/check_agent_session_archival.py --selftest
  ```
  Done looks like: the same `CONTROL_FLOOR = 26`-or-more controls reported passing as before this change (this file is untouched by this plan, so this is a no-op confirmation, not a fix).

- [x] T10. Done 2026-09-23: the new module is collected (`info: 1630 test function(s) on disk in .ci/rediacc_ci/tests/gates`, `info: corpus 7091 across 3 root(s) (floor 150)`) and its 15 cases are absent from every FAILED line.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      The gate itself exits 1 on 53 pre-existing failures in `test_build_build_json.py`, `test_gate_worklist_env_registry.py`, `test_quality_python_lint.py`, `test_quality_editorconfig.py`, `test_canonical_sys_path_hop.py`, `test_core_dockerx.py` and `test_env_create_e2e_env.py`. Grep for `test_gate_agent_session_archival` across the whole run log returns 0 matches, so none of them names this port.
      Run the full Python corpus and confirm the new module is collected and the whole suite is still green:
  ```
  npm run check:ci-pytest
  ```
  Done looks like: the per-root `info: N test function(s) on disk in .ci/rediacc_ci/tests/gates` count is higher by the number of functions added in T2, and the gate exits 0. No manual floor bump is needed anywhere -- `corpus_test_count`/`testpath_dirs` (`.ci/rediacc_ci/check_pytest.py:780-802`) derive the count from disk every run.

- [x] T11. Done 2026-09-23. `npm run lint` and `npm run typecheck` are both green (`typecheck-workers: 4 worker project(s) typechecked clean`), so the `manifest.ts` edit costs nothing on the TypeScript side.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      `npm run check:ci-python-lint` first named this port among 5 files needing `ruff format`; it was formatted, and the gate now names only 4 files, all of them other live work (`bws_env.py`, `test_core_bws_env.py`, `check_bws_rotation_notice.py`, `test-block_unproven_bulk_transform.py`), which are out of this plan's ownership.
      `npm run check:ci-python-types` reports 31 new findings across 15 files, all in `bws`, `hint-corpus` and `.claude/hooks/stop` work; grep for `test_gate_agent_session_archival` in its output returns 0.
      Run lint and types on the new file (and on `manifest.ts` if T6 touched formatting nearby):
  ```
  npm run check:ci-python-lint
  npm run check:ci-python-types
  npm run lint
  npm run typecheck
  ```
  Done looks like: all four green, with no new findings attributable to `test_gate_agent_session_archival.py` or the `manifest.ts` edit.

- [x] T12. Done 2026-09-23. `check:ci-gate-reachability-coverage` green: `probe agrees with all 337 manifest registrations`, with its own control firing. `check:ci-parity` green: `347 manifest gate(s); 2 workflow scope(s); 9 exempt; 5 battery test(s)` and `agree in both directions`.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      `check:ci-gate-manifest` exits 1 on 10 findings, all pre-existing and none naming anything this plan touched: 9 are `[tier]` timing drift on unrelated gates (`check:ci-toolchain-pins`, `check:ci-changed-selection` and 7 others) and 1 is `[leaf] check:ci-shell-lint declares paths but not its own leaf`.
      Run the manifest-consistency gates that watch removals like T6:
  ```
  npm run check:ci-gate-reachability-coverage
  npm run check:ci-parity
  npm run check:ci-gate-manifest
  ```
  Done looks like: all three green. (`check:ci-parity` is the one that would catch an orphaned reference to the deleted `.sh` path or a manifest entry pointing at a `leaves:` file that no longer exists.)

- [x] T13. Done 2026-09-23: the only hits are prose. This plan, `PLAN-tooling-transformation.md`, one header line in the port itself, and one comment in `scripts/gates/check-shape-duplication.ts:1851` recording the retirement. No wiring file (`.ts` object, `.json` entry, `.yml` step) names the path any more.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Confirm no stray reference to the deleted bash file remains anywhere in the tree:
  ```
  grep -rn "test-agent-session-archival.sh" . --include='*.ts' --include='*.json' --include='*.py' --include='*.md' --include='*.yml' 2>/dev/null
  ```
  Done looks like: zero matches (or only this plan file itself, which is expected and fine).

- [x] T14. Done 2026-09-23: `Quality-gate tests: 5 passed, 0 failed (86 assertions)`, `schedule: lock, jobs: 8, 5 test(s)`, exit 0. The step still has five bash gate-tests riding it, so the retirement orphaned nothing.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Run the shared "Quality-gate unit tests" battery locally to confirm the retirement didn't orphan the CI step it rode on:
  ```
  npm run check:ci-quality-gates
  ```
  Done looks like: green. (`gate-test:agent-session-archival` was one of several `gate-test:*` entries sharing the hand-written `Quality-gate unit tests` step in `.github/workflows/ci-quality.yml:2344`; six other `gate-test:*` entries remain wired to the same step, so removing this one does not orphan it.)

- [x] T15. Done 2026-09-23: `check:ci-language-policy` re-run after T6/T7 is green at `38 control(s) passed` with no NEW bash finding, and this plan's `Status:` is now `done`. The tree is staged by name and left uncommitted, per the session default.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
      Final full check: `npm run check:ci-language-policy` once more (belt and suspenders after T6/T7), then hand this plan to CI via the normal commit/PR flow. Update this plan's `Status:` line to `done` with a one-line summary of what actually ran green, following the convention in `agent/plans/PLAN-fix-python-lint-violations.md`.

## What this plan deliberately does not touch

- `.ci/rediacc_ci/quality/agent_session_archival.py`, `.ci/scripts/quality/check_agent_session_archival.py`, `.ci/config/agent-session-archival.json`, `.ci/rediacc_ci/tests/test_quality_agent_session_archival.py` -- all already staged by the other piece of work this session, already Python, out of scope here except as read-only context.
- `agent/plans/PLAN-agent-session-archival.md` -- the original feature plan (Status: done), unrelated to this language-policy remediation.
- The `check:ci-agent-session-archival` production gate's manifest entry (`scripts/ci-runner/manifest.ts:2026-2029`) -- unaffected; only the standalone `gate-test:` entry is retired.

### Critical Files for Implementation
- .ci/scripts/test/gates/test-agent-session-archival.sh
- .ci/rediacc_ci/tests/gates/test_gate_agent_session_archival.py
- .ci/rediacc_ci/tests/gates/test_gate_plan_folders.py
- .ci/scripts/quality/check_agent_session_archival.py
- scripts/ci-runner/manifest.ts
