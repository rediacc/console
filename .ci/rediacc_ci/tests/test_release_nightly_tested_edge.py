"""The weekly fleet run as the test evidence for the stable promotion (PLAN-health-checks-local D4, design D-promote).

CONTROLS: a cancelled drift run never triggers a promotion; a weekly run 9 days old is no evidence (the soak decides); the newest qualifying scheduled run is the one read, never an older green one hiding a newer red.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from rediacc_ci.core import ghx
from rediacc_ci.release import nightly_tested_edge as nte

NOW = datetime(2026, 11, 8, 6, 0, tzinfo=UTC)


def run(
    run_id: int,
    days_old: float,
    conclusion: str = "success",
    *,
    status: str = "completed",
    event: str = "schedule",
) -> dict[str, Any]:
    stamp = (NOW - timedelta(days=days_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "id": run_id,
        "status": status,
        "event": event,
        "conclusion": conclusion,
        "updated_at": stamp,
        "head_sha": f"{run_id:040x}",
    }


@pytest.mark.parametrize("conclusion", ["success", "failure"])
def test_a_drift_run_that_succeeded_or_failed_triggers(conclusion: str) -> None:
    assert nte.drift_run_qualifies(conclusion)[0] is True


@pytest.mark.parametrize(
    "conclusion", ["cancelled", "startup_failure", "timed_out", "skipped", "neutral", ""]
)
def test_control_any_other_drift_conclusion_never_triggers(conclusion: str) -> None:
    ok, reason = nte.drift_run_qualifies(conclusion)
    assert ok is False
    assert "never triggers a promotion" in reason


def test_the_newest_qualifying_run_is_the_evidence() -> None:
    got, reason = nte.weekly_evidence([run(1, 6), run(2, 2), run(3, 4)], NOW)
    assert got is not None
    assert got["id"] == 2
    assert "2 day(s) old" in reason


def test_a_newer_red_run_is_not_hidden_by_an_older_green_one() -> None:
    got, _ = nte.weekly_evidence([run(1, 6, "success"), run(2, 1, "failure")], NOW)
    assert got is not None
    assert (got["id"], got["conclusion"]) == (2, "failure")


def test_control_a_run_nine_days_old_is_no_evidence() -> None:
    got, reason = nte.weekly_evidence([run(1, 9)], NOW)
    assert got is None
    assert "9 days ago" in reason
    assert "8-day limit" in reason


def test_a_run_exactly_at_the_limit_still_counts() -> None:
    got, _ = nte.weekly_evidence([run(1, 8)], NOW)
    assert got is not None


def test_a_cancelled_newer_run_vouches_for_nothing() -> None:
    got, _ = nte.weekly_evidence([run(2, 1, "cancelled"), run(1, 5, "success")], NOW)
    assert got is not None
    assert got["id"] == 1


def test_an_unfinished_or_non_scheduled_run_is_ignored() -> None:
    runs = [run(1, 1, status="in_progress"), run(2, 1, event="push"), run(3, 3)]
    got, _ = nte.weekly_evidence(runs, NOW)
    assert got is not None
    assert got["id"] == 3


def test_no_runs_is_no_evidence() -> None:
    got, reason = nte.weekly_evidence([], NOW)
    assert got is None
    assert "no completed scheduled" in reason


def test_a_run_without_a_readable_time_is_ignored() -> None:
    bad = run(1, 1)
    bad["updated_at"] = "yesterday"
    assert nte.weekly_evidence([bad], NOW)[0] is None


def test_evidence_outputs_for_a_qualifying_run() -> None:
    out = nte.evidence_outputs("o/r", NOW, fetch=lambda _repo: [run(7, 2, "failure")])
    assert (out["conclusion"], out["run_id"], out["head_sha"]) == ("failure", "7", f"{7:040x}")


def test_control_evidence_outputs_for_a_nine_day_old_run_is_none() -> None:
    out = nte.evidence_outputs("o/r", NOW, fetch=lambda _repo: [run(7, 9)])
    assert out["conclusion"] == nte.NO_EVIDENCE
    assert (out["head_sha"], out["run_id"]) == ("", "")


def test_evidence_outputs_when_the_runs_cannot_be_read_is_none() -> None:
    def broken(_repo: str) -> list[dict[str, Any]]:
        raise ghx.GhError(["gh", "api"], 1, "HTTP 502", "server")

    out = nte.evidence_outputs("o/r", NOW, fetch=broken)
    assert out["conclusion"] == nte.NO_EVIDENCE
    assert "could not be read" in out["reason"]


def test_fetch_weekly_runs_asks_for_completed_scheduled_main_runs_of_ci_yml() -> None:
    seen: list[str] = []

    def api(path: str, **_: Any) -> object:
        seen.append(path)
        return {"workflow_runs": [run(1, 1), "junk"]}

    got = nte.fetch_weekly_runs("o/r", api=api)
    assert [r["id"] for r in got] == [1]
    assert seen[0].startswith("repos/o/r/actions/workflows/ci.yml/runs?")
    for part in ("event=schedule", "branch=main", "status=completed"):
        assert part in seen[0]


def test_main_writes_the_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    out = tmp_path / "o.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    monkeypatch.setenv("GITHUB_REPOSITORY", "o/r")
    monkeypatch.setattr(
        nte,
        "evidence_outputs",
        lambda *_a, **_k: {
            "head_sha": "abc",
            "conclusion": "success",
            "run_id": "9",
            "reason": "r",
        },
    )
    assert nte.main([]) == 0
    assert out.read_text(encoding="utf-8").splitlines() == [
        "head_sha=abc",
        "conclusion=success",
        "run_id=9",
    ]


def test_main_needs_the_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    assert nte.main([]) == 1
