r"""`rediacc_ci.quality.drill_verdicts` against the harness it drives.

WHAT IS WORTH TESTING HERE. The gate's selftest plants mutated harnesses in fixture roots. What it cannot isolate is the DRIVER: a child interpreter that loads `.ci/rediacc_ci/drills/lib.py` by file path, sets the counters on a `Drill` and hands back `<rc>|<stdout>`. If the driver stops working, EVERY assertion in this gate either fails loudly (good) or, in the shape this repo keeps finding, passes vacuously.

So the cases below drive the REAL `Drill.summary` and assert on its real output, in both directions per verdict.
"""

import io
import pathlib
import re
import time

from rediacc_ci import paths
from rediacc_ci.drills import lib as drills_lib
from rediacc_ci.quality import drill_verdicts as dv


def test_the_harness_exists() -> None:
    """ZERO INPUTS IS A FAILURE. Every case below is vacuous without it, and the gate's own first branch says so in two lines."""
    assert (paths.repo_root() / dv.DRILL_LIB).is_file(), (
        "%s moved; the gate refuses rather than passing, and so should this" % dv.DRILL_LIB
    )


def test_the_driver_returns_both_halves() -> None:
    """`<rc>|<stdout>`. Asserting only on the exit code is what let the original defect through, so the shape itself is asserted."""
    result = dv.run_summary(paths.repo_root(), "3", "0")
    assert "|" in result, result
    rc, _, out = result.partition("|")
    assert rc == "0", result
    assert "3 assertions" in out, out


def test_zero_assertions_says_skipped_and_never_passed() -> None:
    """THE 2026-08-05 DEFECT, driven against the live harness. Both halves: the right word present AND the wrong word absent."""
    rc, _, out = dv.run_summary(paths.repo_root(), "0", "0").partition("|")
    assert rc == "0", "a DECLARED skip keeps exit 0; it was the WORD that was wrong"
    assert "SKIPPED" in out, out
    assert "PASSED" not in out, out


def test_a_real_pass_still_says_passed() -> None:
    """THE CONTROL. Without it a harness hard-wired to SKIPPED would satisfy the
    case above, and the whole table would be satisfied by a constant."""
    rc, _, out = dv.run_summary(paths.repo_root(), "3", "0").partition("|")
    assert rc == "0"
    assert "PASSED" in out, out


def test_a_failure_is_loud_and_non_zero() -> None:
    rc, _, out = dv.run_summary(paths.repo_root(), "3", "1").partition("|")
    assert rc == "1"
    assert "FAILED" in out, out


def test_a_selftest_that_did_not_fire_refuses() -> None:
    rc, _, out = dv.run_summary(paths.repo_root(), "3", "0", "1").partition("|")
    assert rc == "1"
    assert "SELFTEST DID NOT FIRE" in out, out


def test_an_undrivable_harness_yields_an_empty_capture(tmp_path: pathlib.Path) -> None:
    """A harness file with no `Drill.summary`: the child exits 97 before printing, so the capture is "" and `assert_verdict`'s empty-result guard names it."""
    (tmp_path / dv.DRILL_LIB).parent.mkdir(parents=True)
    (tmp_path / dv.DRILL_LIB).write_text("NOTHING_HERE = 1\n", encoding="utf-8")
    assert dv.run_summary(tmp_path, "1", "0") == ""


def test_the_driver_runs_the_same_summary_as_an_in_process_drill() -> None:
    """The child's output against `Drill.summary` called in this process, so the driver is shown to test the harness the drills use rather than something of its own.

    THE ELAPSED SECONDS ARE MASKED, and only those: each side renders its own whole-second duration, and two runs straddling a second boundary differ by a clock tick.
    """
    buf = io.StringIO()
    drill = drills_lib.Drill("gatecheck", stdout=buf)
    drill.started_at = int(time.time())
    rc = drill.summary()
    local = "%d|%s" % (rc, buf.getvalue().rstrip("\n"))
    port = dv.run_summary(paths.repo_root(), "0", "0")
    elapsed = re.compile(r"\(\d+s\)")
    assert elapsed.search(local), "the in-process summary printed no elapsed time: %r" % local
    assert elapsed.search(port), "the driven summary printed no elapsed time: %r" % port
    assert elapsed.sub("(<elapsed>)", port) == elapsed.sub("(<elapsed>)", local)


def test_the_byte_tail_flattens_and_keeps_the_last_200_bytes() -> None:
    text = "line one\nline two\n" + "z" * 250
    tail = dv.tail_summary(text)
    assert len(tail.encode()) == 200
    assert tail == ("z" * 199) + " "


def test_the_four_cases() -> None:
    """The decision TABLE, asserted as a table: every row prints the same shape of line, so a changed row is invisible from the output."""
    assert [(c.count, c.fails, c.selftest, c.want_rc, c.want, c.forbid) for c in dv.CASES] == [
        ("0", "0", "0", "0", "SKIPPED", "PASSED"),
        ("3", "0", "0", "0", "PASSED", ""),
        ("3", "1", "0", "1", "FAILED", ""),
        ("3", "0", "1", "1", "SELFTEST DID NOT FIRE", ""),
    ]


def test_selftest_is_green() -> None:
    assert dv.selftest() == 0


def test_the_real_tree_passes() -> None:
    assert dv.main([]) == 0
