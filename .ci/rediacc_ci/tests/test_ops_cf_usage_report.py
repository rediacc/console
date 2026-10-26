"""cf_usage_report with a fake GraphQL and Loki: under budget, one bucket over, the maintenance line, an empty read."""

from __future__ import annotations

import io
import json
import urllib.parse
from datetime import UTC, datetime

import pytest

from rediacc_ci.ops import cf_usage_report as ur

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
TOKEN = "cfut_SECRET_CF_TOKEN"
GRAFANA_TOKEN = "glsa_SECRET_GRAFANA"
ENV = {"CLOUDFLARE_API_TOKEN": TOKEN, "OBS_GRAFANA_READ_TOKEN": GRAFANA_TOKEN}
CEILINGS = {
    "workers_requests_month": 1000,
    "workers_cpu_ms_month": 1000,
    "r2_storage_bytes": 1000,
    "r2_class_a_month": 100,
    "r2_class_b_month": 100,
    "d1_storage_bytes": 1000,
}

DATA = {
    "r2StorageAdaptiveGroups": [
        {
            "dimensions": {"bucketName": "b1"},
            "max": {"payloadSize": 100, "metadataSize": 5, "objectCount": 3},
        },
        {
            "dimensions": {"bucketName": "b1"},
            "max": {"payloadSize": 90, "metadataSize": 5, "objectCount": 2},
        },
    ],
    "r2OperationsAdaptiveGroups": [
        {"dimensions": {"bucketName": "b1", "actionType": "PutObject"}, "sum": {"requests": 10}},
        {"dimensions": {"bucketName": "b1", "actionType": "GetObject"}, "sum": {"requests": 20}},
        {
            "dimensions": {"bucketName": "b1", "actionType": "DeleteObject"},
            "sum": {"requests": 999},
        },
    ],
    "d1StorageAdaptiveGroups": [
        {
            "dimensions": {"databaseId": "d1", "date": "2026-10-21"},
            "max": {"databaseSizeBytes": 50},
        },
        {
            "dimensions": {"databaseId": "d1", "date": "2026-10-22"},
            "max": {"databaseSizeBytes": 70},
        },
    ],
    "workersInvocationsAdaptive": [
        {"dimensions": {"scriptName": "w1"}, "sum": {"requests": 400, "cpuTimeUs": 300_000}},
    ],
    "containersMetricsAdaptiveGroups": [
        {
            "dimensions": {"applicationId": "app1"},
            "sum": {"cpuTimeSec": 10.0, "allocatedMemory": 50 * 2**30},
        },
    ],
}


class Fake:
    def __init__(self, data=None, maintenance=0, loki_down=False, telemetry=None, gql_status=200):
        self.data = dict(DATA if data is None else data)
        self.maintenance = maintenance
        self.loki_down = loki_down
        self.telemetry = telemetry
        self.gql_status = gql_status
        self.calls: list = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, dict(headers), body))
        if url.endswith("/graphql"):
            if self.gql_status != 200:
                return self.gql_status, None
            query = body["query"]
            name = next(k for k in self.data if k in query)
            return 200, {
                "data": {"viewer": {"accounts": [{name: self.data[name]}]}},
                "errors": None,
            }
        if "/uid/loki/" in url:
            if self.loki_down:
                return 502, None
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["query"][0]
            assert ur.MAINTENANCE_LINE in query
            return 200, {"data": {"result": [{"metric": {}, "value": [1, str(self.maintenance)]}]}}
        if "/telemetry/query" in url:
            if self.telemetry is None:
                return 403, {"success": False}
            return 200, {
                "success": True,
                "result": {"calculations": [{"aggregates": [{"value": self.telemetry}]}]},
            }
        return 404, None


def go(fake, ceilings=None):
    out = io.StringIO()
    rc = ur.run(ENV, fake, now=NOW, ceilings=ceilings or dict.fromkeys(CEILINGS, 10**12), out=out)
    return rc, out.getvalue()


def test_under_budget_is_exit_0_and_folds_the_reads():
    rc, text = go(Fake())
    assert rc == 0, text
    assert "r2.bucket.b1.bytes value=105 objects=3" in text  # peak, not a sum of the two groups
    assert "r2.class_a.month value=10 ceiling" in text
    assert "r2.class_b.month value=20 ceiling" in text
    assert "d1.d1.bytes value=70" in text  # the latest day
    assert "workers.w1.requests value=400 cpu_ms=300" in text
    assert "workers.cpu_ms.month value=300 ceiling" in text  # microseconds to milliseconds
    assert "1 buckets, 1 databases, 1 Workers, 1 container apps read; 0 over" in text


def test_one_bucket_over_the_ceiling_is_exit_1_and_named():
    ceilings = dict.fromkeys(CEILINGS, 10**12) | {"r2_storage_bytes": 100}
    rc, text = go(Fake(), ceilings)
    assert rc == 1
    assert "OVER r2.storage.total.bytes value=105 ceiling=100" in text
    assert text.count("OVER") == 1


def test_the_maintenance_line_in_loki_alerts():
    rc, text = go(Fake(maintenance=3))
    assert rc == 1
    assert "ALERT maintenance" in text
    assert "3 times" in text
    assert "(loki)" in text


def test_loki_down_falls_back_to_the_telemetry_query():
    rc, text = go(Fake(loki_down=True, telemetry=2))
    assert rc == 1
    assert "(telemetry-query)" in text
    rc, text = go(Fake(loki_down=True, telemetry=0))
    assert rc == 0
    assert "(telemetry-query)" in text


def test_a_log_count_nobody_could_read_is_exit_2(capsys):
    rc, _ = go(Fake(loki_down=True))
    assert rc == 2
    assert "maintenance line unreadable" in capsys.readouterr().err


def test_an_empty_read_is_exit_2_for_each_kind(capsys):
    for key, label in (
        ("r2StorageAdaptiveGroups", "buckets"),
        ("d1StorageAdaptiveGroups", "databases"),
        ("workersInvocationsAdaptive", "Workers"),
    ):
        rc, _ = go(Fake(data=DATA | {key: []}))
        assert rc == 2
        assert "zero %s read" % label in capsys.readouterr().err


def test_a_failed_graphql_read_is_exit_2(capsys):
    rc, _ = go(Fake(gql_status=403))
    assert rc == 2
    assert "graphql answered 403" in capsys.readouterr().err


def test_no_secret_reaches_the_output_or_a_body(capsys):
    fake = Fake()
    rc, text = go(fake)
    assert rc == 0
    seen = text + capsys.readouterr().err + json.dumps([[c[0], c[1], c[3]] for c in fake.calls])
    assert TOKEN not in seen
    assert GRAFANA_TOKEN not in seen
    assert fake.calls[0][2] == {"Authorization": "Bearer %s" % TOKEN}


def test_ceilings_come_from_the_json_report_object(tmp_path):
    (tmp_path / ".ci/config").mkdir(parents=True)
    (tmp_path / ur.CONFIG_REL).write_text(
        json.dumps({"report": {"r2_storage_bytes": 7, "bogus": 1}})
    )
    got = ur.load_ceilings(tmp_path)
    assert got["r2_storage_bytes"] == 7.0
    assert got["workers_requests_month"] == ur.DEFAULT_CEILINGS["workers_requests_month"]
    assert "bogus" not in got
    assert ur.load_ceilings(tmp_path / "missing") == ur.DEFAULT_CEILINGS


def test_malformed_ceiling_json_is_an_error_not_the_defaults(tmp_path):
    """Review d945e387.3: a present-but-broken config must not silently yield the default ceilings."""
    (tmp_path / ".ci/config").mkdir(parents=True)
    (tmp_path / ur.CONFIG_REL).write_text("{not json")
    with pytest.raises(ur.ReportError, match="not valid JSON"):
        ur.load_ceilings(tmp_path)


def test_container_usage_over_the_ceiling_is_exit_1_and_names_the_cost():
    ceilings = dict.fromkeys(CEILINGS, 10**12) | {"containers_memory_gib_seconds_month": 40}
    rc, text = go(Fake(), ceilings)
    assert rc == 1
    assert "OVER containers.app.app1 gib_seconds=50 (ceiling 40)" in text
    # 50 GiB-s * 0.0000025 + 10 vCPU-s * 0.00002
    assert "est_cost_usd=0.00" in text
    big = {"app1": 4_000_000 * 2**30}
    data = DATA | {
        "containersMetricsAdaptiveGroups": [
            {
                "dimensions": {"applicationId": "app1"},
                "sum": {"cpuTimeSec": 1.0, "allocatedMemory": big["app1"]},
            }
        ]
    }
    rc, text = go(
        Fake(data=data),
        dict.fromkeys(CEILINGS, 10**12) | {"containers_memory_gib_seconds_month": 3_000_000},
    )
    assert rc == 1
    assert "est_cost_usd=10.00" in text


def test_container_usage_under_the_ceilings_is_ok():
    rc, text = go(Fake())
    assert rc == 0, text
    assert "OK   containers.app.app1 gib_seconds=50" in text


def test_no_container_rows_is_ok_and_says_so():
    rc, text = go(Fake(data=DATA | {"containersMetricsAdaptiveGroups": []}))
    assert rc == 0, text
    assert "containers no usage rows" in text


def test_a_failed_container_read_is_exit_2(capsys):
    class Down(Fake):
        def __call__(self, method, url, headers, body):
            if url.endswith("/graphql") and "containersMetricsAdaptiveGroups" in body["query"]:
                return 500, None
            return super().__call__(method, url, headers, body)

    rc, _ = go(Down())
    assert rc == 2
    assert "containers: graphql answered 500" in capsys.readouterr().err


def test_container_total_over_the_account_ceiling_is_exit_1_though_each_app_is_under():
    big = 3_000_000 * 2**30
    rows = [
        {
            "dimensions": {"applicationId": "app%d" % n},
            "sum": {"cpuTimeSec": 1_000_000.0, "allocatedMemory": big},
        }
        for n in range(3)
    ]
    ceilings = dict.fromkeys(CEILINGS, 10**12) | {"containers_total_usd_month": 50}
    rc, text = go(Fake(data=DATA | {"containersMetricsAdaptiveGroups": rows}), ceilings)
    assert rc == 1
    assert "OVER containers.total est_cost_usd=" in text
    assert "OVER containers.app." not in text


def _one_app(usd_memory: float, usd_vcpu: float) -> dict:
    return DATA | {
        "containersMetricsAdaptiveGroups": [
            {
                "dimensions": {"applicationId": "app1"},
                "sum": {
                    "cpuTimeSec": usd_vcpu / ur.CONTAINERS_USD_PER_VCPU_SECOND,
                    "allocatedMemory": usd_memory / ur.CONTAINERS_USD_PER_GIB_SECOND * 2**30,
                },
            }
        ]
    }


# The real per-metric ceilings (each about 50 USD alone) and the per-target dollar ceiling.
TARGET_CEILINGS = dict.fromkeys(CEILINGS, 10**12) | {
    "containers_memory_gib_seconds_month": 20_000_000,
    "containers_vcpu_seconds_month": 2_500_000,
    "containers_target_usd_month": 50,
}


def test_a_target_at_49_usd_memory_plus_49_usd_vcpu_is_over_the_target_ceiling():
    rc, text = go(Fake(data=_one_app(49, 49)), TARGET_CEILINGS)
    assert rc == 1, text
    assert "OVER containers.app.app1" in text
    assert "est_cost_usd=98.00 (ceiling 50.00)" in text


def test_a_target_at_20_usd_memory_plus_20_usd_vcpu_is_not_over():
    rc, text = go(Fake(data=_one_app(20, 20)), TARGET_CEILINGS)
    assert rc == 0, text
    assert "OK   containers.app.app1" in text
