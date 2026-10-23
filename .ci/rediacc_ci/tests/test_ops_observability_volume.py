"""observability_volume with a fake transport: counts from the telemetry API, bytes from Loki and Tempo."""

from __future__ import annotations

import io
import json
import urllib.parse
from typing import Any

import pytest

from rediacc_ci.ops import observability_volume as ov

TOKEN = "cfut_SECRET_CF_TOKEN"
GRAFANA_TOKEN = "glsa_SECRET_GRAFANA"
ENV = {"CLOUDFLARE_API_TOKEN": TOKEN, "OBS_GRAFANA_READ_TOKEN": GRAFANA_TOKEN}
END = 1_800_000_000.0


def aggregate(service: str, kind: str, value: int) -> dict:
    return {
        "groups": [
            {"key": "$metadata.service", "value": service},
            {"key": "$metadata.type", "value": kind},
        ],
        "value": value,
    }


class Fake:
    def __init__(
        self, aggregates, loki_bytes=None, loki_lines=None, telemetry_status=200, tempo=True
    ):
        self.aggregates = aggregates
        self.loki_bytes = loki_bytes if loki_bytes is not None else {"a": 1000.0}
        self.loki_lines = loki_lines if loki_lines is not None else {"a": 10.0}
        self.telemetry_status = telemetry_status
        self.tempo = tempo
        self.calls: list[tuple[str, str, dict, Any]] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        if "/telemetry/query" in url:
            if self.telemetry_status != 200:
                return self.telemetry_status, {
                    "success": False,
                    "errors": [{"message": "Authentication error"}],
                }
            return 200, {
                "success": True,
                "result": {"calculations": [{"aggregates": self.aggregates}]},
            }
        parts = urllib.parse.urlsplit(url)
        qs = urllib.parse.parse_qs(parts.query)
        if "/uid/loki/" in url:
            query = qs["query"][0]
            data = self.loki_bytes if "bytes_over_time" in query else self.loki_lines
            return 200, {
                "data": {
                    "result": [
                        {"metric": {"service_name": s}, "value": [END, str(v)]}
                        for s, v in data.items()
                    ]
                }
            }
        if url.endswith("/api/search") or "/api/search?" in url:
            return 200, {"traces": [{"traceID": "t1"}] if self.tempo else []}
        if "/api/traces/t1" in url:
            return 200, {"batches": [{"spanId": "x" * 100}, {"spanId": "y" * 100}]}
        return 404, None


def test_counts_are_grouped_by_service_and_type():
    fake = Fake(
        [aggregate("w1", "span", 5), aggregate("w1", "cf-worker", 3), aggregate("w2", "span", 7)]
    )
    counts = ov.event_counts(fake, ov.cf_headers(ENV), "acct", 0, 1)
    assert counts == {"w1": {"span": 5, "cf-worker": 3}, "w2": {"span": 7}}
    body = fake.calls[0][3]
    assert body["view"] == "calculations"
    assert body["parameters"]["calculations"][0]["operator"] == "count"
    assert [g["value"] for g in body["parameters"]["groupBys"]] == [
        "$metadata.service",
        "$metadata.type",
    ]


def test_bytes_use_the_own_mean_and_fall_back_to_the_all_service_mean():
    rows, fallback = ov.estimate(
        {"a": {"cf-worker": 4}, "b": {"cf-worker": 2}},
        {"a": (1000.0, 10.0)},
        None,
    )
    by = {r["service"]: r for r in rows}
    assert by["a"]["bytes"] == 4 * 100
    assert by["a"]["basis"] == "own"
    assert by["b"]["bytes"] == 2 * 100
    assert by["b"]["basis"] == "all"
    assert fallback is True


def test_spans_and_logs_are_sized_separately():
    rows, fallback = ov.estimate(
        {"a": {"span": 10, "span_event": 2, "cf-worker": 5}}, {"a": (1000.0, 10.0)}, 2000.0
    )
    assert rows[0]["spans"] == 12
    assert rows[0]["logs"] == 5
    assert rows[0]["bytes"] == 12 * 2000 + 5 * 100
    assert fallback is False


def test_projection_scales_the_window_to_thirty_days():
    out = io.StringIO()
    rows = [
        {
            "service": "a",
            "spans": 0,
            "logs": 1,
            "log_mean": 1.0,
            "span_mean": 1.0,
            "basis": "own",
            "bytes": 1e9,
        }
    ]
    ov.render(rows, False, 86400, 7, out)
    text = out.getvalue()
    assert text.count("month=30.0000 GB (60.000% of 50 GB") == 2  # the row and the total
    assert "storage=7.0000 GB (70.000% of 10 GB-month, retention 7 d)" in text


def test_tempo_mean_span_size():
    fake = Fake([])
    size = ov.tempo_span_size(fake, ov.GRAFANA_ORIGIN, GRAFANA_TOKEN, 0, 1)
    assert size is not None
    assert size > 100
    assert ov.tempo_span_size(Fake([], tempo=False), ov.GRAFANA_ORIGIN, GRAFANA_TOKEN, 0, 1) is None


def test_full_run_prints_a_row_per_worker_and_no_secret(capsys):
    fake = Fake([aggregate("a", "span", 10), aggregate("a", "cf-worker", 10)])
    rc = ov.run(ENV, fake, hours=24, end_s=END, retention_days=7)
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.count("\n") == 2
    assert captured.out.startswith("a ")
    assert "TOTAL 1 Workers" in captured.out
    for secret in (TOKEN, GRAFANA_TOKEN):
        assert secret not in captured.out + captured.err
        assert all(secret not in json.dumps([c[0], c[1], c[3]]) for c in fake.calls)


def test_zero_stored_events_is_exit_0_and_says_so(capsys):
    """persist = false means Cloudflare stores nothing; an answered count of zero is that state, not a failed read."""
    assert ov.run(ENV, Fake([]), hours=24, end_s=END, retention_days=7) == 0
    assert "TOTAL 0 Workers" in capsys.readouterr().out


def test_the_telemetry_query_prefers_the_global_key_over_the_scoped_token():
    both = {"CLOUDFLARE_API_TOKEN": "t", "CF_GLOBAL_API_KEY": "k", "CF_EMAIL": "e"}
    assert set(ov.telemetry_headers(both)) == {"X-Auth-Key", "X-Auth-Email"}
    assert ov.cf_headers(both) == {"Authorization": "Bearer t"}, "GraphQL keeps the scoped token"
    assert ov.telemetry_headers({"CLOUDFLARE_API_TOKEN": "t"}) == {"Authorization": "Bearer t"}


def test_a_refused_count_is_exit_1_with_cloudflares_text(capsys):
    rc = ov.run(ENV, Fake([], telemetry_status=403), hours=24, end_s=END, retention_days=7)
    assert rc == 1
    assert "Authentication error" in capsys.readouterr().err


def test_missing_grafana_token_is_exit_2(capsys):
    rc = ov.run({"CLOUDFLARE_API_TOKEN": TOKEN}, Fake([]), hours=24, end_s=END, retention_days=7)
    assert rc == 2
    assert "OBS_GRAFANA_READ_TOKEN" in capsys.readouterr().err


def test_credentials_prefer_the_token_then_the_global_key():
    assert ov.cf_headers({"CLOUDFLARE_API_TOKEN": "t"}) == {"Authorization": "Bearer t"}
    assert set(ov.cf_headers({"CF_GLOBAL_API_KEY": "k", "CF_EMAIL": "e"})) == {
        "X-Auth-Key",
        "X-Auth-Email",
    }
    with pytest.raises(ov.VolumeError):
        ov.cf_headers({})
