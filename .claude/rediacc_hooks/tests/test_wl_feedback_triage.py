"""The `feedback-triage-due` Stop advisory (box T4 of agent/plans/PLAN-rdc-feedback.md): `wl_feedback_triage.due` names the triage command when the newest ci:quick receipt is red and no triage run has happened since it finished, or when the newest run recorded in the cursor (`.ci/cache/feedback/last-run.json`, written by `rediacc_ci.feedback.client.write_cursor`) is older than 24 h.

REAL FILES: each case builds a throwaway root holding `.ci/rediacc_ci/feedback/triage.py` (the package marker the check looks for), the receipt `.ci/cache/prepush-receipt.json` and the cursor, then runs the function the Stop hook runs. Controls: a green receipt with a 23 h run is silent, a red receipt with a run after it is silent, an absent cursor with a green receipt is silent (no run recorded, so nothing has gone stale), and a tree without the feedback package is silent whatever the receipt says.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import TYPE_CHECKING

import pytest
import wl_feedback_triage as F
import wl_standdown

from rediacc_hooks.tests import wlfix

if TYPE_CHECKING:
    import pathlib

NOW = datetime.datetime(2026, 11, 19, 12, 0, tzinfo=datetime.UTC)


def iso(hours_ago: float) -> str:
    return (NOW - datetime.timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")


def make_root(
    tmp_path: pathlib.Path,
    exit_code: int | None = 0,
    receipt_age_h: float = 1.0,
    run_ages_h: list[float] | None = None,
    package: bool = True,
    cursor_text: str | None = None,
) -> pathlib.Path:
    root = tmp_path / "root"
    cache = root / ".ci" / "cache"
    cache.mkdir(parents=True)
    if package:
        pkg = root / ".ci" / "rediacc_ci" / "feedback"
        pkg.mkdir(parents=True)
        (pkg / "triage.py").write_text("", encoding="utf-8")
    if exit_code is not None:
        (cache / "prepush-receipt.json").write_text(
            json.dumps({"exitCode": exit_code, "finishedAt": iso(receipt_age_h), "head": "a" * 40}),
            encoding="utf-8",
        )
    if cursor_text is not None or run_ages_h is not None:
        (cache / "feedback").mkdir()
        if cursor_text is None:
            regions = {
                "r%d" % i: {"ranAt": iso(age), "since": iso(age + 1)}
                for i, age in enumerate(run_ages_h or [])
            }
            cursor_text = json.dumps({"version": 1, "regions": regions})
        (cache / "feedback" / "last-run.json").write_text(cursor_text, encoding="utf-8")
    return root


def test_a_red_receipt_with_no_run_since_speaks(tmp_path):
    text = F.due(make_root(tmp_path, exit_code=1, receipt_age_h=1, run_ages_h=[3]), now=NOW)
    assert text is not None
    assert "red" in text
    assert F.COMMAND in text


def test_a_red_receipt_with_no_cursor_speaks(tmp_path):
    text = F.due(make_root(tmp_path, exit_code=1), now=NOW)
    assert text is not None
    assert F.COMMAND in text


def test_a_25_hour_old_run_speaks(tmp_path):
    text = F.due(make_root(tmp_path, exit_code=0, run_ages_h=[25]), now=NOW)
    assert text is not None
    assert "25 h" in text
    assert F.COMMAND in text


def test_the_newest_region_run_decides(tmp_path):
    """CONTROL: one stale region beside a 23 h one is not a stale triage; the last run is the newest row."""
    assert F.due(make_root(tmp_path, exit_code=0, run_ages_h=[40, 23]), now=NOW) is None


def test_a_green_receipt_and_a_23_hour_run_are_silent(tmp_path):
    assert F.due(make_root(tmp_path, exit_code=0, run_ages_h=[23]), now=NOW) is None


def test_a_red_receipt_triaged_after_it_is_silent(tmp_path):
    """CONTROL: the run that followed the red receipt already answered it."""
    root = make_root(tmp_path, exit_code=1, receipt_age_h=5, run_ages_h=[2])
    assert F.due(root, now=NOW) is None


def test_an_absent_cursor_with_a_green_receipt_is_silent(tmp_path):
    """CONTROL: no run recorded is no run gone stale, and a green receipt asks for nothing."""
    assert F.due(make_root(tmp_path, exit_code=0), now=NOW) is None
    assert F.due(make_root(tmp_path / "b", exit_code=None), now=NOW) is None


@pytest.mark.parametrize("exit_code", [0, 1])
def test_a_tree_without_the_feedback_package_is_silent(tmp_path, exit_code):
    root = make_root(tmp_path, exit_code=exit_code, run_ages_h=[48], package=False)
    assert F.due(root, now=NOW) is None


def test_an_unreadable_cursor_speaks_and_says_so(tmp_path):
    """A cursor the triage module would refuse is named, never read as a fresh run."""
    text = F.due(make_root(tmp_path, exit_code=0, cursor_text="{not json"), now=NOW)
    assert text is not None
    assert "unreadable" in text


def test_the_advisory_rides_the_allow_queue_at_advise_level():
    source = (wlfix.STOP_DIR / "wl_checks.py").read_text(encoding="utf-8")
    assert 'vadd("feedback-triage-due"' not in source
    assert re.search(r'"feedback-triage-due",\s*_ft,', source)
    table = json.loads((wlfix.STOP_DIR.parent.parent / "config" / "effort.json").read_text("utf-8"))
    assert table["checks"]["feedback-triage-due"] == {"advise": "low"}
    assert "feedback-triage-due" not in wl_standdown.CORE
