"""Daily D1 size report: tables, rows, value bytes, file size and tenants per region, with alerts.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_size_report [--region <id>] [--json-out <file>] [--md-out <file>]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_size_report --compare-telemetry --days 7 [--region <id>]

WHY IT EXISTS (agent/plans/PLAN-d1-scaling.md, Z7). One D1 database per region holds every tenant, and the sharding cutover (H5) waits on this report alerting for a region. It reads each region's database through the D1 REST query API, the way docs/d1-scaling-review.md measured it:
  - the table list (`sqlite_master`), the row count and the value bytes per table as `sum(length(CAST(col AS BLOB)))` over every column. D1 has no `dbstat`, so index and page bytes are an estimate: value bytes times the review's factor of 1.6.
  - the database file size (`meta.size_after` of the query answer) and the tenant count (`count(*)` of `subscriptions`).

REGIONS come only from regions.json (`id`, `d1.name`), so the enterprise leak gate's masking rule holds: no company database is read or printed.

ALERTS: tenants >= 25,000, or file size >= 5 GB (half the 10 GB D1 limit). Bytes per tenant is printed for the trend; it is not an alert of its own, since the review's typical tenant (15 MB) would hold it permanently on. Exit 3 when any alert fires.

EXIT CODES. 0 nothing alerts; 3 at least one alert; 2 a region cannot be read (named; wins over 3, since a report that cannot look has not passed); 1 with `--compare-telemetry`, a count outside 2%.

--compare-telemetry --days N (box LA1's soak check): per region, the Analytics Engine count of telemetry types (`cli.*` prefix, `config.pull`, `config.version.read`) over N days, read through the AE SQL API, against D1's `event_log` count of the same types over the same window. Exit 0 within 2%.

Credentials come from the environment, as the other ops modules read them: CLOUDFLARE_API_TOKEN (or the Global API Key pair) and CLOUDFLARE_ACCOUNT_ID. The AE dataset of a region is `TELEMETRY_AE_DATASET` with `{region}` expanded (default `AE_DATASET_TEMPLATE`; the W1 binding must carry the same name). No secret reaches argv or output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from rediacc_ci.core import https
from rediacc_ci.ops import observability_volume as ov
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

TENANT_ALERT = 25_000
FILE_ALERT_BYTES = 5 * 10**9
INDEX_FACTOR = 1.6
TOLERANCE = 0.02
AE_DATASET_TEMPLATE = "telemetry_{region}"
TELEMETRY_PREFIX = "cli."
TELEMETRY_TYPES = ("config.pull", "config.version.read")
EXIT_COMPARE_OFF = 1
EXIT_UNREACHABLE = 2
EXIT_ALERT = 3


class RegionError(Exception):
    """A region's database could not be read; the message names the region."""


def load_regions(root: Path | None = None) -> list[dict[str, str]]:
    """`id` and D1 `name` of every region in regions.json."""
    path = (root or Path(__file__).resolve().parents[3]) / "regions.json"
    try:
        data = json.loads(path.read_text())
        return [{"id": r["id"], "database": r["d1"]["name"]} for r in data["regions"]]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RegionError("regions.json cannot be read: %s" % exc) from exc


def _sql(*parts: str) -> str:
    """A statement from fixed text plus values this module computed (quoted identifiers, an ISO stamp, an int); nothing here comes from a request."""
    return "".join(parts)


def _quote(ident: str) -> str:
    return '"%s"' % ident.replace('"', '""')


class D1Reader:
    """One region's database over the D1 REST API."""

    def __init__(
        self,
        transport: ov.Transport,
        headers: Mapping[str, str],
        account: str,
        region: str,
        database: str,
    ) -> None:
        self.transport = transport
        self.headers = headers
        self.account = account
        self.region = region
        self.database = database
        self._uuid: str | None = None

    def _fail(self, what: str) -> RegionError:
        return RegionError("%s: %s" % (self.region, what))

    def _resolve(self) -> str:
        if self._uuid:
            return self._uuid
        url = "%s/accounts/%s/d1/database?name=%s" % (CF_API_BASE, self.account, self.database)
        status, body = self.transport("GET", url, self.headers, None)
        if status != 200 or not isinstance(body, dict) or not body.get("success"):
            raise self._fail("database lookup answered %s" % (status or "nothing"))
        for item in body.get("result") or []:
            if isinstance(item, dict) and item.get("name") == self.database and item.get("uuid"):
                self._uuid = str(item["uuid"])
                return self._uuid
        raise self._fail("database not found")

    def query(self, sql: str) -> tuple[list[dict], int]:
        """(rows, database size in bytes after the statement)."""
        url = "%s/accounts/%s/d1/database/%s/query" % (CF_API_BASE, self.account, self._resolve())
        status, body = self.transport("POST", url, self.headers, {"sql": sql})
        if status != 200 or not isinstance(body, dict) or not body.get("success"):
            raise self._fail("query answered %s" % (status or "nothing"))
        try:
            first = body["result"][0]
            rows = first.get("results") or []
            size = int((first.get("meta") or {}).get("size_after") or 0)
        except (KeyError, IndexError, TypeError, ValueError):
            raise self._fail("query returned no result") from None
        return rows, size

    def count(self, sql: str) -> int:
        rows, _ = self.query(sql)
        try:
            return int(next(iter(rows[0].values())))
        except (IndexError, StopIteration, TypeError, ValueError):
            raise self._fail("count query returned no number") from None


def read_region(reader: D1Reader) -> dict:
    """Tables with rows and value bytes, file size, tenants and the alerts of one region."""
    names, _ = reader.query(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' ORDER BY name"
    )
    tables: dict[str, dict] = {}
    for row in names:
        table = str(row["name"])
        cols, _ = reader.query("PRAGMA table_info(%s)" % _quote(table))
        sums = "".join(
            ", sum(length(CAST(%s AS BLOB))) AS c%d" % (_quote(c["name"]), i)
            for i, c in enumerate(cols)
        )
        stats, _ = reader.query(_sql("SELECT count(*) AS n", sums, " FROM ", _quote(table)))
        stat = stats[0] if stats else {}
        value_bytes = sum(int(stat.get("c%d" % i) or 0) for i in range(len(cols)))
        tables[table] = {
            "rows": int(stat.get("n") or 0),
            "value_bytes": value_bytes,
            "estimated_bytes": round(value_bytes * INDEX_FACTOR),
        }
    tenants = reader.count("SELECT count(*) AS n FROM subscriptions")
    _, size = reader.query("SELECT 1 AS one")
    alerts = []
    if tenants >= TENANT_ALERT:
        alerts.append("tenants %d >= %d" % (tenants, TENANT_ALERT))
    if size >= FILE_ALERT_BYTES:
        alerts.append("file %d B >= %d B" % (size, FILE_ALERT_BYTES))
    return {
        "region": reader.region,
        "tenants": tenants,
        "file_bytes": size,
        "bytes_per_tenant": round(size / tenants) if tenants else None,
        "tables": tables,
        "alerts": alerts,
    }


def render_markdown(regions: list[dict], unreachable: list[str]) -> str:
    lines = ["# D1 size report", ""]
    lines += ["| region | tenants | file MB | bytes per tenant | alerts |", "|---|---|---|---|---|"]
    for r in regions:
        per_tenant = r["bytes_per_tenant"] if r["bytes_per_tenant"] is not None else "-"
        lines.append(
            "| %s | %d | %.1f | %s | %s |"
            % (
                r["region"],
                r["tenants"],
                r["file_bytes"] / 1e6,
                per_tenant,
                "; ".join(r["alerts"]) or "none",
            )
        )
    lines += ["| %s | - | - | - | UNREACHABLE |" % name for name in unreachable]
    for r in regions:
        lines += ["", "## %s tables (top 10 by estimated bytes)" % r["region"], ""]
        lines += ["| table | rows | value bytes | estimated bytes (x1.6) |", "|---|---|---|---|"]
        top = sorted(r["tables"].items(), key=lambda kv: -kv[1]["estimated_bytes"])[:10]
        lines += [
            "| %s | %d | %d | %d |" % (name, t["rows"], t["value_bytes"], t["estimated_bytes"])
            for name, t in top
        ]
    return "\n".join(lines) + "\n"


def _pick(regions: list[dict[str, str]], only: str | None) -> list[dict[str, str]]:
    if only is None:
        if not regions:
            raise RegionError("regions.json lists no region to read")
        return regions
    chosen = [r for r in regions if r["id"] == only]
    if not chosen:
        known = ", ".join(r["id"] for r in regions)
        raise RegionError("unknown region %s (regions.json has %s)" % (only, known))
    return chosen


def run_report(
    env: Mapping[str, str],
    transport: ov.Transport,
    *,
    region: str | None = None,
    regions: list[dict[str, str]] | None = None,
    json_out: Path | None = None,
    md_out: Path | None = None,
    out=None,
) -> int:
    out = out or sys.stdout
    try:
        targets = _pick(regions if regions is not None else load_regions(), region)
        headers = ov.cf_headers(env)
    except (RegionError, ov.VolumeError) as exc:
        print("d1_size_report: %s" % exc, file=sys.stderr)
        return EXIT_UNREACHABLE
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
    results: list[dict] = []
    unreachable: list[str] = []
    for target in targets:
        reader = D1Reader(transport, headers, account, target["id"], target["database"])
        try:
            results.append(read_region(reader))
        except RegionError as exc:
            print("d1_size_report: %s" % exc, file=sys.stderr)
            unreachable.append(target["id"])
    markdown = render_markdown(results, unreachable)
    out.write(markdown)
    if json_out:
        document = {"regions": results, "unreachable": unreachable}
        json_out.write_text(json.dumps(document, indent=2) + "\n")
    if md_out:
        md_out.write_text(markdown)
    if unreachable:
        print("d1_size_report: unreachable: %s" % ", ".join(unreachable), file=sys.stderr)
        return EXIT_UNREACHABLE
    return EXIT_ALERT if any(r["alerts"] for r in results) else 0


def telemetry_predicate_d1() -> str:
    types = ", ".join("'%s'" % t for t in TELEMETRY_TYPES)
    return "(type LIKE '%s%%' OR type IN (%s))" % (TELEMETRY_PREFIX, types)


def telemetry_predicate_ae() -> str:
    types = ", ".join("'%s'" % t for t in TELEMETRY_TYPES)
    return "(blob1 LIKE '%s%%' OR blob1 IN (%s))" % (TELEMETRY_PREFIX, types)


def real_ae_client(headers: Mapping[str, str]) -> Callable[[str, str], list[dict]]:
    """The AE SQL API: the statement is the raw POST body, the answer `{data: [...]}`."""

    def client(account: str, sql: str) -> list[dict]:
        url = "%s/accounts/%s/analytics_engine/sql" % (CF_API_BASE, account)
        request = https.build_request(
            url,
            data=sql.encode(),
            headers={"User-Agent": ov.USER_AGENT, **headers},
            method="POST",
        )
        try:
            with https.urlopen(request, timeout=ov.TIMEOUT_S) as resp:
                body = json.loads(resp.read(50_000_000))
        except urllib.error.HTTPError as exc:
            code = exc.code
            exc.close()
            raise RegionError("analytics engine answered %s" % code) from None
        except (OSError, ValueError):
            raise RegionError("analytics engine unreachable") from None
        rows = body.get("data") if isinstance(body, dict) else None
        if not isinstance(rows, list):
            raise RegionError("analytics engine returned no data")
        return rows

    return client


def compare_region(
    reader: D1Reader,
    ae: Callable[[str, str], list[dict]],
    account: str,
    dataset: str,
    days: int,
    now: datetime,
) -> dict:
    since = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    d1_count = reader.count(
        _sql(
            "SELECT count(*) AS n FROM event_log WHERE timestamp >= '",
            since,
            "' AND ",
            telemetry_predicate_d1(),
        )
    )
    try:
        rows = ae(
            account,
            _sql(
                "SELECT sum(_sample_interval) AS n FROM ",
                dataset,
                " WHERE timestamp > NOW() - INTERVAL '",
                str(int(days)),
                "' DAY AND ",
                telemetry_predicate_ae(),
            ),
        )
    except RegionError as exc:
        raise RegionError("%s: %s" % (reader.region, exc)) from None
    try:
        ae_count = int(float(rows[0]["n"] or 0))
    except (IndexError, KeyError, TypeError, ValueError):
        raise RegionError("%s: analytics engine count unreadable" % reader.region) from None
    diff = abs(ae_count - d1_count) / d1_count if d1_count else (0.0 if ae_count == 0 else 1.0)
    return {
        "region": reader.region,
        "d1": d1_count,
        "ae": ae_count,
        "difference": round(diff, 4),
        "within": diff <= TOLERANCE,
    }


_DATASET_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _dataset_name(template: str, region_id: str) -> str:
    """The AE dataset of a region, checked as a plain identifier before it is spliced into SQL."""
    try:
        name = template.format(region=region_id)
    except (KeyError, IndexError, ValueError) as exc:
        raise RegionError(
            "TELEMETRY_AE_DATASET %r is not a usable template: %s" % (template, exc)
        ) from None
    if not _DATASET_RE.fullmatch(name):
        raise RegionError("%s: AE dataset name %r is not an identifier" % (region_id, name))
    return name


def run_compare(
    env: Mapping[str, str],
    transport: ov.Transport,
    ae: Callable[[str, str], list[dict]] | None,
    *,
    days: int,
    region: str | None = None,
    regions: list[dict[str, str]] | None = None,
    now: datetime | None = None,
    out=None,
) -> int:
    out = out or sys.stdout
    now = now or datetime.now(UTC)
    try:
        targets = _pick(regions if regions is not None else load_regions(), region)
        headers = ov.cf_headers(env)
    except (RegionError, ov.VolumeError) as exc:
        print("d1_size_report: %s" % exc, file=sys.stderr)
        return EXIT_UNREACHABLE
    client = ae or real_ae_client(headers)
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
    template = env.get("TELEMETRY_AE_DATASET") or AE_DATASET_TEMPLATE
    verdicts: list[dict] = []
    unreachable: list[str] = []
    for target in targets:
        reader = D1Reader(transport, headers, account, target["id"], target["database"])
        try:
            dataset = _dataset_name(template, target["id"])
            verdicts.append(compare_region(reader, client, account, dataset, days, now))
        except RegionError as exc:
            print("d1_size_report: %s" % exc, file=sys.stderr)
            unreachable.append(target["id"])
    for v in verdicts:
        out.write(
            "%s %s d1=%d ae=%d difference=%.2f%%\n"
            % (
                "OK  " if v["within"] else "OFF ",
                v["region"],
                v["d1"],
                v["ae"],
                v["difference"] * 100,
            )
        )
    if unreachable:
        print("d1_size_report: unreachable: %s" % ", ".join(unreachable), file=sys.stderr)
        return EXIT_UNREACHABLE
    return 0 if all(v["within"] for v in verdicts) else EXIT_COMPARE_OFF


ISSUE_TITLE = "D1 size alert"


def alert_marker(document: Mapping[str, object]) -> str:
    """The body marker naming the alerting regions, so a later run can tell a changed alert set from the same one."""
    regions = document.get("regions")
    rows = regions if isinstance(regions, list) else []
    alerting = sorted(str(r["region"]) for r in rows if r.get("alerts"))
    return "<!-- d1-size-alerts: %s -->" % ",".join(alerting)


def sync_alert_issue(
    document: Mapping[str, object], report_md: str, gh: Callable[..., str]
) -> list[str]:
    """Create the alert issue, or edit its body to the latest report and comment only when the alerting regions changed. `gh(*args)` returns stdout. Returns the gh verbs run, in order."""
    marker = alert_marker(document)
    body = "%s\n%s\n" % (report_md.rstrip("\n"), marker)
    listing = json.loads(
        gh(
            "issue",
            "list",
            "--state",
            "open",
            "--search",
            '"%s" in:title' % ISSUE_TITLE,
            "--json",
            "number,title,body",
        )
        or "[]"
    )
    found = [i for i in listing if i.get("title") == ISSUE_TITLE]
    if not found:
        gh("issue", "create", "--title", ISSUE_TITLE, "--body", body)
        return ["create"]
    number = str(found[0]["number"])
    gh("issue", "edit", number, "--body", body)
    if marker in str(found[0].get("body") or ""):
        return ["edit"]
    gh("issue", "comment", number, "--body", body)
    return ["edit", "comment"]


def _real_gh(*args: str) -> str:
    return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="d1_size_report")
    parser.add_argument("--region", help="one regions.json id")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    parser.add_argument("--compare-telemetry", action="store_true")
    parser.add_argument(
        "--alert-issue",
        action="store_true",
        help="sync the alert issue from --json-out and --md-out files (needs GH_TOKEN and GH_REPO)",
    )
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args(argv)
    if args.alert_issue:
        if not (args.json_out and args.md_out):
            print("d1_size_report: --alert-issue needs --json-out and --md-out", file=sys.stderr)
            return EXIT_UNREACHABLE
        sync_alert_issue(json.loads(args.json_out.read_text()), args.md_out.read_text(), _real_gh)
        return 0
    if args.compare_telemetry:
        if args.days < 1:
            print("d1_size_report: --days must be at least 1", file=sys.stderr)
            return EXIT_UNREACHABLE
        return run_compare(os.environ, ov.real_transport, None, days=args.days, region=args.region)
    return run_report(
        os.environ,
        ov.real_transport,
        region=args.region,
        json_out=args.json_out,
        md_out=args.md_out,
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
