"""d1_size_report with a recorded-response fake of the D1 query API and the AE SQL client."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime

from rediacc_ci.ops import d1_size_report as sr

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
TOKEN = "cfut_SECRET_D1_TOKEN"
ENV = {"CLOUDFLARE_API_TOKEN": TOKEN, "CLOUDFLARE_ACCOUNT_ID": "acct"}
REGIONS = [
    {"id": "eu", "database": "account-eu"},
    {"id": "us", "database": "account-us"},
]


class FakeD1:
    """Answers the lookup and each query shape the module sends, from per-region numbers."""

    def __init__(self, regions: dict[str, dict], down: tuple[str, ...] = ()) -> None:
        self.regions = regions
        self.down = down
        self.calls: list[tuple[str, str, object]] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, body))
        assert headers["Authorization"] == "Bearer %s" % TOKEN
        if method == "GET":
            name = url.rsplit("name=", 1)[1]
            region = name.removeprefix("account-")
            return 200, {"success": True, "result": [{"name": name, "uuid": "uuid-" + region}]}
        region = url.split("/database/")[1].split("/")[0].removeprefix("uuid-")
        if region in self.down:
            return 0, None
        spec = self.regions[region]
        sql = body["sql"]
        if "sqlite_master" in sql:
            rows = [{"name": t} for t in spec["tables"]]
        elif sql.startswith("PRAGMA"):
            rows = [{"name": "id"}, {"name": "data"}]
        elif "FROM subscriptions" in sql:
            rows = [{"n": spec["tenants"]}]
        elif "FROM event_log" in sql:
            rows = [{"n": spec["telemetry"]}]
        elif sql.startswith("SELECT count(*) AS n, ") or "sum(length" in sql:
            table = sql.rsplit("FROM ", 1)[1].strip('"')
            rows_n, bytes_n = spec["tables"][table]
            rows = [{"n": rows_n, "c0": bytes_n // 2, "c1": bytes_n - bytes_n // 2}]
        else:
            rows = [{"one": 1}]
        return 200, {
            "success": True,
            "result": [{"results": rows, "meta": {"size_after": spec["file"]}}],
        }


def region(tenants: int, file: int, telemetry: int = 0) -> dict:
    return {
        "tenants": tenants,
        "file": file,
        "telemetry": telemetry,
        "tables": {"event_log": (10, 1000), "subscriptions": (tenants, 500)},
    }


def run(fake: FakeD1, **kwargs):
    out = io.StringIO()
    rc = sr.run_report(ENV, fake, regions=REGIONS, out=out, **kwargs)
    return rc, out.getvalue()


def test_below_both_thresholds_is_quiet():
    fake = FakeD1({"eu": region(24_999, 4_999_999_999), "us": region(10, 1_000_000)})
    rc, out = run(fake)
    assert rc == 0
    assert "none" in out
    assert "UNREACHABLE" not in out


def test_tenants_at_threshold_alerts():
    fake = FakeD1({"eu": region(25_000, 1_000_000), "us": region(10, 1_000_000)})
    rc, out = run(fake)
    assert rc == 3
    assert "tenants 25000 >= 25000" in out


def test_file_size_at_five_gb_alerts():
    fake = FakeD1({"eu": region(10, 5_000_000_000), "us": region(10, 1_000_000)})
    rc, out = run(fake)
    assert rc == 3
    assert "file 5000000000 B" in out


def test_unreachable_region_is_named_and_exits_2(capsys):
    fake = FakeD1({"eu": region(25_000, 1), "us": region(10, 1)}, down=("us",))
    rc, out = run(fake)
    err = capsys.readouterr().err
    assert rc == 2
    assert "unreachable: us" in err
    assert "| us | - | - | - | UNREACHABLE |" in out


def test_region_flag_limits_the_read():
    fake = FakeD1({"eu": region(1, 1), "us": region(30_000, 1)})
    rc, out = run(fake, region="eu")
    assert rc == 0
    assert "| us |" not in out
    assert all("uuid-us" not in url and "account-us" not in url for _, url, _ in fake.calls)


def test_unknown_region_exits_2(capsys):
    rc, _ = run(FakeD1({}), region="mars")
    assert rc == 2
    assert "unknown region mars" in capsys.readouterr().err


def test_value_bytes_and_estimate_and_json(tmp_path):
    fake = FakeD1({"eu": region(4, 2_000_000), "us": region(1, 1)})
    json_out = tmp_path / "r.json"
    md_out = tmp_path / "r.md"
    rc, out = run(fake, json_out=json_out, md_out=md_out)
    assert rc == 0
    data = json.loads(json_out.read_text())
    eu = next(r for r in data["regions"] if r["region"] == "eu")
    assert eu["tables"]["event_log"] == {"rows": 10, "value_bytes": 1000, "estimated_bytes": 1600}
    assert eu["tenants"] == 4
    assert eu["file_bytes"] == 2_000_000
    assert eu["bytes_per_tenant"] == 500_000
    assert md_out.read_text() == out
    assert TOKEN not in out


def test_names_come_only_from_regions_json():
    names = sr.load_regions()
    assert {r["id"] for r in names} >= {"eu", "us", "asia"}
    assert all(r["database"].startswith("account-") for r in names)


class _AeClient:
    """A fake AE SQL client recording each query."""

    def __init__(self, value) -> None:
        self.value = value
        self.seen: list[str] = []

    def __call__(self, _account, sql):
        self.seen.append(sql)
        return [{"n": self.value}]


def ae_returning(value):
    return _AeClient(value)


def compare(fake, ae, **kwargs):
    out = io.StringIO()
    rc = sr.run_compare(ENV, fake, ae, days=7, regions=REGIONS, now=NOW, out=out, **kwargs)
    return rc, out.getvalue()


def test_compare_within_two_percent_exits_0():
    fake = FakeD1({"eu": region(1, 1, telemetry=1000), "us": region(1, 1, telemetry=1000)})
    ae = ae_returning(1020)
    rc, out = compare(fake, ae)
    assert rc == 0
    assert out.count("OK  ") == 2
    sql = ae.seen[0]
    assert "blob1 LIKE 'cli.%'" in sql
    assert "'config.pull', 'config.version.read'" in sql
    assert "INTERVAL '7' DAY" in sql
    assert "telemetry_eu" in sql


def test_compare_outside_two_percent_exits_1():
    fake = FakeD1({"eu": region(1, 1, telemetry=1000), "us": region(1, 1, telemetry=1000)})
    rc, out = compare(fake, ae_returning(1021))
    assert rc == 1
    assert "OFF  eu d1=1000 ae=1021" in out


def test_compare_one_region_and_d1_window():
    fake = FakeD1({"eu": region(1, 1, telemetry=50), "us": region(1, 1, telemetry=0)})
    rc, _ = compare(fake, ae_returning(50), region="eu")
    assert rc == 0
    window = [b["sql"] for _, _, b in fake.calls if isinstance(b, dict) and "event_log" in b["sql"]]
    assert "timestamp >= '2026-11-02T12:00:00.000Z'" in window[0]


def test_compare_both_zero_is_within():
    fake = FakeD1({"eu": region(1, 1), "us": region(1, 1)})
    rc, _ = compare(fake, ae_returning(0))
    assert rc == 0


def test_compare_ae_failure_is_named_and_exits_2(capsys):
    fake = FakeD1({"eu": region(1, 1, telemetry=5), "us": region(1, 1, telemetry=5)})

    def broken(_account, _sql):
        raise sr.RegionError("analytics engine answered 403")

    rc, _ = compare(fake, broken)
    assert rc == 2
    assert "eu: analytics engine answered 403" in capsys.readouterr().err


def test_an_empty_region_list_is_not_a_green_empty_report(capsys):
    rc = sr.run_report(ENV, FakeD1({}), regions=[], out=io.StringIO())
    assert rc == 2
    assert "no region" in capsys.readouterr().err
    rc = sr.run_compare(ENV, FakeD1({}), ae_returning(0), days=7, regions=[], out=io.StringIO())
    assert rc == 2


def test_value_bytes_are_summed_over_the_blob_cast():
    fake = FakeD1({"eu": region(1, 1), "us": region(1, 1)})
    run(fake)
    sums = [
        str(body["sql"])
        for _, _, body in fake.calls
        if isinstance(body, dict) and "sum(length" in str(body["sql"])
    ]
    assert sums
    assert all("length(CAST(" in sql and "AS BLOB)" in sql for sql in sums)


def test_a_dataset_name_that_is_not_an_identifier_is_refused_before_any_ae_query(capsys):
    fake = FakeD1({"eu": region(1, 1, telemetry=5), "us": region(1, 1, telemetry=5)})
    ae = ae_returning(5)
    env = {**ENV, "TELEMETRY_AE_DATASET": "t_{region}; DROP TABLE x"}
    out = io.StringIO()
    rc = sr.run_compare(env, fake, ae, days=7, regions=REGIONS, now=NOW, out=out)
    assert rc == 2
    assert ae.seen == []
    assert "not an identifier" in capsys.readouterr().err


class _FakeGh:
    def __init__(self, issues: list[dict]) -> None:
        self.issues = issues
        self.verbs: list[str] = []

    def __call__(self, *args: str) -> str:
        self.verbs.append(args[1])
        return json.dumps(self.issues) if args[1] == "list" else ""


def _doc(*alerting: str) -> dict:
    return {
        "regions": [{"region": r, "alerts": ["x"]} for r in alerting]
        + [{"region": "ok", "alerts": []}]
    }


def test_the_alert_issue_is_created_when_none_is_open():
    gh = _FakeGh([])
    assert sr.sync_alert_issue(_doc("eu"), "report", gh) == ["create"]


def test_the_same_alert_set_edits_the_body_without_a_new_comment():
    marker = sr.alert_marker(_doc("eu"))
    gh = _FakeGh([{"number": 7, "title": sr.ISSUE_TITLE, "body": "old\n" + marker}])
    assert sr.sync_alert_issue(_doc("eu"), "report", gh) == ["edit"]
    assert gh.verbs == ["list", "edit"]


def test_a_changed_alert_set_edits_and_comments():
    gh = _FakeGh([{"number": 7, "title": sr.ISSUE_TITLE, "body": sr.alert_marker(_doc("eu"))}])
    assert sr.sync_alert_issue(_doc("eu", "us"), "report", gh) == ["edit", "comment"]
