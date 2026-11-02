"""proxy_job_cost with a recorded GraphQL response: sums, empty read, GraphQL error, one-row control."""

from __future__ import annotations

import io
from typing import Any

import pytest

from rediacc_ci.ops import proxy_job_cost as pc

ENV = {"CLOUDFLARE_API_TOKEN": "cfut_SECRET_CF_TOKEN"}
ARGS: dict[str, Any] = {
    "script": "rediacc-proxy-bench",
    "start": "2026-10-29T10:00:00Z",
    "end": "2026-10-29T11:00:00Z",
}


def _do(requests, wall, p50, p99, errors=0):
    return {
        "dimensions": {"scriptName": "rediacc-proxy-bench"},
        "sum": {"requests": requests, "errors": errors, "wallTime": wall},
        "quantiles": {"wallTimeP50": p50, "wallTimeP99": p99},
    }


def _container(app, seconds):
    return {"dimensions": {"applicationId": app}, "sum": {"cpuTimeSec": seconds}}


class _Transport:
    def __init__(self, do_rows, container_rows, errors, status):
        self.do_rows, self.container_rows = do_rows, container_rows
        self.errors, self.status = errors, status
        self.seen: list[tuple] = []

    def __call__(self, method, url, headers, body):
        self.seen.append((method, url, dict(headers), body))
        if "durableObjectsInvocationsAdaptiveGroups" in body["query"]:
            key, rows = "do", self.do_rows
        else:
            key, rows = "c", self.container_rows
        if self.errors:
            return self.status, {"data": None, "errors": [{"message": self.errors}]}
        return self.status, {"data": {"viewer": {"accounts": [{key: rows}]}}, "errors": None}


def _transport(do_rows, container_rows, *, errors=None, status=200):
    return _Transport(do_rows, container_rows, errors, status)


def _run(transport, **extra):
    out = io.StringIO()
    rc = pc.run(ENV, transport, out=out, **{**ARGS, **extra})
    return rc, out.getvalue()


def test_recorded_response_yields_sums():
    t = _transport(
        [
            _do(100, 4_000_000, 20_000, 300_000, errors=2),
            _do(300, 8_000_000, 40_000, 900_000, errors=1),
        ],
        [_container("app1", 10.5), _container("app2", 4.0)],
    )
    rc, out = _run(t)
    assert rc == 0
    assert "requests=400 errors=3 wall_ms_sum=12000.0 wall_ms_p50=35.0 wall_ms_p99=900.0" in out
    assert "container active_seconds=14.50 rows=2 scope=all" in out
    assert t.seen[0][2]["Authorization"] == "Bearer cfut_SECRET_CF_TOKEN"
    assert t.seen[0][3]["variables"]["n"] == "rediacc-proxy-bench"
    assert "cfut_SECRET" not in out


def test_application_filter_scopes_containers():
    t = _transport([_do(1, 1000, 1000, 1000)], [_container("app1", 10.5), _container("app2", 4.0)])
    rc, out = _run(t, applications=["app2"])
    assert rc == 0
    assert "container active_seconds=4.00 rows=1 scope=listed" in out


def test_empty_response_exits_2(capsys):
    rc, out = _run(_transport([], []))
    assert rc == 2
    assert out == ""
    assert "zero Durable Object rows" in capsys.readouterr().err


def test_graphql_error_exits_2(capsys):
    rc, out = _run(_transport([], [], errors="unknown field wallTime"))
    assert rc == 2
    assert out == ""
    assert "unknown field wallTime" in capsys.readouterr().err


def test_http_failure_exits_2():
    rc, _ = _run(_transport([], [], status=500, errors="boom"))
    assert rc == 2


def test_missing_credential_exits_2(capsys):
    rc = pc.run({}, _transport([_do(1, 1, 1, 1)], []), out=io.StringIO(), **ARGS)
    assert rc == 2
    assert "no Cloudflare credential" in capsys.readouterr().err


def test_control_one_row_prints_that_row():
    rc, out = _run(_transport([_do(7, 7_000, 1_000, 2_000, errors=1)], []))
    assert rc == 0
    assert "requests=7 errors=1 wall_ms_sum=7.0 wall_ms_p50=1.0 wall_ms_p99=2.0" in out
    assert "container active_seconds=0.00 rows=0" in out


@pytest.mark.parametrize("bad", ["2026-10-29", "yesterday"])
def test_bad_timestamp_exits_2(bad):
    assert pc.main(["--script", "s", "--from", bad, "--to", "2026-10-29T11:00:00Z"]) == 2
