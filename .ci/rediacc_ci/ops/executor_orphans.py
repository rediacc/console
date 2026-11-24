#!/usr/bin/env python3
"""Executor-created repositories, forks and machines of one account target, read from the audit trail (agent/plans/PLAN-rmcp-orphan-recovery.md, Design 1, 5 and the output contract, boxes OR1, OR2 and OR-OP1).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orphans list --target bench|stable [--region R] [--json]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.executor_orphans list --target onprem (--env .onprem/stack.env | --sqlite <path>) [--json]

THE READ. One SELECT over `event_log`: the `cli.repo.create`, `cli.repo.fork` and `cli.machine.provision` rows that carry `data.commandPath`. The executor (`rdc serve`) is the only emitter that sets `commandPath` (`packages/shared/src/audit/event-schema.ts`, `baseData`), while the audit route stores every event with source `cli` whoever relayed it, so `commandPath` is what separates an executor event from the CLI's own. Nothing is written. A target `bench` or `stable` goes through `wrangler d1 execute --remote --json`, `onprem` opens the on-premise account server's SQLite file read-only.

THE OUTPUT CONTRACT. `--json` prints one JSON object per event on stdout with exactly `org` (the first 8 characters of the org id), `machine`, `repo`, `guid`, `at` (the event timestamp), `function` (`repository_create`, `repository_fork` or `machine_provision`); without `--json` the same rows print as a table. A field the event data does not carry is JSON `null` (an empty cell in the table): the audit schema has no GUID field, so `guid` is null until an event carries one, and `rdc repo admin orphan list --executor-events` then joins on the repo name. Diagnostics go to stderr.

NO FULL ID IS PRINTED. Every org is named by its 8-character prefix.

THE ENVIRONMENT of `bench` and `stable` follows `rediacc_ci.ops.executor_orgs`: `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` come from CD's Bitwarden step, or a bare local run re-executes itself under `bws_env exec --profile executor-orphans` (`.ci/config/secret-supply.json`). `onprem` needs no credential.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import pathlib
import sqlite3
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.deploy import console_executor as target_mod
from rediacc_ci.ops import executor_orgs

SELF = "rediacc_ci.ops.executor_orphans"
PROFILE = "executor-orphans"
PREFIX_LEN = executor_orgs.PREFIX_LEN
ONPREM_TARGET = "onprem"
TARGETS = (*target_mod.TARGETS, ONPREM_TARGET)
# The env file key the on-premise stack writes for the account server's SQLite file (`rediacc_ci.testrun.onprem_stack`).
SQLITE_ENV_KEY = "ONPREM_ACCOUNT_SQLITE"

# The event type each audited function records under, and the function a row's type names.
FUNCTION_BY_TYPE = {
    "cli.repo.create": "repository_create",
    "cli.repo.fork": "repository_fork",
    "cli.machine.provision": "machine_provision",
}
FIELDS = ("org", "machine", "repo", "guid", "at", "function")

EVENTS_SQL = (
    "SELECT org_id AS org_id, type AS type, timestamp AS at, "
    "json_extract(data, '$.machineName') AS machine, "
    "json_extract(data, '$.repoName') AS repo, "
    "json_extract(data, '$.guid') AS guid "
    "FROM event_log WHERE source = 'cli' "
    "AND type IN ('cli.repo.create', 'cli.repo.fork', 'cli.machine.provision') "
    "AND json_extract(data, '$.commandPath') IS NOT NULL "
    "ORDER BY timestamp, id"
)


class RefusedError(target_mod.RefusedError):
    """A run that must stop with exit 1."""


def to_event(row: dict) -> dict[str, str | None]:
    """The contract object of one SELECT row."""
    kind = row.get("type")
    if kind not in FUNCTION_BY_TYPE:
        raise RefusedError("%s: a row has the unexpected type %r" % (SELF, kind))
    org = row.get("org_id")

    def text(key: str) -> str | None:
        value = row.get(key)
        return None if value is None or value == "" else str(value)

    return {
        "org": str(org)[:PREFIX_LEN] if org else None,
        "machine": text("machine"),
        "repo": text("repo"),
        "guid": text("guid"),
        "at": text("at"),
        "function": FUNCTION_BY_TYPE[kind],
    }


def read_sqlite(path: pathlib.Path) -> list[dict]:
    """The rows of `EVENTS_SQL` from an account server SQLite file, opened read-only."""
    if not path.is_file():
        raise RefusedError("--sqlite %s is not a file" % path)
    try:
        with contextlib.closing(sqlite3.connect("file:%s?mode=ro" % path, uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(EVENTS_SQL)]
    except sqlite3.Error as exc:
        raise RefusedError("%s cannot be read as an account database: %s" % (path, exc)) from None


def read_d1(worker_dir: pathlib.Path, config: str) -> list[dict]:
    """The rows of `EVENTS_SQL` from one target's D1."""
    database = executor_orgs.database_name(worker_dir / config)
    proc = subprocess.run(
        executor_orgs.d1_argv(database, config, EVENTS_SQL),
        cwd=worker_dir,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode != 0:
        raise RefusedError(
            "wrangler d1 execute on %s exited %d%s"
            % (database, proc.returncode, executor_orgs.d1_cause(proc.stdout))
        )
    rows = executor_orgs.parse_rows(proc.stdout)
    if rows is None:
        raise RefusedError(
            "UNVERIFIED: wrangler d1 execute on %s did not print result rows" % database
        )
    return rows


def env_file_value(env_file: pathlib.Path, key: str) -> str:
    """The value of `KEY=value` in a stack env file, refused when the file or the key is missing."""
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise RefusedError("--env %s cannot be read: %s" % (env_file, exc)) from None
    for line in text.splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == key:
            return value.strip().strip("'\"")
    raise RefusedError("--env %s does not name %s" % (env_file, key))


def render(events: list[dict], as_json: bool) -> str:
    """The stdout text: JSON lines, or a table with a header row."""
    if as_json:
        return "\n".join(
            json.dumps({k: e[k] for k in FIELDS}, separators=(",", ":")) for e in events
        )
    cells = [list(FIELDS)] + [[e[k] or "" for k in FIELDS] for e in events]
    widths = [max(len(row[i]) for row in cells) for i in range(len(FIELDS))]
    return "\n".join(
        "  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip() for row in cells
    )


def run(args: argparse.Namespace, argv: list[str] | None = None) -> int:
    root = paths.repo_root()
    try:
        rows: list[dict] | None
        if args.target == ONPREM_TARGET:
            rows = read_sqlite(onprem_sqlite(args))
            where = "onprem"
        else:
            if args.env or args.sqlite:
                raise RefusedError("--env and --sqlite belong to --target onprem")
            rows = read_targets(args, root, argv)
            if rows is None:
                return _reexec(args, argv)
            where = args.target
        events = [to_event(r) for r in rows]
        text = render(events, args.json)
    except target_mod.RefusedError as exc:
        log.error(str(exc))
        return 1
    if text:
        print(text)
    log.info("%d executor event(s) on %s" % (len(events), where))
    return 0


def onprem_sqlite(args: argparse.Namespace) -> pathlib.Path:
    if bool(args.env) == bool(args.sqlite):
        raise RefusedError("--target onprem needs exactly one of --env and --sqlite")
    if args.sqlite:
        return pathlib.Path(args.sqlite)
    return pathlib.Path(env_file_value(pathlib.Path(args.env), SQLITE_ENV_KEY))


def read_targets(
    args: argparse.Namespace, root: pathlib.Path, argv: list[str] | None
) -> list[dict] | None:
    """The rows of every selected region; None when the credentials are missing and this run must re-execute under the profile."""
    regions = [args.region] if args.region else None
    if regions is None:
        regions = target_mod.region_ids(root) if args.target == target_mod.STABLE_TARGET else [None]
    missing = target_mod.missing_env()
    if missing:
        if argv is not None and not target_mod.profile_bound(PROFILE):
            return None
        raise RefusedError(
            "%s must be set (CD's Bitwarden step, or bws_env exec --profile %s)"
            % (" and ".join(missing), PROFILE)
        )
    worker_dir = root.joinpath(*target_mod.ACCOUNT_SUBDIR)
    rows: list[dict] = []
    for region in regions:
        _, config = target_mod.resolve_target(root, args.target, region)
        rows.extend(read_d1(worker_dir, config))
    return rows


def _reexec(args: argparse.Namespace, argv: list[str] | None) -> int:
    del args
    return subprocess.run(
        target_mod.reexec_argv(PROFILE, argv or [], SELF), check=False, env=target_mod.package_env()
    ).returncode


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=SELF, description=(__doc__ or "").splitlines()[0])
    parser.add_argument("action", choices=("list",))
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument(
        "--region", default=None, help="eu, us or asia (stable: every region when omitted)"
    )
    parser.add_argument("--env", default=None, help="onprem: the stack env file")
    parser.add_argument("--sqlite", default=None, help="onprem: the account server's SQLite file")
    parser.add_argument("--json", action="store_true", help="one JSON object per event")
    return parser


def main(argv: list[str]) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    return run(args, argv=argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
