"""The regional control databases (agent/plans/PLAN-enterprise-isolation.md, *Scope data*): create `control-<region>` and `control-bench-<region>` in D1 and apply private/account/control/migrations/0001_control.sql.

    PYTHONPATH=.ci python3 -m rediacc_ci.enterprise.control_db ensure [--bench] [--region <r>]

EVERY CALL GOES THROUGH WRANGLER, spelled by `core.wrangler.ARGV`, from a neutral temporary directory so no worker config is picked up. The runner is injected (`Runner(argv, *, cwd) -> Completed`), so the tests drive a fake over in-memory sqlite and never reach Cloudflare.

IDEMPOTENT. `ensure` lists the account's databases first and creates only a missing one, then applies the migration only when the `companies` table is absent, so a second run changes nothing. The migration's `CREATE TABLE` statements have no `IF NOT EXISTS`, which is why the table probe decides rather than a blind re-apply.

THE QUERY TRANSPORT. `transport(runner)` is the `registry.Query` the registry and `enterprise add` read and write through: `wrangler d1 execute <db> --remote --json --command <sql>`. wrangler binds no parameters, so `bind` inlines each `?` as a quoted literal (single quotes doubled), counting placeholders outside string literals only and refusing a count mismatch.

WRANGLER'S OUTPUT IS NEVER QUOTED IN AN ERROR, because it can name a company label or echo a token. An error names the database, the operation and the exit code.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from typing import NamedTuple

from rediacc_ci import paths
from rediacc_ci.core import wrangler
from rediacc_ci.enterprise import registry

SELF = "rediacc_ci.enterprise.control_db"
TABLE_PROBE = "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'companies'"


class Completed(NamedTuple):
    rc: int
    stdout: str
    stderr: str


Runner = Callable[..., Completed]


class ControlDbError(RuntimeError):
    """A control database step failed; the message names the database and never quotes wrangler."""


class Ensured(NamedTuple):
    database: str
    uuid: str
    created: bool
    migrated: bool


def run_wrangler(argv: list[str], *, cwd: pathlib.Path | str | None = None) -> Completed:
    """The production runner: both streams captured. `cwd=None` runs from a fresh empty directory."""
    if cwd is not None:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, check=False)
        return Completed(proc.returncode, proc.stdout, proc.stderr)
    with tempfile.TemporaryDirectory(prefix="control-db-") as tmp:
        proc = subprocess.run(argv, cwd=tmp, capture_output=True, text=True, check=False)
    return Completed(proc.returncode, proc.stdout, proc.stderr)


def _call(runner: Runner, argv: list[str]) -> Completed:
    with tempfile.TemporaryDirectory(prefix="control-db-") as tmp:
        try:
            return runner(argv, cwd=pathlib.Path(tmp))
        except OSError as exc:
            raise ControlDbError("wrangler could not run: %s" % (exc.strerror or exc)) from None


def location(region: str, root: pathlib.Path | None = None) -> str:
    """The D1 location hint of a region, from regions.json."""
    data = json.loads(((root or paths.repo_root()) / "regions.json").read_text(encoding="utf-8"))
    for entry in data["regions"]:
        if str(entry["id"]) == region:
            return str(entry["d1"]["location"])
    raise ControlDbError("no region %r in regions.json" % region)


def list_argv() -> list[str]:
    return [*wrangler.ARGV, "d1", "list", "--json"]


def create_argv(name: str, where: str) -> list[str]:
    return [*wrangler.ARGV, "d1", "create", name, "--location", where]


def execute_argv(name: str, *, sql: str | None = None, file: str | None = None) -> list[str]:
    tail = ["--command", sql] if sql is not None else ["--file", str(file)]
    return [*wrangler.ARGV, "d1", "execute", name, "--remote", "--json", "--yes", *tail]


def parse_json(text: str) -> object:
    """The JSON document in wrangler's stdout, skipping any banner lines before it."""
    starts = [i for i in (text.find("["), text.find("{")) if i >= 0]
    if not starts:
        raise ControlDbError("wrangler printed no JSON document")
    try:
        return json.loads(text[min(starts) :])
    except ValueError:
        raise ControlDbError("wrangler printed JSON that does not parse") from None


def _literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return "'%s'" % value.replace("'", "''")
    raise ControlDbError("cannot bind a %s value" % type(value).__name__)


def bind(sql: str, params: Sequence[object]) -> str:
    """`sql` with each `?` outside a string literal replaced by its parameter as a literal."""
    out: list[str] = []
    quoted = False
    holes = sum(1 for _ in _holes(sql))
    if holes != len(params):
        raise ControlDbError(
            "the statement has %d placeholder(s) and %d parameter(s)" % (holes, len(params))
        )
    values = iter(params)
    for ch in sql:
        if ch == "'":
            quoted = not quoted
        if ch == "?" and not quoted:
            out.append(_literal(next(values)))
        else:
            out.append(ch)
    return "".join(out)


def _holes(sql: str):
    quoted = False
    for ch in sql:
        if ch == "'":
            quoted = not quoted
        elif ch == "?" and not quoted:
            yield ch


def database_ids(runner: Runner) -> dict[str, str]:
    """Every D1 database of the account: name -> uuid."""
    done = _call(runner, list_argv())
    if done.rc != 0:
        raise ControlDbError("wrangler d1 list exited %d" % done.rc)
    rows = parse_json(done.stdout)
    if not isinstance(rows, list):
        raise ControlDbError("wrangler d1 list did not print a list")
    return {str(r["name"]): str(r["uuid"]) for r in rows if isinstance(r, dict) and "name" in r}


def ensure_database(name: str, region: str, *, runner: Runner) -> tuple[str, bool]:
    """`(uuid, created)` for the D1 database `name`, created in the region's location when missing."""
    known = database_ids(runner)
    if name in known:
        return known[name], False
    done = _call(runner, create_argv(name, location(region)))
    if done.rc != 0:
        raise ControlDbError("wrangler d1 create %s exited %d" % (name, done.rc))
    uuid = database_ids(runner).get(name)
    if not uuid:
        raise ControlDbError("%s was created but is not listed afterwards" % name)
    return uuid, True


def query(database: str, sql: str, params: Sequence[object], *, runner: Runner) -> list[dict]:
    """The rows of one statement on a remote D1 database. Raises ControlDbError (a RuntimeError, so the registry names the region)."""
    done = _call(runner, execute_argv(database, sql=bind(sql, list(params))))
    if done.rc != 0:
        raise ControlDbError("wrangler d1 execute on %s exited %d" % (database, done.rc))
    answer = parse_json(done.stdout)
    rows: list[dict] = []
    for part in answer if isinstance(answer, list) else [answer]:
        if isinstance(part, dict):
            rows.extend(r for r in part.get("results") or [] if isinstance(r, dict))
    return rows


def transport(runner: Runner = run_wrangler) -> registry.Query:
    """The registry's `Query` over wrangler."""

    def run(database: str, sql: str, params: list) -> list[dict]:
        return query(database, sql, params, runner=runner)

    return run


def migrated(database: str, *, runner: Runner) -> bool:
    return bool(query(database, TABLE_PROBE, [], runner=runner))


def apply_migration(database: str, *, runner: Runner, root: pathlib.Path | None = None) -> None:
    path = (root or paths.repo_root()) / registry.MIGRATION_REL
    done = _call(runner, execute_argv(database, file=str(path)))
    if done.rc != 0:
        raise ControlDbError("applying the control migration to %s exited %d" % (database, done.rc))


def ensure(region: str, *, bench: bool, runner: Runner = run_wrangler) -> Ensured:
    """Create the region's control database when missing, and migrate it when it has no schema."""
    database = registry.control_database(region, bench)
    uuid, created = ensure_database(database, region, runner=runner)
    applied = False
    if not migrated(database, runner=runner):
        apply_migration(database, runner=runner)
        applied = True
    return Ensured(database, uuid, created, applied)


def ensure_all(*, bench: bool, runner: Runner = run_wrangler) -> list[Ensured]:
    """`ensure` for every region of the environment, in registry order."""
    return [ensure(region, bench=bench, runner=runner) for region in registry.databases(bench)]


def main(argv: Sequence[str], *, runner: Runner = run_wrangler) -> int:
    ap = argparse.ArgumentParser(
        prog="./run.sh enterprise control", description="create and migrate the control databases"
    )
    ap.add_argument("action", choices=["ensure"])
    ap.add_argument("--bench", action="store_true", help="control-bench-<region> (eu, us)")
    ap.add_argument("--region", default=None, help="one region instead of every region")
    try:
        args = ap.parse_args(list(argv))
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    regions = list(registry.databases(args.bench))
    if args.region is not None and args.region not in regions:
        print(
            "%s: --region %s is not one of %s" % (SELF, args.region, ", ".join(regions)),
            file=sys.stderr,
        )
        return 2
    try:
        for region in [args.region] if args.region else regions:
            got = ensure(region, bench=args.bench, runner=runner)
            state = [("created" if got.created else "present")]
            state.append("migrated" if got.migrated else "schema present")
            print("%s: %s" % (got.database, ", ".join(state)))
    except ControlDbError as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
