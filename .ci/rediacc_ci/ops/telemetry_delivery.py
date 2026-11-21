"""Does a request to each account Worker reach Tempo and Loki: the end-to-end check of the Workers telemetry export.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.telemetry_delivery [--timeout-s 600] [--interval-s 20]

WHY IT EXISTS. The export runs through Cloudflare destinations, a collector and the observability stack, and a break anywhere along it reads as silence, not as an error (agent/plans/PLAN-telemetry-export.md, T16). One probe per host proves the whole path: the Worker answers, Cloudflare ships the span and the log, and both are queryable.

THE PROBE. `GET https://<host>/account/api/v1/health` with `X-Rediacc-Probe: <uuid4>`. The Worker records the uuid as the `rediacc.probe` attribute on the root span and on its logs. The hosts are the three of regions.json (one shared set per region) plus bench, taken from `portal_health.hosts`. Proxy hosts (the routes of `PROXY_CONFIGS`) are probed at `/v1/health` instead, since the account path answers a proxy 401; the proxy logs `telemetry-probe <uuid>` and sets `rediacc.probe`, so the same Tempo tag search and Loki uuid filter match (its Tempo service name is the script name, so the search never filters on service.name).

THE POLL. For each probe, Tempo is searched through the Grafana datasource proxy (`/api/datasources/proxy/uid/tempo/api/search`, tag `rediacc.probe=<uuid>`) and Loki is queried (`/loki/api/v1/query_range`, line filter on the uuid), every `--interval-s` seconds until each signal is seen or `--timeout-s` (default 600) has passed. All probes are sent first and polled together, so the deadline is one 10 minute window and not one per host.

THE ALERT SERIES. The Grafana silent-sender alert watches `traces_spanmetrics_calls_total{service="account-<region>", deployment_environment=..., rediacc_region=<region>}` over 6h (the Workers report their script name as the service, `telemetry.account_service_template`) (agent/plans/PLAN-telemetry-export.md T11), labels the uuid search never touches: a Worker that emits another `deployment_environment` passes the uuid path while the alert starves. So after the uuid path, for each regions.json region the Prometheus datasource (same Grafana proxy, same token) is asked for that series with `deployment_environment` matching one of `telemetry.account_environments` in `.ci/config/ops-health.json` (a hand-kept mirror of the values the alert rule accepts: the rule lives in the observability repo's provisioning, nothing here reads it, so a rule change needs the same edit in that file) and a non-zero 6h increase, polled like the other signals. A region without it prints `SILENT <region> (alert labels)` naming the labels looked for, and the exit is 1.

OUTPUT. One line per host and signal: `PASS <host> <signal>` or `SILENT <host> <signal>`, signal `traces` or `logs`. A probe the host did not answer with 200 makes both of its signals `SILENT` with the reason after it. Nothing from a response body is printed, and the Grafana token is read from the environment (`OBS_GRAFANA_READ_TOKEN`, delivered by the bws-secrets action), sent only as a header, and never on argv or in output. Exit 0 when every line is PASS, 1 on any SILENT, 2 on a usage or setup error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from rediacc_ci.core import https
from rediacc_ci.core.common import repo_root
from rediacc_ci.ops import portal_health

# One declaration of the Grafana origin for both observability readers: a third typed copy would make it an owned literal that belongs in .ci/config/well-known.env.
from rediacc_ci.ops.observability_volume import GRAFANA_ORIGIN, PROMETHEUS_UID

TEMPO_UID = "tempo"
LOKI_UID = "loki"
ALERT_WINDOW = "6h"
CONFIG_REL = ".ci/config/ops-health.json"
_LABEL_VALUE = re.compile(r"[A-Za-z0-9_.-]+")
READ_CREDENTIAL_ENV = "OBS_GRAFANA_READ_TOKEN"
HEALTH_PATH = portal_health.HEALTH_PATH
PROXY_HEALTH_PATH = "/v1/health"
# The proxy Worker configs whose routes are probed: bench is live, and eu joins this tuple when its Worker deploys the probe-aware code.
PROXY_CONFIGS = ("workers/proxy/wrangler.bench-eu.toml",)
PROBE_HEADER = "X-Rediacc-Probe"
SIGNALS = ("traces", "logs")
TIMEOUT_S = 20.0
USER_AGENT = "rediacc-telemetry-delivery/1"
# The Workers' service name is the script name (account-<r>, proxy-<r>), not a fixed prefix.
LOKI_SELECTOR = '{service_name=~"(account|proxy)-.+"}'


@dataclass(frozen=True)
class Reply:
    """`status` is 0 when no HTTP answer arrived, and `error` then names the exception class."""

    status: int
    body: bytes = b""
    error: str = ""


Get = Callable[[str, Mapping[str, str]], Reply]


def make_get(http: str = "never") -> Get:
    """A GET through `rediacc_ci.core.https`; `http="loopback"` admits a fixture server the caller started."""

    def get(url: str, headers: Mapping[str, str]) -> Reply:
        try:
            request = https.build_request(
                url, headers={"User-Agent": USER_AGENT, **headers}, method="GET", http=http
            )
            with https.urlopen(request, timeout=TIMEOUT_S, http=http) as resp:
                return Reply(resp.status, resp.read(2_000_000))
        except urllib.error.HTTPError as exc:
            exc.close()
            return Reply(exc.code)
        except (OSError, ValueError) as exc:
            return Reply(0, error=type(exc).__name__)

    return get


@dataclass
class Target:
    host: str
    probe_id: str
    sent_at: float
    sent: Reply
    seen: dict[str, bool] = field(default_factory=lambda: dict.fromkeys(SIGNALS, False))
    # The last Grafana answer per signal that was not a 200 (status, or the error class when none arrived): a rejected token or a wrong datasource uid reads differently from an empty result.
    query_failed: dict[str, str] = field(default_factory=dict)


@dataclass
class AlertSeries:
    """The alert's series per account region: `found` once a series with a non-zero 6h increase exists, `failed` the last Prometheus answer that was not a 200."""

    regions: list[str]
    environments: list[str]
    # The Workers report their script name as `service` (account-eu, account-us, ...), one per region: `{region}` is replaced by the region id.
    service_template: str
    found: dict[str, bool] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.regions or not self.environments:
            raise ValueError("alert series needs at least one region and one environment")
        if "{region}" not in self.service_template:
            raise ValueError("service template %r has no {region}" % self.service_template)
        for value in (*self.regions, *self.environments):
            if not _LABEL_VALUE.fullmatch(value):
                raise ValueError("label value %r is not a plain label value" % value)
        for region in self.regions:
            if not _LABEL_VALUE.fullmatch(self.service(region)):
                raise ValueError(
                    "service name %r is not a plain label value" % self.service(region)
                )
        self.found = dict.fromkeys(self.regions, False)

    def service(self, region: str) -> str:
        return self.service_template.replace("{region}", region)

    def labels(self, region: str) -> str:
        return '{service="%s", deployment_environment=~"%s", rediacc_region="%s"}' % (
            self.service(region),
            "|".join(self.environments),
            region,
        )

    def query(self, region: str) -> str:
        return "sum(increase(traces_spanmetrics_calls_total%s[%s])) > 0" % (
            self.labels(region),
            ALERT_WINDOW,
        )


def account_environments(root=None) -> list[str]:
    """`telemetry.account_environments` of ops-health.json; a missing or malformed entry is an error, never a default."""
    base = root or repo_root()
    with open(base / CONFIG_REL, encoding="utf-8") as fh:
        doc = json.load(fh)
    envs = (doc.get("telemetry") or {}).get("account_environments")
    if not isinstance(envs, list) or not envs or not all(isinstance(e, str) for e in envs):
        raise ValueError("%s telemetry.account_environments is not a non-empty list" % CONFIG_REL)
    return envs


def account_service_template(root=None) -> str:
    """`telemetry.account_service_template` of ops-health.json (`account-{region}`); a missing or malformed entry is an error, never a default."""
    base = root or repo_root()
    with open(base / CONFIG_REL, encoding="utf-8") as fh:
        doc = json.load(fh)
    template = (doc.get("telemetry") or {}).get("account_service_template")
    if not isinstance(template, str) or "{region}" not in template:
        raise ValueError("%s telemetry.account_service_template has no {region}" % CONFIG_REL)
    return template


def _prom_url(grafana: str, query: str) -> str:
    return "%s/api/datasources/proxy/uid/%s/api/v1/query?%s" % (
        grafana,
        PROMETHEUS_UID,
        urllib.parse.urlencode({"query": query}),
    )


def prom_has(reply: Reply) -> bool:
    data = _json(reply)
    if not isinstance(data, dict) or data.get("status") != "success":
        return False
    return bool((data.get("data") or {}).get("result"))


def poll_alert_series(alert: AlertSeries, get: Get, grafana: str, token: str) -> None:
    headers = {"Authorization": "Bearer %s" % token}
    for region in alert.regions:
        if alert.found[region]:
            continue
        reply = get(_prom_url(grafana, alert.query(region)), headers)
        if reply.status != 200:
            alert.failed[region] = str(reply.status or reply.error or "nothing")
        else:
            alert.failed.pop(region, None)
        alert.found[region] = prom_has(reply)


def all_hosts(regions: list[dict] | None = None) -> list[str]:
    out: list[str] = []
    for target in portal_health.TARGETS:
        out.extend(portal_health.hosts(target, None, regions))
    return out


def proxy_hosts(configs: tuple[str, ...] = PROXY_CONFIGS, root=None) -> list[str]:
    """The custom-domain route patterns of the listed proxy wrangler configs, in order."""
    base = root or repo_root()
    out: list[str] = []
    for rel in configs:
        with open(base / rel, "rb") as fh:
            conf = tomllib.load(fh)
        for route in conf.get("routes", []):
            pattern = route if isinstance(route, str) else route.get("pattern", "")
            if not pattern:
                raise ValueError("route without a pattern in %s" % rel)
            out.append(pattern)
    return out


def send_probe(host: str, get: Get, base: str | None = None, path: str = HEALTH_PATH) -> Target:
    probe_id = str(uuid.uuid4())
    url = (base or "https://%s" % host).rstrip("/") + path
    sent_at = time.time()
    return Target(host, probe_id, sent_at, get(url, {PROBE_HEADER: probe_id}))


def _tempo_url(grafana: str, t: Target, now: float) -> str:
    query = urllib.parse.urlencode(
        {
            "tags": "rediacc.probe=%s" % t.probe_id,
            "start": int(t.sent_at) - 60,
            "end": int(now) + 60,
            "limit": 5,
        }
    )
    return "%s/api/datasources/proxy/uid/%s/api/search?%s" % (grafana, TEMPO_UID, query)


def _loki_url(grafana: str, t: Target, now: float) -> str:
    query = urllib.parse.urlencode(
        {
            "query": '%s |= "%s"' % (LOKI_SELECTOR, t.probe_id),
            "start": int((t.sent_at - 60) * 1e9),
            "end": int((now + 60) * 1e9),
            "limit": 5,
        }
    )
    return "%s/api/datasources/proxy/uid/%s/loki/api/v1/query_range?%s" % (grafana, LOKI_UID, query)


def _json(reply: Reply) -> object:
    if reply.status != 200:
        return None
    try:
        return json.loads(reply.body)
    except ValueError:
        return None


def tempo_has(reply: Reply) -> bool:
    data = _json(reply)
    return isinstance(data, dict) and bool(data.get("traces"))


def loki_has(reply: Reply) -> bool:
    data = _json(reply)
    if not isinstance(data, dict) or data.get("status") != "success":
        return False
    result = (data.get("data") or {}).get("result")
    if not result:
        return False
    return any(stream.get("values") for stream in result)


def poll_once(targets: list[Target], get: Get, grafana: str, token: str) -> None:
    headers = {"Authorization": "Bearer %s" % token}
    now = time.time()
    for t in targets:
        if t.sent.status != 200:
            continue
        for signal, url, has in (
            ("traces", _tempo_url(grafana, t, now), tempo_has),
            ("logs", _loki_url(grafana, t, now), loki_has),
        ):
            if t.seen[signal]:
                continue
            reply = get(url, headers)
            if reply.status != 200:
                t.query_failed[signal] = str(reply.status or reply.error or "nothing")
            else:
                t.query_failed.pop(signal, None)
            t.seen[signal] = has(reply)


def run(
    hosts: list[str],
    get: Get,
    grafana: str,
    token: str,
    *,
    timeout_s: float,
    interval_s: float,
    base_for: Callable[[str], str | None] = lambda _host: None,
    proxies: frozenset[str] = frozenset(),
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    out=None,
    alert: AlertSeries | None = None,
) -> int:
    out = out or sys.stdout
    if not hosts:
        # No target means nothing was probed, and a probe that probed nothing proves nothing: not a pass.
        print("no hosts to probe: nothing was verified", file=sys.stderr)
        return 2
    targets = [
        send_probe(h, get, base_for(h), PROXY_HEALTH_PATH if h in proxies else HEALTH_PATH)
        for h in hosts
    ]
    deadline = clock() + timeout_s
    while True:
        poll_once(targets, get, grafana, token)
        if alert:
            poll_alert_series(alert, get, grafana, token)
        pending = [t for t in targets if t.sent.status == 200 and not all(t.seen.values())]
        alert_pending = alert is not None and not all(alert.found.values())
        if not (pending or alert_pending) or clock() >= deadline:
            break
        sleep(interval_s)
    queried = [t for t in targets if t.sent.status == 200]
    # Every Grafana answer a 401 or 403: the credential is rejected, which is not a telemetry outage and must not read as one.
    rejected = {t.query_failed.get(sig) for t in queried for sig in SIGNALS}
    if alert:
        rejected |= {alert.failed.get(r) for r in alert.regions}
    if queried and rejected and rejected <= {"401", "403"}:
        print(
            "grafana rejected %s (answered %s to every query): the read credential is revoked or wrong, delivery was not judged"
            % (READ_CREDENTIAL_ENV, "/".join(sorted(str(r) for r in rejected))),
            file=sys.stderr,
        )
        return 2
    silent = 0
    for t in targets:
        for signal in SIGNALS:
            if t.seen[signal]:
                print("PASS %s %s" % (t.host, signal), file=out)
                continue
            silent += 1
            why = ""
            if t.sent.status != 200:
                why = " (probe answered %s)" % (t.sent.status or t.sent.error or "nothing")
            elif signal in t.query_failed:
                why = " (grafana query answered %s)" % t.query_failed[signal]
            print("SILENT %s %s%s" % (t.host, signal, why), file=out)
    signals = len(targets) * len(SIGNALS)
    if alert:
        for region in alert.regions:
            signals += 1
            if alert.found[region]:
                print("PASS %s (alert labels)" % region, file=out)
                continue
            silent += 1
            why = ""
            if region in alert.failed:
                why = " (grafana query answered %s)" % alert.failed[region]
            print(
                "SILENT %s (alert labels): no series %s with a non-zero increase over %s%s"
                % (region, alert.labels(region), ALERT_WINDOW, why),
                file=out,
            )
    print("%d hosts, %d signals, %d silent" % (len(targets), signals, silent), file=out)
    return 1 if silent else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="telemetry_delivery", description=__doc__.splitlines()[0])
    parser.add_argument("--timeout-s", type=float, default=600.0)
    parser.add_argument("--interval-s", type=float, default=20.0)
    parser.add_argument("--grafana", default=GRAFANA_ORIGIN)
    args = parser.parse_args(argv)
    token = os.environ.get(READ_CREDENTIAL_ENV, "")
    if not token:
        print("%s is not set" % READ_CREDENTIAL_ENV, file=sys.stderr)
        return 2
    try:
        proxies = proxy_hosts()
        hosts = list(dict.fromkeys(all_hosts() + proxies))
        alert = AlertSeries(
            [r["id"] for r in portal_health.load_regions()],
            account_environments(),
            account_service_template(),
        )
    except (ValueError, OSError, KeyError) as exc:
        print("cannot list hosts: %s" % type(exc).__name__, file=sys.stderr)
        return 2
    return run(
        hosts,
        make_get(),
        args.grafana.rstrip("/"),
        token,
        timeout_s=args.timeout_s,
        interval_s=args.interval_s,
        proxies=frozenset(proxies),
        alert=alert,
    )


if __name__ == "__main__":
    raise SystemExit(main())
