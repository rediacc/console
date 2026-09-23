#!/usr/bin/env python3
"""Entry point for the ported Python lint + format gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.python_lint`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.python_lint` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-python-lint.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `emit:`, no `blocker:`, no `id:`, no `run:`, no
`kind:`, no `lane:`, no `why:`.

NO `lane:` IS CORRECT, and it is not an omission. This gate's step sits INSIDE the `# >>> gate-bind` region of `quality-static` (ci-quality.yml:199-346), so the lane is read off the region the step already lives in rather than declared. The twin ran that way; nothing about the lane moves here.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) strips the `check_` prefix and maps `_` to `-`, so this basename derives `check:ci-python-lint`, which is the manifest id. Verified by calling `bind()` rather than by reading the rule.

`selftest: true` is inert for a `.py` gate (`headerLines` emits that field only
for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and
because `python_lint.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files rather than by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers `[]` and this two-import entry point infers `[]`, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both sides resolve to the empty set `needs: none` declares.

PINNED BY PATH IN TWO HARNESSES, and the two rows take DIFFERENT arms.

  - `.ci/rediacc_ci/tests/gates/test_gate_gate_anti_vacuity.py` registers
    `.ci/scripts/quality/check_python_lint.py` against `VACUOUS INPUT` and RUNS
    that path against an empty tree, asserting the diagnostic. That is a
    run-in-place row, so if it is ever repointed it must be repointed at THIS
    ENTRY POINT, never at the module. The bash twin that carried the same
    registry was retired 2026-09-21.
  - `.ci/rediacc_ci/tests/test_core_dockerx.py` used to read the TWIN as TEXT
    and regex-match a whole line of the form `exit <digits>`, asserting the
    cannot-run code 77 was among them. That is a behavioural needle in the
    SOURCE, and the needle was never in this three-line shim, so W7P5-c
    repointed the row at the MODULE `.ci/rediacc_ci/quality/python_lint.py`
    when it deleted the twin. THE PATTERN MOVED WITH IT, measured rather than
    assumed: the twin carried a bare `exit 77` at line 191 among nine `exit
    <digits>` lines, so the assertion there was MEMBERSHIP; the module writes
    `EXIT_CANNOT_RUN = 77` at python_lint.py:175 and never emits that line
    shape at all, so the assertion is now EQUALITY, the same one the two other
    constant-naming files already get. A repoint that had kept the old pattern
    would have found nothing, which that test does catch -- it asserts the
    match set is non-empty and says "the pattern has rotted".
  - `.ci/rediacc_ci/tests/test_quality_python_lint.py` sets
    `TWIN = ".ci/scripts/quality/check-python-lint.sh"` and still does, but it
    is no longer a DIFFERENTIAL: it names the deleted twin so that
    `test_the_twin_is_gone_and_its_recording_names_it` can assert the file is
    absent AND that every golden's provenance header names it. Repointing that
    constant at either Python file would make the port compare against itself.

The first row still runs in place against this entry point; the other two moved with the deletion below.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-python-lint.sh   -> exit 0
    .ci/scripts/quality/check_python_lint.py   -> exit 0
    stdout: BYTE-IDENTICAL, 200 bytes, sha256 1d2d738b79a6d7ab...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was first run TWICE against an unchanged tree to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, and NOT by mutating the real tree. The plant lives in a `cp -r` fixture repository at a scratch path: a `git init` tree carrying twelve clean `.py` files (the twin's `MIN_PY_FILES` floor is 10, so eleven would have been a vacuity refusal wearing a lint failure's exit code), this repo's `pyproject.toml`, `.devcontainer/toolchain.env`, `.ci/scripts/lib/`, and a
copy of the TWIN at the same relative path so its `$BASH_SOURCE`-derived root lands on the fixture. The port is aimed at the same tree with `REDIACC_CI_ROOT`. `cp -r`, never a link, for the reason `mutate-check.sh:122` records: `realpath --relative-to` resolves symlinks, and a fixture linked at the real tree makes both sides agree by reading the same corrupted tree.

THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN, twice over: bare `ruff check` on the planted file reports F821 and exits non-zero, and `git ls-files` in the fixture still enumerates twelve `.py` files, so the plant changes the VERDICT and not the corpus size.

    both sides -> exit 1, stdout BYTE-IDENTICAL (388 bytes,
    sha256 43986f90c55cb50e...), stderr BYTE-IDENTICAL (267 bytes,
    sha256 2344b3a79c038338...):

    F821 Undefined name `undefined_name_8a`  --> src/mod7.py:3:12
    ✗ ruff reported findings in Python this gate scans (tracked and untracked).

A PORT GAP WAS FOUND DOING THIS AND FIXED IN `python_lint.py`. The first fixture had no `.devcontainer/`, and the two sides split: the twin exited 1 printing `toolchain: pins file missing or unreadable: ...` and nothing else, because `check-python-lint.sh:137` is `toolchain_load || exit 1`; the port exited 0 with a full green report over twelve files, because it reads the pin
from a literal and never opened the pins file at all. That is an anti-vacuity
refusal silently dropped in a port. The refusal is now in the module, in the twin's position (after the two VACUOUS INPUT checks, before the resolver), with `toolchain.sh:28`'s `REDIACC_TOOLCHAIN_LOADED` early return, and both sides now print the same 91 bytes and exit 1 on that input.

THE REAL TREE WAS NEVER WRITTEN TO for this gate. `git status --porcelain` carries no probe file, and neither this twin nor any other was edited here.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-python-lint.sh` stayed on disk as the differential twin through this cutover, and W7P5-c DELETED it on 2026-09-23 (blob `471b915b87984c59aeaca380951aa3dd5bd3b702`, `git cat-file -p` still yields it). The licence is `.ci/shadow/w7p2-python-lint.observations.jsonl`: 6 rows, 6 distinct trees, 6 distinct fingerprints,
every one `EQUIVALENT`. The nine cases that executed the twin now compare against its own recorded bytes in `.ci/rediacc_ci/tests/goldens/python-lint/`, captured from the tracked script on its last day in the tree.

---- gate ----
step: Python lint + format (ruff)
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import python_lint

if __name__ == "__main__":
    raise SystemExit(python_lint.main(sys.argv[1:]))
