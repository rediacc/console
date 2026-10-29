"""Cost of one proxy Worker script over a window: Durable Object requests and wall time, and container active seconds.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile cf-usage-report -- \
        python3 -m rediacc_ci.ops.proxy_job_cost --script rediacc-proxy-bench \
        --from 2026-10-29T10:00:00Z --to 2026-10-29T11:00:00Z

WHY IT EXISTS (agent/plans/PLAN-detached-jobs.md, J12). The detached-job protocol changes how long a proxy Durable Object stays busy, so L0 and L5 compare these numbers before and after.

CONFIRMED AGAINST THE LIVE GraphQL API (introspection and one query, 2026-10-29, token of the `cf-usage-report` bws profile, Account Analytics Read):
  - `durableObjectsInvocationsAdaptiveGroups` (account level). Filter: `datetime_geq`, `datetime_leq`, `scriptName`. Dimensions include `scriptName`, `namespaceId`, `objectId`, `status`, `type`. `sum{requests errors wallTime responseBodySize}`; `quantiles{wallTimeP25 .. wallTimeP999}` (also cpuTimeP*). `wallTime` is MICROSECONDS (p50 54792384 for a long-lived stream is 54.8 s); printed here in milliseconds.
  - `containersMetricsAdaptiveGroups` (account level). Dimensions: `applicationId`, `active`, `deploymentId`, `durableObjectId`, `instanceId`, `region`, ... There is NO `scriptName` dimension, so a container read cannot be scoped to one script by the API. `sum{cpuTimeSec containerUptime allocatedMemory ...}`; `cpuTimeSec` is the active vCPU-seconds Cloudflare bills CPU on (the same field cf_usage_report reads). `--application <id>` (repeatable) scopes the container read; without it the line sums every application and says so. `containerUptime` is not used: its unit is unconfirmed.

OUTPUT. `durable_object script=... requests=N errors=N wall_ms_sum=X wall_ms_p50=X wall_ms_p99=X` and `container active_seconds=X rows=N scope=all|listed`. When one script has several groups, p50 is the request-weighted mean and p99 the maximum of the groups (an upper bound).

EXIT. 0 printed; 2 on a transport or GraphQL error, a missing credential, bad arguments, or zero Durable Object rows for the script (a read that saw nothing has not measured anything). Zero container rows prints `active_seconds=0` with `rows=0`: a window can have no container use. No secret reaches argv or output.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from rediacc_ci.ops import cf_usage_report as cu

if TYPE_CHECKING:
    from collections.abc import Mapping

ov = cu.ov

DO_QUERY = (
    "query($a:String!,$s:Time!,$e:Time!,$n:String!){viewer{accounts(filter:{accountTag:$a}){"
    "do:durableObjectsInvocationsAdaptiveGroups(limit:10000,"
    "filter:{datetime_geq:$s,datetime_leq:$e,scriptName:$n}){"
    "dimensions{scriptName} sum{requests errors wallTime} quantiles{wallTimeP50 wallTimeP99}}}}}"
)
CONTAINER_QUERY = (
    "query($a:String!,$s:Time!,$e:Time!){viewer{accounts(filter:{accountTag:$a}){"
    "c:containersMetricsAdaptiveGroups(limit:10000,filter:{datetime_geq:$s,datetime_leq:$e}){"
    "dimensions{applicationId} sum{cpuTimeSec}}}}}"
)


def _read(
    transport: ov.Transport,
    headers: Mapping[str, str],
    query: str,
    variables: dict[str, str],
    key: str,
) -> list[dict]:
    status, body = transport(
        "POST",
        "%s/graphql" % cu.CF_API_BASE,
        headers,
        {"query": query, "variables": variables},
    )
    if status != 200 or not isinstance(body, dict):
        raise cu.ReportError("%s: graphql answered %s" % (key, status or "nothing"))
    if body.get("errors"):
        first = body["errors"][0]
        raise cu.ReportError(
            "%s: graphql error: %s"
            % (key, first.get("message") if isinstance(first, dict) else first)
        )
    try:
        groups = body["data"]["viewer"]["accounts"][0][key]
    except (KeyError, IndexError, TypeError):
        raise cu.ReportError("%s: graphql returned no account data" % key) from None
    if not isinstance(groups, list):
        raise cu.ReportError("%s: graphql returned no group list" % key)
    return groups


def _num(mapping: object, name: str) -> float:
    return float((mapping or {}).get(name) or 0) if isinstance(mapping, dict) else 0.0


def run(
    env: Mapping[str, str],
    transport: ov.Transport,
    *,
    script: str,
    start: str,
    end: str,
    applications: list[str] | None = None,
    out=None,
) -> int:
    out = out or sys.stdout
    err = sys.stderr
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
    try:
        headers = ov.cf_headers(env)
        do_rows = _read(
            transport,
            headers,
            DO_QUERY,
            {"a": account, "s": start, "e": end, "n": script},
            "do",
        )
        container_rows = _read(
            transport, headers, CONTAINER_QUERY, {"a": account, "s": start, "e": end}, "c"
        )
    except (cu.ReportError, ov.VolumeError) as exc:
        print("proxy_job_cost: %s" % exc, file=err)
        return 2
    if not do_rows:
        print(
            "proxy_job_cost: zero Durable Object rows for script %s between %s and %s"
            % (script, start, end),
            file=err,
        )
        return 2
    requests = errors = wall = 0.0
    weighted_p50 = 0.0
    p99 = 0.0
    for row in do_rows:
        total = row.get("sum")
        quant = row.get("quantiles")
        count = _num(total, "requests")
        requests += count
        errors += _num(total, "errors")
        wall += _num(total, "wallTime")
        weighted_p50 += _num(quant, "wallTimeP50") * count
        p99 = max(p99, _num(quant, "wallTimeP99"))
    p50 = weighted_p50 / requests if requests else 0.0
    wanted = set(applications or [])
    kept = [
        r
        for r in container_rows
        if not wanted or (r.get("dimensions") or {}).get("applicationId") in wanted
    ]
    seconds = sum(_num(r.get("sum"), "cpuTimeSec") for r in kept)
    print(
        "durable_object script=%s requests=%d errors=%d wall_ms_sum=%.1f wall_ms_p50=%.1f wall_ms_p99=%.1f"
        % (script, requests, errors, wall / 1000.0, p50 / 1000.0, p99 / 1000.0),
        file=out,
    )
    print(
        "container active_seconds=%.2f rows=%d scope=%s"
        % (seconds, len(kept), "listed" if wanted else "all"),
        file=out,
    )
    return 0


def _valid_iso(text: str) -> str:
    try:
        datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        raise argparse.ArgumentTypeError("%r is not YYYY-MM-DDTHH:MM:SSZ" % text) from None
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="proxy_job_cost", description=__doc__.split("\n")[0])
    parser.add_argument("--script", required=True)
    parser.add_argument("--from", dest="start", required=True, type=_valid_iso)
    parser.add_argument("--to", dest="end", required=True, type=_valid_iso)
    parser.add_argument("--application", action="append", default=[])
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    return run(
        os.environ,
        ov.real_transport,
        script=args.script,
        start=args.start,
        end=args.end,
        applications=args.application,
    )


if __name__ == "__main__":
    raise SystemExit(main())
