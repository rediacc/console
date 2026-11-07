"""The daily drift job (PLAN-health-checks-local D1): its set is computed, never listed twice, and its verdict is one JSON plus one exit code.

CONTROLS: a lock missing one drift id exits 2 (DriftSetError); one planted red gate exits 1 with that gate named in the JSON. Both are driven through `main` with the commands replaced, because the claim is what the job DECIDES from a result, and each gate has its own tests.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.release import drift_job, nightly_tested_edge

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Sequence


def write_lock(path: pathlib.Path, ids: Sequence[str]) -> pathlib.Path:
    entries = [
        {
            "id": gate,
            "ci": {"kind": "step", "workflow": ".github/workflows/x.yml", "job": "j", "step": gate},
        }
        for gate in ids
    ]
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


def full_ids() -> list[str]:
    return [*nightly_tested_edge.DRIFT_GATE_IDS, *drift_job.CLOCK_GATE_IDS]


def green(argv: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(list(argv), 0, "ok\n", "")


def test_the_set_is_the_drift_ids_plus_the_clock_ids_plus_the_two_split_steps(
    tmp_path: pathlib.Path,
) -> None:
    lock = write_lock(tmp_path / "lock.json", full_ids())
    names = [check.name for check in drift_job.drift_set(lock)]
    assert names[: len(nightly_tested_edge.DRIFT_GATE_IDS)] == list(
        nightly_tested_edge.DRIFT_GATE_IDS
    )
    for gate in drift_job.CLOCK_GATE_IDS:
        assert names.count(gate) == 1
    for step in nightly_tested_edge.SPLIT_DRIFT_STEPS:
        assert names.count(step) == 1
    assert len(names) == len(set(names))


def test_a_clock_id_already_in_the_drift_set_runs_once(tmp_path: pathlib.Path) -> None:
    lock = write_lock(tmp_path / "lock.json", full_ids())
    extra = nightly_tested_edge.DRIFT_GATE_IDS[0]
    assert (
        sum(
            1
            for check in drift_job.drift_set(lock, clock_ids=(extra, *drift_job.CLOCK_GATE_IDS))
            if check.name == extra
        )
        == 1
    )


def test_control_a_lock_missing_one_drift_id_exits_2(tmp_path: pathlib.Path) -> None:
    ids = full_ids()
    missing = ids.pop(0)
    lock = write_lock(tmp_path / "lock.json", ids)
    out = tmp_path / "verdict.json"
    rc = drift_job.main(["--lock", str(lock), "--out", str(out)], runner=green)
    assert rc == 2
    assert not out.exists()
    with pytest.raises(nightly_tested_edge.DriftSetError, match=missing):
        drift_job.drift_set(lock)


def test_a_lock_missing_a_clock_id_exits_2(tmp_path: pathlib.Path) -> None:
    ids = [gate for gate in full_ids() if gate != drift_job.CLOCK_GATE_IDS[0]]
    lock = write_lock(tmp_path / "lock.json", ids)
    assert (
        drift_job.main(["--lock", str(lock), "--out", str(tmp_path / "v.json")], runner=green) == 2
    )


def test_an_unreadable_lock_exits_2(tmp_path: pathlib.Path) -> None:
    assert (
        drift_job.main(
            ["--lock", str(tmp_path / "absent.json"), "--out", str(tmp_path / "v.json")],
            runner=green,
        )
        == 2
    )


def test_all_green_exits_0_and_writes_every_check(tmp_path: pathlib.Path) -> None:
    lock = write_lock(tmp_path / "lock.json", full_ids())
    out = tmp_path / "verdict.json"
    assert drift_job.main(["--lock", str(lock), "--out", str(out)], runner=green) == 0
    verdict = json.loads(out.read_text(encoding="utf-8"))
    assert verdict["ok"] is True
    assert verdict["state"] == "green"
    assert len(verdict["checks"]) == len(drift_job.drift_set(lock))
    assert {c["rc"] for c in verdict["checks"]} == {0}


def test_control_one_planted_red_gate_exits_1_and_is_named(tmp_path: pathlib.Path) -> None:
    lock = write_lock(tmp_path / "lock.json", full_ids())
    out = tmp_path / "verdict.json"
    planted = nightly_tested_edge.DRIFT_GATE_IDS[2]

    def runner(argv: Sequence[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        if planted in argv:
            return subprocess.CompletedProcess(list(argv), 1, "", "advisory published\n")
        return green(argv, **kw)

    assert drift_job.main(["--lock", str(lock), "--out", str(out)], runner=runner) == 1
    verdict = json.loads(out.read_text(encoding="utf-8"))
    assert verdict["ok"] is False
    assert verdict["state"] == "red"
    assert [c["name"] for c in verdict["checks"] if c["rc"] != 0] == [planted]
    assert planted in verdict["detail"]
    assert (
        "advisory published" in next(c for c in verdict["checks"] if c["name"] == planted)["tail"]
    )


def test_a_command_that_cannot_start_is_red_not_a_crash(tmp_path: pathlib.Path) -> None:
    lock = write_lock(tmp_path / "lock.json", full_ids())
    out = tmp_path / "verdict.json"

    def runner(_argv: Sequence[str], **_: Any) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("npm")

    assert drift_job.main(["--lock", str(lock), "--out", str(out)], runner=runner) == 1
    verdict = json.loads(out.read_text(encoding="utf-8"))
    assert {c["rc"] for c in verdict["checks"]} == {127}


def test_only_runs_the_named_checks(tmp_path: pathlib.Path) -> None:
    lock = write_lock(tmp_path / "lock.json", full_ids())
    out = tmp_path / "verdict.json"
    only = drift_job.CLOCK_GATE_IDS[1]
    assert (
        drift_job.main(["--lock", str(lock), "--out", str(out), "--only", only], runner=green) == 0
    )
    assert [c["name"] for c in json.loads(out.read_text(encoding="utf-8"))["checks"]] == [only]


def test_an_unknown_only_name_exits_2(tmp_path: pathlib.Path) -> None:
    lock = write_lock(tmp_path / "lock.json", full_ids())
    assert (
        drift_job.main(
            ["--lock", str(lock), "--out", str(tmp_path / "v.json"), "--only", "nope"], runner=green
        )
        == 2
    )


def test_the_real_lock_yields_a_set() -> None:
    names = [check.name for check in drift_job.drift_set()]
    assert "check:ci-security-audit" in names
    assert nightly_tested_edge.OBS_UPSTREAM_STEP in names
    assert nightly_tested_edge.GOVULNCHECK_STEP in names


def test_control_a_spent_budget_records_the_rest_red_unrun_and_still_writes(
    tmp_path: pathlib.Path,
) -> None:
    # CONTROL for review bc59d04d.3: the run budget, not the job timeout, ends a slow run,
    # so the verdict file exists for the ingest step.
    lock = write_lock(tmp_path / "lock.json", full_ids())
    out = tmp_path / "v.json"
    ticks = iter(
        [0.0, 0.0, float(drift_job.RUN_BUDGET_S + 1)] + [float(drift_job.RUN_BUDGET_S + 1)] * 200
    )
    calls: list[float] = []

    def runner(argv: Sequence[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(kw["timeout"])
        return subprocess.CompletedProcess(list(argv), 0, "ok\n", "")

    rc = drift_job.main(
        ["--lock", str(lock), "--out", str(out)], runner=runner, clock=lambda: next(ticks)
    )
    assert rc == 1
    verdict = json.loads(out.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert calls[0] <= drift_job.CHECK_TIMEOUT_S
    unrun = [c for c in verdict["checks"] if c["rc"] == 124]
    assert unrun
    assert len(unrun) == len(verdict["checks"]) - 1
    assert all("run budget" in c["tail"] for c in unrun)
