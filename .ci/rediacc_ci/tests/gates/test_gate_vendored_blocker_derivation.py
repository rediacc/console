"""The W4 P3d gate, driven as a PROCESS rather than as a function.

WHAT THIS ADDS OVER THE MODULE'S OWN CONTROLS, which is the only reason a gate test earns its place. `selftest()` inside `rediacc_ci.quality.vendored_blocker_derivation` proves the predicates; it can prove nothing about the wrapper, the exit codes, the streams, or the one claim that is only meaningful against the REAL directory:

  * the entry point is reachable at the path the registry will name, and its
    `--selftest` flag exits 0 rather than 1 (an inverted `return 1 if ...`
    passed every internal control in a sibling gate and was caught only here),
  * a refusal exits 1 with its reason on STDERR, not stdout,
  * INVARIANT 8, end to end: after a full run against the real tree,
    `.ci/breakpoint/` is byte-identical and `git status` reports it clean. The
    module asserts this about a temporary copy; only this file can assert it
    about the drift-locked original, and the original is the thing invariant 8
    is about.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_vendored_blocker_derivation.py")
BREAKPOINT_DIR = paths.from_root(".ci", "breakpoint")
VENDORED = paths.from_root(".ci", "breakpoint", "lib", "breakpoint-blocker.sh")


def _tree_digest(root: pathlib.Path) -> str:
    """One digest over every file under `root`, path included.

    PATHS ARE HASHED TOO, not just contents. A digest over contents alone cannot see a rename, and a rename inside a vendored, drift-locked directory is exactly as much of a write as an edit is.
    """
    accumulator = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        accumulator.update(str(path.relative_to(root)).encode("utf-8"))
        accumulator.update(path.read_bytes())
    return accumulator.hexdigest()


def test_the_gate_is_reachable_as_a_program(gate):
    gate.log_test("the entry point runs at the path the registry names, and prints its shape")
    result = harness.run([str(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the gate passes on this tree")
    gate.assert_contains(result.out, "  PASS  ", "with its own controls run first, on stdout")
    # THE VERDICT IS ON STDERR AND THE CONTROL TALLY IS ON STDOUT, which is not a slip: `rediacc_ci.log` writes every level to ONE stream (stderr by default, `log.py:221-235`) while `Checker` prints its PASS lines with a bare `print`. Asserting the two separately is what makes that split visible; asserting `out + err` would pass just as happily if the verdict vanished.
    gate.assert_contains(
        result.err, "divergence(s) all attributed", "and it says what it derived, on stderr"
    )
    # THE SHAPE, NOT THE VERDICT. A success line that said only "OK" could not show a reader that the corpus collapsed to two cases.
    gate.assert_contains(result.err, "20 corpus case(s)", "naming the corpus size it read")
    gate.assert_contains(result.err, "0 vendored substrings", "and the claim it is built on")
    gate.log_pass("the gate is reachable, green, and prints the numbers behind the verdict")


def test_the_selftest_flag_exits_zero_on_a_green_run(gate):
    gate.log_test("--selftest is a process too, and its exit code is not the controls' opinion")
    result = harness.run([str(GATE), "--selftest"], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "a fully green control run exits 0 under --selftest")
    gate.assert_contains(result.out, "  PASS  ", "and the controls printed their tally")
    gate.log_pass("--selftest exits 0 when every control passed")


def test_a_tree_without_the_subject_is_refused_through_the_env_seam(gate):
    gate.log_test("a root with no vendored copy is a REFUSAL on stderr, exit 1")
    with harness.temp_dir() as root:
        result = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"VENDORED_BLOCKER_ROOT": str(root)}
        )
        gate.assert_exit_code(1, result.rc, "a tree it cannot see exits 1, not 0 and not 2")
        gate.assert_contains(
            result.err, "does not exist", "and stderr says which subject was missing"
        )
        gate.assert_contains(
            result.err, "would mean nothing", "and why that is a failure rather than a note"
        )
        gate.assert_not_contains(
            result.out, "does not exist", "the refusal is on stderr, not the control tally"
        )
    gate.log_pass("an unseeable tree refuses loudly, on the right stream")


def test_a_deleted_manifest_is_not_a_free_pass(gate):
    gate.log_test("deleting MANIFEST.sha256 must not be the cheapest way past this gate")
    with harness.temp_dir() as root:
        target = pathlib.Path(root)
        for rel in (
            ".ci/breakpoint/lib/breakpoint-blocker.sh",
            ".ci/scripts/test/gates/test-blocker-golden-corpus.sh",
        ):
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((paths.repo_root() / rel).read_bytes())
        # No MANIFEST.sha256 at all: the file this gate compares its two reads to.
        result = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"VENDORED_BLOCKER_ROOT": str(root)}
        )
        gate.assert_exit_code(1, result.rc, "no manifest is a hard refusal")
        gate.assert_contains(
            result.err, "never be the way past a gate", "and it says so in those words"
        )
        # CONTROL: the same tree WITH a correct manifest passes, so the case above is measuring the missing manifest and not the copied fixture.
        digest = hashlib.sha256((target / ".ci/breakpoint/lib/breakpoint-blocker.sh").read_bytes())
        (target / ".ci/breakpoint/MANIFEST.sha256").write_text(
            "%s  lib/breakpoint-blocker.sh\n" % digest.hexdigest(), encoding="utf-8"
        )
        clean = harness.run(
            [str(GATE)], cwd=paths.repo_root(), env={"VENDORED_BLOCKER_ROOT": str(root)}
        )
        gate.assert_exit_code(0, clean.rc, "CONTROL: the same tree with a manifest passes")
    gate.log_pass("an absent pin is refused, and the control proves the fixture was otherwise fine")


def test_the_gate_does_not_write_to_the_vendored_directory(gate):
    gate.log_test("invariant 8, end to end: a real run leaves .ci/breakpoint/ untouched")
    before = _tree_digest(BREAKPOINT_DIR)
    before_bytes = VENDORED.read_bytes()
    result = harness.run([str(GATE)], cwd=paths.repo_root())
    gate.assert_exit_code(0, result.rc, "the run under observation actually completed")
    gate.assert_eq(
        _tree_digest(BREAKPOINT_DIR), before, "every file under .ci/breakpoint/ is identical"
    )
    gate.assert_eq(
        VENDORED.read_bytes() == before_bytes, True, "the vendored validator is byte-identical"
    )
    # AND THROUGH GIT, which is a different oracle: the digest above would agree
    # with itself if the gate had rewritten the file identically in both reads,
    # and it cannot see a file the gate created and deleted between them either. `git status` is the claim a reviewer would make.
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", ".ci/breakpoint"],
        cwd=str(paths.repo_root()),
        capture_output=True,
        text=True,
        check=False,
    )
    gate.assert_eq(dirty.stdout.strip(), "", "git reports .ci/breakpoint/ clean after the run")
    gate.log_pass("the gate reads and hashes the vendored tree and writes nothing to it")
