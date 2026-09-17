#!/usr/bin/env python3
"""Entry point for the ported Python lint + format gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.python_lint`, which pytest and the
port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.python_lint` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-python-lint.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `emit:`, no `blocker:`, no `id:`, no `run:`, no
`kind:`, no `lane:`, no `why:`.

NO `lane:` IS CORRECT, and it is not an omission. This gate's step sits INSIDE the `# >>> gate-bind` region of `quality-static` (ci-quality.yml:199-346), so the lane is read off the region the step already lives in rather than declared.
The twin ran that way; nothing about the lane moves here.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) strips the `check_` prefix and maps `_` to `-`, so this basename derives `check:ci-python-lint`, which is the manifest id. Verified by calling `bind()` rather than by reading the rule.

`selftest: true` is inert for a `.py` gate (`headerLines` emits that field only
for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and
because `python_lint.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files rather than by reading them. `bind()` unions declared needs with
`inferredNeeds(source)`; the twin infers `[]` and this two-import entry point
infers `[]`, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both sides resolve to the empty set `needs: none` declares.

PINNED BY PATH IN TWO HARNESSES, and the two rows take DIFFERENT arms.

  - `.ci/scripts/test/gates/test-gate-anti-vacuity.sh:110` registers
    `".ci/scripts/quality/check-python-lint.sh|VACUOUS INPUT"` and RUNS that
    path against an empty tree, asserting the diagnostic. That is a
    run-in-place row, so if it is ever repointed it must be repointed at THIS
    ENTRY POINT, never at the module.
  - `.ci/rediacc_ci/tests/test_core_dockerx.py:562` reads the same path as TEXT
    and regex-matches a whole line of the form `exit <digits>`, asserting the
    cannot-run code 77 is among them. That is a behavioural needle in the
    SOURCE, and the needle is not in this three-line shim, so that row must be
    repointed at the MODULE `.ci/rediacc_ci/quality/python_lint.py` if it is
    repointed at all. AND ITS PATTERN MUST MOVE WITH IT, measured rather than
    assumed: the twin carries a bare `exit 77` at line 191, while the module
    writes `EXIT_CANNOT_RUN = 77` at python_lint.py:194 and never emits that
    line shape at all. A repoint that kept the old pattern would find nothing,
    which that test does catch -- it asserts the match set is non-empty and
    says "the pattern has rotted" -- but a writer should not need the harness
    to discover it.
  - `.ci/rediacc_ci/tests/test_quality_python_lint.py:46` sets
    `TWIN = ".ci/scripts/quality/check-python-lint.sh"`. That one is a
    DIFFERENTIAL and MUST KEEP NAMING THE TWIN: repointing it would make the
    port compare against itself.

Repointing is the driver's call; all three go on working unchanged after this
cutover because invariant 5 keeps the twin on disk.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-python-lint.sh   -> exit 0
    .ci/scripts/quality/check_python_lint.py   -> exit 0
    stdout: BYTE-IDENTICAL, 200 bytes, sha256 1d2d738b79a6d7ab...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was first run TWICE against an unchanged tree to establish that its own output is byte-stable
against itself; it is, on both streams.

DRIVEN RED AS WELL, and NOT by mutating the real tree. The plant lives in a `cp -r` fixture repository at a scratch path: a `git init` tree carrying twelve clean `.py` files (the twin's `MIN_PY_FILES` floor is 10, so eleven would have been a vacuity refusal wearing a lint failure's exit code), this repo's `pyproject.toml`, `.devcontainer/toolchain.env`, `.ci/scripts/lib/`, and a
copy of the TWIN at the same relative path so its `$BASH_SOURCE`-derived root lands on the fixture. The port is aimed at the same tree with `REDIACC_CI_ROOT`. `cp -r`, never a link, for the reason `mutate-check.sh:122` records: `realpath --relative-to` resolves symlinks, and a fixture linked at the real tree makes both sides agree by reading the same corrupted tree.

THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN, twice over: bare `ruff check` on the planted file reports F821 and exits non-zero, and `git ls-files` in the fixture still enumerates twelve `.py` files, so the plant changes the VERDICT and not the corpus size.

    both sides -> exit 1, stdout BYTE-IDENTICAL (388 bytes,
    sha256 43986f90c55cb50e...), stderr BYTE-IDENTICAL (267 bytes,
    sha256 2344b3a79c038338...):

    F821 Undefined name `undefined_name_8a`  --> src/mod7.py:3:12
    ✗ ruff reported findings in Python this gate scans (tracked and untracked).

A PORT GAP WAS FOUND DOING THIS AND FIXED IN `python_lint.py`. The first fixture had no `.devcontainer/`, and the two sides split: the twin exited 1 printing `toolchain: pins file missing or unreadable: ...` and nothing else,
because `check-python-lint.sh:137` is `toolchain_load || exit 1`; the port
exited 0 with a full green report over twelve files, because it reads the pin
from a literal and never opened the pins file at all. That is an anti-vacuity
refusal silently dropped in a port. The refusal is now in the module, in the twin's position (after the two VACUOUS INPUT checks, before the resolver), with `toolchain.sh:28`'s `REDIACC_TOOLCHAIN_LOADED` early return, and both sides now print the same 91 bytes and exit 1 on that input.

THE REAL TREE WAS NEVER WRITTEN TO for this gate. `git status --porcelain` carries no probe file, and neither this twin nor any other was edited here.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-python-lint.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Python lint + format (ruff) needs: none selftest: true ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import python_lint

if __name__ == "__main__":
    raise SystemExit(python_lint.main(sys.argv[1:]))
