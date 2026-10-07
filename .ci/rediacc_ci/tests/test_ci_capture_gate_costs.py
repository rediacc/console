"""`rediacc_ci.ci.capture_gate_costs`, the port of `.ci/scripts/ci/capture-gate-costs.sh`: housekeeping's three capture phases.

The runner is replaced by a small Python program (`FAKE`) through `run_bounded`'s `runner` seam, so the bound, the process-group kill, the live stderr log and the phase verdicts are driven for real with no npx and no network. Each case has its mirror: a hang that is named against a run that is not, a merge that adds against one that keeps a prerequisite once, a rotation failure that writes its rc against one that writes 0.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest

from rediacc_ci.ci import capture_gate_costs as cgc

if TYPE_CHECKING:
    from pathlib import Path

GOOD = {
    "jobs": 1,
    "utilisation": {"cores": 4},
    "gates": [{"id": "a", "status": "ok", "ms": 100, "cpuMs": 90}],
}

# argv[1] is the mode; the remaining argv is the runner's own (args + RUNNER_TAIL), echoed to stderr so the test can see what it was asked.
FAKE = r"""
import json, os, signal, sys, time
mode = sys.argv[1]
print("start " + " ".join(sys.argv[2:]), file=sys.stderr, flush=True)
if mode == "good":
    print(json.dumps(%s))
    sys.exit(1)
if mode == "empty":
    print(json.dumps({"gates": []}))
    sys.exit(0)
if mode == "hang":
    time.sleep(60)
if mode == "stubborn":
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("ignoring SIGTERM", file=sys.stderr, flush=True)
    time.sleep(60)
""" % json.dumps(GOOD)


@pytest.fixture
def fake(tmp_path: Path) -> Path:
    path = tmp_path / "fake_runner.py"
    path.write_text(FAKE, encoding="utf-8")
    return path


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    out = tmp_path / "out"
    logs = tmp_path / "logs"
    out.mkdir(exist_ok=True)
    logs.mkdir(exist_ok=True)
    return {"CAPTURE_DIR": str(out), "RUNNER_TEMP": str(logs), **extra}


def _runner(fake: Path, mode: str) -> dict[str, Any]:
    return {"runner": (sys.executable, str(fake), mode)}


# --------------------------------------------------------------------------- bounds and the kill ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("12m", 720.0), ("32m", 1920.0), ("30s", 30.0), ("1h", 3600.0), ("5", 5.0)],
)
def test_parse_bound_reads_timeouts_spelling(text: str, seconds: float) -> None:
    assert cgc.parse_bound(text) == seconds


@pytest.mark.parametrize("text", ["", "12 minutes", "-1m", "0", "m"])
def test_parse_bound_refuses_anything_else(text: str) -> None:
    with pytest.raises(ValueError, match="duration"):
        cgc.parse_bound(text)


def test_a_run_inside_its_bound_returns_the_runners_own_status(fake: Path, tmp_path: Path) -> None:
    out, log = tmp_path / "o.json", tmp_path / "o.log"
    rc = cgc.run_bounded(30, out, log, ["--quick"], runner=(sys.executable, str(fake), "good"))
    assert rc == 1
    assert json.loads(out.read_text(encoding="utf-8")) == GOOD
    assert "start --quick --jobs 1 --sched slots --json" in log.read_text(encoding="utf-8")


def test_a_hung_run_gets_sigterm_at_its_bound_and_answers_124(fake: Path, tmp_path: Path) -> None:
    started = time.monotonic()
    rc = cgc.run_bounded(
        0.5, tmp_path / "o.json", tmp_path / "o.log", [], runner=(sys.executable, str(fake), "hang")
    )
    assert rc == cgc.TIMED_OUT_TERM
    assert cgc.hung(rc)
    assert time.monotonic() - started < 20


def test_a_run_that_ignores_sigterm_is_killed_and_answers_137(fake: Path, tmp_path: Path) -> None:
    started = time.monotonic()
    rc = cgc.run_bounded(
        0.5,
        tmp_path / "o.json",
        tmp_path / "o.log",
        [],
        runner=(sys.executable, str(fake), "stubborn"),
        kill_after_s=0.5,
    )
    assert rc == cgc.TIMED_OUT_KILL
    assert time.monotonic() - started < 20, "SIGKILL ended it, not the fake's own 60 s sleep"
    assert "ignoring SIGTERM" in (tmp_path / "o.log").read_text(encoding="utf-8")


def test_a_missing_runner_is_127_not_a_hang(tmp_path: Path) -> None:
    rc = cgc.run_bounded(
        5, tmp_path / "o.json", tmp_path / "o.log", [], runner=("/nonexistent/runner",)
    )
    assert rc == 127
    assert not cgc.hung(rc)


# --------------------------------------------------------------------------- phases ---------------------------------------------------------------------------


def test_quick_passes_on_a_usable_capture_despite_gate_reds(
    fake: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _env(tmp_path, CAPTURE_EXTRA_ARGS="--only  check:x")
    assert cgc.phase_quick(env, **_runner(fake, "good")) == 0
    out = capsys.readouterr().out
    assert "run.ts exit 1 (gate reds are expected" in out
    log = (tmp_path / "logs" / "gate-costs-quick.log").read_text(encoding="utf-8")
    assert "start --quick --only check:x --jobs 1" in log


def test_quick_fails_on_a_capture_that_measured_nothing(fake: Path, tmp_path: Path) -> None:
    assert cgc.phase_quick(_env(tmp_path), **_runner(fake, "empty")) == 1


def test_quick_names_a_hang_with_its_bound(
    fake: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _env(tmp_path, QUICK_BOUND="1s")
    assert cgc.phase_quick(env, **_runner(fake, "hang")) == 1
    out = capsys.readouterr().out
    assert (
        "::error title=Gate cost capture hung::the serial ci:quick outlived its 1s bound (exit 124)"
        in out
    )


def test_rotation_never_fails_itself_and_carries_its_verdict_in_rc(
    fake: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "gh_output"
    env = _env(tmp_path, CAPTURE_NIGHT="2", GITHUB_OUTPUT=str(output))
    assert cgc.phase_rotation(env, **_runner(fake, "good")) == 0
    assert output.read_text(encoding="utf-8") == "rc=0\n"
    log = (tmp_path / "logs" / "gate-costs-rotation.log").read_text(encoding="utf-8")
    assert "start --slow-rotation 2/3 --gate-timeout 600 --jobs 1" in log
    assert "slow rotation 2/3" in capsys.readouterr().out

    output.unlink()
    assert cgc.phase_rotation(env, **_runner(fake, "empty")) == 0
    assert output.read_text(encoding="utf-8") == "rc=1\n"


def test_rotation_names_a_hang_and_still_exits_zero(
    fake: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "gh_output"
    env = _env(tmp_path, CAPTURE_NIGHT="3", ROTATION_BOUND="1s", GITHUB_OUTPUT=str(output))
    assert cgc.phase_rotation(env, **_runner(fake, "hang")) == 0
    assert output.read_text(encoding="utf-8") == "rc=124\n"
    assert (
        "::error title=Slow-gate rotation hung::run.ts --slow-rotation 3/3 outlived its 1s bound (exit 124)"
        in capsys.readouterr().out
    )


def test_rotation_with_a_bad_bound_records_a_failure_rather_than_raising(tmp_path: Path) -> None:
    output = tmp_path / "gh_output"
    env = _env(tmp_path, ROTATION_BOUND="soon", GITHUB_OUTPUT=str(output))
    assert cgc.phase_rotation(env) == 0
    assert output.read_text(encoding="utf-8") == "rc=1\n"


def test_rotation_night_follows_the_day_of_year_unless_overridden() -> None:
    jan1 = datetime(2026, 1, 1, tzinfo=UTC)  # day 1
    assert cgc.rotation_night({}, jan1) == 2
    assert cgc.rotation_night({}, datetime(2026, 1, 2, tzinfo=UTC)) == 3
    assert cgc.rotation_night({}, datetime(2026, 1, 3, tzinfo=UTC)) == 1
    assert cgc.rotation_night({"CAPTURE_NIGHT": "1"}, jan1) == 1


def test_merge_adds_the_rotation_gates_once_and_records_the_selection(tmp_path: Path) -> None:
    env = _env(tmp_path, ROTATION_RC="0")
    out = tmp_path / "out"
    quick = dict(GOOD)
    rotation = {
        "selection": "2/3",
        "gates": [
            {"id": "a", "status": "ok", "ms": 999, "cpuMs": 999},
            {"id": "slow", "status": "ok", "ms": 50, "cpuMs": 40},
        ],
    }
    (out / "quick.json").write_text(json.dumps(quick), encoding="utf-8")
    (out / "rotation.json").write_text(json.dumps(rotation), encoding="utf-8")
    assert cgc.phase_merge(env) == 0
    merged = json.loads((out / "gate-costs.json").read_text(encoding="utf-8"))
    assert [g["id"] for g in merged["gates"]] == ["a", "slow"]
    assert merged["gates"][0]["ms"] == 100, (
        "a prerequisite both runs ran is kept from the quick run"
    )
    assert merged["slowRotation"] == {"selection": "2/3", "gates": ["a", "slow"]}
    assert merged["utilisation"] == {"cores": 4}


def test_a_failed_rotation_uploads_the_quick_capture_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    env = _env(tmp_path, ROTATION_RC="124")
    out = tmp_path / "out"
    (out / "quick.json").write_text(json.dumps(GOOD), encoding="utf-8")
    (out / "rotation.json").write_text("not json", encoding="utf-8")
    assert cgc.phase_merge(env) == 0
    assert json.loads((out / "gate-costs.json").read_text(encoding="utf-8")) == GOOD
    assert (
        "::warning::the slow rotation produced no usable capture (rc '124')"
        in capsys.readouterr().out
    )


def test_merge_refuses_an_unreadable_rotation_it_was_told_is_good(tmp_path: Path) -> None:
    env = _env(tmp_path, ROTATION_RC="0")
    out = tmp_path / "out"
    (out / "quick.json").write_text(json.dumps(GOOD), encoding="utf-8")
    (out / "rotation.json").write_text("not json", encoding="utf-8")
    assert cgc.phase_merge(env) == 1


def test_an_unknown_phase_is_usage_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert cgc.main(["sideways"]) == 2
    assert cgc.main([]) == 2
    assert "quick|rotation|merge" in capsys.readouterr().err
