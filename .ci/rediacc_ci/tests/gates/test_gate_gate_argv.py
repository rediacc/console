"""check:ci-gate-argv driven for real: the registered entry point, the real tree, and a copy of the real tree with one plant.

The copy is the control that matters. A plant in a hand-written fixture proves the helpers work; a plant in a COPY of the real `.ci/scripts/quality` proves the real invocation, over the real entry points and the real package.json, turns red on one bypass and on one bad registered call, and that the same copy without the plant is green.
"""

import os
import pathlib
import shutil
import sys

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

GATE = paths.from_root(".ci", "scripts", "quality", "check_gate_argv.py")
ROOT = paths.repo_root()


def _copy_tree(dst: pathlib.Path) -> pathlib.Path:
    """The quality entry points copied, the library, the other script directories and the call sources linked, and the lock the gate reads its population from copied, under `dst`."""
    (dst / ".ci" / "scripts").mkdir(parents=True)
    shutil.copytree(ROOT / ".ci" / "scripts" / "quality", dst / ".ci" / "scripts" / "quality")
    for sibling in (ROOT / ".ci" / "scripts").iterdir():
        if sibling.is_dir() and sibling.name != "quality":
            os.symlink(sibling, dst / ".ci" / "scripts" / sibling.name)
    os.symlink(ROOT / ".ci" / "rediacc_ci", dst / ".ci" / "rediacc_ci")
    shutil.copy(ROOT / "package.json", dst / "package.json")
    (dst / "scripts" / "ci-runner").mkdir(parents=True)
    shutil.copy(
        ROOT / "scripts" / "ci-runner" / "gates.lock.json",
        dst / "scripts" / "ci-runner" / "gates.lock.json",
    )
    return dst


def _run(root: pathlib.Path | None = None) -> harness.RunResult:
    env = {"GATE_ARGV_SCAN_ROOT": str(root)} if root is not None else {}
    return harness.run([sys.executable, str(GATE)], cwd=ROOT, env=env, timeout=600)


def test_selftest_passes(gate):
    result = harness.run([sys.executable, str(GATE), "--selftest"], cwd=ROOT)
    gate.assert_exit_code(0, result.rc, "the gate's own controls pass")
    gate.assert_contains(result.combined, "control(s) passed", "the selftest reports its count")
    gate.log_pass("selftest rc 0")


def test_an_unknown_argument_is_refused(gate):
    result = harness.run([sys.executable, str(GATE), "--update"], cwd=ROOT)
    gate.assert_exit_code(2, result.rc, "the gate refuses a flag it does not take")
    gate.assert_contains(
        result.err, "check_gate_argv.py: unknown argument '--update'", "named on stderr"
    )
    gate.log_pass("the gate uses the parser it polices")


def test_real_tree_is_green_with_a_non_trivial_shape(gate):
    result = _run()
    gate.assert_exit_code(0, result.rc, "check:ci-gate-argv on the real tree")
    gate.assert_contains(result.combined, "0 bypass", "no entry point bypasses the parser")
    gate.assert_contains(
        result.combined, "own refusal (exempt by name", "the named exemptions are printed"
    )
    gate.log_pass("real tree green")


def test_a_planted_bypass_in_a_copy_of_the_real_tree_is_red(gate, tmp_path):
    root = _copy_tree(tmp_path)
    clean = _run(root)
    gate.assert_exit_code(
        0, clean.rc, "the unplanted copy is green, so the plant below is what turns it red"
    )
    target = root / ".ci" / "scripts" / "quality" / "check_npmrc.py"
    text = target.read_text()
    planted = text.replace(
        '    _gate_args.parse("check_npmrc.py", sys.argv[1:], switches=("--selftest",))\n', ""
    )
    assert planted != text, "the plant must change the file"
    target.write_text(planted)
    red = _run(root)
    gate.assert_exit_code(1, red.rc, "a dropped parse is red")
    gate.assert_contains(red.err, "check_npmrc.py: reaches neither", "the bypass is named by file")
    gate.log_pass("a planted bypass turns the real-tree copy red")


def test_a_planted_bad_registered_call_in_a_copy_is_red(gate, tmp_path):
    root = _copy_tree(tmp_path)
    # The one registered call that still passes a flag by entry-point path lives in a workflow, which is a call source the gate scans.
    workflow = ROOT / ".github" / "workflows" / "ops-housekeeping.yml"
    dst = root / ".github" / "workflows" / workflow.name
    dst.parent.mkdir(parents=True)
    text = workflow.read_text()
    assert "check_region_consistency.py --live" in text, (
        "the real registered call is gone: re-point the plant"
    )
    planted = text.replace(
        "check_region_consistency.py --live", "check_region_consistency.py --lvie"
    )
    assert planted != text, "the plant must change the workflow"
    dst.write_text(text)
    clean = _run(root)
    gate.assert_exit_code(0, clean.rc, "the copy with the real call is green")
    dst.write_text(planted)
    red = _run(root)
    gate.assert_exit_code(1, red.rc, "an undeclared flag in a registered call is red")
    gate.assert_contains(
        red.err, "calls check_region_consistency.py with '--lvie'", "the call is named"
    )
    gate.log_pass("a planted bad call turns the real-tree copy red")


def test_a_collapsed_scan_is_refused(gate, tmp_path):
    (tmp_path / ".ci" / "scripts" / "quality").mkdir(parents=True)
    result = _run(tmp_path)
    gate.assert_exit_code(1, result.rc, "zero entry points is a refusal, never a pass")
    gate.assert_contains(result.err, "the scan is not seeing the tree", "the refusal says why")
    gate.log_pass("vacuity refused")
