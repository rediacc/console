"""Port of `.ci/scripts/test/gates/test-nightly-retry-filters.sh`, retired in W7 P5.

The nightly retry's FILTERS are the whole feature, so they are what this tests.

Measured baseline, three days of rediacc/console runs: 589 success, 230 skipped, 117 cancelled, 64 failure -- and 63 of the 64 are watchdog-monitor.yml failing BY DESIGN (it cancels the run it monitors, then core.setFailed()s to signal that). Exactly ONE genuine failure. A sweeper without these filters retries 63 deliberate failures, and if it also accepted `cancelled` it would
revive 117 superseded pipelines.

So every assertion below is a MEASURED false positive, not a hypothetical:
  - cancelled is the superseded shape (117 of them)
  - the watchdog fails on purpose (63 of them)
  - a dead head is superseded by another route
  - an attempt-capped run is not going to be fixed by a fourth rerun

HERMETIC: `gh` is shimmed inside `tmp_path` and put on PATH for the subprocess only. A gate that needs GitHub up is a gate that gets skipped during exactly the outage that produces retryable failures.

WHAT THIS CANNOT SEE: it drives the script's decisions, not GitHub's rerun semantics. It cannot prove `rerun-failed-jobs` does the right thing, and it cannot prove a retried workflow is idempotent -- that is a review question.
"""

import datetime
import json
import os
import pathlib

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

SUT = paths.from_root(".ci", "rediacc_ci", "housekeeping", "retry_failed_runs.py")

LIVE_SHA = "a" * 40
DEAD_SHA = "b" * 40

# A gh that answers branches, the run list, and records every rerun POST so the
# case can assert on what was ATTEMPTED rather than on what was printed.
FAKE_GH = """#!/bin/bash
args="$*"
case "$args" in
  *branches*)      echo "%(live)s" ;;
  *rerun-failed-jobs*)
      echo "$args" | grep -oE 'runs/[0-9]+' | cut -d/ -f2 >> "%(reran)s"
      echo '{}' ;;
  *actions/runs*)  cat "%(runs)s" ;;
  *) echo '{}' ;;
esac
"""

# The branch lookup FAILS. Anything that reruns anyway is retrying blind.
FAKE_GH_NO_BRANCHES = """#!/bin/bash
case "$*" in
  *branches*) exit 1 ;;
  *rerun-failed-jobs*) echo "BAD" >> "%(reran)s"; echo '{}' ;;
  *) echo '[]' ;;
esac
"""


def now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def old_iso() -> str:
    stamp = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)
    return stamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_record(run_id: int, name: str, path: str, sha: str, attempt: int, created: str) -> dict:
    return {
        "id": run_id,
        "name": name,
        "path": path,
        "head_sha": sha,
        "run_attempt": attempt,
        "created_at": created,
    }


class Fixture:
    """The shimmed `gh`, the recorded reruns, and a driver for the subject."""

    def __init__(self, gate, tmp_path: pathlib.Path) -> None:
        if not SUT.is_file():
            gate.log_fail("subject under test is missing: %s" % SUT)
        harness.require_tool("python3", "install python3; the subject is a Python module")
        self.gate = gate
        self.root = tmp_path
        self.bindir = tmp_path / "bin"
        self.bindir.mkdir(exist_ok=True)
        self.reran = tmp_path / "reran"
        self.runs = tmp_path / "runs.json"

    def fake_gh(self, records: list[dict]) -> None:
        self.reran.write_text("", encoding="utf-8")
        self.runs.write_text(json.dumps(records), encoding="utf-8")
        shim = self.bindir / "gh"
        shim.write_text(
            FAKE_GH % {"live": LIVE_SHA, "reran": self.reran, "runs": self.runs},
            encoding="utf-8",
        )
        shim.chmod(0o755)

    def fake_gh_without_branches(self) -> None:
        self.reran.write_text("", encoding="utf-8")
        shim = self.bindir / "gh"
        shim.write_text(FAKE_GH_NO_BRANCHES % {"reran": self.reran}, encoding="utf-8")
        shim.chmod(0o755)

    def run(self, script: pathlib.Path | None = None) -> harness.RunResult:
        return harness.run(
            ["python3", str(script or SUT)],
            env={
                "PATH": "%s%s%s" % (self.bindir, os.pathsep, os.environ.get("PATH", "")),
                "PYTHONPATH": str(paths.from_root(".ci")),
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            timeout=300,
        )

    def reran_ids(self) -> str:
        if not self.reran.is_file():
            return ""
        return " ".join(self.reran.read_text(encoding="utf-8").split())


def source(gate) -> str:
    if not SUT.is_file():
        gate.log_fail("subject under test is missing: %s" % SUT)
    return SUT.read_text(encoding="utf-8")


def test_watchdog_is_excluded_by_path(gate, tmp_path):
    """A watchdog run must NOT be retried (63 of 64 failures are these)."""
    fx = Fixture(gate, tmp_path)
    fx.fake_gh(
        [
            run_record(
                1,
                "Watchdog: run 999 (gen 3)",
                ".github/workflows/watchdog-monitor.yml",
                LIVE_SHA,
                1,
                now_iso(),
            )
        ]
    )
    fx.run()
    if fx.reran_ids():
        gate.log_fail("a by-design watchdog failure was retried: %s" % fx.reran_ids())
    gate.log_pass("watchdog excluded by path")


def test_name_match_would_not_have_worked(gate):
    """Exclusion must key on PATH, because the display name is generated."""
    text = source(gate)
    if "watchdog-monitor.yml" not in text:
        gate.log_fail("the watchdog path is not excluded at all")
    # A name-based exclusion is unwritable: the name carries a run id and a generation number, so no literal can match it.
    if "EXCLUDED_PATHS" not in text and "is_excluded" not in text:
        gate.log_fail("exclusion is not path-based; a generated display name cannot be matched")
    gate.log_pass("exclusion is path-keyed")


def test_genuine_failure_on_live_head_is_retried(gate, tmp_path):
    fx = Fixture(gate, tmp_path)
    fx.fake_gh(
        [
            run_record(
                42,
                "Cleanup PR Preview",
                ".github/workflows/cleanup-preview.yml",
                LIVE_SHA,
                1,
                now_iso(),
            )
        ]
    )
    fx.run()
    if fx.reran_ids() != "42":
        gate.log_fail("expected run 42 retried, got: '%s'" % fx.reran_ids())
    gate.log_pass("the measured real case (Cleanup PR Preview) is retried")


def test_dead_head_is_skipped(gate, tmp_path):
    """A run whose head is no longer a branch tip must be skipped."""
    fx = Fixture(gate, tmp_path)
    fx.fake_gh([run_record(43, "Console CI", ".github/workflows/ci.yml", DEAD_SHA, 1, now_iso())])
    fx.run()
    if fx.reran_ids():
        gate.log_fail("a superseded head was revived: %s" % fx.reran_ids())
    gate.log_pass("dead head skipped")


def test_attempt_cap_is_honoured(gate, tmp_path):
    fx = Fixture(gate, tmp_path)
    fx.fake_gh([run_record(44, "Console CI", ".github/workflows/ci.yml", LIVE_SHA, 3, now_iso())])
    fx.run()
    if fx.reran_ids():
        gate.log_fail("a run at the attempt cap was retried again: %s" % fx.reran_ids())
    gate.log_pass("attempt cap honoured")


def test_age_floor_is_honoured(gate, tmp_path):
    fx = Fixture(gate, tmp_path)
    fx.fake_gh([run_record(45, "Console CI", ".github/workflows/ci.yml", LIVE_SHA, 1, old_iso())])
    fx.run()
    if fx.reran_ids():
        gate.log_fail("a 10-day-old run was retried: %s" % fx.reran_ids())
    gate.log_pass("age floor honoured")


def test_only_failure_status_is_queried(gate):
    """cancelled must never enter the candidate set (117 superseded runs)."""
    text = source(gate)
    if "status=failure" not in text:
        gate.log_fail("the run query is not restricted to status=failure")
    for bad in ("status=cancelled", "status=completed"):
        if bad in text:
            gate.log_fail("the query would pull cancelled/completed runs into the candidate set")
    gate.log_pass("query is failure-only")


def test_fails_closed_without_branch_list(gate, tmp_path):
    """An unreadable branch list must SKIP, not retry blind."""
    fx = Fixture(gate, tmp_path)
    fx.fake_gh_without_branches()
    fx.run()
    if fx.reran_ids():
        gate.log_fail("retried with no way to tell a superseded head from a live one")
    gate.log_pass("unreadable branch list skips the sweep")


def test_summary_always_reports(gate, tmp_path):
    """A legitimate zero must be distinguishable from a broken sweeper."""
    fx = Fixture(gate, tmp_path)
    fx.fake_gh(
        [
            run_record(
                1,
                "Watchdog: run 9 (gen 1)",
                ".github/workflows/watchdog-monitor.yml",
                LIVE_SHA,
                1,
                now_iso(),
            )
        ]
    )
    result = fx.run()
    gate.assert_contains(
        result.combined, "considered=", "no breakdown printed; 0 retried reads as broken"
    )
    gate.assert_contains(result.combined, "excluded=1", "the breakdown does not say WHY it skipped")
    gate.log_pass("summary reports the breakdown, not just a count")


def test_control_removing_the_watchdog_filter_is_caught(gate, tmp_path):
    """CONTROL: without the path filter, the watchdog IS retried.

    A real BEHAVIOURAL control, not a file-differs check. The override is inserted immediately after the genuine `is_excluded` definition -- appending it at the end of the file would define it AFTER the loop already ran, so the mutant would behave identically and the control would pass against unmutated behaviour. That is the vacuity this repo's control-vacuity gate exists to
    catch, and it is easy to write by accident.
    """
    fx = Fixture(gate, tmp_path)
    mutant = tmp_path / "mutant.py"
    # The twin's `is_excluded() { ... }` became a `def`, so the plant is a SECOND definition that rebinds the name. It goes BEFORE the `if __name__` line and not at the end of the file: an override appended after the entry point is defined too late to affect the run it is supposed to change, and the control would then report a pass for a mutation that never happened.
    text = source(gate)
    anchor = "def is_excluded(path: str) -> bool:\n"
    if text.count(anchor) != 1:
        gate.log_fail("CONTROL ANCHOR MOVED: %r is not in the subject exactly once" % anchor)
    entry = 'if __name__ == "__main__":'
    if text.count(entry) != 1:
        gate.log_fail("CONTROL ANCHOR MOVED: the subject has no single entry-point guard")
    override = "def is_excluded(path: str) -> bool:\n    del path\n    return False\n\n\n"
    mutant.write_text(text.replace(entry, override + entry), encoding="utf-8")
    if "    return False\n" not in mutant.read_text(encoding="utf-8"):
        gate.log_fail("CONTROL WAS NOT PLANTED: the mutant is unmodified")

    fx.fake_gh(
        [
            run_record(
                1,
                "Watchdog: run 9 (gen 1)",
                ".github/workflows/watchdog-monitor.yml",
                LIVE_SHA,
                1,
                now_iso(),
            )
        ]
    )
    fx.run(mutant)
    if fx.reran_ids() != "1":
        gate.log_fail("CONTROL DID NOT FIRE: mutant skipped it too (reran='%s')" % fx.reran_ids())
    gate.log_pass("control fires: the mutant retries the watchdog the real script skips")
