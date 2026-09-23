# PLAN: Fix the two remaining check:ci-python-lint violations

Status: done 2026-09-22 -- all 5 boxes done, check:ci-python-lint fully green tree-wide (1103 files, ruff check + format + shebang/mode agreement).
Owner: d778be9d
First-Seen: 2026-09-22
Updated: 2026-09-22

## Why

`check:ci-python-lint` (`gate: true`) is red with 19 findings, none in files this session is actively editing: 7 ISC004 (unparenthesized implicit string concatenation) in `.ci/rediacc_ci/tests/test_core_release_age.py`, and 12 S101 (bare `assert`) in `.ci/rediacc_ci/tests/gates/test_gate_go_deps_probe_failure.py`.

**ISC004** is a real, deliberate multi-line string concatenation ruff cannot safely auto-wrap (`--fix` alone does not touch it; `--unsafe-fixes` does, and the diff is genuinely just adding parentheses).

**S101** is a glob-scoping bug, not a real finding. `pyproject.toml:155`'s per-file-ignore for bare `assert` (`"**/tests/test_*.py"`) requires the file to sit directly inside a directory literally named `tests`, so it misses everything one level deeper.
`pyproject.toml:359-363`'s own `testpaths` already lists `.ci/rediacc_ci/tests/gates` as a real pytest root beside `.ci/rediacc_ci/tests` and `.claude/rediacc_hooks/tests`, and `test_gate_go_deps_probe_failure.py` (`import pytest` at line 31, six `def test_*` functions) is genuinely pytest-collected there, so its bare `assert`s DO get pytest's rewriting -- the same fact the existing S101 exemption's own reasoning already rests on, just not reaching this file.
Verified: `find . -type d -name tests` outside `node_modules`/`private`/`.ci/cache` shows exactly two real Python pytest roots (`.ci/rediacc_ci/tests`, `.claude/rediacc_hooks/tests`), both already three-point-wired into `testpaths`; `find .ci/rediacc_ci/tests -mindepth 2 -name 'test_*.py' | wc -l` = 160, all under `tests/gates/`, all pytest-collected the same way.
`.claude/rediacc_hooks/tests` itself has no nested subdirectories, so the gap is confined to one place.

## Tasks

- [x] T1 In `.ci/rediacc_ci/tests/test_core_release_age.py`, wrap each of the 7 implicitly-concatenated string pairs in parentheses (mechanical, `ruff check --fix --unsafe-fixes` then a byte-diff review, since ruff itself can apply this one safely once told to).
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
    (done) 2026-09-22: `ruff check --fix --unsafe-fixes` applied all 7, diff reviewed (pure parenthesization, no semantic change), `ruff format` applied after for correct indentation.
- [x] T2 Widen `pyproject.toml:155`'s per-file-ignore glob from `"**/tests/test_*.py"` to `"**/tests/**/test_*.py"`, with a short comment noting the `tests/gates/` case this now covers and that both are real pytest roots per `testpaths`.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
    (done) 2026-09-22: `pyproject.toml:154-161`, comment explains the one-level-deeper gap and cites `testpaths`.
- [x] T3 Run `ruff check .ci/rediacc_ci/tests/test_core_release_age.py .ci/rediacc_ci/tests/gates/test_gate_go_deps_probe_failure.py` -- 0 findings.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
    (done) 2026-09-22: `All checks passed!`
- [x] T4 Run `npm run check:ci-python-lint` on the whole tree -- confirm green, and confirm the widened glob did not newly exempt anything that shouldn't be (spot-check that no non-pytest gate script matches `**/tests/**/test_*.py`).
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
    (done) 2026-09-22: green, `1103 Python file(s) pass ruff lint and format (+ 1099 checked for shebang/mode agreement)`. Also fixed 17 files' pre-existing format drift and 2 files' git-mode/shebang mismatch found while re-running this gate, unrelated to this plan's own 2 files but blocking the same gate.
- [x] T5 Run the two files' own test suites (`pytest .ci/rediacc_ci/tests/test_core_release_age.py .ci/rediacc_ci/tests/gates/test_gate_go_deps_probe_failure.py`) to confirm the parenthesization changed no behavior.
    (ticked) 2026-09-23T11:19:17Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
    (done) 2026-09-22: `56 passed`.
