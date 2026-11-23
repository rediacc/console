# PLAN: Silent failure sweep -- a quality script refuses a flag it does not know, and a failed Stop hook read names its failure instead of reading as "no data"

Status: approved
Depends-On: no-dep -- SF4-SF6 wait on PLAN-tooling-speed.md SP1, SP2, SP3 and SP5 at box level, and SF7 waits on lease commits that have not landed yet; both are named under Ordering
Priority: P1 -- a mistyped gate flag exits 0 and does nothing, and a failed Stop hook read looks the same as "nothing to report". In both cases a success is reported that nothing checked.
Concurrency: parallel -- SF1 edits only gate argument handling, and SF2 and SF3 edit Stop hook files that do not overlap; SF4-SF7 wait for the live writers that hold their files
Owns: agent/plans/PLAN-silent-failure-sweep.md, .ci/rediacc_ci/gate_args.py, .ci/scripts/quality/**, .ci/rediacc_ci/quality/** (module mains, gate_argv.py, swallowed_failures.py), .ci/rediacc_ci/tests/test_gate_args*.py, .ci/rediacc_ci/tests/test_quality_gate_argv*.py, .ci/rediacc_ci/tests/gates/test_gate_gate_argv.py, .ci/rediacc_ci/tests/test_quality_swallowed_failures.py, .ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py, .ci/policy/swallowed-except-baseline.json, package.json (one gate entry, through gate:bind), scripts/ci-runner/manifest.ts (one gate entry, through gate:bind), scripts/ci-runner/gates.lock.json (one gate entry, through gate:bind), .claude/hooks/stop/wl_checks.py, .claude/hooks/stop/wl_admit.py, .claude/hooks/stop/wl_backlog.py, .claude/hooks/stop/wl_benchblock.py, .claude/hooks/stop/wl_checklist.py, .claude/hooks/stop/wl_ci.py, .claude/hooks/stop/wl_civerdict.py, .claude/hooks/stop/wl_handover.py, .claude/hooks/stop/wl_hints.py, .claude/hooks/stop/wl_lessons.py, .claude/hooks/stop/wl_liveness.py, .claude/hooks/stop/wl_lkg.py, .claude/hooks/stop/wl_planenforce.py, .claude/hooks/stop/wl_planfile.py, .claude/hooks/stop/wl_reggate.py, .claude/hooks/stop/wl_renettests.py, .claude/hooks/stop/wl_roster.py, .claude/hooks/stop/wl_ruling.py, .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_core.py, .claude/hooks/stop/wl_review.py, .claude/hooks/stop/wl_schedred.py, .claude/hooks/stop/wl_histfirst.py, .claude/hooks/stop/wl_resprofile.py, .claude/hooks/stop/worklist.py, .claude/hooks/stop/wl_stack.py, .claude/hooks/stop/wl_bgsweep.py, .claude/rediacc_hooks/tests/test_wl_named_reads*.py
First-Seen: 2026-11-23
Owner: ace763dd
Updated: 2026-11-23

## Ask

Operator /ask, 2026-11-23: "One plan this branch but start in parallel immediately". This followed a read-only sweep that found two classes of silent failure: (A) quality scripts that ignore an argument they do not know, and (B) broad `except Exception` handlers in the Stop hook that return an empty default without naming the failure. Writers SF1, SF2 and SF3 started at once. This plan records them and schedules the rest.

## Context (checked against the 1121-1 tip 85f5d7f514, 2026-11-23)

Class A: quality scripts ignore an unknown argument.

1. The trigger: `npm run check:ci-record-paths -- --update` exited 0 and did nothing. At the tip, `main` in `.ci/scripts/quality/check_record_paths.py:1788` reads argv through `_flag`, which only looks up the names it knows. Lease commit f5f6574e60 (not on 1121-1 yet) adds `SWITCHES`, `VALUED` and a `parse_args`. That function exits 2 naming the argument and the accepted flags, and it comes with three selftest controls.
2. The counts. The sweep found 146 scripts that read `sys.argv`: 8 refuse an unknown argument and 138 ignore it. A static re-read of the tip finds 175 entry points: the 174 `check_*.py` files plus `shape_cluster_diff.py` (`_cipath.py` is the path shim, not an entry point). 25 of them refuse:
   - 14 use argparse, and none of them uses `parse_known_args`.
   - 8 hand argv to a module `main` that refuses: cli_contract, gh_retry_reads, inline_suppressions, model_invocable_commands, python_types, region_consistency, silent_failure_patterns and swallowed_failures (for example `.ci/rediacc_ci/quality/swallowed_failures.py:455-470`).
   - 3 refuse inline: `.ci/scripts/quality/check_operator_rulings.py:150-158`, `.ci/scripts/quality/check_plan_feedback.py:282-285` and `.ci/scripts/quality/check_plan_bindings.py:353-356`. The last two refuse only unknown arguments that start with `--`.

   That leaves about 150 that ignore an unknown argument. 132 read argv loosely. 18 never read it at all, so every argument is dropped (for example `.ci/scripts/quality/check_docker_npm_pins.py:295` and `.ci/scripts/quality/check_hint_corpus.py:431`, where `main()` takes no argv). The sweep's 138 missed those 18 and counted five delegators that do refuse. SF10 measures with the count from SF8's gate, not with either hand count.
3. Where the argument handling lives. 105 entry points are shims of the form `raise SystemExit(<module>.main(sys.argv[1:]))` into `.ci/rediacc_ci` (`.ci/scripts/quality/_cipath.py` explains why the shim exists). For these, the argument handling is the module's `main`. For example, `.ci/rediacc_ci/quality/npmrc.py:245-252` catches `--selftest` and ignores everything else. Adoption therefore has to edit module mains as well as entry points.
4. Shared helpers. Shared CI Python lives in `.ci/rediacc_ci`: `rediacc_ci/controls.py` is the counted-controls runner, and `.ci/rediacc_ci/core/allowlist.py:533` holds `validate_reason`. Neither `.ci/scripts/lib` (only `toolchain.sh`) nor `.ci/scripts/quality/lib` (only `check_sanctioned_registry.py`) is a Python helper package.
5. Callers pass arguments today. `package.json` registers three quality gates with arguments: check:ci-turnstile-drift, check:ci-region-consistency and check:ci-tutorial-healthcheck-headroom. `scripts/ci-runner/manifest.ts`, the workflows and the hooks call others. If a caller passes a flag that a script ignores today, that call goes red on the day the script starts refusing it.

Class B: Stop hook handlers that return an empty value without naming the failure.

6. The count uses the D7 rule: a handler that catches `Exception`, `BaseException` or everything, does not re-raise, does not use the bound exception, and ends in `return` of an empty value or None, `pass`, `continue`, or assignment of an empty value. Over `.claude/hooks/stop/*.py`, excluding `test-*.py`, it finds 104 sites in 27 files:
   - wl_checks 38, worklist 7
   - wl_review, wl_roster, wl_schedred, wl_stack and wl_store 5 each
   - wl_planfile 4
   - wl_ci and wl_lessons 3 each
   - wl_bgsweep, wl_checklist, wl_civerdict, wl_lkg, wl_planenforce, wl_reggate and wl_resprofile 2 each
   - one each in wl_admit, wl_backlog, wl_benchblock, wl_core, wl_handover, wl_hints, wl_histfirst, wl_liveness, wl_renettests and wl_ruling

   The sweep's 80 sites in 23 files (wl_checks 36) used a narrower rule. A stricter rule, counting only handlers that make no call at all, gives 89 in 26 files (wl_checks 34). SF9's rule is the one counted before and after.
7. Examples:
   - `.claude/hooks/stop/wl_checks.py:84`: a failed `import wl_ruling` becomes `None`.
   - `.claude/hooks/stop/wl_checks.py:3946-3955`: three liveness reads become `[]`, `[]` and `{}`, and the stop then certifies a pure wait.
   - `.claude/hooks/stop/wl_checks.py:690`: a failed fold becomes `""`.
8. The cd-done latch. `.claude/hooks/stop/wl_checks.py:3393-3395` writes `state_doc["landing"] = {"cd_done": sha}` before it checks whether the notice is empty. `wl_stack.notify_line` (`.claude/hooks/stop/wl_stack.py:479-483`) returns `""` when the landing record read raises. So one failed read uses up the latch for that sha, and the development session is never sent the cd-done message.
9. `wl_core.landing_record` (`.claude/hooks/stop/wl_core.py:398-417`) turns an unreadable or malformed record into `None`, the same answer as having no record. The unreadable case is the `(OSError, ValueError)` handler at :405-406, and the malformed case is the shape checks at :407-415. `commit_policy.read_landing_record` (`.claude/rediacc_hooks/commit_policy.py:297`) already returns `(record, problem)`. This site is not in the count in item 6 because its handler is narrow.
10. Already fixed. wl_stack.py and landing_promote.py were fixed by 8cd21a2a34 and 83f2247313 (lease commits, not on 1121-1 yet), after f2893b51ee, the fix for review e943d92e.1 (on 1121-1). The pattern: a typed `StackReadError` is raised by the reader and answered as an advisory under the existing `landing-stack` key, and nothing new blocks. Two broad handlers in the fixed wl_stack.py are still silent:
    - `main_checkout_tasks` (`except Exception: return []`)
    - `notify_line` (`return ""`), which causes item 8
11. Existing gates.
    - check:ci-silent-failures (`.ci/rediacc_ci/quality/silent_failure_patterns.py`, `SCAN_DIRS` at :80) scans shell under pipefail for pipelines that are guarded too little.
    - check:ci-swallowed-failures (`.ci/rediacc_ci/quality/swallowed_failures.py`) catches the opposite case: a probe failure folded into a value that looks the same as an empty result. It scans shell gates (`DEFAULT_SCAN_DIRS` at :142) and accepts a `# swallowed-failure-ok: <reason>` waiver (`WAIVER_RE` at :174), held to `validate_reason`. Its bash twin was deleted in 3d027a717f, so changing its verdict breaks no shadow ledger.

    Class B is the swallowed-failures class, written in Python.
12. The advisory channel is `outq_add` (`.claude/hooks/stop/wl_checks.py:1279`). Every key it queues needs an entry in `.claude/config/effort.json`, enforced by the effort-table rule of `npm run check:ci-plan-record`.

## Design

D1. **One parser.** A shared module sits beside `controls.py` under `.ci/rediacc_ci/`. This plan calls it `gate_args`; SF1 fixes the name.
- Signature: `parse(argv, prog, switches=(), valued=(), positional=None)`. The accepted flags are literal tuples, so a gate can read them without running the script.
- An unknown argument, or a valued flag with no value, prints one stderr line naming the argument and the accepted set, then exits 2 before any work. The message follows the shape of f5f6574e60.
- `--help` and `-h` print the accepted set and exit 0.
- A script that takes no arguments still calls `parse` with nothing declared, so any argument is refused.

D2. **Where the call goes.** `parse` is the first statement of the function that owns argv: the module `main` for a shim, and the script's own `main` otherwise. The shims themselves do not change. argparse without `parse_known_args` is the one other accepted form, because it already refuses with exit 2 and names the argument. Those scripts are not rewritten.

D3. **Callers before refusal.** Before a script starts refusing, every call to it is read: `package.json`, `scripts/ci-runner/manifest.ts`, `.github/workflows`, the `.claude` hooks and other scripts. Each argument a caller passes is either declared by the script or fixed at the caller in the same commit.

D4. **The class A gate.** the new gate-argv gate is added through a `---- gate ----` header and `npm run gate:bind`. It checks every entry point under `.ci/scripts/quality`:
- The function that owns argv must reach `gate_args.parse`, or argparse without `parse_known_args`.
- It refuses:
  - a `sys.argv` read anywhere except the shim's `main(sys.argv[1:])`
  - a hand scan of argv (`in argv`, `argv.index`)
  - a `main` that never reads argv
- It checks the arguments of every registered call against the script's declared tuples.
- Controls: a planted fixture for each refusal and for each accepted form, plus a floor that refuses a run scanning fewer than 150 entry points.

D5. **Class B: name the failure, add no block.** A broad handler in a Stop hook module does one of three things:
- raises a typed read error that its caller answers, as `StackReadError` does;
- returns a value that carries the reason, as `(value, problem)` does in `wl_stack._promote_dirt`;
- adds the reason to the text of the check that already speaks on that path, whether as a block or as an advisory under its existing key.

There is no new `vadd` key. A new `outq_add` key is allowed only when no existing key speaks on that path, and it must come with its `effort.json` `advise` entry. Some handlers are correct to treat absence as the answer: an optional import with a real fallback, or best-effort cleanup. Those narrow the exception type, or carry the waiver with a reason that passes `validate_reason`.

D6. **The two named defects.**
- The cd-done latch is written only when the notice is not empty. When it is empty, the landing step names why the notice could not be built, and the next stop tries again.
- `wl_stack.notify_line` returns its reason, so that text can name it (SF7).
- `wl_core.landing_record` reads through `commit_policy.read_landing_record`. A missing file stays `None` without comment. A defective record still binds nothing, but the problem is handed to the caller, which names it once.

D7. **The class B gate.** check:ci-swallowed-failures gains a Python mode:
- It scans `.claude/hooks/stop/*.py` (excluding `test-*.py`) with the rule from Context 6.
- It uses the same waiver marker, held to the same `validate_reason` bar.
- It has its own scan-seam environment variable and its own floor, refusing a run that scans fewer than 60 modules (89 exist today).
- It holds a ratchet, `.ci/policy/swallowed-except-baseline.json`, mapping each file to its allowed count, for files whose box has not landed yet. A file above its row is red. A file below its row is also red, and the message says to lower the row. A file with no row allows 0. When every box has landed, the baseline is `{}`.

## Ordering against other live work

- SF3 edits wl_checks.py, which PLAN-tooling-speed.md also owns. Add SF3 to the list of wl_checks.py boxes that SP3 lands after.
- SF4 waits on PLAN-tooling-speed.md SP1 (wl_store.py, wl_core.py).
- SF5 waits on SP2 (wl_review.py, wl_schedred.py, wl_histfirst.py) and SP5 (wl_resprofile.py).
- SF6 waits on SP3 (worklist.py).
- SF7 waits for 8cd21a2a34 and 83f2247313 to land on 1121-1.
- SF1 rebases over f5f6574e60, which edits check_record_paths.py.
- Several SF2 files are also owned by other plans:
  - wl_reggate.py: PLAN-tooling-speed.md SP2 and PLAN-reggate-debt-collection.md
  - wl_hints.py: PLAN-weekly-lessons.md W2
  - wl_roster.py, wl_ci.py and wl_handover.py: PLAN-simple-two-tree-loop.md

  These edits do not overlap, so whichever change lands second rebases.

## Risks

- **A caller that passes an ignored flag goes red.** D3 makes reading the callers part of adoption, and SF8's check of every registered call keeps it true afterwards.
- **SF1's brief may stop at `.ci/scripts/quality`.** About 97 of the scripts that still ignore arguments do their parsing in a module `main` under `.ci/rediacc_ci` (Context 3). SF8's gate stays red until those mains adopt the parser too. Before ticking SF1, the lead checks its commits cover them; if they do not, the rest becomes a follow-up box.
- **Exit 2 already means "cannot see inputs" for some gates.** The refusal names the argument, so the two cases are told apart by their message. CI treats both as red.
- **Naming every failure makes noise.** D5 puts the reason in text that already speaks, and outq deduplicates by signature, so a repeated failure shows once per stop and adds no block.
- **The AST rule flags a legitimate empty default.** Such a site gets the waiver with a reason of 30 or more characters, and SF10 lists every waiver as a survivor with that reason.
- **Registering a gate touches shared files** (`package.json`, `manifest.ts`, `gates.lock.json`). PLAN-tooling-speed.md SP7 is editing the same files in its own lease. `gate:bind` regenerates them, so the rebase is mechanical.

## Tasks

- [x] SF1 [writer] Class A parser and adoption (D1-D3). The `gate_args` module is adopted by every entry point under `.ci/scripts/quality` that ignores an unknown argument, and by the module `main` each shim hands argv to. Callers' arguments are read first and declared or fixed. check_record_paths keeps the refusal and the three controls from f5f6574e60, now through `gate_args`.
  In flight: writer started 2026-11-23 on the operator's "start in parallel immediately"; tick when its commits land on 1121-1 with the Accept evidence.
  Owns: .ci/rediacc_ci/gate_args.py, .ci/scripts/quality/**, .ci/rediacc_ci/quality/** (module mains only), .ci/rediacc_ci/tests/test_gate_args*.py
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_gate_args.py` rc 0, with these tests:
  - an unknown switch exits 2 and names the argument and the accepted set
  - a valued flag with no value is refused
  - `--help` exits 0
  - a declared positional argument is accepted and an undeclared one is refused
  - a script with nothing declared refuses any argument
    (ticked) 2026-11-23T08:06:18Z by ace763dd: commit:8ad54bea68 fileline:.ci/scripts/quality/_gate_args.py:1 -- shared parser adopted by 147 quality entry points (unknown flag exits 2 naming it); test_gate_quality_argv_helper.py + test_gate_quality_argv_adoption.py rc 0 (185 passed); the box named test_gate_args.py, the tests landed under these names

  Also: `npm run -s check:ci-record-paths -- --update` and `npm run -s check:ci-npmrc -- --update` each exit 2 naming `--update`, and a bare run of each still exits 0.
- [x] SF2 [writer] Class B (D5) in wl_admit, wl_backlog, wl_benchblock, wl_checklist, wl_ci, wl_civerdict, wl_handover, wl_hints, wl_lessons, wl_liveness, wl_lkg, wl_planenforce, wl_planfile, wl_reggate, wl_renettests, wl_roster and wl_ruling. That is 33 sites by the Context 6 rule. Each one names its failure through an existing return value, error or check text, and none adds a block.
  In flight: writer started 2026-11-23 on the operator's "start in parallel immediately"; tick when its commits land on 1121-1 with the Accept evidence.
  Owns: the 17 `.claude/hooks/stop/wl_*.py` files named above, .claude/rediacc_hooks/tests/test_wl_named_reads*.py
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_named_reads.py` rc 0, with:
  - one control per changed site that forces the read to raise and asserts the reason appears in the stop text or the return value
  - one silent control per file, showing that a clean read adds no text
    (ticked) 2026-11-23T08:06:19Z by ace763dd: commit:91ecf84b92 fileline:.claude/rediacc_hooks/tests/test_wl_silent_b.py:1 -- 17 stop-hook modules name their read failures; test_wl_silent_a.py + test_wl_silent_b.py rc 0 (43 passed); the box named test_wl_named_reads.py, the tests landed under these names

  Also: the whole `test_wl_*` family passes; `npm run check:ci-plan-record` rc 0; `git diff` adds no `block` entry to `.claude/config/effort.json`. Once SF9 has landed, its count over these 17 files is 0, or each survivor carries a waiver.
- [x] SF3 [writer] Class B (D5, D6) in wl_checks.py: all 38 sites by the Context 6 rule (36 by the sweep's rule), plus the cd-done latch at `.claude/hooks/stop/wl_checks.py:3393-3395`, which is written only when the notice is not empty. When the notice is empty, the landing step names that it could not be built, and the next stop tries again.
  In flight: writer started 2026-11-23 on the operator's "start in parallel immediately"; tick when its commits land on 1121-1 with the Accept evidence.
  Owns: .claude/hooks/stop/wl_checks.py, .claude/rediacc_hooks/tests/test_wl_named_reads_checks.py
  Depends on: none.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_named_reads_checks.py` rc 0, with:
  - per-site controls as in SF2, including the `import wl_ruling` fallback at :84 and the liveness reads at :3946-3955
  - a cd-done test: with `notify_line` returning `""`, the latch is not written and the step text names the missing notice; the control shows a real notice is latched once and not repeated
    (ticked) 2026-11-23T08:06:21Z by ace763dd: commit:cc68eafa0a fileline:.claude/rediacc_hooks/tests/test_wl_checks_silent_failure.py:1 -- wl_checks.py names 46 read failures via check-read-failed, cd-done latch only on a non-empty notice; test_wl_checks_silent_failure.py rc 0 (39 passed)

  Also: the whole `test_wl_*` family passes, and `npm run check:ci-plan-record` rc 0.
- [ ] SF4 [writer] Class B (D5, D6) in wl_store.py (5 sites) and wl_core.py (1 site at :938). `landing_record` (`.claude/hooks/stop/wl_core.py:398-417`) reads through `commit_policy.read_landing_record`: a missing file stays `None`, and a defective record hands its problem to the caller, which names it once.
  Owns: .claude/hooks/stop/wl_store.py, .claude/hooks/stop/wl_core.py, .claude/rediacc_hooks/tests/test_wl_named_reads_core.py
  Depends on: PLAN-tooling-speed.md SP1.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_named_reads_core.py` rc 0, with:
  - a malformed landing record named in the caller's text
  - a missing record that stays silent
  - per-site controls for wl_store

  Also: if SF9 has landed, this commit deletes the two files' rows from `.ci/policy/swallowed-except-baseline.json`, and `npm run -s check:ci-swallowed-failures` stays rc 0.
- [ ] SF5 [writer] Class B (D5) in wl_review.py (5), wl_schedred.py (5), wl_histfirst.py (1) and wl_resprofile.py (2).
  Owns: .claude/hooks/stop/wl_review.py, .claude/hooks/stop/wl_schedred.py, .claude/hooks/stop/wl_histfirst.py, .claude/hooks/stop/wl_resprofile.py, .claude/rediacc_hooks/tests/test_wl_named_reads_git.py
  Depends on: PLAN-tooling-speed.md SP2 and SP5.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_named_reads_git.py` rc 0, with per-site controls and a silent control per file; baseline rows deleted as in SF4.
- [ ] SF6 [writer] Class B (D5) in worklist.py (7 sites). Once SP3 has moved the CLI verbs, each site is fixed in whichever of worklist.py or wl_cli.py now holds it.
  Owns: .claude/hooks/stop/worklist.py, .claude/rediacc_hooks/tests/test_wl_named_reads_cli.py
  Depends on: PLAN-tooling-speed.md SP3.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_named_reads_cli.py` rc 0; baseline row deleted as in SF4.
- [ ] SF7 [writer] Class B (D5, D6) in the two wl_stack.py handlers left after the lease fix, and in wl_bgsweep.py (2 sites, at `.claude/hooks/stop/wl_bgsweep.py:443` and `:531` at the tip).
  - `main_checkout_tasks` stops returning `[]` on a raise.
  - `notify_line` returns its reason, which SF3's landing text names.
  Owns: .claude/hooks/stop/wl_stack.py, .claude/hooks/stop/wl_bgsweep.py, .claude/rediacc_hooks/tests/test_wl_named_reads_stack.py
  Depends on: 8cd21a2a34 and 83f2247313 on 1121-1; SF3.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .claude/rediacc_hooks/tests/test_wl_named_reads_stack.py` rc 0 and `python3 .claude/hooks/stop/test-landing-stack.py` rc 0. One test feeds an unreadable landing record and asserts the cd-done step names the record's problem. Baseline rows deleted as in SF4.
- [ ] SF8 [writer] The class A gate, check:ci-gate-argv (D4). The entry point `.ci/scripts/quality/check_gate_argv.py` uses `gate_args` itself and is registered through its `---- gate ----` header and `npm run gate:bind`. The module is `.ci/rediacc_ci/quality/gate_argv.py`. If SF1's commits already carry this gate, tick SF8 with SF1's sha.
  Owns: .ci/scripts/quality/check_gate_argv.py, .ci/rediacc_ci/quality/gate_argv.py, .ci/rediacc_ci/tests/test_quality_gate_argv.py, .ci/rediacc_ci/tests/gates/test_gate_gate_argv.py, package.json, scripts/ci-runner/manifest.ts, scripts/ci-runner/gates.lock.json
  Depends on: SF1.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_quality_gate_argv.py .ci/rediacc_ci/tests/gates/test_gate_gate_argv.py` rc 0. The controls:
  - planted red cases: `if "--x" in sys.argv`, a `main()` that never reads argv, `parse_known_args`, and a registered call passing an undeclared flag
  - planted green cases: the shared parser and plain argparse
  - a floor control: a run scanning fewer than 150 entry points is refused

  Also: the new gate-argv gate rc 0 on the tree, and `npm run check:ci-gates-lock` and `npm run check:ci-parity` rc 0.
- [ ] SF9 [writer] The class B regression gate (D7). check:ci-swallowed-failures gains its Python mode over `.claude/hooks/stop/*.py` with the Context 6 rule, the existing `# swallowed-failure-ok:` waiver held to `validate_reason`, a scan-seam environment variable, a 60-module floor, and the ratchet `.ci/policy/swallowed-except-baseline.json` seeded with the counts left by whichever of SF4-SF7 have not landed. The shell mode's verdict does not change.
  Owns: .ci/rediacc_ci/quality/swallowed_failures.py, .ci/scripts/quality/check_swallowed_failures.py, .ci/policy/swallowed-except-baseline.json, .ci/rediacc_ci/tests/test_quality_swallowed_failures.py, .ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py
  Depends on: SF2, SF3.
  Accept: `PYTHONPATH=.ci .ci/cache/toolchain/uv-tools/bin/pytest -q .ci/rediacc_ci/tests/test_quality_swallowed_failures.py .ci/rediacc_ci/tests/gates/test_gate_swallowed_failures.py` rc 0. The controls:
  - planted red cases: `except Exception: return []`, `except: pass`, and a handler that binds `exc` but never uses it
  - planted green cases: a re-raise, a handler that uses `exc` in returned text, and a waived handler with a 30+ character reason
  - a waiver with a short reason is red
  - ratchet: a file above its baseline row is red, and a file below its row is red with a "lower the row" message
  - a run scanning fewer than 60 modules is refused
  - the existing shell controls are unchanged

  Also: `npm run -s check:ci-swallowed-failures` rc 0 on the tree.
- [ ] SF10 [lead] Measure both classes after SF1-SF9.
  Before: class A 138 by the sweep and about 150 by the static read in Context 2; class B 80 by the sweep and 104 by the Context 6 rule.
  Accept:
  - the new gate-argv gate rc 0, reporting 0 entry points that bypass the parser.
  - This loop prints no SURVIVOR line, or every SURVIVOR is named here with its reason: `for f in .ci/scripts/quality/check_*.py .ci/scripts/quality/shape_cluster_diff.py; do err=$(timeout 60 python3 "$f" --sf-no-such-flag 2>&1 >/dev/null); rc=$?; { [ "$rc" = 2 ] && printf '%s' "$err" | grep -q -- --sf-no-such-flag; } || echo "SURVIVOR $f rc=$rc"; done`
  - `npm run -s check:ci-swallowed-failures` rc 0 with `.ci/policy/swallowed-except-baseline.json` equal to `{}`.
  - The after counts (target 0 and 0) are quoted in the tick evidence, with every waived handler listed by file:line and reason.

### Critical Files for Implementation
- .ci/rediacc_ci/gate_args.py (new, SF1)
- .ci/scripts/quality/check_record_paths.py
- .ci/rediacc_ci/quality/swallowed_failures.py
- .claude/hooks/stop/wl_checks.py
- .claude/hooks/stop/wl_core.py
