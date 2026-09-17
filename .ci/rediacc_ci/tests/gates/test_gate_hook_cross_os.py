"""The gate test for `check:ci-hook-cross-os`, which has no bash twin.

NEW GATE, NOT A PORT. What is tested here and not in the selftest is the gate as
a PROCESS against the REAL hook package: 65 files, the real `proc.py` seam, the
real declaration. The selftest runs against a three-file fixture, which proves
the predicate and proves nothing about whether the declaration matches the tree.

THE PLANT ADDS A FILE TO THE REAL SCAN ROOT rather than editing one, and the
first draft did the opposite. It appended a dead function to the hook package's
operator-invoked pytest runner, which the plan records as wired to nothing, and
that broke a DIFFERENT gate permanently rather than for the seconds of the
plant. `check:ci-dead-python` exempts that runner BY NAME with a BLOCKER reason
and checks the exemption in BOTH directions, so the moment this file NAMED it,
the runner acquired a `mentioned` route and the gate correctly reported that the
exemption had stopped being true.

THE RUNNER'S FILENAME IS NOT SPELLED ANYWHERE IN THIS FILE, and that is not
squeamishness. The `mentioned` route is a path-SUFFIX match over the text of
anything already reached, so writing the name even in a comment is what confers
it. Deleting the plant and leaving the sentence behind fixed nothing, and that
is how the second half of this paragraph came to exist. A test that gives its
plant target a false life signal corrupts the dead-code census in order to prove
something about a scanner.

Creating and removing a file is also the more realistic defect. Nobody adds a
`/proc` read to a file that has been there for months; somebody adds a new
guard. The scan root is walked with `rglob`, not `git ls-files`, so a file that
exists for the length of one case is in the corpus for exactly that case. It is
removed in a `finally`, and a later case asks `git status` whether anything was
left behind.
"""

import contextlib
import fcntl
import subprocess
import sys

import pytest

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

# THE PLANT IS A FIXED PATH IN THE REAL TREE, so these cases cannot run beside each other. One writes `__gate_test_plant.py` into `.claude/rediacc_hooks/`
# and expects the gate to red on it; two others scan that same directory and
# expect it CLEAN. Without a group `--dist loadgroup` is free to put them on different workers, and measured 2026-09-15 it did:
#
# clean tree (stderr: ✗ .claude/rediacc_hooks/__gate_test_plant.py:7 pgrep (proc-tool) is platform-sensitive ...): expected 0, got 1
#
# -- the clean-tree case failing on the OTHER case's plant, which reads as the gate being broken rather than as two cases colliding. Same defect as the deploy differentials fixed in 3ba9b417d, one directory over: the group name is the mutex, and any module that writes a fixed path needs one. This plant is inside the REPO rather than /tmp, which if anything makes it worse -- a
# case killed between the write and its `finally` leaves a file in the tree.
pytestmark = pytest.mark.xdist_group("hook-cross-os-plant")

GATE = paths.from_root(".ci", "scripts", "quality", "check_hook_cross_os.py")
SEAM = paths.from_root(".claude", "rediacc_hooks", "proc.py")
# Deliberately NOT an existing file: see the module docstring. The name starts
# with a double underscore so that a stray copy, if a case is killed between the
# write and the `finally`, is obviously not part of the package.
PLANT_TARGET = paths.from_root(".claude", "rediacc_hooks", "__gate_test_plant.py")

PLANTED = (
    '"""A file that exists for the length of one assertion."""\n\n'
    "import subprocess\n\n\n"
    "def probe(pid):\n"
    '    subprocess.run(["pgrep", "-f", "x"], check=False)\n'
    '    return open("/proc/%d/comm" % pid).read()\n'
)


# THE GROUP IS NOT ENOUGH, and the demonstration is why this lock exists.
# `xdist_group` serialises these cases WITHIN one pytest run; it does nothing
# about a SECOND run in the same tree, and this repository runs concurrent gate batteries as a matter of course. Measured 2026-09-15, one process looping the plant case against another looping the two scanning cases:
#
# clean-tree scans that FAILED while a planter ran concurrently: 12 of 12
#
# Twelve out of twelve, not an occasional flake. The plant lives in the REPO rather than in /tmp, so the blast radius is worse than the deploy modules' `/tmp/config`: a concurrent battery reds on a file it did not create, and a
# case killed between the write and its `finally` leaves it in the working tree.
#
# Same shape as `FIXED_TMP_LOCK` in test_deploy_simulate_promotion.py, and the lesson that file taught tonight is applied here rather than repeated: a lock only one of two parties takes is not a lock, so BOTH the planting case and the scanning cases hold it.
PLANT_LOCK = "/tmp/rediacc-hook-cross-os-plant.lock"


@contextlib.contextmanager
def _plant_guard():
    """Serialise every case that depends on the real scan root being stable."""
    with open(PLANT_LOCK, "a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _run(*args) -> harness.RunResult:
    return harness.run([sys.executable, str(GATE), *args], cwd=paths.repo_root())


def test_the_real_hook_package_is_fully_seamed(gate):
    with _plant_guard():
        gate.log_test("the real 65-file package, through the real entry point")
        for subject in (GATE, SEAM):
            if not subject.is_file():
                gate.log_fail("subject under test is missing: %s" % paths.relative_to_root(subject))
        result = _run()
        gate.assert_exit_code(0, result.rc, "clean tree (stderr: %s)" % result.err)
        gate.assert_contains(result.combined, "0 unclaimed, 0 dead", "set equality both ways")
        gate.assert_contains(result.combined, "Python file(s) under", "prints the corpus size")
        # The scope table is printed on SUCCESS as well as on failure. An exemption only visible when something is already broken is an exemption nobody drains.
        gate.assert_contains(
            result.combined, "seam proc-table ", "the scope table is always printed"
        )
        gate.assert_contains(result.combined, "REDIACC_PROC_BACKEND", "with the override named")
        gate.log_pass("the real package has one seam, it is declared, and nothing escapes it")


def test_the_corpus_is_not_trivially_small(gate):
    with _plant_guard():
        gate.log_test("the corpus the gate reports is the corpus on disk")
        result = _run()
        gate.assert_exit_code(0, result.rc, "clean run")
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


def test_a_planted_platform_read_reds_on_the_real_tree(gate):
    with _plant_guard():
        gate.log_test("PLANT: a new file in the real scan root reads /proc and runs pgrep")
        if PLANT_TARGET.exists():
            gate.log_fail(
                "%s already exists; a previous run left it behind and this case would be "
                "asserting about somebody else's file" % paths.relative_to_root(PLANT_TARGET)
            )
        before = _run()
        gate.assert_exit_code(0, before.rc, "the tree is green before the plant")
        try:
            PLANT_TARGET.write_text(PLANTED, encoding="utf-8")
            result = _run()
            gate.assert_exit_code(1, result.rc, "an unclaimed platform read must red")
            gate.assert_contains(result.combined, "__gate_test_plant.py", "names the file")
            gate.assert_contains(result.combined, "(procfs)", "and the class")
            gate.assert_contains(result.combined, "(proc-tool)", "and the second class")
            gate.assert_contains(
                result.combined,
                "Do not widen an existing scope",
                "and refuses the shortcut explicitly",
            )
        finally:
            PLANT_TARGET.unlink(missing_ok=True)
        gate.assert_eq(PLANT_TARGET.exists(), False, "the planted file is gone")
        after = _run()
        gate.assert_exit_code(0, after.rc, "and the tree is green again once the plant is gone")
        gate.log_pass("red with the plant, gone after it, green again")


def test_the_plant_left_the_tree_exactly_as_it_found_it(gate):
    with _plant_guard():
        gate.log_test("a second instrument is asked whether anything was left behind")
        # `git status --porcelain` and not `git diff`: the plant was an UNTRACKED file, and `git diff` does not show untracked files at all -- it would report a clean tree whether or not the plant was cleaned up, which is a control that cannot fail.
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--", ".claude/rediacc_hooks/"],
            cwd=paths.repo_root(),
            capture_output=True,
            text=True,
            check=False,
        )
        gate.assert_exit_code(0, proc.returncode, "git status ran")
        leftovers = [ln for ln in proc.stdout.splitlines() if "__gate_test_plant" in ln]
        gate.assert_eq(leftovers, [], "no planted file remains under the hook package")
        gate.log_pass("git status agrees the scan root is as it was")


def test_the_selftest_covers_both_directions(gate):
    gate.log_test("--selftest runs, and asserts non-findings as well as findings")
    result = _run("--selftest")
    gate.assert_exit_code(0, result.rc, "selftest (stderr: %s)" % result.err)
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
