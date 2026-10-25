"""List, and optionally archive then delete, the secrets on a live account Worker that no deploy pushes any more.

WHY. `wrangler secret bulk` only ever adds or overwrites: a name dropped from `set_account_worker_secrets.KEYS` stays on the Worker for good, still readable by the code, and nothing reports it. The 2026-10-15 cleanup of the shared backup pair was done by hand. This verb compares the names the live Worker holds with the names the deploy pushes and names the difference.

WHY THE API AND NOT `wrangler secret delete`. Each `wrangler secret delete` mints a new Worker version, and on an assets-bound Worker a new version disassociates the static assets the last deploy uploaded (the reason the deploy is one bulk call). Cloudflare's own `DELETE /accounts/{id}/workers/scripts/{name}/secrets/{secret}` removes the one binding and keeps the ASSETS binding (measured 2026-10-15).

DEFAULT IS A LISTING. Nothing is deleted without `--delete` or `--archive`. Names are the only output, never a value (the list endpoint returns none).

ARCHIVE BEFORE DELETE (operator ruling 2026-10-25). Worker secrets are write-only, so a deleted value cannot be read back from Cloudflare. `--archive` therefore takes the value from Bitwarden (bws), PUTs it as `__ARCHIVE_<NAME>` through the same secrets endpoint, confirms the archive name is listed, and only then DELETEs `<NAME>`. A name with no bws value is reported as having no recoverable copy and is left in place. `__ARCHIVE_*` names never count as extras. The value travels only in the JSON body of the PUT, never on argv or in a printed line.

WHICH BWS KEY HOLDS A LEGACY NAME (`LEGACY_BWS`, mapped explicitly; found by comparing `set_account_worker_secrets.KEYS` with `.ci/config/bws-secret-map.json` on 2026-10-25): the legacy names are the pre-`ACCOUNT_` spellings of pushed keys. `API_KEY` is `ACCOUNT_SERVER_API_KEY`, `JWT_SECRET` is `ACCOUNT_JWT_SECRET`, `{ED25519,X25519}_{PRIVATE,PUBLIC}_KEY` are the `ACCOUNT_`-prefixed names, `TURNSTILE_SECRET_KEY` is `CLOUDFLARE_TURNSTILE_SECRET_KEY`, and `OTLP_CLIENT_CREDENTIALS` is the region's `OBS_OTLP_CREDENTIALS_<SUFFIX>`. The archive holds the CURRENT store value of the successor key, which equals the Worker's legacy value only while the key was not rotated after the rename; the archive is a recovery copy of the lineage, not a byte-proof of what the Worker held.

The PUT is an unmeasured step for the ASSETS binding (only the DELETE was measured, 2026-10-15): check the Worker's static assets after the first archive run.

Run: `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile deploy-workers -- python3 -m rediacc_ci.ops.prune_worker_secrets --region eu --target stable`

Options: `--region eu|us|asia|all` (default all), `--target stable|edge|all` (default all), `--archive` (archive then delete; needs an explicit `--region`; prefer it to a bare `--delete`), `--dry-run` (with `--archive`: report which names have a bws value, write nothing), `--delete` (needs an explicit `--region`; prints each deleted name, keeps no copy), `--json` (one JSON object on stdout, for `check:ci-worker-secret-names`).

Exit codes: 0 no extras, 1 extras listed (or a delete failed), 2 no verdict (missing credential, API failure, unknown option).
"""

from __future__ import annotations

import dataclasses
import io
import json
import os
import re
import sys
import urllib.error
import urllib.parse
from typing import TYPE_CHECKING

from rediacc_ci import paths
from rediacc_ci.core import bws_env, https
from rediacc_ci.deploy import set_account_worker_secrets as pusher
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    import pathlib
    from collections.abc import Callable, Mapping

    # (method, path, token, optional JSON body) -> the envelope `result`.
    Fetch = Callable[..., object]
    # bws key names -> {key: value} for the keys the store holds non-empty.
    Values = Callable[[list[str]], dict[str, str]]

SELF = "rediacc_ci.ops.prune_worker_secrets"
REGIONS_REL = "regions.json"
# The binding type the secrets endpoint reports for a value set through `wrangler secret`. Other types on the list were not pushed by the bulk call and are never touched.
TEXT_BINDING = "secret_text"
ARCHIVE_PREFIX = "__ARCHIVE_"
# Legacy Worker secret name -> the bws key that holds its successor. `{SUFFIX}` is the region's `secretSuffix`.
LEGACY_BWS: dict[str, str] = {
    "API_KEY": "ACCOUNT_SERVER_API_KEY",
    "ED25519_PRIVATE_KEY": "ACCOUNT_ED25519_PRIVATE_KEY",
    "ED25519_PUBLIC_KEY": "ACCOUNT_ED25519_PUBLIC_KEY",
    "X25519_PRIVATE_KEY": "ACCOUNT_X25519_PRIVATE_KEY",
    "X25519_PUBLIC_KEY": "ACCOUNT_X25519_PUBLIC_KEY",
    "JWT_SECRET": "ACCOUNT_JWT_SECRET",
    "TURNSTILE_SECRET_KEY": "CLOUDFLARE_TURNSTILE_SECRET_KEY",
    "OTLP_CLIENT_CREDENTIALS": "OBS_OTLP_CREDENTIALS_{SUFFIX}",
}


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
    archive: bool = False
    dry_run: bool = False
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
        if item.get("type", TEXT_BINDING) == TEXT_BINDING
        and str(item.get("name")) not in keep
        and not str(item.get("name")).startswith(ARCHIVE_PREFIX)
    )


def _cf_errors(raw: bytes) -> str:
    try:
        errs = json.loads(raw).get("errors") or []
        return ": " + "; ".join("%s %s" % (e.get("code"), e.get("message")) for e in errs)
    except (ValueError, AttributeError):
        return ""


def http_fetch(method: str, path: str, token: str, body: Mapping[str, str] | None = None) -> object:
    """The `result` of a successful Cloudflare v4 envelope; ApiError otherwise. A `body` goes out as JSON and is never echoed."""
    label = re.sub(r"/accounts/[^/]+", "/accounts/{account_id}", path)
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "rediacc-ci-prune-worker-secrets",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = https.build_request(
        CF_API_BASE + path,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        headers=headers,
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
        envelope = json.loads(raw)
    except ValueError:
        raise ApiError("non-JSON body on %s %s" % (method, label)) from None
    if not isinstance(envelope, dict) or envelope.get("success") is not True:
        raise ApiError("success is not true on %s %s%s" % (method, label, _cf_errors(raw)))
    return envelope.get("result")


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


def delete_extras(
    rows: list[Row], account: str, token: str, fetch: Fetch
) -> tuple[list[str], list[str]]:
    """Delete every extra through the API. Returns (one line per deleted name, failure lines)."""
    deleted: list[str] = []
    failures: list[str] = []
    for row in rows:
        for name in row.extras:
            try:
                fetch("DELETE", secrets_path(account, row.worker, name), token)
            except ApiError as exc:
                failures.append("%s: %s" % (row.worker, exc))
                continue
            deleted.append("deleted %s: %s" % (row.worker, name))
    return deleted, failures


def region_suffixes(root: pathlib.Path | None = None) -> dict[str, str]:
    """Region id -> the `secretSuffix` that selects its fan-in keys in the store."""
    base = paths.repo_root() if root is None else root
    doc = json.loads(base.joinpath(REGIONS_REL).read_text(encoding="utf-8"))
    return {region["id"]: region["secretSuffix"] for region in doc["regions"]}


def bws_key(name: str, suffix: str) -> str | None:
    """The bws key behind a legacy Worker secret name, or None when no mapping exists."""
    template = LEGACY_BWS.get(name)
    return None if template is None else template.replace("{SUFFIX}", suffix)


def bws_values(keys: list[str]) -> dict[str, str]:
    """Non-empty store values for `keys`. bws_env's absent-name notice (names only) goes to a discarded stream."""
    resolved, _missing, _rc = bws_env.load(keys, stderr=io.StringIO())
    return resolved


def archive_extras(
    rows: list[Row],
    account: str,
    token: str,
    fetch: Fetch,
    values: Values,
    suffixes: Mapping[str, str],
    *,
    dry_run: bool,
) -> tuple[list[str], int]:
    """Archive each extra as `__ARCHIVE_<NAME>`, confirm it is listed, then delete the original. Returns (lines, count not removed)."""
    lines: list[str] = []
    left = 0
    wanted: dict[tuple[str, str], str | None] = {}
    for row in rows:
        for name in row.extras:
            wanted[(row.worker, name)] = bws_key(name, suffixes[row.region])
    have = values(sorted({k for k in wanted.values() if k}))
    for row in rows:
        for name in row.extras:
            key = wanted[(row.worker, name)]
            value = have.get(key) if key else None
            if not value:
                lines.append(
                    "no recoverable copy, left in place: %s: %s (bws key: %s)"
                    % (row.worker, name, key or "unmapped")
                )
                left += 1
                continue
            archive = ARCHIVE_PREFIX + name
            if dry_run:
                lines.append(
                    "would archive %s: %s as %s (bws key: %s)" % (row.worker, name, archive, key)
                )
                left += 1
                continue
            try:
                fetch(
                    "PUT",
                    secrets_path(account, row.worker),
                    token,
                    {"name": archive, "text": value, "type": TEXT_BINDING},
                )
                listed = fetch("GET", secrets_path(account, row.worker), token)
                if not isinstance(listed, list) or archive not in {
                    str(item.get("name")) for item in listed if isinstance(item, dict)
                }:
                    raise ApiError("%s is not listed after the PUT on %s" % (archive, row.worker))
                fetch("DELETE", secrets_path(account, row.worker, name), token)
            except ApiError as exc:
                lines.append("failed %s: %s: %s" % (row.worker, name, exc))
                left += 1
                continue
            lines.append("archived %s: %s as %s" % (row.worker, name, archive))
            lines.append("deleted %s: %s" % (row.worker, name))
    return lines, left


def parse(argv: list[str]) -> Options | None:
    opts = Options()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--delete":
            opts.delete = True
        elif arg == "--archive":
            opts.archive = True
        elif arg == "--dry-run":
            opts.dry_run = True
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
    values: Values | None = None,
) -> tuple[int, list[str], list[Row]]:
    """(exit code, lines, surveyed rows). Pure apart from `fetch` and `values`."""
    opts = parse(argv)
    if opts is None:
        return 2, ["%s: unexpected argument; see the module docstring" % SELF], []
    if (opts.delete or opts.archive) and opts.region == "all":
        # A delete names its region: one run never removes secrets from every account Worker at once.
        flag = "--archive" if opts.archive else "--delete"
        return 2, ["%s: %s needs --region eu|us|asia; nothing deleted" % (SELF, flag)], []
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
    if opts.archive:
        try:
            done, left = archive_extras(
                rows,
                account,
                token,
                fetch,
                bws_values if values is None else values,
                region_suffixes(root),
                dry_run=opts.dry_run,
            )
        except bws_env.RefusalError as exc:
            msg = "%s: the bws store could not be read; nothing archived" % SELF
            return 2, [*lines, msg, *exc.lines], rows
        tail = "dry run: nothing written" if opts.dry_run else "archive run finished"
        return (1 if left else 0), [*lines, *done, "%s; %d extra(s) remain" % (tail, left)], rows
    if opts.delete:
        deleted, failures = delete_extras(rows, account, token, fetch)
        lines += [*deleted, "deleted %d extra(s) through the API" % len(deleted), *failures]
        return (1 if failures else 0), lines, rows
    lines.append(
        "dry run: nothing deleted; re-run with --archive (keeps a recovery copy) or --delete to remove the extras"
    )
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
