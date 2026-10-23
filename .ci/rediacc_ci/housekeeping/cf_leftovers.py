#!/usr/bin/env python3
"""Report-only listing of Cloudflare leftovers that no PR cleanup owns.

PLAN-cloudflare-spend-guard T7. Four listings, all read with GET, nothing deleted or changed:

  script  a Workers script named by no `workers/*/wrangler*.toml` (nor `private/account/wrangler.toml`) and not a PR preview (`pr-<n>`, which the PR-close cleanup owns)
  d1      a D1 database matching `edge-*` or `*-bench` that no config binds as `database_name`
  route   a Workers route in any zone whose script is absent from the account, or that names no script
  domain  a Workers custom domain whose service is absent from the account

Exit status: 0 whatever was found (a finding is a report line, never a failure). 1 when a listing could not be read or the environment is incomplete: an unreadable listing printed as "nothing found" is the vacuity this report must not have.

Usage: PYTHONPATH=.ci python3 -m rediacc_ci.housekeeping.cf_leftovers
Environment: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID. The token is sent in a header only and never printed.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.request

from rediacc_ci import paths
from rediacc_ci.well_known import CF_API_BASE

PR_SCRIPT_RE = re.compile(r"^pr-[0-9]+$")
D1_PATTERNS = ("edge-*", "*-bench")
CONFIG_GLOBS = ("workers/*/wrangler*.toml", "private/account/wrangler*.toml")
PAGE = 100


class CfError(Exception):
    """A Cloudflare read that failed; the message names the path and Cloudflare's own errors."""


def fetch(path: str, token: str) -> dict:
    """GET one API path and return the decoded body, raising CfError on any failure. The only network call here."""
    req = urllib.request.Request(
        CF_API_BASE + path, headers={"Authorization": "Bearer " + token}, method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CfError("GET %s: %s" % (path, exc)) from None
    try:
        body = json.loads(raw)
    except ValueError:
        raise CfError("GET %s: non-JSON answer" % path) from None
    if not isinstance(body, dict) or body.get("success") is not True:
        errors = body.get("errors") if isinstance(body, dict) else None
        raise CfError("GET %s: %s" % (path, json.dumps(errors)))
    return body


def listing(path: str, token: str, get=fetch) -> list:
    """Every `result` item of a paginated path (`per_page` and `page` appended)."""
    sep = "&" if "?" in path else "?"
    items: list = []
    page = 1
    while True:
        body = get("%s%sper_page=%d&page=%d" % (path, sep, PAGE, page), token)
        chunk = body.get("result") or []
        items.extend(chunk)
        info = body.get("result_info") or {}
        total_pages = info.get("total_pages")
        if total_pages is not None:
            if page >= total_pages:
                break
        elif len(chunk) < PAGE:
            break
        page += 1
    return items


def _dbs(node, dbs: set) -> None:
    if isinstance(node, dict):
        db = node.get("database_name")
        if isinstance(db, str):
            dbs.add(db)
        for value in node.values():
            _dbs(value, dbs)
    elif isinstance(node, list):
        for value in node:
            _dbs(value, dbs)


def configured(root) -> tuple[set, set]:
    """(Worker names, D1 database names) the repo's wrangler configs declare, `[env.*]` blocks included."""
    scripts: set = set()
    dbs: set = set()
    files = sorted({p for g in CONFIG_GLOBS for p in root.glob(g)})
    if not files:
        raise CfError("no wrangler config found under %s" % root)
    for path in files:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        top = data.get("name")
        if isinstance(top, str):
            scripts.add(top)
        for env in (data.get("env") or {}).values():
            if isinstance(env, dict) and isinstance(env.get("name"), str):
                scripts.add(env["name"])
        _dbs(data, dbs)
    return scripts, dbs


def find_leftovers(
    root, account: str, token: str, get=fetch, scanned: dict | None = None
) -> list[tuple[str, str, str]]:
    """Every (kind, name, detail) leftover. Raises CfError when any listing cannot be read."""
    known_scripts, known_dbs = configured(root)
    live = [
        s["id"]
        for s in listing("/accounts/%s/workers/scripts" % account, token, get)
        if isinstance(s, dict) and isinstance(s.get("id"), str)
    ]
    live_set = set(live)
    counts = {"scripts": len(live_set), "d1": 0, "routes": 0, "domains": 0}
    out: list[tuple[str, str, str]] = []

    for name in sorted(live_set):
        if name not in known_scripts and not PR_SCRIPT_RE.match(name):
            out.append(("script", name, "named by no wrangler config"))

    d1_all = listing("/accounts/%s/d1/database" % account, token, get)
    counts["d1"] = len(d1_all)
    for db in d1_all:
        name = db.get("name", "") if isinstance(db, dict) else ""
        if any(fnmatch.fnmatchcase(name, pat) for pat in D1_PATTERNS) and name not in known_dbs:
            out.append(("d1", name, "bound by no wrangler config (uuid %s)" % db.get("uuid", "?")))

    for zone in listing("/zones", token, get):
        zid, zname = zone.get("id"), zone.get("name", "?")
        zone_routes = listing("/zones/%s/workers/routes" % zid, token, get)
        counts["routes"] += len(zone_routes)
        for route in zone_routes:
            script = route.get("script")
            pattern = route.get("pattern", "?")
            if not script:
                out.append(("route", pattern, "zone %s: names no script" % zname))
            elif script not in live_set:
                out.append(("route", pattern, "zone %s: script %s does not exist" % (zname, script)))

    domains = listing("/accounts/%s/workers/domains" % account, token, get)
    counts["domains"] = len(domains)
    for dom in domains:
        service = dom.get("service")
        if service not in live_set:
            out.append(
                ("domain", dom.get("hostname", "?"), "service %s does not exist" % service)
            )
    if scanned is not None:
        scanned.update(counts)
    return out


def main(argv: list[str], get=fetch) -> int:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account:
        print("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required", file=sys.stderr)
        return 1
    try:
        scanned: dict = {}
        found = find_leftovers(paths.repo_root(), account, token, get, scanned)
    except CfError as exc:
        print("cf_leftovers: cannot read: %s" % exc, file=sys.stderr)
        return 1
    for kind, name, detail in found:
        print("LEFTOVER %-6s %s  (%s)" % (kind, name, detail))
    print("cf_leftovers: scanned %s" % ", ".join("%d %s" % (v, k) for k, v in scanned.items()))
    print("cf_leftovers: %d leftover(s); report only, nothing deleted" % len(found))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
