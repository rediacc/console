"""Put `.ci` on `sys.path` so an entry point in this directory can import `rediacc_ci`.

Imported for its SIDE EFFECT, once per entry point:

    import _cipath  # noqa: F401
    from rediacc_ci.quality import <mod>

Eighty-one entry points carried a byte-identical copy of the insert below and
not one of them said why. The three questions that copy raised, each answered
here once instead of nowhere eighty-one times:

WHY AN ENTRY POINT EXISTS AT ALL, rather than registering the library module
directly. The registry invokes a gate BY PATH -- `package.json` holds
`".ci/scripts/quality/check_npmrc.py"` and `scripts/ci-runner/manifest.ts`
repeats it as a leaf. The obvious alternative,
`python3 -m rediacc_ci.quality.npmrc`, does run, and is still wrong:
`check:ci-parity`'s tokenizer cannot read `-m`, so it resolves the leaves to
`[python3]` and the gate fails parity. `derivedRun` in
`scripts/lib/gate-header.ts` records that trap for `.py` by name. So each gate
needs a file at a path, and that file is a shim.

WHY THE HOP IS NEEDED. Nothing puts `.ci` on `sys.path` for a path invocation.
Run `python3 .ci/rediacc_ci/quality/npmrc.py` and it dies at
`from rediacc_ci import log, paths` before doing any work. What a path
invocation DOES put on `sys.path[0]` is the script's own directory --
`.ci/scripts/quality` -- which is both why `import _cipath` resolves with no
hop of its own and why the hop has to exist for anything else. That
`sys.path[0]` behaviour is switched off by `-P`, `-I` and `PYTHONSAFEPATH`;
none of the three is used anywhere in this tree, and a gate started under any
of them would fail loudly at this import rather than quietly skip a check.

WHY AN IMPORT FOR SIDE EFFECT AND NOT A FUNCTION. Settled with ruff rather
than argued, measured through `ruff check --stdin-filename`:

    a stdlib import placed AFTER the hop          -> I001
    the hop behind a helper call, `ci_path()`     -> E402
    `import _cipath` then `from rediacc_ci ...`   -> clean

A function call is a statement, and any import after a statement is E402. The
import form is the only spelling that keeps the whole prologue inside the
import block, which is where `select = ["ALL"]` insists it stays.

WHY THE NUMBER IS CHECKED RATHER THAN NAMED. `.ci/rediacc_ci/paths.py:73`
writes its own hop as three named steps, on the argument that "the number is
the part that goes wrong when a file moves, and a name cannot be off by one
silently". The `raise` below buys the same guarantee a different way, and buys
it here because the number is now written ONCE: move this file and the reader
gets a message naming the directory that was computed, instead of a
`ModuleNotFoundError: rediacc_ci` raised from a line that never mentions
`_cipath` at all.

ANOTHER GATE READS THIS ASSIGNMENT. `check_python_gate_deps.py` resolves
`CI_DIR = ...parents[2]` to decide that `rediacc_ci` is a first-party import
rather than something a job forgot to `pip install`, and reaches this file at
all because it follows a sibling module one hop. Both halves were added in the
same change as this file: without them it reported 69 findings, every one of
them a gate that had just stopped writing the insert itself.
"""

import pathlib
import sys

CI_DIR = pathlib.Path(__file__).resolve().parents[2]

if not (CI_DIR / "rediacc_ci" / "__init__.py").is_file():
    raise RuntimeError(
        "_cipath computed %s as the .ci directory, but there is no rediacc_ci "
        "package in it. This file has moved: it must stay in .ci/scripts/quality/, "
        "two directories below .ci." % CI_DIR
    )

sys.path.insert(0, str(CI_DIR))
