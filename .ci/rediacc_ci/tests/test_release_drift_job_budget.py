"""drift_job: the time spent before main runs comes off the run budget (review 2f7cc3f0.1)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from rediacc_ci.release import drift_job, nightly_tested_edge

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence


def write_lock(path: pathlib.Path) -> pathlib.Path:
    ids = [*nightly_tested_edge.DRIFT_GATE_IDS, *drift_job.CLOCK_GATE_IDS]
    entries = [
        {
            "id": gate,
            "ci": {"kind": "step", "workflow": ".github/workflows/x.yml", "job": "j", "step": gate},
        }
        for gate in ids
    ]
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def test_time_spent_before_main_is_taken_off_the_run_budget(tmp_path: pathlib.Path) -> None:
    lock = write_lock(tmp_path / "lock.json")
    out = tmp_path / "v.json"
    spent = 20 * 60
    started = datetime.now(UTC).timestamp() - spent
    calls: list[float] = []

    def runner(argv: Sequence[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kw["timeout"])
        return subprocess.CompletedProcess(list(argv), 0, "ok\n", "")

    drift_job.main(
        ["--lock", str(lock), "--out", str(out)],
        runner=runner,
        env={drift_job.STARTED_ENV: str(started)},
        clock=lambda: 0.0,
    )
    assert 0 < calls[0] <= drift_job.RUN_BUDGET_S - spent + 5


def test_control_without_a_recorded_start_the_whole_budget_is_available(
    tmp_path: pathlib.Path,
) -> None:
    lock = write_lock(tmp_path / "lock.json")
    calls: list[float] = []

    def runner(argv: Sequence[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kw["timeout"])
        return subprocess.CompletedProcess(list(argv), 0, "ok\n", "")

    drift_job.main(
        ["--lock", str(lock), "--out", str(tmp_path / "v.json")],
        runner=runner,
        env={},
        clock=lambda: 0.0,
    )
    assert calls[0] == drift_job.CHECK_TIMEOUT_S
