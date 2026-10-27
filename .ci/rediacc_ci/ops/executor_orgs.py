#!/usr/bin/env python3
"""Console executor orgs of one account target: list, verify, block, unblock (agent/plans/PLAN-console-executor-multi-org.md, Design items 2 and 4, box T1).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orgs list    --target edge|stable|bench [--region eu|us|asia]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orgs verify  --target T [--region R] --org A --org B
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orgs block   --target T [--region R] --org A
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orgs unblock --target T [--region R] --org A

THE READ. `list` and `verify` read the target's D1 through `wrangler d1 execute --remote --json`, one SELECT over organizations, subscriptions and config_stores. The entitlement rule is the one `ConsoleEntitlementService.check` applies (Design item 4): the org is not blocked, its primary subscription is live (status active, grace or inactive, and not past `expires_at`; ranked by status, then type, then newest), the primary subscription's plan has `webConsole`, and the org's config store holds a server-recoverable passphrase. Only the presence of that passphrase is selected, never its value.

NO FULL ID IS PRINTED. Every line names an org by the first 8 characters of its id. `--org` takes a full id or a prefix of at least 8 characters that names exactly one org.

THE WRITE. `block` and `unblock` do the writes of `POST /admin/orgs/<id>/console-executor/block` and `/unblock` through `wrangler d1 execute --remote`, the way the reads go, and then re-read the org to confirm its verdict changed. That route needs a root elevated session, which is minutes long and cannot be a stored secret, and the account Worker accepts no other credential for root routes, so this tool holds none. The SQL (`BLOCK_SQL`, `UNBLOCK_SQL`) is the route's `ConsoleEntitlementService.block` and `unblock` written out, and `root-console-block.test.ts` runs it against the same schema beside the route and compares: change one, change the other. An org's audit row is `console_executor.blocked` or `console_executor.unblocked`, source `ops-executor-orgs`, written in the same statement batch.

THE TARGET AND THE ENVIRONMENT follow `rediacc_ci.deploy.console_executor`: `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` come from CD's Bitwarden step, or a bare local run re-executes itself under `bws_env exec --profile deploy-proxy` (bench: `deploy-proxy-bench`).
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import re
import subprocess
import sys
import tomllib
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.core import wrangler
from rediacc_ci.deploy import console_executor as target_mod

if TYPE_CHECKING:
    import pathlib

SELF = "rediacc_ci.ops.executor_orgs"

ACTIONS = ("list", "verify", "block", "unblock")
PREFIX_LEN = 8
ORG_ID = re.compile(r"^[A-Za-z0-9_-]{%d,64}\Z" % PREFIX_LEN)

# Mirrors the executor issuer's ranking (LIVE_STATUS_RANK and TYPE_RANK in the account service) and PLAN_METADATA[plan].webConsole in packages/shared.
LIVE_STATUS_RANK = {"active": 0, "grace": 1, "inactive": 2}
TYPE_RANK = {"subscription": 0, "perpetual": 1, "trial": 2}
WEB_CONSOLE_PLANS = frozenset({"PROFESSIONAL", "BUSINESS", "ENTERPRISE"})

ORGS_SQL = (
    "SELECT o.id AS id, o.console_executor_blocked_at AS blocked_at, "
    "s.id AS sub_id, s.plan_code AS plan_code, s.status AS status, s.type AS type, "
    "s.expires_at AS expires_at, s.created_at AS sub_created_at, "
    "(SELECT COUNT(*) FROM config_stores c WHERE c.org_id = o.id "
    "AND c.server_recoverable_org_passphrase IS NOT NULL) AS store_count "
    "FROM organizations o LEFT JOIN subscriptions s ON s.customer_id = o.customer_id "
    "ORDER BY o.id"
)


# The writes of ConsoleEntitlementService.block and .unblock (private/account/src/services/console-entitlement.service.ts), with @ORG@ and @NOW@ filled in by `statements`. An issuer key is `executor:<ENV>:<REGION>:<orgId>`, so the org is its suffix. The audit row selects from organizations, so an unknown org writes nothing.
BLOCK_SQL = (
    (
        "UPDATE organizations SET console_executor_blocked_at = "
        "COALESCE(console_executor_blocked_at, '@NOW@') WHERE id = '@ORG@';"
    ),
    (
        "UPDATE api_tokens SET revoked_at = '@NOW@' WHERE revoked_at IS NULL "
        "AND issuer_key LIKE 'executor:%' "
        "AND substr(issuer_key, -(length('@ORG@') + 1)) = ':@ORG@';"
    ),
    (
        "DELETE FROM config_executor_grants WHERE config_store_id IN "
        "(SELECT id FROM config_stores WHERE org_id = '@ORG@');"
    ),
    (
        "INSERT INTO event_log (id, type, source, actor_role, org_id, customer_id, data, timestamp) "
        "SELECT lower(hex(randomblob(16))), 'console_executor.blocked', 'ops-executor-orgs', 'root', "
        "o.id, o.customer_id, '{\"via\":\"wrangler-d1\"}', '@NOW@' "
        "FROM organizations o WHERE o.id = '@ORG@';"
    ),
)
UNBLOCK_SQL = (
    "UPDATE organizations SET console_executor_blocked_at = NULL WHERE id = '@ORG@';",
    (
        "INSERT INTO event_log (id, type, source, actor_role, org_id, customer_id, data, timestamp) "
        "SELECT lower(hex(randomblob(16))), 'console_executor.unblocked', 'ops-executor-orgs', 'root', "
        "o.id, o.customer_id, '{\"via\":\"wrangler-d1\"}', '@NOW@' "
        "FROM organizations o WHERE o.id = '@ORG@';"
    ),
)
SQL_ORG_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}\Z")


class RefusedError(target_mod.RefusedError):
    """A run that must stop with exit 1."""


@dataclasses.dataclass(frozen=True)
class Verdict:
    org_id: str
    entitled: bool
    reason: str
    plan: str


def prefix(org_id: str) -> str:
    return org_id[:PREFIX_LEN]


def d1_argv(database: str, config: str, command: str = ORGS_SQL) -> list[str]:
    return [
        *wrangler.ARGV,
        "d1",
        "execute",
        database,
        "--remote",
        "--json",
        "--command",
        command,
        "--config",
        config,
    ]


def parse_rows(text: str) -> list[dict] | None:
    """The result rows of `wrangler d1 execute --json`; None when the text is not that shape. A banner ahead of the JSON array is skipped."""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(data, list) or not data:
        return None
    rows: list[dict] = []
    for statement in data:
        if not isinstance(statement, dict) or statement.get("success") is not True:
            return None
        found = statement.get("results")
        if not isinstance(found, list) or not all(isinstance(r, dict) for r in found):
            return None
        rows.extend(found)
    return rows


def evaluate(org_id: str, subs: list[dict], blocked: bool, has_store: bool, now: str) -> Verdict:
    """The entitlement verdict for one org; any doubt refuses."""
    live = [
        s
        for s in subs
        if s.get("status") in LIVE_STATUS_RANK
        and (not s.get("expires_at") or str(s["expires_at"]) > now)
    ]
    # Stable passes, least significant first: id ascending, then newest created_at first (an empty value is the oldest), then status and type rank.
    live.sort(key=lambda s: str(s.get("sub_id") or ""))
    live.sort(key=lambda s: str(s.get("sub_created_at") or ""), reverse=True)
    live.sort(
        key=lambda s: (
            LIVE_STATUS_RANK.get(s["status"], 99),
            TYPE_RANK.get(str(s.get("type")), 99),
        )
    )
    plan = str(live[0].get("plan_code") or "") if live else ""
    if blocked:
        return Verdict(org_id, False, "blocked", plan)
    if not live:
        return Verdict(org_id, False, "subscription", plan)
    if plan not in WEB_CONSOLE_PLANS:
        return Verdict(org_id, False, "plan", plan)
    if not has_store:
        return Verdict(org_id, False, "store", plan)
    return Verdict(org_id, True, "entitled", plan)


def verdicts(rows: list[dict], now: str) -> list[Verdict]:
    """One verdict per org id, in id order."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        org_id = row.get("id")
        if not isinstance(org_id, str) or not org_id:
            raise RefusedError("%s: a D1 row has no org id" % SELF)
        grouped.setdefault(org_id, []).append(row)
    out = []
    for org_id in sorted(grouped):
        group = grouped[org_id]
        subs = [r for r in group if r.get("sub_id")]
        blocked = any(r.get("blocked_at") for r in group)
        has_store = any(int(r.get("store_count") or 0) > 0 for r in group)
        out.append(evaluate(org_id, subs, blocked, has_store, now))
    return out


def resolve_org(known: list[Verdict], wanted: str) -> Verdict:
    """The one org a full id or a prefix names, refused when it names none or several."""
    if not ORG_ID.match(wanted):
        raise RefusedError(
            "--org needs a full org id or a prefix of at least %d characters" % PREFIX_LEN
        )
    hits = [v for v in known if v.org_id == wanted] or [
        v for v in known if v.org_id.startswith(wanted)
    ]
    if not hits:
        raise RefusedError("--org %s names no org on this target" % prefix(wanted))
    if len(hits) > 1:
        raise RefusedError(
            "--org %s names %d orgs, give more characters" % (prefix(wanted), len(hits))
        )
    return hits[0]


def database_name(config_path: pathlib.Path) -> str:
    try:
        doc = tomllib.loads(config_path.read_text(encoding="utf-8"))
        name = doc["d1_databases"][0]["database_name"]
    except (OSError, tomllib.TOMLDecodeError, KeyError, IndexError, TypeError) as exc:
        raise RefusedError(
            "%s has no readable d1_databases entry: %s" % (config_path, exc)
        ) from None
    if not isinstance(name, str) or not name:
        raise RefusedError("%s has an empty database_name" % config_path)
    return name


def _wrangler(
    worker_dir: pathlib.Path, argv: list[str], org_id: str = ""
) -> subprocess.CompletedProcess[str]:
    """Runs wrangler with stderr captured and re-printed with the org id cut to its prefix, so an echoed --command cannot put a full id on the terminal."""
    proc = subprocess.run(
        argv,
        cwd=worker_dir,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stderr:
        shown = proc.stderr.replace(org_id, prefix(org_id)) if org_id else proc.stderr
        print(shown, end="", file=sys.stderr)
    return proc


def read_orgs(worker_dir: pathlib.Path, config: str, now: str) -> list[Verdict]:
    """Every org of the target with its verdict, read from D1."""
    database = database_name(worker_dir / config)
    proc = _wrangler(worker_dir, d1_argv(database, config))
    if proc.returncode != 0:
        raise RefusedError("wrangler d1 execute on %s exited %d" % (database, proc.returncode))
    rows = parse_rows(proc.stdout)
    if rows is None:
        raise RefusedError(
            "UNVERIFIED: wrangler d1 execute on %s did not print result rows" % database
        )
    return verdicts(rows, now)


def statements(action: str, org_id: str, now: str) -> str:
    """The SQL of `block` or `unblock` for one org, as one batch."""
    if not SQL_ORG_ID.match(org_id):
        raise RefusedError("%s: org id %s is not safe to put in SQL" % (SELF, prefix(org_id)))
    template = BLOCK_SQL if action == "block" else UNBLOCK_SQL
    return " ".join(sql.replace("@ORG@", org_id).replace("@NOW@", now) for sql in template)


def write_org(worker_dir: pathlib.Path, config: str, command: str, org_id: str = "") -> None:
    """Runs one write batch through wrangler; anything but a success on every statement refuses."""
    database = database_name(worker_dir / config)
    proc = _wrangler(worker_dir, d1_argv(database, config, command), org_id)
    if proc.returncode != 0:
        raise RefusedError("wrangler d1 execute on %s exited %d" % (database, proc.returncode))
    if parse_rows(proc.stdout) is None:
        raise RefusedError(
            "UNVERIFIED: wrangler d1 execute on %s did not report every statement a success"
            % database
        )


def reexec_argv(profile: str, argv: list[str]) -> list[str]:
    return [
        sys.executable,
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        profile,
        "--",
        sys.executable,
        "-m",
        SELF,
        *argv,
    ]


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def run(
    args: argparse.Namespace,
    repo_root: pathlib.Path | None = None,
    argv: list[str] | None = None,
    now: str | None = None,
) -> int:
    root = repo_root or paths.repo_root()
    try:
        region, config = target_mod.resolve_target(root, args.target, args.region)
    except target_mod.RefusedError as exc:
        log.error(str(exc))
        return 1
    missing = target_mod.missing_env()
    if missing:
        profile = target_mod.profile_for(args.target)
        if argv is not None and not target_mod.profile_bound(profile):
            return subprocess.run(
                reexec_argv(profile, argv), check=False, env=target_mod.package_env()
            ).returncode
        log.error(
            "%s must be set (CD's Bitwarden step, or bws_env exec --profile %s)"
            % (" and ".join(missing), profile)
        )
        return 1
    worker_dir = root.joinpath(*target_mod.ACCOUNT_SUBDIR)
    try:
        stamp = now or _now()
        known = read_orgs(worker_dir, config, stamp)
        return _act(args, known, worker_dir, config, region, stamp)
    except target_mod.RefusedError as exc:
        log.error(str(exc))
        return 1


def _act(
    args: argparse.Namespace,
    known: list[Verdict],
    worker_dir: pathlib.Path,
    config: str,
    region: str,
    now: str,
) -> int:
    where = "%s %s" % (args.target, region)
    if args.action == "list":
        entitled = [v for v in known if v.entitled]
        for v in entitled:
            log.info("%s  %s" % (prefix(v.org_id), v.plan))
        log.info("%d of %d orgs entitled on %s" % (len(entitled), len(known), where))
        return 0
    wanted = args.org or []
    if args.action == "verify":
        if len(wanted) < 2:
            raise RefusedError("verify needs at least two --org values")
        chosen = [resolve_org(known, w) for w in wanted]
        if len({v.org_id for v in chosen}) != len(chosen):
            raise RefusedError("verify needs distinct orgs")
        for v in chosen:
            log.info(
                "%s  %s"
                % (prefix(v.org_id), "entitled" if v.entitled else "NOT entitled: " + v.reason)
            )
        return 0 if all(v.entitled for v in chosen) else 1
    if len(wanted) != 1:
        raise RefusedError("%s needs exactly one --org" % args.action)
    org = resolve_org(known, wanted[0])
    write_org(worker_dir, config, statements(args.action, org.org_id, now), org.org_id)
    after = next((v for v in read_orgs(worker_dir, config, now) if v.org_id == org.org_id), None)
    if after is None or (after.reason == "blocked") != (args.action == "block"):
        raise RefusedError(
            "UNVERIFIED: %s on %s ran but a re-read does not show the org %sed"
            % (args.action, prefix(org.org_id), args.action)
        )
    log.info("%s %sed on %s" % (prefix(org.org_id), args.action, where))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    parser.add_argument("action", choices=ACTIONS)
    parser.add_argument("--target", required=True, help="edge, stable or bench")
    parser.add_argument("--region", default=None, help="eu, us or asia (bench: eu only)")
    parser.add_argument(
        "--org", action="append", default=None, help="org id or 8+ character prefix"
    )
    return parser


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return run(args, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
