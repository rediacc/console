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
        self,
        aggregates,
        loki_bytes=None,
        loki_lines=None,
        telemetry_status=200,
        tempo=True,
        spans=None,
        prom_status=200,
    ):
        self.aggregates = aggregates
        self.spans = spans if spans is not None else {"a": 10.0}
        self.prom_status = prom_status
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
        if "/uid/prometheus/" in url:
            if self.prom_status != 200:
                return self.prom_status, None
            return 200, {
                "data": {
                    "result": [
                        {"metric": {"service": s}, "value": [END, str(v)]}
                        for s, v in self.spans.items()
                    ]
                }
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


def test_spans_and_log_bytes_are_summed_per_worker_and_non_workers_dropped():
    rows, fallback, dropped = ov.estimate(
        {"a": 12.0, "renet-list": 5.0, "rediacc-cli": 1.0},
        {"a": (1000.0, 10.0), "b": (500.0, 5.0)},
        2000.0,
    )
    by = {r["service"]: r for r in rows}
    assert set(by) == {"a", "b"}
    assert by["a"]["bytes"] == 12 * 2000 + 1000
    assert by["b"]["bytes"] == 500
    assert dropped == 2
    assert fallback is False


def test_span_size_falls_back_to_the_log_mean():
    rows, fallback, _ = ov.estimate({"a": 4.0}, {"a": (1000.0, 10.0)}, None)
    assert rows[0]["bytes"] == 4 * 100 + 1000
    assert fallback is True


def test_the_fallback_span_size_ignores_non_worker_log_bytes():
    rows, fallback, _ = ov.estimate(
        {"a": 4.0}, {"a": (1000.0, 10.0), "renet-list": (900000.0, 10.0)}, None
    )
    assert rows[0]["bytes"] == 4 * 100 + 1000
    assert fallback is True


def test_projection_scales_the_window_to_thirty_days():
    out = io.StringIO()
    rows = [
        {
            "service": "a",
            "spans": 0,
            "log_lines": 1,
            "log_bytes": 1e9,
            "span_mean": 1.0,
            "bytes": 1e9,
        }
    ]
    ov.render(rows, False, 86400, 7, out)
    text = out.getvalue()
    assert text.count("month=30.0000 GB (60.000% of 50 GB") == 2  # the row and the total
    assert "storage=7.0000 GB (70.000% of 10 GB-month, retention 7 d)" in text


def test_tempo_span_counts_read_the_spanmetrics_counter():
    fake = Fake([], spans={"w1": 7.0, "w2": 3.0})
    assert ov.tempo_span_counts(fake, ov.GRAFANA_ORIGIN, GRAFANA_TOKEN, 86400, END) == {
        "w1": 7.0,
        "w2": 3.0,
    }
    url = fake.calls[0][1]
    assert "/uid/prometheus/" in url
    assert "traces_spanmetrics_calls_total" in urllib.parse.unquote_plus(url)
    assert "86400s" in urllib.parse.unquote_plus(url)


def test_a_non_numeric_span_count_raises_naming_the_worker():
    fake = Fake([], spans={"w1": "n/a"})
    with pytest.raises(ov.VolumeError, match="prometheus returned a non-numeric value for w1"):
        ov.tempo_span_counts(fake, ov.GRAFANA_ORIGIN, GRAFANA_TOKEN, 86400, END)


def test_a_non_numeric_loki_size_raises_naming_the_service():
    fake = Fake([], loki_bytes={"w1": "n/a"})
    with pytest.raises(ov.VolumeError, match="loki returned a non-numeric value for w1"):
        ov.loki_log_sizes(fake, ov.GRAFANA_ORIGIN, GRAFANA_TOKEN, 86400, END)


def test_the_span_size_fallback_is_the_workers_own_mean_log_line():
    rows, fell_back, _ = ov.estimate(
        {"w1": 2.0}, {"w1": (100.0, 10.0), "renet-list": (900000.0, 10.0)}, None
    )
    assert fell_back
    assert rows[0]["span_mean"] == 10.0


def test_tempo_mean_span_size():
    fake = Fake([])
    size = ov.tempo_span_size(fake, ov.GRAFANA_ORIGIN, GRAFANA_TOKEN, 0, 1)
    assert size is not None
    assert size > 100
    assert ov.tempo_span_size(Fake([], tempo=False), ov.GRAFANA_ORIGIN, GRAFANA_TOKEN, 0, 1) is None


def test_full_run_prints_a_row_per_worker_and_no_secret(capsys):
    fake = Fake([], spans={"a": 10.0, "renet-list": 99.0})
    rc = ov.run(ENV, fake, hours=24, end_s=END, retention_days=7)
    captured = capsys.readouterr()
    assert rc == 0
    assert captured.out.startswith("a ")
    assert "spans=10 " in captured.out
    assert "TOTAL 1 Workers" in captured.out
    assert "1 non-Worker" in captured.out
    assert "OK Cloudflare stored 0 events" in captured.out
    for secret in (TOKEN, GRAFANA_TOKEN):
        assert secret not in captured.out + captured.err
        assert all(secret not in json.dumps([c[0], c[1], c[3]]) for c in fake.calls)


def test_an_empty_window_is_exit_0(capsys):
    assert (
        ov.run(
            ENV,
            Fake([], spans={}, loki_bytes={}, loki_lines={}),
            hours=24,
            end_s=END,
            retention_days=7,
        )
        == 0
    )
    assert "TOTAL 0 Workers" in capsys.readouterr().out


def test_stored_events_at_cloudflare_warn_by_worker_and_stay_exit_0(capsys):
    fake = Fake(
        [aggregate("a", "cf-worker", 4), aggregate("a", "span", 2), aggregate("b", "span", 0)]
    )
    assert ov.run(ENV, fake, hours=24, end_s=END, retention_days=7) == 0
    out = capsys.readouterr().out
    assert "WARN a stored 6 events" in out
    assert "WARN b" not in out


def test_a_refused_cloudflare_check_is_a_note_not_a_failure(capsys):
    rc = ov.run(ENV, Fake([], telemetry_status=403), hours=24, end_s=END, retention_days=7)
    out = capsys.readouterr().out
    assert rc == 0
    assert "NOTE Cloudflare stored-event check skipped" in out
    assert "Authentication error" in out


def test_no_cloudflare_credential_skips_the_check(capsys):
    rc = ov.run(
        {"OBS_GRAFANA_READ_TOKEN": GRAFANA_TOKEN}, Fake([]), hours=24, end_s=END, retention_days=7
    )
    assert rc == 0
    assert (
        "NOTE Cloudflare stored-event check skipped: no Cloudflare credential"
        in capsys.readouterr().out
    )


def test_a_failed_prometheus_read_is_exit_1(capsys):
    rc = ov.run(ENV, Fake([], prom_status=500), hours=24, end_s=END, retention_days=7)
    assert rc == 1
    assert "prometheus" in capsys.readouterr().err


@pytest.mark.parametrize("result", [{}, {"calculations": None}, {"calculations": "x"}])
def test_a_malformed_count_answer_is_a_note_not_a_zero(capsys, result):
    """A result with no calculations list must not read as zero stored events (review 930f0082.2)."""
    inner = Fake([])

    def transport(method, url, headers, body):
        if "/telemetry/query" in url:
            return 200, {"success": True, "result": result}
        return inner(method, url, headers, body)

    assert ov.run(ENV, transport, hours=24, end_s=END, retention_days=7) == 0
    out = capsys.readouterr().out
    assert "no calculations list" in out
    assert "OK Cloudflare stored 0" not in out


def test_the_telemetry_query_prefers_the_global_key_over_the_scoped_token():
    both = {"CLOUDFLARE_API_TOKEN": "t", "CF_GLOBAL_API_KEY": "k", "CF_EMAIL": "e"}
    assert set(ov.telemetry_headers(both)) == {"X-Auth-Key", "X-Auth-Email"}
    assert ov.cf_headers(both) == {"Authorization": "Bearer t"}, "GraphQL keeps the scoped token"
    assert ov.telemetry_headers({"CLOUDFLARE_API_TOKEN": "t"}) == {"Authorization": "Bearer t"}


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
