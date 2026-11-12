#!/usr/bin/env python3
"""One-off repair: organizations left on the owner's user id after a paid Stripe Checkout.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.repair_org_customer_ids --target bench|edge|stable [--region eu|us|asia] [--write [--confirm-stable]]

THE DEFECT. Before private/account commit 49fa2a3, `handleCheckoutCompleted` re-pointed `subscriptions.customer_id` and `users.customer_id` to the Stripe customer id (`cus_...`) but left `organizations.customer_id` at the owner's user id. The portal resolves the subscription through the org, so the buyer got a 404 on GET /portal/subscription. Orgs of purchases made before that fix deployed are still in that state; this tool re-points them.

SELECTION (`SELECT_SQL`), exact: an org whose `customer_id` is its owner's user id, whose owner's `users.customer_id` starts with `cus_`, and a subscription row carries that `cus_` id. An org deliberately pointed at any other customer id never matches.

DRY RUN BY DEFAULT: one line per org (org id, owner user id, old -> new customer id, subscription id and plan; no emails or names), then the count, exit 0. `--write` applies `UPDATE organizations SET customer_id = <new> WHERE id = <org> AND customer_id = <old>` per org (guarded on the old value, so a concurrent change is never overwritten), re-reads, prints the remaining count and exits 1 when any match remains. Before the first UPDATE of a `--write` on edge or stable it records the D1 time-travel bookmark (the restore handle) and prints it; a `--write` that matches no org writes nothing and records none. A stable `--write` also needs `--confirm-stable`, checked before any SQL runs.

TARGETS. bench is `account-bench`; edge and stable name the same per-region databases (`wrangler.<region>.toml`), so the two targets differ only in the guard. The run re-executes itself under `bws_env exec` (bench: `deploy-proxy-bench`, else `deploy-proxy`), the profiles `console_executor` and `executor_orgs` use for the same D1 calls; no secret is printed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Callable
from typing import TYPE_CHECKING

from rediacc_ci import log, paths
from rediacc_ci.deploy import console_executor as target_mod
from rediacc_ci.deploy import deploy_record
from rediacc_ci.ops import executor_orgs

if TYPE_CHECKING:
    import pathlib

SELF = "rediacc_ci.ops.repair_org_customer_ids"

TARGETS = ("bench", "edge", "stable")
BOOKMARKED = ("edge", "stable")

SELECT_SQL = (
    "SELECT o.id AS org_id, o.owner_user_id AS owner_id, o.customer_id AS old_customer_id, "
    "u.customer_id AS new_customer_id, s.id AS sub_id, s.plan_code AS plan_code "
    "FROM organizations o "
    "JOIN users u ON u.id = o.owner_user_id "
    "JOIN subscriptions s ON s.customer_id = u.customer_id "
    "WHERE substr(u.customer_id, 1, 4) = 'cus_' "
    "AND o.customer_id = o.owner_user_id "
    "AND o.customer_id <> u.customer_id "
    "ORDER BY o.id, s.id"
)
UPDATE_SQL = (
    "UPDATE organizations SET customer_id = '@NEW@' WHERE id = '@ORG@' AND customer_id = '@OLD@'"
)
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}\Z")

# One SQL statement in, its result rows out.
Runner = Callable[[str], list[dict]]
Bookmarker = Callable[[], str]


class RefusedError(Exception):
    """A run that must stop with exit 1."""


def matches(rows: list[dict]) -> list[dict]:
    """One entry per org (the first subscription by id), refusing a row of an unexpected shape."""
    seen: dict[str, dict] = {}
    for row in rows:
        fields = ("org_id", "owner_id", "old_customer_id", "new_customer_id", "sub_id")
        if not all(isinstance(row.get(k), str) and row[k] for k in fields):
            raise RefusedError("UNVERIFIED: a D1 row lacks one of %s" % ", ".join(fields))
        seen.setdefault(row["org_id"], row)
    return [seen[k] for k in sorted(seen)]


def update_sql(match: dict) -> str:
    values = {
        "@ORG@": match["org_id"],
        "@OLD@": match["old_customer_id"],
        "@NEW@": match["new_customer_id"],
    }
    for value in values.values():
        if not SAFE_ID.match(value):
            raise RefusedError("%s: an id is not safe to put in SQL" % SELF)
    sql = UPDATE_SQL
    for key, value in values.items():
        sql = sql.replace(key, value)
    return sql


def find(runner: Runner) -> list[dict]:
    return matches(runner(SELECT_SQL))


def wrangler_runner(worker_dir: pathlib.Path, config: str) -> Runner:
    """The real D1 runner: `wrangler d1 execute --remote --json`, one statement per call."""
    database = executor_orgs.database_name(worker_dir / config)

    def run_sql(sql: str) -> list[dict]:
        proc = subprocess.run(
            executor_orgs.d1_argv(database, config, sql),
            cwd=worker_dir,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.stderr:
            print(proc.stderr, end="", file=sys.stderr)
        if proc.returncode != 0:
            raise RefusedError("wrangler d1 execute on %s exited %d" % (database, proc.returncode))
        rows = executor_orgs.parse_rows(proc.stdout)
        if rows is None:
            raise RefusedError(
                "UNVERIFIED: wrangler d1 execute on %s did not report every statement a success"
                % database
            )
        return rows

    return run_sql


def wrangler_bookmarker(worker_dir: pathlib.Path, config: str) -> Bookmarker:
    database = executor_orgs.database_name(worker_dir / config)

    def bookmark() -> str:
        try:
            return deploy_record.d1_bookmark(worker_dir, database, config)
        except deploy_record.RecordError as exc:
            raise RefusedError(str(exc)) from None

    return bookmark


def report(found: list[dict]) -> None:
    for m in found:
        log.info(
            "org %s owner %s %s -> %s subscription %s plan %s"
            % (
                m["org_id"],
                m["owner_id"],
                m["old_customer_id"],
                m["new_customer_id"],
                m["sub_id"],
                m.get("plan_code") or "-",
            )
        )


def repair(args: argparse.Namespace, runner: Runner, bookmarker: Bookmarker) -> int:
    where = args.target if args.target == "bench" else "%s %s" % (args.target, args.region)
    found = find(runner)
    report(found)
    log.info("%d org(s) on the pre-fix customer id on %s" % (len(found), where))
    if not args.write:
        log.info("dry run: nothing written (--write applies it)")
        return 0
    if not found:
        return 0
    if args.target in BOOKMARKED:
        log.info("D1 time-travel bookmark before the write: %s" % bookmarker())
    for m in found:
        runner(update_sql(m))
    remaining = find(runner)
    log.info("%d org(s) still match after the write on %s" % (len(remaining), where))
    return 1 if remaining else 0


def run(
    args: argparse.Namespace,
    repo_root: pathlib.Path | None = None,
    argv: list[str] | None = None,
    runner: Runner | None = None,
    bookmarker: Bookmarker | None = None,
) -> int:
    root = repo_root or paths.repo_root()
    if args.write and args.target == "stable" and not args.confirm_stable:
        log.error("--write on stable needs --confirm-stable")
        return 1
    account_target = "bench" if args.target == "bench" else "stable"
    try:
        region, config = target_mod.resolve_target(root, account_target, args.region)
    except target_mod.RefusedError as exc:
        log.error(str(exc))
        return 1
    args.region = region
    worker_dir = root.joinpath(*target_mod.ACCOUNT_SUBDIR)
    if runner is None:
        missing = target_mod.missing_env()
        if missing:
            profile = target_mod.profile_for(account_target)
            if argv is not None and not target_mod.profile_bound(profile):
                return subprocess.run(
                    target_mod.reexec_argv(profile, argv, SELF),
                    check=False,
                    env=target_mod.package_env(),
                ).returncode
            log.error(
                "%s must be set (bws_env exec --profile %s)" % (" and ".join(missing), profile)
            )
            return 1
    try:
        return repair(
            args,
            runner or wrangler_runner(worker_dir, config),
            bookmarker or wrangler_bookmarker(worker_dir, config),
        )
    except (RefusedError, executor_orgs.RefusedError) as exc:
        log.error(str(exc))
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--region", default=None, help="eu, us or asia (bench has none)")
    parser.add_argument("--write", action="store_true", help="apply the repair (default: dry run)")
    parser.add_argument("--confirm-stable", action="store_true", help="required for stable --write")
    return parser


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return run(args, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
