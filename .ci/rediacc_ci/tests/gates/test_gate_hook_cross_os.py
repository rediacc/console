"""The gate test for `check:ci-hook-cross-os`, which has no bash twin.

NEW GATE, NOT A PORT. What is tested here and not in the selftest is the gate as a PROCESS against the REAL hook package: 65 files, the real `proc.py` seam, the real declaration. The selftest runs against a three-file fixture, which proves the predicate and proves nothing about whether the declaration matches the tree.

THE PLANT GOES INTO A COPY, never the real tree. The gate scans `.claude/rediacc_hooks/` with `rglob`, and `npm run ci:quick` runs it beside `check:ci-pytest`; a plant written into the real directory was visible to the concurrently running gate, which went red on `__gate_test_plant.py` (receipt run 2026-10-19). The test now copies the hook package into pytest's `tmp_path`, plants there, and points the gate at the copy with `--root`. The real tree is only ever read, so no lock, no xdist group and no cleanup assertion is needed.

The plant ADDS A NEW FILE to the copy rather than editing one: nobody adds a `/proc` read to a file that has been there for months, somebody adds a new guard. The control still has both halves: the copy is GREEN before the plant and RED with it, so a gate that ignored `--root` (and scanned the real tree) would fail the red assertion.
"""

import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_hook_cross_os.py")
SEAM = paths.from_root(".claude", "rediacc_hooks", "proc.py")
HOOKS_REL = (".claude", "rediacc_hooks")
PLANT_NAME = "__gate_test_plant.py"

PLANTED = (
    '"""A file that exists for the length of one assertion."""\n\n'
    "import subprocess\n\n\n"
    "def probe(pid):\n"
    '    subprocess.run(["pgrep", "-f", "x"], check=False)\n'
    '    return open("/proc/%d/comm" % pid).read()\n'
)


def _copy_tree(tmp_path):
    """Copy the scanned hook package to `<tmp>/.claude/rediacc_hooks`; return the root."""
    dst = tmp_path.joinpath(*HOOKS_REL)
    shutil.copytree(
        paths.from_root(*HOOKS_REL), dst, ignore=shutil.ignore_patterns("__pycache__")
    )
    return tmp_path


def _run(*args, root=None) -> harness.RunResult:
    extra = ["--root", str(root)] if root is not None else []
    return harness.run([sys.executable, str(GATE), *extra, *args], cwd=paths.repo_root())


def test_the_real_hook_package_is_fully_seamed(gate):
    gate.log_test("the real 65-file package, through the real entry point")
    for subject in (GATE, SEAM):
        if not subject.is_file():
            gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(subject))
    result = _run()
    gate.assert_exit(0, result, "clean tree")
    gate.assert_contains(result.combined, "0 unclaimed, 0 dead", "set equality both ways")
    gate.assert_contains(result.combined, "Python file(s) under", "prints the corpus size")
    # The scope table is printed on SUCCESS as well as on failure. An exemption only visible when something is already broken is an exemption nobody drains.
    gate.assert_contains(result.combined, "seam proc-table ", "the scope table is always printed")
    gate.assert_contains(result.combined, "REDIACC_PROC_BACKEND", "with the override named")
    gate.log_pass("the real package has one seam, it is declared, and nothing escapes it")


def test_the_corpus_is_not_trivially_small(gate):
    gate.log_test("the corpus the gate reports is the corpus on disk")
    result = _run()
    gate.assert_exit(0, result, "clean run")
    on_disk = len(
        [
            p
            for p in paths.from_root(".claude", "rediacc_hooks").rglob("*.py")
            if "__pycache__" not in p.parts
        ]
    )
    gate.assert_eq(on_disk >= 50, True, "%d Python files under the hook package" % on_disk)
    gate.assert_contains(
        result.combined, "%d Python file(s)" % on_disk, "and the gate says the same number"
    )
    gate.log_pass("the reported corpus size (%d) is the one on disk" % on_disk)


def test_a_planted_platform_read_reds_on_a_copy(gate, tmp_path):
    gate.log_test("PLANT: a new file in a COPY of the scan root reads /proc and runs pgrep")
    root = _copy_tree(tmp_path)
    before = _run(root=root)
    gate.assert_exit(0, before, "the copy is green before the plant")
    plant = root.joinpath(*HOOKS_REL, PLANT_NAME)
    plant.write_text(PLANTED, encoding="utf-8")
    result = _run(root=root)
    gate.assert_exit(1, result, "an unclaimed platform read must red")
    gate.assert_contains(result.combined, PLANT_NAME, "names the file")
    gate.assert_contains(result.combined, "(procfs)", "and the class")
    gate.assert_contains(result.combined, "(proc-tool)", "and the second class")
    gate.assert_contains(
        result.combined, "Do not widen an existing scope", "and refuses the shortcut explicitly"
    )
    plant.unlink()
    after = _run(root=root)
    gate.assert_exit(0, after, "and the copy is green again once the plant is gone")
    # The real tree was never written: the plant exists only under tmp_path.
    gate.assert_eq(
        paths.from_root(*HOOKS_REL, PLANT_NAME).exists(), False, "nothing planted in the real tree"
    )
    gate.log_pass("red with the plant, green without it, real tree untouched")


def test_the_selftest_covers_both_directions(gate):
    gate.log_test("--selftest runs, and asserts non-findings as well as findings")
    result = _run("--selftest")
    gate.assert_exit(0, result, "selftest")
    passes = [ln for ln in result.combined.splitlines() if "PASS " in ln]
    gate.assert_eq(len(passes) >= 16, True, "%d control(s) ran, floor 16" % len(passes))
    plants = [ln for ln in passes if "PLANT:" in ln]
    anti = [ln for ln in passes if "ANTI-SILENCER:" in ln]
    vacuity = [ln for ln in passes if "VACUITY:" in ln]
    gate.assert_eq(len(plants) >= 7, True, "%d plants" % len(plants))
    gate.assert_eq(len(anti) >= 2, True, "%d anti-silencers" % len(anti))
    gate.assert_eq(len(vacuity) >= 4, True, "%d vacuity refusals" % len(vacuity))
    gate.log_pass(
        "%d plants, %d anti-silencers, %d refusals" % (len(plants), len(anti), len(vacuity))
    )
