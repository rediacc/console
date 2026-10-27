"""Audit every Worker `[[services]]` binding against the Workers that exist on Cloudflare.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- \\
        env PYTHONPATH=.ci python3 -m rediacc_ci.ops.service_bindings_audit [--json]

WHY. `deploy_account --target edge` once applied D1 migrations 0060-0066 and only then died on wrangler's `Service binding 'EXECUTOR' references Worker 'edge-rediacc-proxy-eu' which was not found [code: 10143]` (2026-10-27). A binding to a Worker that is not deployed is knowable up front.

WHAT IT DOES. Parses every `workers/*/wrangler*.toml` (a template carrying `@@` placeholders is skipped), takes the config's worker name, its side (bench, edge, stable, dev) and region from the file name, and its `[[services]]` bindings. It lists the account's Workers read-only (`GET /accounts/<id>/workers/scripts`) and prints one row per binding, `present` or `MISSING`. A config whose own Worker is not deployed is an advisory (`NOT-DEPLOYED`), never a failure. Nothing is deployed or written.

EXIT. 0 nothing missing; 1 a binding target is missing; 77 the account could not be read (unset credentials, API error, empty list): never green on no data.

AUTH. `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the environment (profile `deploy-workers`); the token goes in a request header, never argv, and no value is printed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import subprocess
import sys
import tomllib
import typing

from rediacc_ci import paths
from rediacc_ci.core import curl_stdin

EX_UNAVAILABLE = 77
API = "https://api.cloudflare.com/client/v4"
MAX_PAGES = 50
PER_PAGE = 100


class AuditError(Exception):
    """The account could not be read; the exit status is 77."""


@dataclasses.dataclass(frozen=True)
class Binding:
    config: str
    worker: str
    side: str
    region: str
    binding: str
    service: str


@dataclasses.dataclass(frozen=True)
class Config:
    config: str
    worker: str
    side: str
    region: str


def side_region(rel: pathlib.PurePosixPath) -> tuple[str, str]:
    """(side, region) from the wrangler file name: `wrangler.edge-eu.toml` -> edge/eu."""
    stem = rel.name.removeprefix("wrangler.").removesuffix(".toml")
    if rel.name == "wrangler.toml":
        stem = ""
    if stem == "bench":
        return "bench", "-"
    if stem == "dev":
        return "dev", "-"
    if stem == "edge":
        return "edge", "-"
    if stem.startswith("edge-"):
        return "edge", stem[len("edge-") :]
    return "stable", stem or "-"


def load_configs(root: pathlib.Path) -> tuple[list[Config], list[Binding]]:
    configs: list[Config] = []
    bindings: list[Binding] = []
    for path in sorted((root / "workers").glob("*/wrangler*.toml")):
        rel = pathlib.PurePosixPath(path.relative_to(root).as_posix())
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise AuditError("cannot parse %s: %s" % (rel, exc)) from None
        name = str(data.get("name") or "")
        if not name or "@@" in name:
            continue
        side, region = side_region(rel)
        configs.append(Config(str(rel), name, side, region))
        for svc in data.get("services") or []:
            service = str(svc.get("service") or "")
            if service and "@@" not in service:
                bindings.append(
                    Binding(str(rel), name, side, region, str(svc.get("binding") or ""), service)
                )
    return configs, bindings


def _get(url: str, token: str) -> dict:
    argv, stdin = curl_stdin.stdin_headers(
        ["curl", "-sS", "--max-time", "30", "-H", "Authorization: Bearer " + token, url]
    )
    try:
        proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise AuditError("curl exited %d" % proc.returncode)
        return json.loads(proc.stdout)
    except (OSError, ValueError) as exc:
        raise AuditError("Cloudflare API unreadable: %s" % type(exc).__name__) from None


Fetch = typing.Callable[[str, str], dict]


def list_workers(account: str, token: str, fetch: Fetch = _get) -> set[str]:
    names: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        body = fetch(
            "%s/accounts/%s/workers/scripts?page=%d&per_page=%d" % (API, account, page, PER_PAGE),
            token,
        )
        if not body.get("success", False):
            raise AuditError("Cloudflare API refused the Workers listing (success=false)")
        result = body.get("result") or []
        names.update(str(w.get("id") or "") for w in result if isinstance(w, dict))
        if len(result) < PER_PAGE:
            break
    names.discard("")
    if not names:
        raise AuditError("the account lists ZERO Workers: wrong account or token, no verdict")
    return names


def audit(root: pathlib.Path, env: typing.Mapping[str, str], fetch: Fetch = _get) -> dict:
    """The report dict; `rc` is 0, 1 or 77, `error` is set on 77."""
    token = (env.get("CLOUDFLARE_API_TOKEN") or "").strip()
    account = (env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    try:
        if not token or not account:
            raise AuditError("CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID unset or empty")
        configs, bindings = load_configs(root)
        live = list_workers(account, token, fetch)
    except AuditError as exc:
        return {"rc": EX_UNAVAILABLE, "error": str(exc), "bindings": [], "not_deployed": []}
    rows = [
        {**dataclasses.asdict(b), "status": "present" if b.service in live else "MISSING"}
        for b in bindings
    ]
    not_deployed = [dataclasses.asdict(c) for c in configs if c.worker not in live]
    missing = [r for r in rows if r["status"] == "MISSING"]
    return {
        "rc": 1 if missing else 0,
        "error": None,
        "bindings": rows,
        "not_deployed": not_deployed,
        "workers_on_account": len(live),
    }


def render(report: dict) -> str:
    if report["error"]:
        return "service-bindings-audit: no verdict: %s" % report["error"]
    fmt = "%-7s %-6s %-30s %-9s %-28s %s"
    lines = [fmt % ("SIDE", "REGION", "WORKER", "BINDING", "TARGET", "STATUS")]
    lines.extend(
        fmt % (r["side"], r["region"], r["worker"], r["binding"], r["service"], r["status"])
        for r in report["bindings"]
    )
    lines.extend(
        "NOT-DEPLOYED (advisory): %s (%s %s, %s)"
        % (c["worker"], c["side"], c["region"], c["config"])
        for c in report["not_deployed"]
    )
    missing = sum(1 for r in report["bindings"] if r["status"] == "MISSING")
    lines.append(
        "%d binding(s), %d MISSING, %d Worker(s) on the account"
        % (len(report["bindings"]), missing, report["workers_on_account"])
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    report = audit(paths.repo_root(), os.environ)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return int(report["rc"])


if __name__ == "__main__":
    sys.exit(main())
