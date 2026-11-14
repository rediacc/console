"""The ops-health ingest POST (PLAN-health-checks-local D1): the bearer, the retry rules and the exit codes, driven through `main` with the connection replaced."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from rediacc_ci.release import ops_health_post

if TYPE_CHECKING:
    import pathlib


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
    rc = ops_health_post.main(
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
    assert ops_health_post.main(["--post", str(path), "--source", "drift"], env={}) == 2


def test_post_to_a_non_https_url_is_refused(tmp_path: pathlib.Path) -> None:
    connect, log, _ = connector(200)
    rc = ops_health_post.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t", "OPS_HEALTH_URL": "http://h.example"},
        connect=connect,
    )
    assert rc == 2
    assert log == []


def test_post_a_missing_verdict_reports_red(tmp_path: pathlib.Path) -> None:
    """The job died before it wrote a verdict: that is `red` at the ingest, never silence under `if: always()`."""
    connect, log, _ = connector(200)
    rc = ops_health_post.main(
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
    rc = ops_health_post.main(
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
    rc = ops_health_post.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t"},
        connect=connect,
        sleep=no_sleep,
    )
    assert rc == 1
    assert len(log) == ops_health_post.POST_ATTEMPTS


def test_a_5xx_is_retried_and_a_later_200_succeeds(tmp_path: pathlib.Path) -> None:
    connect, log, _ = connector(502, 200)
    rc = ops_health_post.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "t"},
        connect=connect,
        sleep=no_sleep,
    )
    assert rc == 0
    assert len(log) == 2


def test_a_401_is_not_retried(tmp_path: pathlib.Path) -> None:
    connect, log, _ = connector(401)
    rc = ops_health_post.main(
        ["--post", str(verdict_file(tmp_path, "green", "")), "--source", "drift"],
        env={"OPS_HEALTH_INGEST_TOKEN": "wrong"},
        connect=connect,
        sleep=no_sleep,
    )
    assert rc == 1
    assert len(log) == 1
