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


# --- the ingest POST ---------------------------------------------------------------------


class FakeConn:
    """An HTTPSConnection stand-in: records each request and answers from a script of statuses or exceptions."""

    def __init__(self, script: list[Any], log: list[dict[str, Any]]) -> None:
        self.script = script
        self.log = log
        self.status = 200

    def request(self, method: str, path: str, body: bytes, headers: dict[str, str]) -> None:
        self.log.append(
            {"method": method, "path": path, "body": json.loads(body), "headers": headers}
        )
        step = self.script[min(len(self.log), len(self.script)) - 1]
        if isinstance(step, Exception):
            raise step
        self.status = step

    def getresponse(self) -> FakeConn:
        return self

    def close(self) -> None:
        return None


def connector(*script: Any) -> tuple[Any, list[dict[str, Any]], list[tuple[str, int]]]:
    log: list[dict[str, Any]] = []
    hosts: list[tuple[str, int]] = []

    def connect(host: str, port: int, *, timeout: float) -> FakeConn:
        assert timeout > 0
        hosts.append((host, port))
        return FakeConn(list(script), log)

    return connect, log, hosts


def verdict_file(tmp_path: pathlib.Path, state: str, detail: str) -> pathlib.Path:
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps({"state": state, "detail": detail, "at": "2026-11-06T02:15:00Z"}))
    return path


def no_sleep(_seconds: float) -> None:
    return None


def test_post_sends_source_state_detail_at_with_the_bearer(tmp_path: pathlib.Path) -> None:
    connect, log, hosts = connector(200)
    rc = drift_job.main(
        ["--post", str(verdict_file(tmp_path, "red", "check:x")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "tok", "OPS_HEALTH_URL": "https://h.example"},
        connect=connect,
    )
    assert rc == 0
    assert hosts == [("h.example", 443)]
    assert log[0]["method"] == "POST"
    assert log[0]["path"] == "/v1/ingest"
    assert log[0]["headers"]["Authorization"] == "Bearer tok"
    assert log[0]["body"] == {
        "source": "drift",
        "state": "red",
        "detail": "check:x",
        "at": "2026-11-06T02:15:00Z",
    }


def test_post_without_the_token_is_refused(tmp_path: pathlib.Path) -> None:
    path = verdict_file(tmp_path, "green", "")
    assert drift_job.main(["--post", str(path), "--source", "drift"], env={}) == 2


def test_post_to_a_non_https_url_is_refused(tmp_path: pathlib.Path) -> None:
    connect, log, _ = connector(200)
    rc = drift_job.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t", "OPS_HEALTH_URL": "http://h.example"},
        connect=connect,
    )
    assert rc == 2
    assert log == []


def test_post_a_missing_verdict_reports_red(tmp_path: pathlib.Path) -> None:
    """The job died before it wrote a verdict: that is `red` at the ingest, never silence under `if: always()`."""
    connect, log, _ = connector(200)
    rc = drift_job.main(
        ["--post", str(tmp_path / "absent.json"), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t"},
        connect=connect,
        sleep=no_sleep,
    )
    assert rc == 0
    assert log[0]["body"]["state"] == "red"
    assert "no verdict" in log[0]["body"]["detail"]


def test_post_state_and_detail_come_from_arguments_for_the_weekly_run() -> None:
    connect, log, _ = connector(200)
    rc = drift_job.main(
        ["--post-state", "red", "--detail", "Quality failure", "--source", "ci-weekly"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t"},
        connect=connect,
    )
    assert rc == 0
    body = log[0]["body"]
    assert (body["source"], body["state"], body["detail"]) == (
        "ci-weekly",
        "red",
        "Quality failure",
    )
    assert body["at"].endswith("Z")


def test_a_failed_post_is_retried_then_fails(tmp_path: pathlib.Path) -> None:
    connect, log, _ = connector(ConnectionError("down"))
    rc = drift_job.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t"},
        connect=connect,
        sleep=no_sleep,
    )
    assert rc == 1
    assert len(log) == drift_job.POST_ATTEMPTS


def test_a_5xx_is_retried_and_a_later_200_succeeds(tmp_path: pathlib.Path) -> None:
    connect, log, _ = connector(502, 200)
    rc = drift_job.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t"},
        connect=connect,
        sleep=no_sleep,
    )
    assert rc == 0
    assert len(log) == 2


def test_a_401_is_not_retried(tmp_path: pathlib.Path) -> None:
    connect, log, _ = connector(401)
    rc = drift_job.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "wrong"},
        connect=connect,
        sleep=no_sleep,
    )
    assert rc == 1
    assert len(log) == 1
