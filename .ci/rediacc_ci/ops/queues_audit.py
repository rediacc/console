"""Audit the Cloudflare Queues one Worker config binds against the queues that exist on the account.

    PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- \\
        env PYTHONPATH=.ci python3 -m rediacc_ci.ops.queues_audit --config workers/account/wrangler.edge-eu.toml [--create] [--json]

WHY. `wrangler deploy` refuses a Worker whose `[[queues.producers]]` or `[[queues.consumers]]` names a queue that does not exist, after `deploy_account` has already applied the D1 migrations: the same failure shape `service_bindings_audit` guards for `[[services]]`. A missing queue is knowable up front.

WHAT IT DOES. Reads the producer queue, consumer queue and consumer `dead_letter_queue` names from one wrangler config (tomllib), lists the account's queues (`GET /accounts/<id>/queues`, paginated) and reports each as `present` or `MISSING`. `ensure` creates the missing ones (`POST /accounts/<id>/queues {queue_name}`), dead-letter queues first, and re-lists to confirm. Creation is idempotent and nothing is ever deleted or renamed.

EXIT. 0 nothing missing (or all created with --create); 1 a queue is missing (no --create) or a create did not confirm; 77 the account could not be read (unset credentials, API error, unparseable config): never green on no data.

AUTH. `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` from the environment; the token goes in a request header on curl's stdin, never argv, and no value is printed.
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

from rediacc_ci.core import curl_stdin
from rediacc_ci.ops.service_bindings_audit import API, EX_UNAVAILABLE, MAX_PAGES, PER_PAGE

Fetch = typing.Callable[[str, str], dict]
Post = typing.Callable[[str, str, dict], dict]


class QueueAuditError(Exception):
    """The account or the config could not be read; the exit status is 77."""


class QueueCreateError(Exception):
    """A queue could not be created, or did not show up on the re-list."""


@dataclasses.dataclass(frozen=True)
class Queue:
    name: str
    role: str  # "dead-letter", "consumer" or "producer"


def _curl(url: str, token: str, extra: list[str]) -> dict:
    argv, stdin = curl_stdin.stdin_headers(
        ["curl", "-sS", "--max-time", "30", *extra, "-H", "Authorization: Bearer " + token, url]
    )
    try:
        proc = subprocess.run(argv, input=stdin, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise QueueAuditError("curl exited %d" % proc.returncode)
        body = json.loads(proc.stdout)
    except (OSError, ValueError) as exc:
        raise QueueAuditError("Cloudflare API unreadable: %s" % type(exc).__name__) from None
    if not isinstance(body, dict):
        raise QueueAuditError("Cloudflare API answered JSON that is not an object")
    return body


def _get(url: str, token: str) -> dict:
    return _curl(url, token, [])


def _post(url: str, token: str, payload: dict) -> dict:
    return _curl(
        url,
        token,
        ["-X", "POST", "-H", "Content-Type: application/json", "-d", json.dumps(payload)],
    )


_ROLE_ORDER = {"dead-letter": 0, "consumer": 1, "producer": 2}


def config_queues(path: pathlib.Path) -> list[Queue]:
    """The distinct queues a wrangler config binds, dead-letter queues first, then consumers, then producers; each name appears once, at its first role."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise QueueAuditError("cannot parse %s: %s" % (path.name, exc)) from None
    queues = data.get("queues") or {}
    if not isinstance(queues, dict):
        raise QueueAuditError("cannot read %s: `queues` is not a table" % path.name)
    found: dict[str, str] = {}

    def add(section: str, key: str, role: str) -> None:
        entries = queues.get(section) or []
        if not isinstance(entries, list) or not all(isinstance(e, dict) for e in entries):
            raise QueueAuditError(
                "cannot read %s: queues.%s is not an array of tables" % (path.name, section)
            )
        for entry in entries:
            name = str(entry.get(key) or "")
            if name and "@@" not in name:
                found.setdefault(name, role)

    add("consumers", "dead_letter_queue", "dead-letter")
    add("consumers", "queue", "consumer")
    add("producers", "queue", "producer")
    ordered = sorted(found.items(), key=lambda kv: (_ROLE_ORDER[kv[1]], kv[0]))
    return [Queue(n, r) for n, r in ordered]


def list_queues(account: str, token: str, fetch: Fetch = _get) -> set[str]:
    """Every queue name on the account. An empty account is a real answer (nothing provisioned yet), unlike an empty Workers list."""
    names: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        body = fetch(
            "%s/accounts/%s/queues?page=%d&per_page=%d" % (API, account, page, PER_PAGE), token
        )
        if not isinstance(body, dict):
            raise QueueAuditError("Cloudflare API answered JSON that is not an object")
        if not body.get("success", False):
            raise QueueAuditError("Cloudflare API refused the queues listing (success=false)")
        result = body.get("result") or []
        names.update(str(q.get("queue_name") or "") for q in result if isinstance(q, dict))
        if len(result) < PER_PAGE:
            break
    else:
        raise QueueAuditError(
            "the queues listing runs past %d pages: a partial list gives no verdict" % MAX_PAGES
        )
    names.discard("")
    return names


def credentials(env: typing.Mapping[str, str]) -> tuple[str, str]:
    """(token, account id); QueueAuditError when either is unset or empty."""
    token = (env.get("CLOUDFLARE_API_TOKEN") or "").strip()
    account = (env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    if not token or not account:
        raise QueueAuditError("CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID unset or empty")
    return token, account


def audit(config: pathlib.Path, env: typing.Mapping[str, str], fetch: Fetch = _get) -> dict:
    """The report dict; `rc` is 0, 1 or 77 with `error` set on 77. A config without queues makes no API call and is rc 0."""
    try:
        wanted = config_queues(config)
        if not wanted:
            return {"rc": 0, "error": None, "queues": [], "missing": []}
        token, account = credentials(env)
        live = list_queues(account, token, fetch)
    except QueueAuditError as exc:
        return {"rc": EX_UNAVAILABLE, "error": str(exc), "queues": [], "missing": []}
    rows = [
        {"queue": q.name, "role": q.role, "status": "present" if q.name in live else "MISSING"}
        for q in wanted
    ]
    missing = [r["queue"] for r in rows if r["status"] == "MISSING"]
    return {"rc": 1 if missing else 0, "error": None, "queues": rows, "missing": missing}


def ensure(
    account: str,
    token: str,
    missing: typing.Sequence[str],
    fetch: Fetch = _get,
    post: Post = _post,
) -> list[str]:
    """Create each queue of `missing` in the order given (the report lists dead-letter queues first), then re-list and confirm. Returns the created names; QueueCreateError when a create is refused or a queue is absent from the re-list. Nothing is deleted or renamed."""
    created: list[str] = []
    for name in missing:
        try:
            body = post("%s/accounts/%s/queues" % (API, account), token, {"queue_name": name})
        except QueueAuditError as exc:
            raise QueueCreateError("creating queue %s failed: %s" % (name, exc)) from None
        if not isinstance(body, dict) or not body.get("success", False):
            raise QueueCreateError("Cloudflare refused creating queue %s (success=false)" % name)
        created.append(name)
    if not created:
        return created
    try:
        live = list_queues(account, token, fetch)
    except QueueAuditError as exc:
        raise QueueCreateError("cannot confirm the created queues: %s" % exc) from None
    absent = [n for n in created if n not in live]
    if absent:
        raise QueueCreateError(
            "queue(s) %s absent from the listing after creation" % ", ".join(absent)
        )
    return created


def render(report: dict) -> str:
    if report["error"]:
        return "queues-audit: no verdict: %s" % report["error"]
    lines = ["%-12s %-45s %s" % ("ROLE", "QUEUE", "STATUS")]
    lines.extend("%-12s %-45s %s" % (r["role"], r["queue"], r["status"]) for r in report["queues"])
    lines.append("%d queue(s), %d MISSING" % (len(report["queues"]), len(report["missing"])))
    if report.get("create_error"):
        lines.append("create failed: %s" % report["create_error"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--config", required=True, help="path of one wrangler config")
    ap.add_argument("--create", action="store_true", help="create the missing queues")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    report = audit(pathlib.Path(args.config), os.environ)
    if args.create and report["rc"] == 1:
        token, account = credentials(os.environ)
        try:
            report["created"] = ensure(account, token, report["missing"])
            report["rc"] = 0
            # The rows were read before the create; ensure() confirmed every created queue on a re-list.
            for row in report["queues"]:
                if row["queue"] in report["created"]:
                    row["status"] = "created"
            report["missing"] = []
        except QueueCreateError as exc:
            report["create_error"] = str(exc)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return int(report["rc"])


if __name__ == "__main__":
    sys.exit(main())
