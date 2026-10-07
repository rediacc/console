"""Controls for the `gate` fixture's TEARDOWN, the refusal `conftest.py` exists to make.

WHY A SUBPROCESS. The refusal fires in teardown, after the test body has already returned, so no assertion inside a test can observe it: the only witness is the outcome pytest reports for a whole test. Each control therefore plants a tiny test file in a temp directory, runs a nested pytest on it with the real fixture re-exported, and reads the per-test verdict out of that run's `-rA` short summary.

BOTH DIRECTIONS, because a teardown that refused everything would pass every "must fail" control below. The plants that must stay GREEN are what prove the refusal is aimed, not blanket.

THE FINDING THIS PINS (worklist #9e34f61f). `gate.no()` RECORDS a failure and keeps going; only `tally_finish` raised on it. A test that called `no()` and never reached `tally_finish` therefore exited green with its FAIL line printed and ignored, which is how a shrink-only baseline test stayed green against an empty baseline. The teardown now refuses a tally that holds a failure, so the plant `test_no_without_finish` must be red.
"""

import os
import pathlib
import re
import subprocess
import sys
import textwrap

from rediacc_ci.tests.gates import harness

_CI_DIR = pathlib.Path(__file__).resolve().parents[3]

# Re-exporting the hook and the fixture is the whole conftest: the plant runs against the real code, not a copy of it.
_PLANT_CONFTEST = (
    "from rediacc_ci.tests.gates.conftest import gate, pytest_runtest_makereport  # noqa: F401\n"
)

_PLANT_TESTS = textwrap.dedent(
    """
    def test_no_without_finish(gate):
        gate.ok("this one held")
        gate.no("this one did not")

    def test_no_only_without_finish(gate):
        gate.no("the only control, and it failed")

    def test_ok_only(gate):
        gate.ok("a clean tally")

    def test_ok_then_finish(gate):
        gate.ok("a clean tally")
        gate.tally_finish("a clean subject")

    def test_log_pass_only(gate):
        gate.log_pass("a log_pass control, no tally at all")

    def test_no_then_finish(gate):
        gate.ok("this one held")
        gate.no("this one did not")
        gate.tally_finish("a red subject")

    def test_zero_controls(gate):
        pass

    def test_body_fails_after_no(gate):
        gate.no("recorded first")
        raise AssertionError("the body's own failure")
    """
)


def _run_plant(directory: pathlib.Path) -> tuple[dict[str, tuple[str, str]], harness.RunResult]:
    """Run the plant; return {test name: (outcome, message)} and the raw run."""
    (directory / "conftest.py").write_text(_PLANT_CONFTEST, encoding="utf-8")
    (directory / "test_plant.py").write_text(_PLANT_TESTS, encoding="utf-8")
    # An empty ini of its own: the repo's pyproject carries `--dist loadgroup` in addopts, which needs xdist on, and the plant must not depend on the outer run's plugins.
    (directory / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_CI_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env.pop(harness.LEDGER_ENV, None)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(directory),
            "-q",
            "-p",
            "no:cacheprovider",
            "-c",
            str(directory / "pytest.ini"),
            "--rootdir",
            str(directory),
            # -rA lists EVERY outcome in the short summary, and a teardown error is a separate ERROR line beside the call's PASSED one; the full messages are read from the long report below it.
            "-rA",
        ],
        cwd=directory,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    result = harness.RunResult(completed.returncode, completed.stdout, completed.stderr)
    verdicts: dict[str, tuple[str, str]] = {}
    rank = {"PASSED": 0, "FAILED": 1, "ERROR": 2}
    for line in completed.stdout.splitlines():
        match = re.match(r"^(PASSED|FAILED|ERROR) test_plant\.py::(\w+)(?: - (.*))?$", line)
        if not match:
            continue
        word, name, message = match.group(1), match.group(2), match.group(3) or ""
        # The worst outcome wins: a call that PASSED followed by a teardown ERROR is an error.
        if name in verdicts and rank[verdicts[name][0]] >= rank[word]:
            continue
        verdicts[name] = (word, message)
    # The summary line carries only the first line of a message, so each case's message is its whole long-report section instead: every `____ <header> ____` block whose header ends in the case's name ("test_x", "ERROR at teardown of test_x").
    parts = re.split(r"^_{3,} (.+?) _{3,}$", completed.stdout, flags=re.MULTILINE)
    for header, body in zip(parts[1::2], parts[2::2], strict=True):
        name = header.split()[-1]
        if name in verdicts:
            verdicts[name] = (verdicts[name][0], verdicts[name][1] + "\n" + body)
    return verdicts, result


def test_the_teardown_refuses_an_unfinished_red_tally_and_nothing_else(gate, tmp_path):
    verdicts, result = _run_plant(tmp_path)
    if len(verdicts) != 8:
        gate.log_fail("the plant did not run all 8 cases (saw %s)" % sorted(verdicts), result)
    gate.log_pass("the nested run reported all 8 planted cases")

    def outcome(name: str) -> str:
        return verdicts[name][0]

    def message(name: str) -> str:
        return verdicts[name][1]

    # MUST FIRE: the finding itself.
    gate.assert_eq(outcome("test_no_without_finish"), "ERROR", "no() without tally_finish")
    gate.assert_contains(
        message("test_no_without_finish"),
        "1 of 2 control(s) failed",
        "the teardown raises tally_finish's own verdict wording",
    )
    gate.log_pass("a no() that no tally_finish raised now reds the test in teardown")

    gate.assert_eq(outcome("test_no_only_without_finish"), "ERROR", "a lone no()")
    gate.assert_contains(message("test_no_only_without_finish"), "1 of 1 control(s) failed")
    gate.log_pass("a lone no() reds with the tally verdict, not the zero-control message")

    # MUST FIRE, pre-existing behaviour that must survive the change.
    gate.assert_eq(
        outcome("test_no_then_finish"), "FAILED", "tally_finish still raises in the body"
    )
    gate.assert_eq(outcome("test_zero_controls"), "ERROR", "a zero-control test")
    gate.assert_contains(message("test_zero_controls"), "without recording a single control")
    gate.log_pass("tally_finish and the zero-control refusal still fire")

    # MUST NOT FIRE: the refusal is aimed.
    for name in ("test_ok_only", "test_ok_then_finish", "test_log_pass_only"):
        gate.assert_eq(outcome(name), "PASSED", "%s stays green" % name)
    gate.log_pass("clean tallies and log_pass-only tests stay green")

    # A body that already failed keeps ITS diagnostic; the teardown adds no second, vaguer one.
    gate.assert_eq(outcome("test_body_fails_after_no"), "FAILED", "the body's own failure")
    gate.assert_contains(message("test_body_fails_after_no"), "the body's own failure")
    gate.assert_not_contains(result.combined, "ERROR at teardown of test_body_fails_after_no")
    gate.log_pass("a test that already failed is not re-failed in teardown")
