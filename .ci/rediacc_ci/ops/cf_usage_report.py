"""Weekly Cloudflare usage report: R2, D1 and Workers usage against ceilings, and the account Worker's "maintenance is NOT running" log line.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.cf_usage_report

WHY IT EXISTS (agent/plans/PLAN-cloudflare-spend-guard.md, T6). No Cloudflare billing alert existed, and the account Worker's nightly cron logs `Nightly maintenance is NOT running` (private/account/src/entry/cloudflare.ts) while still reporting success. This run is read-only: GraphQL Analytics reads and one log count.

WHAT IT READS, all from the account GraphQL endpoint (token permission "Account Analytics" Read):
  - `r2StorageAdaptiveGroups`: peak payload plus metadata bytes and object count per bucket over the last two days.
  - `r2OperationsAdaptiveGroups`: requests per action over the billing month so far, folded into Class A and Class B (an action it does not know counts as Class A, the dearer one).
  - `d1StorageAdaptiveGroups`: the latest daily size per database.
  - `workersInvocationsAdaptive`: requests and CPU (`cpuTimeUs` summed, shown in ms) per script over the billing month so far.

CEILINGS come from the `report` object of `.ci/config/cf-spend-guard.json` when the file carries one, key by key, and from `DEFAULT_CEILINGS` below otherwise: workers_requests_month, workers_cpu_ms_month, r2_storage_bytes, r2_class_a_month, r2_class_b_month, d1_storage_bytes. Each is compared with the account total, and the per-item lines are for reading.

THE LOG LINE is counted over seven days in Loki (through the Grafana datasource proxy, `OBS_GRAFANA_READ_TOKEN`); when Loki cannot answer, the Workers Observability telemetry query counts it instead. When neither answers the run is exit 2, because a guard that cannot look has not passed.

OUTPUT. One line per item: `OK` or `OVER`, the item, the value and its ceiling. Then `ALERT maintenance ...` when the line was logged. Exit 0 when nothing is over and the line is absent, 1 on any `OVER` or `ALERT`, 2 when a read of zero buckets, databases or Workers came back, a GraphQL read failed, or the log count could not be read. No secret reaches argv or output.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from rediacc_ci.ops import observability_volume as ov
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    from collections.abc import Mapping

CONFIG_REL = ".ci/config/cf-spend-guard.json"
MAINTENANCE_LINE = "Nightly maintenance is NOT running"
LOOKBACK_DAYS = 7

DEFAULT_CEILINGS: dict[str, float] = {
    "workers_requests_month": 20_000_000,
    "workers_cpu_ms_month": 60_000_000,
    "r2_storage_bytes": 200e9,
    "r2_class_a_month": 2_000_000,
    "r2_class_b_month": 20_000_000,
    "d1_storage_bytes": 4e9,
}

# https://developers.cloudflare.com/r2/pricing/ : the free actions are not listed; everything unknown is billed as Class A here.
CLASS_B = frozenset(
    {
        "HeadBucket",
        "HeadObject",
        "GetObject",
        "UsageSummary",
        "GetBucketEncryption",
        "GetBucketLocation",
        "GetBucketCors",
        "GetBucketLifecycleConfiguration",
    }
)
FREE = frozenset({"DeleteObject", "DeleteBucket", "AbortMultipartUpload"})

GQL_ACCOUNT = "viewer{accounts(filter:{accountTag:$a}){%s}}"
QUERIES = {
    "r2_storage": (
        "r2StorageAdaptiveGroups(limit:10000,filter:{datetime_geq:$s,datetime_leq:$e})"
        "{dimensions{bucketName} max{payloadSize metadataSize objectCount}}"
    ),
    "r2_ops": (
        "r2OperationsAdaptiveGroups(limit:10000,filter:{datetime_geq:$m,datetime_leq:$e})"
        "{dimensions{bucketName actionType} sum{requests}}"
    ),
    "d1": (
        "d1StorageAdaptiveGroups(limit:10000,filter:{datetime_geq:$s,datetime_leq:$e})"
        "{dimensions{databaseId date} max{databaseSizeBytes}}"
    ),
    "workers": (
        "workersInvocationsAdaptive(limit:10000,filter:{datetime_geq:$m,datetime_leq:$e})"
        "{dimensions{scriptName} sum{requests cpuTimeUs}}"
    ),
}


class ReportError(Exception):
    """A read that failed outright (exit 2)."""


def load_ceilings(root: Path | None = None) -> dict[str, float]:
    """`DEFAULT_CEILINGS` overlaid by the `report` object of the spend-guard JSON, when present."""
    ceilings = dict(DEFAULT_CEILINGS)
    path = (root or Path(__file__).resolve().parents[3]) / CONFIG_REL
    try:
        text = path.read_text()
    except OSError:
        return ceilings
    # A file that exists but does not parse must not fall back to the defaults silently: the operator's ceilings would be ignored and the report could pass against thresholds nobody chose.
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ReportError("%s is not valid JSON: %s" % (CONFIG_REL, exc)) from exc
    report = data.get("report") if isinstance(data, dict) else None
    if isinstance(report, dict):
        for key in ceilings:
            value = report.get(key)
            if isinstance(value, int | float) and not isinstance(value, bool):
                ceilings[key] = float(value)
    return ceilings


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def graphql(
    transport: ov.Transport,
    headers: Mapping[str, str],
    account: str,
    name: str,
    now: datetime,
) -> list[dict]:
    """One dataset read; the list of groups, or ReportError naming the dataset."""
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    query = "query($a:String!,$s:Time!,$m:Time!,$e:Time!){%s}" % (GQL_ACCOUNT % QUERIES[name])
    variables = {
        "a": account,
        "s": _iso(now - timedelta(days=2)),
        "m": _iso(month),
        "e": _iso(now),
    }
    status, body = transport(
        "POST", "%s/graphql" % CF_API_BASE, headers, {"query": query, "variables": variables}
    )
    if status != 200 or not isinstance(body, dict):
        raise ReportError("%s: graphql answered %s" % (name, status or "nothing"))
    if body.get("errors"):
        first = body["errors"][0]
        raise ReportError(
            "%s: graphql error: %s"
            % (name, first.get("message") if isinstance(first, dict) else first)
        )
    try:
        accounts = body["data"]["viewer"]["accounts"]
        groups = next(iter(accounts[0].values()))
    except (KeyError, IndexError, TypeError, StopIteration):
        raise ReportError("%s: graphql returned no account data" % name) from None
    if not isinstance(groups, list):
        raise ReportError("%s: graphql returned no group list" % name)
    return groups


def maintenance_count(
    env: Mapping[str, str],
    transport: ov.Transport,
    headers: Mapping[str, str],
    account: str,
    now: datetime,
    grafana: str = ov.GRAFANA_ORIGIN,
) -> tuple[int, str]:
    """Occurrences of the log line over seven days and the source that counted them; ReportError when neither could."""
    token = env.get("OBS_GRAFANA_READ_TOKEN", "")
    loki_error = "OBS_GRAFANA_READ_TOKEN is not set"
    if token:
        try:
            rows = ov.loki_instant(
                transport,
                grafana,
                token,
                'sum(count_over_time({service_name=~".+"} |= "%s" [%dd]))'
                % (MAINTENANCE_LINE, LOOKBACK_DAYS),
                now.timestamp(),
            )
            total = 0
            for row in rows:
                value = row.get("value")
                if isinstance(value, list) and len(value) == 2:
                    total += int(float(value[1]))
            return total, "loki"
        except (ov.VolumeError, ValueError) as exc:
            loki_error = str(exc)
    try:
        result = ov.telemetry_query(
            transport,
            headers,
            account,
            {
                "queryId": "maintenance-line",
                "timeframe": {
                    "from": int((now - timedelta(days=LOOKBACK_DAYS)).timestamp() * 1000),
                    "to": int(now.timestamp() * 1000),
                },
                "view": "calculations",
                "parameters": {
                    "calculations": [{"operator": "count", "alias": "lines"}],
                    "filters": [
                        {
                            "key": "$metadata.message",
                            "operation": "includes",
                            "type": "string",
                            "value": MAINTENANCE_LINE,
                        }
                    ],
                    "limit": 10,
                },
            },
        )
    except ov.VolumeError as exc:
        raise ReportError(
            "maintenance line unreadable: loki: %s; telemetry query: %s" % (loki_error, exc)
        ) from None
    total = 0
    for calc in result.get("calculations") or []:
        for agg in calc.get("aggregates") or []:
            value = agg.get("value")
            if isinstance(value, int | float):
                total += int(value)
    return total, "telemetry-query"


def _line(ok: bool, item: str, value: float, ceiling: float | None, unit: str = "") -> str:
    shown = "" if ceiling is None else " ceiling=%d" % ceiling
    return "%s %s value=%d%s%s" % ("OK  " if ok else "OVER", item, value, shown, unit)


def run(
    env: Mapping[str, str],
    transport: ov.Transport,
    *,
    now: datetime | None = None,
    ceilings: Mapping[str, float] | None = None,
    out=None,
) -> int:
    out = out or sys.stdout
    err = sys.stderr
    now = now or datetime.now(UTC)
    try:
        ceilings = dict(ceilings if ceilings is not None else load_ceilings())
    except ReportError as exc:
        print("cf_usage_report: %s" % exc, file=err)
        return 2
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
    try:
        headers = ov.cf_headers(env)
        storage = graphql(transport, headers, account, "r2_storage", now)
        ops = graphql(transport, headers, account, "r2_ops", now)
        d1 = graphql(transport, headers, account, "d1", now)
        workers = graphql(transport, headers, account, "workers", now)
    except (ReportError, ov.VolumeError) as exc:
        print("cf_usage_report: %s" % exc, file=err)
        return 2

    buckets: dict[str, dict[str, float]] = {}
    for g in storage:
        name = (g.get("dimensions") or {}).get("bucketName")
        m = g.get("max") or {}
        if name:
            size = float(m.get("payloadSize") or 0) + float(m.get("metadataSize") or 0)
            cur = buckets.setdefault(name, {"bytes": 0.0, "objects": 0.0})
            cur["bytes"] = max(cur["bytes"], size)
            cur["objects"] = max(cur["objects"], float(m.get("objectCount") or 0))
    databases: dict[str, tuple[str, float]] = {}
    for g in d1:
        d = g.get("dimensions") or {}
        db = d.get("databaseId")
        if db:
            size = float((g.get("max") or {}).get("databaseSizeBytes") or 0)
            day = str(d.get("date") or "")
            if db not in databases or day >= databases[db][0]:
                databases[db] = (day, size)
    scripts: dict[str, dict[str, float]] = {}
    for g in workers:
        name = (g.get("dimensions") or {}).get("scriptName")
        s = g.get("sum") or {}
        if name:
            cur = scripts.setdefault(name, {"requests": 0.0, "cpu_ms": 0.0})
            cur["requests"] += float(s.get("requests") or 0)
            cur["cpu_ms"] += float(s.get("cpuTimeUs") or 0) / 1000.0
    for label, found in (("buckets", buckets), ("databases", databases), ("Workers", scripts)):
        if not found:
            print(
                "cf_usage_report: zero %s read; the report cannot vouch for anything" % label,
                file=err,
            )
            return 2

    class_a = class_b = 0.0
    for g in ops:
        action = (g.get("dimensions") or {}).get("actionType")
        n = float((g.get("sum") or {}).get("requests") or 0)
        if action in FREE:
            continue
        if action in CLASS_B:
            class_b += n
        else:
            class_a += n

    over = 0

    def emit(item: str, value: float, key: str | None, unit: str = "") -> None:
        nonlocal over
        ceiling = ceilings[key] if key else None
        ok = ceiling is None or value <= ceiling
        over += 0 if ok else 1
        print(_line(ok, item, value, ceiling, unit), file=out)

    for name in sorted(buckets):
        emit(
            "r2.bucket.%s.bytes" % name,
            buckets[name]["bytes"],
            None,
            " objects=%d" % buckets[name]["objects"],
        )
    emit("r2.storage.total.bytes", sum(b["bytes"] for b in buckets.values()), "r2_storage_bytes")
    emit("r2.class_a.month", class_a, "r2_class_a_month")
    emit("r2.class_b.month", class_b, "r2_class_b_month")
    for db in sorted(databases):
        emit("d1.%s.bytes" % db, databases[db][1], None)
    emit("d1.storage.total.bytes", sum(s for _, s in databases.values()), "d1_storage_bytes")
    for name in sorted(scripts):
        emit(
            "workers.%s.requests" % name,
            scripts[name]["requests"],
            None,
            " cpu_ms=%d" % scripts[name]["cpu_ms"],
        )
    emit(
        "workers.requests.month",
        sum(s["requests"] for s in scripts.values()),
        "workers_requests_month",
    )
    emit("workers.cpu_ms.month", sum(s["cpu_ms"] for s in scripts.values()), "workers_cpu_ms_month")

    try:
        count, source = maintenance_count(env, transport, ov.telemetry_headers(env), account, now)
    except ReportError as exc:
        print("cf_usage_report: %s" % exc, file=err)
        return 2
    if count:
        over += 1
        print(
            'ALERT maintenance: "%s" logged %d times in the last %d days (%s)'
            % (MAINTENANCE_LINE, count, LOOKBACK_DAYS, source),
            file=out,
        )
    else:
        print("OK   maintenance line absent for %d days (%s)" % (LOOKBACK_DAYS, source), file=out)
    print(
        "%d buckets, %d databases, %d Workers read; %d over"
        % (len(buckets), len(databases), len(scripts), over),
        file=out,
    )
    return 1 if over else 0


def main(argv: list[str] | None = None) -> int:
    if argv:
        print("cf_usage_report takes no arguments", file=sys.stderr)
        return 2
    return run(os.environ, ov.real_transport)


if __name__ == "__main__":
    raise SystemExit(main())
