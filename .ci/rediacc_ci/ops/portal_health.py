"""Is the account portal of one environment up: the login page, every asset it references, and the API health route.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.portal_health --target stable|edge|bench [--region eu|us|asia]

WHY IT EXISTS. A secret push to an account Worker mints a new Worker version, and on an assets-bound Worker a bad version can strand the static assets the last deploy uploaded (the reason `set_account_worker_secrets` pushes in ONE bulk call). `push_backup_credentials` rotates the backup key pair on a live Worker outside a release, so it needs a before-and-after verdict that covers the three ways a portal breaks: the SPA shell, the bundle it loads, and the API behind it (agent/plans/PLAN-backup-credential-isolation.md B3 and B6).

THE THREE PROBES, per host, all GET, nothing written:

  1. `https://<host>/account/login` answers 200 with an HTML content type.
  2. Every `/account/assets/*.js` and `/account/assets/*.css` that page references answers 200. A login page that references NO asset is RED, not vacuously green: the shell that loads the portal always references its bundle, so zero means the page is not the portal.
  3. `https://<host>/account/api/v1/health` answers 200 with a JSON body whose `status` is `ok` (private/account/src/routes/index.ts).

HOSTS come from regions.json (`domain` for stable, `edgeDomain` for edge, every region or the one `--region` names) and, for bench, from `well_known.BENCH_ORIGIN`, the origin deploy_bench deploys to.

OUTPUT IS A URL AND A STATUS PER LINE, and nothing else from a response: no body, no header value. A summary line gives the shape (hosts, URLs, red count) so a collapse to zero is visible. Exit 0 when every probe is green, 1 on any red, 2 on a usage error. A probe that cannot connect is red with the error's class name, never skipped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass

from rediacc_ci import paths
from rediacc_ci.core import https
from rediacc_ci.well_known import BENCH_ORIGIN, GH_ORIGIN, GH_REPO

TARGETS = ("stable", "edge", "bench")
LOGIN_PATH = "/account/login"
HEALTH_PATH = "/account/api/v1/health"
# Every asset reference the login shell carries, as a root-relative or absolute URL path. The class excludes quotes, whitespace, `<`, `>` and `?`/`#` (a query or fragment is not part of the file).
ASSET_RE = re.compile(r"(/account/assets/[^\"'\s<>?#]+\.(?:js|css))")
TIMEOUT_S = 20.0
# Cloudflare answers the default `Python-urllib/x.y` agent with a 403 browser-integrity block on some zones, which would read as a broken portal. A named agent says who is probing.
USER_AGENT = "rediacc-portal-health/1 (+%s/%s)" % (GH_ORIGIN, GH_REPO)


@dataclass(frozen=True)
class Response:
    """What a probe needs from one GET, and no more. `status` is 0 when no HTTP answer arrived; `error` then names the exception class."""

    status: int
    content_type: str = ""
    body: bytes = b""
    error: str = ""


Fetch = Callable[[str], Response]


def http_get(url: str) -> Response:
    """One GET through `rediacc_ci.core.https`, which refuses any scheme but https. An HTTP error status is an answer, not an exception."""
    request = https.build_request(url, headers={"User-Agent": USER_AGENT}, method="GET")
    try:
        with https.urlopen(request, timeout=TIMEOUT_S) as resp:
            return Response(
                resp.status, resp.headers.get("Content-Type") or "", resp.read(2_000_000)
            )
    except urllib.error.HTTPError as exc:
        return Response(exc.code, exc.headers.get("Content-Type") or "" if exc.headers else "")
    except (OSError, ValueError) as exc:
        return Response(0, error=type(exc).__name__)


def load_regions() -> list[dict]:
    with open(paths.repo_root() / "regions.json", encoding="utf-8") as fh:
        regions = json.load(fh)["regions"]
    if not regions:
        raise ValueError("regions.json lists no region")
    return regions


def hosts(target: str, region: str | None, regions: list[dict] | None = None) -> list[str]:
    """The hosts of one environment, or of one region of it. ValueError on an unknown target or region, or a region given for bench."""
    if target not in TARGETS:
        raise ValueError("unknown target %r (expected one of %s)" % (target, ", ".join(TARGETS)))
    if target == "bench":
        if region:
            raise ValueError("bench has one host and no regions; drop --region")
        return [BENCH_ORIGIN.removeprefix("https://").rstrip("/")]
    regions = load_regions() if regions is None else regions
    field = "domain" if target == "stable" else "edgeDomain"
    chosen = [r for r in regions if region is None or r["id"] == region]
    if not chosen:
        raise ValueError(
            "unknown region %r (regions.json has %s)"
            % (region, ", ".join(r["id"] for r in regions))
        )
    return [r[field] for r in chosen]


def asset_paths(html: str) -> list[str]:
    """The distinct asset paths a login page references, in first-seen order."""
    seen: dict[str, None] = {}
    for match in ASSET_RE.finditer(html):
        seen.setdefault(match.group(1), None)
    return list(seen)


@dataclass
class Probe:
    url: str
    status: int
    ok: bool
    why: str = ""


def _line(probe: Probe) -> str:
    verdict = "ok " if probe.ok else "RED"
    status = str(probe.status) if probe.status else "---"
    return "  %s %s  %s%s" % (
        verdict,
        status,
        probe.url,
        ("  (%s)" % probe.why) if probe.why else "",
    )


def check_host(host: str, fetch: Fetch) -> list[Probe]:
    """Every probe for one host, in order: login, its assets, health."""
    base = "https://%s" % host
    probes: list[Probe] = []
    login_url = base + LOGIN_PATH
    login = fetch(login_url)
    html_ok = "text/html" in login.content_type.lower()
    if login.status != 200:
        probes.append(Probe(login_url, login.status, False, login.error or "expected 200"))
    elif not html_ok:
        probes.append(Probe(login_url, login.status, False, "not HTML"))
    else:
        probes.append(Probe(login_url, login.status, True))
    if login.status == 200 and html_ok:
        assets = asset_paths(login.body.decode("utf-8", "replace"))
        if not assets:
            probes.append(
                Probe(
                    login_url, login.status, False, "the page references no /account/assets/ file"
                )
            )
        for path in assets:
            url = base + path
            got = fetch(url)
            ok = got.status == 200
            probes.append(Probe(url, got.status, ok, "" if ok else (got.error or "expected 200")))
    health_url = base + HEALTH_PATH
    health = fetch(health_url)
    status_ok = False
    if health.status == 200:
        try:
            status_ok = json.loads(health.body.decode("utf-8", "replace")).get("status") == "ok"
        except (ValueError, AttributeError):
            status_ok = False
    why = ""
    if not status_ok:
        why = health.error or ("status is not ok" if health.status == 200 else "expected 200")
    probes.append(Probe(health_url, health.status, status_ok, why))
    return probes


def run(target: str, region: str | None, fetch: Fetch = http_get, out=None) -> int:
    """Probe every host of the target (or of the one region); print one line per URL and a summary. 0 green, 1 red."""
    out = sys.stdout if out is None else out
    names = hosts(target, region)
    red = 0
    total = 0
    for host in names:
        print("portal health: %s %s" % (target, host), file=out, flush=True)
        for probe in check_host(host, fetch):
            total += 1
            red += 0 if probe.ok else 1
            print(_line(probe), file=out, flush=True)
    if not total:
        print("portal health: RED, no URL was probed; the verdict would mean nothing", file=out)
        return 1
    print(
        "portal health: %s, %d host(s), %d URL(s), %d red"
        % ("GREEN" if red == 0 else "RED", len(names), total, red),
        file=out,
        flush=True,
    )
    return 0 if red == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rediacc_ci.ops.portal_health",
        description=(__doc__ or "").splitlines()[0],
    )
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--region", default=None, help="one regions.json id (stable and edge only)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run(args.target, args.region)
    except ValueError as exc:
        print("portal health: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
