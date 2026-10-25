"""List, and optionally delete, the secrets on a live account Worker that no deploy pushes any more.

WHY. `wrangler secret bulk` only ever adds or overwrites: a name dropped from `set_account_worker_secrets.KEYS` stays on the Worker for good, still readable by the code, and nothing reports it. The 2026-10-15 cleanup of the shared backup pair was done by hand. This verb compares the names the live Worker holds with the names the deploy pushes and names the difference.

WHY THE API AND NOT `wrangler secret delete`. Each `wrangler secret delete` mints a new Worker version, and on an assets-bound Worker a new version disassociates the static assets the last deploy uploaded (the reason the deploy is one bulk call). Cloudflare's own `DELETE /accounts/{id}/workers/scripts/{name}/secrets/{secret}` removes the one binding and keeps the ASSETS binding (measured 2026-10-15).

DEFAULT IS A LISTING. Nothing is deleted without `--delete`. Names are the only output, never a value (the list endpoint returns none).

Run: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- python3 -m rediacc_ci.ops.prune_worker_secrets --region eu --target stable`

Options: `--region eu|us|asia|all` (default all), `--target stable|edge|all` (default all), `--delete`, `--json` (one JSON object on stdout, for `check:ci-worker-secret-names`).

Exit codes: 0 no extras, 1 extras listed (or a delete failed), 2 no verdict (missing credential, API failure, unknown option).
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
import urllib.error
import urllib.parse
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import https
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Mapping

    Fetch = Callable[[str, str, str], object]

SELF = "rediacc_ci.ops.prune_worker_secrets"
REGIONS_REL = "regions.json"
# The binding type the secrets endpoint reports for a value set through `wrangler secret`. Other types on the list were not pushed by the bulk call and are never touched.
TEXT_BINDING = "secret_text"


class ApiError(Exception):
    """The Cloudflare API gave no usable answer. Names and CF error text only."""


@dataclasses.dataclass
class Row:
    """One live Worker and what it holds beyond the push."""

    region: str
    target: str
    worker: str
    live: int = 0
    expected: int = 0
    extras: list[str] = dataclasses.field(default_factory=list)

    def as_json(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Options:
    region: str = "all"
    target: str = "all"
    delete: bool = False
    json: bool = False


def expected_names() -> list[str]:
    """The Worker keys one account deploy pushes, in push order."""
    return [key for key, _var, _source in pusher.KEYS]


def load_workers(root: pathlib.Path | None = None) -> list[Row]:
    """Every (region, channel, worker) of `regions.json`."""
    base = paths.repo_root() if root is None else root
    doc = json.loads(base.joinpath(REGIONS_REL).read_text(encoding="utf-8"))
    rows: list[Row] = []
    for region in doc["regions"]:
        rows.append(Row(region["id"], "stable", region["workerName"]))
        rows.append(Row(region["id"], "edge", region["edgeWorkerName"]))
    return rows


def extras(live: list[dict[str, object]], expected: list[str]) -> list[str]:
    """Live secret names (type secret_text) the deploy does not push, sorted."""
    keep = set(expected)
    return sorted(
        str(item.get("name"))
        for item in live
        if item.get("type", TEXT_BINDING) == TEXT_BINDING and str(item.get("name")) not in keep
    )


def _cf_errors(raw: bytes) -> str:
    try:
        errs = json.loads(raw).get("errors") or []
        return ": " + "; ".join("%s %s" % (e.get("code"), e.get("message")) for e in errs)
    except (ValueError, AttributeError):
        return ""


def http_fetch(method: str, path: str, token: str) -> object:
    """The `result` of a successful Cloudflare v4 envelope; ApiError otherwise."""
    label = re.sub(r"/accounts/[^/]+", "/accounts/{account_id}", path)
    req = https.build_request(
        CF_API_BASE + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
            "User-Agent": "rediacc-ci-prune-worker-secrets",
        },
        method=method,
    )
    try:
        with https.urlopen(req, timeout=30) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raise ApiError(
            "HTTP %d on %s %s%s" % (exc.code, method, label, _cf_errors(exc.read()))
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError("transport failure on %s %s: %s" % (method, label, exc)) from None
    try:
        body = json.loads(raw)
    except ValueError:
        raise ApiError("non-JSON body on %s %s" % (method, label)) from None
    if not isinstance(body, dict) or body.get("success") is not True:
        raise ApiError("success is not true on %s %s%s" % (method, label, _cf_errors(raw)))
    return body.get("result")


def secrets_path(account: str, worker: str, name: str | None = None) -> str:
    base = "/accounts/%s/workers/scripts/%s/secrets" % (
        urllib.parse.quote(account, safe=""),
        urllib.parse.quote(worker, safe=""),
    )
    return base if name is None else base + "/" + urllib.parse.quote(name, safe="")


def survey(rows: list[Row], account: str, token: str, fetch: Fetch) -> list[Row]:
    """Fill each row with its live count and extras."""
    want = expected_names()
    for row in rows:
        result = fetch("GET", secrets_path(account, row.worker), token)
        if not isinstance(result, list):
            raise ApiError("the secrets list of %s is not a list" % row.worker)
        live = [item for item in result if isinstance(item, dict)]
        row.live = len(live)
        row.expected = len(want)
        row.extras = extras(live, want)
    return rows


def delete_extras(rows: list[Row], account: str, token: str, fetch: Fetch) -> list[str]:
    """Delete every extra through the API. Returns the failure lines."""
    failures: list[str] = []
    for row in rows:
        for name in row.extras:
            try:
                fetch("DELETE", secrets_path(account, row.worker, name), token)
            except ApiError as exc:
                failures.append("%s: %s" % (row.worker, exc))
    return failures


def parse(argv: list[str]) -> Options | None:
    opts = Options()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--delete":
            opts.delete = True
        elif arg == "--json":
            opts.json = True
        elif arg == "--region" and i + 1 < len(argv):
            opts.region = argv[i + 1]
            i += 1
        elif arg == "--target" and i + 1 < len(argv):
            opts.target = argv[i + 1]
            i += 1
        else:
            return None
        i += 1
    return opts


def run(
    argv: list[str],
    env: Mapping[str, str],
    fetch: Fetch,
    root: pathlib.Path | None = None,
) -> tuple[int, list[str], list[Row]]:
    """(exit code, lines, surveyed rows). Pure apart from `fetch`."""
    opts = parse(argv)
    if opts is None:
        return 2, ["%s: unexpected argument; see the module docstring" % SELF], []
    token = (env.get("CLOUDFLARE_API_TOKEN") or "").strip()
    account = (env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if not token or not account:
        return (
            2,
            ["%s: CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set; no verdict" % SELF],
            [],
        )
    chosen = [
        w
        for w in load_workers(root)
        if opts.region in ("all", w.region) and opts.target in ("all", w.target)
    ]
    if not chosen:
        return (
            2,
            ["%s: no Worker matches --region %s --target %s" % (SELF, opts.region, opts.target)],
            [],
        )
    try:
        rows = survey(chosen, account, token, fetch)
    except ApiError as exc:
        return 2, ["%s: %s; failing closed, no verdict" % (SELF, exc)], []
    lines = [
        "%s (%s %s): %d live, %d pushed, extras: %s"
        % (r.worker, r.region, r.target, r.live, r.expected, " ".join(r.extras) or "none")
        for r in rows
    ]
    total = sum(len(r.extras) for r in rows)
    if total == 0:
        return 0, lines, rows
    if opts.delete:
        failures = delete_extras(rows, account, token, fetch)
        lines += ["deleted %d extra(s) through the API" % (total - len(failures)), *failures]
        return (1 if failures else 0), lines, rows
    lines.append("dry run: nothing deleted; re-run with --delete to remove the extras")
    return 1, lines, rows


def main(argv: list[str]) -> int:
    code, lines, rows = run(
        argv,
        {
            "CLOUDFLARE_API_TOKEN": os.environ.get("CLOUDFLARE_API_TOKEN", ""),
            "CLOUDFLARE_ACCOUNT_ID": os.environ.get("CLOUDFLARE_ACCOUNT_ID", ""),
        },
        http_fetch,
    )
    as_json = "--json" in argv
    if as_json and rows:
        print(json.dumps({"workers": [r.as_json() for r in rows]}))
    for line in lines:
        print(line, file=sys.stdout if code == 0 and not as_json else sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
