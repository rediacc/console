"""Observability volume per Worker, measured where the data lands: Tempo span counts and Loki bytes, projected against the included allowance.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.observability_volume [--hours 24] [--end 2026-10-24T14:20:00Z] [--retention-days 7]

WHY IT EXISTS (agent/plans/PLAN-cloudflare-spend-guard.md, T4). Workers Observability bills ingestion and storage from 2026-12-01, but with `persist = false` Cloudflare stores no Worker events, so a Cloudflare-side count reads zero and says nothing about volume. The volume that matters is what the OTLP destinations deliver, and that is measured in the observability stack through the Grafana datasource proxy (the read token and approach of `telemetry_delivery`).

THE SPANS. The Tempo span-metrics counter `traces_spanmetrics_calls_total`, read through the Prometheus datasource, `sum by (service) (increase(...[window]))`: spans per service name (the Worker's script name). The size of a span is the JSON body length over the span count of a sample of recent Tempo traces; a sample that yields none falls back to the log mean, and the NOTE line says so.

THE LOGS. Loki `bytes_over_time` and `count_over_time` per `service_name` over the window: real bytes, not an estimate.

THE CHECK. The Cloudflare telemetry query (`POST /accounts/{id}/workers/observability/telemetry/query`, `view: "calculations"`, a `count` grouped by `$metadata.service`) stays only as a check that stored events stay near zero. A nonzero count prints `WARN <Worker> stored N events` (persist = true somewhere, or events stored before the switch) and never changes the exit code; a missing credential or a refused query prints one NOTE and skips the check. The query takes the Global API Key pair ahead of the scoped token (`telemetry_headers`), because the scoped token cannot run it.

OUTPUT. One line per Worker: spans, log lines, bytes, projected GB a month and its share of the 50 GB included ingestion, then one TOTAL line with the storage steady state (daily bytes x `--retention-days`) against the 10 GB-month included. Services that are not Workers (`NON_WORKER`: the CLI, renet and syslog) are dropped and counted in a footer. Exit 0 when Tempo and Loki answered (an empty window is `TOTAL 0 Workers`), 2 on a setup error, 1 when a Grafana read failed. Secrets (`OBS_GRAFANA_READ_TOKEN`, the optional Cloudflare credential) come from the environment, travel as headers only and never reach argv or output. The bws profile that supplies the Grafana token alone is `telemetry-probe`.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from rediacc_ci.core import https
from rediacc_ci.well_known import CF_API_BASE

DEFAULT_ACCOUNT_ID = "fa51e4a18d553c30e1633288e9733d04"
GRAFANA_ORIGIN = "https://grafana.rediacc.io"
INGESTION_ALLOWANCE_GB = 50.0
STORAGE_ALLOWANCE_GB_MONTH = 10.0
GB = 1e9
TRACE_TYPES = frozenset({"span", "span_event"})
TIMEOUT_S = 60.0
USER_AGENT = "rediacc-observability-volume/1"
TRACE_SAMPLE = 20
PROMETHEUS_UID = "prometheus"
SPAN_COUNTER = "traces_spanmetrics_calls_total"
#: Services in Tempo and Loki that are not Cloudflare Workers.
NON_WORKER = re.compile(r"^(renet-|rediacc-cli$|syslog$)")

#: `(method, url, headers, body)` -> `(status, decoded JSON or None)`. 0 means no HTTP answer.
Transport = Callable[[str, str, Mapping[str, str], object | None], tuple[int, object]]


class VolumeError(Exception):
    """A read the report cannot go on without; the message is what the operator sees."""


def real_transport(
    method: str, url: str, headers: Mapping[str, str], body: object | None
) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"User-Agent": USER_AGENT, **headers}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    try:
        request = https.build_request(url, data=data, headers=hdrs, method=method)
        with https.urlopen(request, timeout=TIMEOUT_S) as resp:
            raw = resp.read(50_000_000)
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(200_000)
        status = exc.code
        exc.close()
    except (OSError, ValueError):
        return 0, None
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


def cf_headers(env: Mapping[str, str]) -> dict[str, str]:
    """Bearer token when `CLOUDFLARE_API_TOKEN` is set, else the Global API Key pair; VolumeError when neither is."""
    token = env.get("CLOUDFLARE_API_TOKEN") or env.get("CF_API_TOKEN")
    if token:
        return {"Authorization": "Bearer %s" % token}
    key, email = env.get("CF_GLOBAL_API_KEY"), env.get("CF_EMAIL")
    if key and email:
        return {"X-Auth-Key": key, "X-Auth-Email": email}
    raise VolumeError(
        "no Cloudflare credential: set CLOUDFLARE_API_TOKEN (or CF_GLOBAL_API_KEY and CF_EMAIL)"
    )


def telemetry_headers(env: Mapping[str, str]) -> dict[str, str]:
    """Headers for the Workers Observability telemetry query: the Global API Key pair when it is set, else `cf_headers`.

    The long-lived scoped `CLOUDFLARE_API_TOKEN` carries no Workers Observability Write and answers this query 403, so preferring it (as `cf_headers` does, rightly, for GraphQL) made the Global-key route that secret-supply.json describes unreachable whenever both were bound.
    """
    key, email = env.get("CF_GLOBAL_API_KEY"), env.get("CF_EMAIL")
    if key and email:
        return {"X-Auth-Key": key, "X-Auth-Email": email}
    return cf_headers(env)


def _cf_errors(body: object) -> str:
    if isinstance(body, dict) and isinstance(body.get("errors"), list):
        return (
            "; ".join(
                str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in body["errors"]
            )
            or "no error detail"
        )
    return "no error detail"


def telemetry_query(
    transport: Transport, headers: Mapping[str, str], account: str, body: dict
) -> dict:
    """One telemetry `query` call; the `result` object, or VolumeError with Cloudflare's own text."""
    url = "%s/accounts/%s/workers/observability/telemetry/query" % (CF_API_BASE, account)
    status, decoded = transport("POST", url, headers, body)
    if status != 200 or not isinstance(decoded, dict) or not decoded.get("success"):
        raise VolumeError(
            "telemetry query answered %s: %s" % (status or "nothing", _cf_errors(decoded))
        )
    result = decoded.get("result")
    if not isinstance(result, dict):
        raise VolumeError("telemetry query returned no result object")
    return result


def event_counts(
    transport: Transport,
    headers: Mapping[str, str],
    account: str,
    from_ms: int,
    to_ms: int,
) -> dict[str, dict[str, int]]:
    """`{service: {type: count}}` over the window."""
    result = telemetry_query(
        transport,
        headers,
        account,
        {
            "queryId": "obs-volume",
            "timeframe": {"from": from_ms, "to": to_ms},
            "view": "calculations",
            "parameters": {
                "calculations": [{"operator": "count", "alias": "events"}],
                "groupBys": [
                    {"type": "string", "value": "$metadata.service"},
                    {"type": "string", "value": "$metadata.type"},
                ],
                "limit": 2000,
            },
        },
    )
    calculations = result.get("calculations")
    # An answer without a calculations list is malformed, not an empty window: reading it as zero would exit 0 on a broken response.
    if not isinstance(calculations, list):
        raise VolumeError("telemetry query returned no calculations list")
    out: dict[str, dict[str, int]] = {}
    for calc in calculations:
        for agg in calc.get("aggregates") or []:
            groups = {g.get("key"): g.get("value") for g in agg.get("groups") or []}
            service = groups.get("$metadata.service")
            kind = groups.get("$metadata.type")
            value = agg.get("value")
            if service is None or kind is None or not isinstance(value, int | float):
                continue
            out.setdefault(str(service), {})[str(kind)] = out.get(str(service), {}).get(
                str(kind), 0
            ) + int(value)
    return out


def _grafana_get(
    transport: Transport,
    grafana: str,
    token: str,
    uid: str,
    path: str,
    params: Mapping[str, object],
) -> object:
    url = "%s/api/datasources/proxy/uid/%s%s?%s" % (
        grafana,
        uid,
        path,
        urllib.parse.urlencode(params),
    )
    status, decoded = transport("GET", url, {"Authorization": "Bearer %s" % token}, None)
    if status != 200:
        raise VolumeError("grafana %s %s answered %s" % (uid, path, status or "nothing"))
    return decoded


def loki_instant(
    transport: Transport, grafana: str, token: str, query: str, at_s: float
) -> list[dict]:
    """The `result` vector of one Loki instant query."""
    data = _grafana_get(
        transport,
        grafana,
        token,
        "loki",
        "/loki/api/v1/query",
        {"query": query, "time": int(at_s * 1e9)},
    )
    body = data.get("data") if isinstance(data, dict) else None
    result = body.get("result") if isinstance(body, dict) else None
    if not isinstance(result, list):
        raise VolumeError("loki returned no result vector")
    return result


def _vector_by_service(rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in rows:
        service = (row.get("metric") or {}).get("service_name")
        value = row.get("value")
        if service and isinstance(value, list) and len(value) == 2:
            try:
                out[str(service)] = out.get(str(service), 0.0) + float(value[1])
            except (TypeError, ValueError):
                raise VolumeError(
                    "prometheus returned a non-numeric span count for %s" % service
                ) from None
    return out


def loki_log_sizes(
    transport: Transport, grafana: str, token: str, window_s: int, end_s: float
) -> dict[str, tuple[float, float]]:
    """`{service: (bytes, lines)}` Loki holds for the window."""
    selector = '{service_name=~".+"}'
    span = "%ds" % window_s
    bytes_by = _vector_by_service(
        loki_instant(
            transport,
            grafana,
            token,
            "sum by (service_name) (bytes_over_time(%s[%s]))" % (selector, span),
            end_s,
        )
    )
    lines_by = _vector_by_service(
        loki_instant(
            transport,
            grafana,
            token,
            "sum by (service_name) (count_over_time(%s[%s]))" % (selector, span),
            end_s,
        )
    )
    return {s: (b, lines_by[s]) for s, b in bytes_by.items() if lines_by.get(s, 0) > 0}


def tempo_span_counts(
    transport: Transport, grafana: str, token: str, window_s: int, end_s: float
) -> dict[str, float]:
    """`{service: spans}` Tempo's span-metrics counter saw over the window, through the Prometheus datasource."""
    data = _grafana_get(
        transport,
        grafana,
        token,
        PROMETHEUS_UID,
        "/api/v1/query",
        {
            "query": "sum by (service) (increase(%s[%ds]))" % (SPAN_COUNTER, window_s),
            "time": int(end_s),
        },
    )
    body = data.get("data") if isinstance(data, dict) else None
    result = body.get("result") if isinstance(body, dict) else None
    if not isinstance(result, list):
        raise VolumeError("prometheus returned no result vector")
    out: dict[str, float] = {}
    for row in result:
        service = (row.get("metric") or {}).get("service")
        value = row.get("value")
        if service and isinstance(value, list) and len(value) == 2:
            try:
                out[str(service)] = out.get(str(service), 0.0) + float(value[1])
            except (TypeError, ValueError):
                continue
    return out


def tempo_span_size(
    transport: Transport, grafana: str, token: str, from_s: float, end_s: float
) -> float | None:
    """Mean JSON bytes per span over a sample of recent traces, or None when no trace could be read."""
    found = _grafana_get(
        transport,
        grafana,
        token,
        "tempo",
        "/api/search",
        {"start": int(from_s), "end": int(end_s), "limit": TRACE_SAMPLE},
    )
    traces = found.get("traces") if isinstance(found, dict) else None
    total_bytes = total_spans = 0
    for trace in traces or []:
        trace_id = trace.get("traceID") if isinstance(trace, dict) else None
        if not trace_id:
            continue
        status, body = transport(
            "GET",
            "%s/api/datasources/proxy/uid/tempo/api/traces/%s" % (grafana, trace_id),
            {"Authorization": "Bearer %s" % token},
            None,
        )
        if status != 200 or body is None:
            continue
        text = json.dumps(body, separators=(",", ":"))
        spans = text.count('"spanId"')
        if spans:
            total_bytes += len(text)
            total_spans += spans
    return total_bytes / total_spans if total_spans else None


def estimate(
    spans: Mapping[str, float],
    log_sizes: Mapping[str, tuple[float, float]],
    span_bytes: float | None,
) -> tuple[list[dict], bool, int]:
    """Per-Worker rows, whether the span size fell back to the log mean, and how many non-Worker services were dropped."""
    services = sorted(set(spans) | set(log_sizes))
    workers = [s for s in services if not NON_WORKER.match(s)]
    # The fallback span size is the Workers' own mean log line: the dropped services (renet, the CLI, syslog) price a span wrongly.
    all_bytes = sum(log_sizes[s][0] for s in workers if s in log_sizes)
    all_lines = sum(log_sizes[s][1] for s in workers if s in log_sizes)
    overall_log = all_bytes / all_lines if all_lines else 0.0
    span_mean = overall_log if span_bytes is None else span_bytes
    rows = []
    for service in workers:
        log_bytes, log_lines = log_sizes.get(service, (0.0, 0.0))
        n_spans = spans.get(service, 0.0)
        rows.append(
            {
                "service": service,
                "spans": n_spans,
                "log_lines": log_lines,
                "log_bytes": log_bytes,
                "span_mean": span_mean,
                "bytes": n_spans * span_mean + log_bytes,
            }
        )
    return rows, span_bytes is None, len(services) - len(workers)


def render(
    rows: list[dict],
    span_fallback: bool,
    window_s: int,
    retention_days: float,
    out=None,
    dropped: int = 0,
) -> None:
    out = out or sys.stdout
    days = window_s / 86400.0
    total = 0.0
    for r in rows:
        monthly_gb = r["bytes"] / days * 30 / GB
        total += r["bytes"]
        print(
            "%-28s spans=%-7d log_lines=%-7d log_bytes=%-10d bytes=%-11d month=%.4f GB (%.3f%% of %.0f GB) mean_span=%.0f"
            % (
                r["service"],
                r["spans"],
                r["log_lines"],
                r["log_bytes"],
                r["bytes"],
                monthly_gb,
                monthly_gb / INGESTION_ALLOWANCE_GB * 100,
                INGESTION_ALLOWANCE_GB,
                r["span_mean"],
            ),
            file=out,
        )
    monthly_gb = total / days * 30 / GB
    storage_gb = total / days * retention_days / GB
    print(
        "TOTAL %d Workers bytes=%d month=%.4f GB (%.3f%% of %.0f GB ingestion) storage=%.4f GB (%.3f%% of %.0f GB-month, retention %g d)"
        % (
            len(rows),
            total,
            monthly_gb,
            monthly_gb / INGESTION_ALLOWANCE_GB * 100,
            INGESTION_ALLOWANCE_GB,
            storage_gb,
            storage_gb / STORAGE_ALLOWANCE_GB_MONTH * 100,
            STORAGE_ALLOWANCE_GB_MONTH,
            retention_days,
        ),
        file=out,
    )
    if dropped:
        print("NOTE %d non-Worker service(s) left out" % dropped, file=out)
    if span_fallback:
        print("NOTE span size not sampled from Tempo; the log mean stands in", file=out)


def stored_check(
    env: Mapping[str, str],
    transport: Transport,
    window_s: int,
    end_s: float,
    out,
) -> None:
    """Print a WARN per Worker Cloudflare still stores events for, or one NOTE when the check cannot run. Never fatal."""
    try:
        counts = event_counts(
            transport,
            telemetry_headers(env),
            env.get("CLOUDFLARE_ACCOUNT_ID") or DEFAULT_ACCOUNT_ID,
            int((end_s - window_s) * 1000),
            int(end_s * 1000),
        )
    except VolumeError as exc:
        print("NOTE Cloudflare stored-event check skipped: %s" % exc, file=out)
        return
    stored = {s: sum(t.values()) for s, t in counts.items() if sum(t.values()) > 0}
    for service in sorted(stored):
        print(
            "WARN %s stored %d events at Cloudflare (persist = false expects 0)"
            % (service, stored[service]),
            file=out,
        )
    if not stored:
        print("OK Cloudflare stored 0 events in the window", file=out)


def run(
    env: Mapping[str, str],
    transport: Transport,
    *,
    hours: float,
    end_s: float,
    retention_days: float,
    grafana: str = GRAFANA_ORIGIN,
    out=None,
) -> int:
    err_out = sys.stderr
    out = out or sys.stdout
    grafana_token = env.get("OBS_GRAFANA_READ_TOKEN", "")
    if not grafana_token:
        print("OBS_GRAFANA_READ_TOKEN is not set", file=err_out)
        return 2
    window_s = int(hours * 3600)
    try:
        spans = tempo_span_counts(transport, grafana, grafana_token, window_s, end_s)
        log_sizes = loki_log_sizes(transport, grafana, grafana_token, window_s, end_s)
        try:
            span_bytes = tempo_span_size(transport, grafana, grafana_token, end_s - window_s, end_s)
        except VolumeError:
            span_bytes = None
    except VolumeError as exc:
        print("observability_volume: %s" % exc, file=err_out)
        return 1
    rows, span_fallback, dropped = estimate(spans, log_sizes, span_bytes)
    render(rows, span_fallback, window_s, retention_days, out, dropped)
    stored_check(env, transport, window_s, end_s, out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="observability_volume", description=__doc__.splitlines()[0]
    )
    parser.add_argument("--hours", type=float, default=24.0)
    parser.add_argument("--end", help="window end, ISO 8601 UTC (default: now)")
    parser.add_argument("--retention-days", type=float, default=7.0)
    parser.add_argument("--grafana", default=GRAFANA_ORIGIN)
    args = parser.parse_args(argv)
    if args.hours <= 0:
        print("--hours must be positive", file=sys.stderr)
        return 2
    end_s = time.time()
    if args.end:
        try:
            end_s = datetime.fromisoformat(args.end).astimezone(UTC).timestamp()
        except ValueError:
            print("--end is not an ISO 8601 time", file=sys.stderr)
            return 2
    return run(
        os.environ,
        real_transport,
        hours=args.hours,
        end_s=end_s,
        retention_days=args.retention_days,
        grafana=args.grafana.rstrip("/"),
    )


if __name__ == "__main__":
    raise SystemExit(main())
