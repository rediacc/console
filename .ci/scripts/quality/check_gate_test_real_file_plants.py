#!/usr/bin/env python3
"""check:ci-gate-test-real-file-plants -- a gate TEST must never write to a
REAL tracked file it also reads as a module-level "the subject's real path"
constant, even inside a try/finally restore.

WHY THIS EXISTS. `test_gate_worklist_env_registry.py` had three such plants
(two into `.ci/policy/worklist-env-registry.json`, one into
`.claude/hooks/stop/worklist-cases/21-cadence.sh`): read the real file's bytes,
mutate and write them, run the gate under test, restore from the in-memory
original in a `finally`. A hard kill landing in the write-to-restore window
leaves the tracked file genuinely corrupted with no backup -- and it happened
for real, twice in one session, from two unrelated causes (a `check:ci-pytest`
suite timeout, then a concurrent pytest invocation from a second live
session). The fix there was a test-only env-var seam
(`WORKLIST_REGISTRY_OVERRIDE_FILE`, `WORKLIST_SOURCE_OVERRIDE_FILE`) that
redirects the gate under test onto a tmp copy instead. This gate exists so the
NEXT gate-test author who reaches for `TARGET.write_text(...); finally:
TARGET.write_bytes(original)` is caught before they write it, not after a
third real corruption.

THE PATTERN, stated as a shape rather than a location. A module-level
constant built from `paths.from_root(...)` or `<root>/...` names a REAL
tracked file. If that same name is the target of a `.write_text(` or
`.write_bytes(` call anywhere in the file, the test plants into the real
tree -- regardless of whether a `finally` restores it afterward, because the
restore only helps a run that finishes.

WHAT THIS DOES NOT CATCH, said out loud. A local variable built from a
sandboxed/copied path (`shutil.copy2(REAL, tmp_copy)`, `tmp_path / "x"`,
`harness.temp_dir()`) is exactly the safe pattern and is not a module-level
constant, so it is invisible to this scan by construction -- which is
correct, that is the pattern this gate wants MORE of, not less.

ALLOWLIST, because one pre-existing instance is known and not yet fixed:
`test_gate_docs_gen.py`'s `TARGET` (`scripts/data/doc-registry.md`) needs the
same override-seam treatment inside `scripts/gen-docs.ts`, a separate,
larger change in a different language than the fix already landed here
tonight. Recorded with a BLOCKER reason rather than silently excused.

---- gate ----
step: Gate-test real-file plants
needs: none
lane: quality-code
selftest: true
---- end gate ----
"""

from __future__ import annotations

import ast
import os
import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[3]
SCAN_DIR = ROOT / ".ci" / "rediacc_ci" / "tests" / "gates"

# ANTI-VACUITY FLOOR. This gate reports success by finding NOTHING, so a scan that
# collapsed -- a moved directory, a broken glob, a rename of the gate-tests package --
# is indistinguishable from a clean tree: both print a tick. The floor makes the
# difference observable. 161 files present on 2026-09-14; the floor sits well below
# that rather than at it, because a floor equal to today's count turns every deleted
# test into a failure and teaches people to lower the floor.
MIN_SCANNED = 100

RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# file -> BLOCKER reason. Printed every run, never silent.
ALLOWLIST = {
    "test_gate_docs_gen.py": (
        "BLOCKER: TARGET (scripts/data/doc-registry.md) needs the same "
        "override-seam treatment as WORKLIST_REGISTRY_OVERRIDE_FILE, inside "
        "scripts/gen-docs.ts (TypeScript, a separate change from tonight's "
        "Python fix). Tracked 2026-09-14, not yet done."
    ),
    "test_gate_generate_tag_inputs.py": (
        "BLOCKER: RESOLVER is a DELIBERATE, documented real-tree WRITER (its "
        "own docstring: 'THE WRITE IS THE POINT and there is no seam that "
        "avoids it' -- resolve-version.sh is invoked from the repo root, so "
        "moving the released version means moving that file). Not the "
        "accidental hazard this gate exists to catch: the restore is verified "
        "by digest AND mode afterward, and the module is registered in "
        "WRITER_TESTS specifically so it is excluded from parallel xdist "
        "workers that would race it."
    ),
    "test_gate_hook_cross_os.py": (
        "BLOCKER: PLANT_TARGET (.claude/rediacc_hooks/__gate_test_plant.py) "
        "is verified NOT tracked by git (`git ls-files` returns empty) -- a "
        "kill mid-test leaves an untracked stray file under a tracked "
        "directory, not a corrupted tracked file. Different, much lower "
        "severity than the class this gate targets; left as-is rather than "
        "moved under tmp_path so its name stays stable across runs."
    ),
}

REAL_PATH_RE = re.compile(r"paths\.from_root\(|paths\.repo_root\(\)\s*/")
TMP_HINT_RE = re.compile(r"tmp|temp|sandbox|scratch", re.IGNORECASE)


def real_path_constants(tree: ast.Module) -> set[str]:
    """Module-level NAME = paths.from_root(...) / <root>/... assignments.

    `tree.body` only, deliberately NOT `ast.walk(tree)`: a local variable
    named `path` inside some unrelated function can be assigned from a
    real-path-shaped expression too, and that is not a "the subject's real
    path" constant this gate cares about -- it is scoping noise. Restricting
    to the module's own top-level statements is what makes a hit mean "this
    file declares a named constant for a real tracked path", not "this file
    contains the substring `paths.from_root(` somewhere".
    """
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        # NOT wrapped in try/except. A defensive `continue` here would SILENTLY
        # skip an assignment this gate might otherwise have caught writing a real
        # tracked file -- which is the exact vacuity hazard the gate exists to
        # prevent, reproduced inside the gate. If `ast.unparse` ever fails, the
        # right outcome is a loud crash, not a quiet pass.
        src = ast.unparse(node.value)
        if not REAL_PATH_RE.search(src):
            continue
        if TMP_HINT_RE.search(src):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def writes_real_file(tree: ast.AST, real_names: set[str]) -> str | None:
    """The first real-path name this file calls .write_text/.write_bytes on."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in ("write_text", "write_bytes"):
            continue
        recv = func.value
        if isinstance(recv, ast.Name) and recv.id in real_names:
            return recv.id
    return None


def scan(scan_dir: pathlib.Path) -> list[tuple[str, str]]:
    """[(rel, real_name)] for every gate-test file that plants into a real path."""
    if not scan_dir.is_dir():
        return []
    findings: list[tuple[str, str]] = []
    for path in sorted(scan_dir.glob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        real_names = real_path_constants(tree)
        if not real_names:
            continue
        hit = writes_real_file(tree, real_names)
        if hit:
            findings.append((path.name, hit))
    return findings


def controls() -> None:
    """A planted real-file-write must be caught; a tmp-only write must not."""
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        (d / "test_gate_planted_hazard.py").write_text(
            "from rediacc_ci import paths\n"
            'TARGET = paths.from_root("scripts", "data", "doc-registry.md")\n'
            "def test_x():\n"
            "    original = TARGET.read_bytes()\n"
            "    TARGET.write_bytes(original)\n",
            encoding="utf-8",
        )
        found = scan(d)
        if not any(name == "test_gate_planted_hazard.py" for name, _ in found):
            print(
                "%s✗ CONTROL FAILED%s: a planted real-file write was not caught" % (RED, NC),
                file=sys.stderr,
            )
            sys.exit(2)
        (d / "test_gate_safe.py").write_text(
            "from rediacc_ci import paths\n"
            'TARGET = paths.from_root("scripts", "data", "doc-registry.md")\n'
            "def test_x(tmp_path):\n"
            "    original = TARGET.read_bytes()\n"
            '    mutated = tmp_path / "mutated.md"\n'
            "    mutated.write_bytes(original)\n",
            encoding="utf-8",
        )
        found2 = scan(d)
        if any(name == "test_gate_safe.py" for name, _ in found2):
            print(
                "%s✗ CONTROL FAILED%s: a tmp_path-only write was misreported as a real "
                "plant" % (RED, NC),
                file=sys.stderr,
            )
            sys.exit(2)


def main() -> int:
    controls()
    scanned = len(list(SCAN_DIR.glob("*.py")))
    if scanned < MIN_SCANNED:
        print(
            "%s\u2717%s VACUOUS: scanned %d file(s) in %s, below the floor of %d. This gate "
            "passes by finding nothing, so a corpus this small means the SCAN broke, not "
            "that the tree is clean. Refusing rather than printing a tick."
            % (RED, NC, scanned, os.path.relpath(SCAN_DIR, ROOT), MIN_SCANNED),
            file=sys.stderr,
        )
        return 1
    findings = scan(SCAN_DIR)
    unallowed = [(f, n) for f, n in findings if f not in ALLOWLIST]
    if ALLOWLIST:
        print("exemptions, printed every run so the debt cannot be forgotten:")
        for f, reason in ALLOWLIST.items():
            print("  %s\n      %s" % (f, reason))
    if unallowed:
        for f, name in unallowed:
            print(
                "%s✗%s %s writes to real tracked file %r without a tmp-path override "
                "seam. A hard kill mid-test corrupts a tracked file with no backup. "
                "See .ci/rediacc_ci/quality/worklist_env_registry.py's "
                "WORKLIST_REGISTRY_OVERRIDE_FILE for the fix pattern." % (RED, NC, f, name),
                file=sys.stderr,
            )
        print(
            "%d gate-test file(s) plant into a real tracked file." % len(unallowed),
            file=sys.stderr,
        )
        return 1
    print(
        "%s✓%s no gate-test file plants into a real tracked file without a declared "
        "exemption (%d file(s) scanned, %d exempted)" % (GREEN, NC, scanned, len(ALLOWLIST))
    )
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        controls()
        print("%s✓%s selftest" % (GREEN, NC))
        sys.exit(0)
    sys.exit(main())
