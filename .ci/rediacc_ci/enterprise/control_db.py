"""The regional control databases (agent/plans/PLAN-enterprise-isolation.md, *Scope data*): create `control-<region>` and `control-bench-<region>` in D1 and apply private/account/control/migrations/0001_control.sql.

    PYTHONPATH=.ci python3 -m rediacc_ci.enterprise.control_db ensure [--bench] [--region <r>]

EVERY CALL GOES THROUGH WRANGLER, spelled by `core.wrangler.ARGV`, from a neutral temporary directory so no worker config is picked up; the production runner swaps that prefix for the pinned binary's absolute path (`core.wrangler.resolve`), because npx finds no install from that directory. The runner is injected (`Runner(argv, *, cwd) -> Completed`), so the tests drive a fake over in-memory sqlite and never reach Cloudflare.

IDEMPOTENT. `ensure` lists the account's databases first and creates only a missing one, then applies the migration only when the `companies` table is absent, so a second run changes nothing. The migration's `CREATE TABLE` statements have no `IF NOT EXISTS`, which is why the table probe decides rather than a blind re-apply.

THE QUERY TRANSPORT. `transport(runner)` is the `registry.Query` the registry and `enterprise add` read and write through: `wrangler d1 execute <db> --remote --json --command <sql>`. wrangler binds no parameters, so `bind` inlines each `?` as a quoted literal (single quotes doubled), counting placeholders outside string literals only and refusing a count mismatch.

A FAILED CALL CARRIES WRANGLER'S STATED CAUSE (`failure_tail`): the `error` of its `--json` stdout, then its last stderr lines (`stderr_tail`: ANSI stripped, blank lines dropped, the last three lines, each cut to 200 characters). Query rows are never quoted, because they hold company labels, and a failed query masks every string value it bound (`mask_values`), because D1 can echo the inlined SQL in an error.

THE TOKEN IS CHECKED UP FRONT. wrangler refuses the Global API Key non-interactively, so `require_token` refuses a missing CLOUDFLARE_API_TOKEN naming the `enterprise` profile of .ci/config/secret-supply.json, before the first call (`main`, `ensure` and `transport` when they run over the production runner, which covers `add`, `control` and the proof readers).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from typing import NamedTuple

from rediacc_ci import paths
from rediacc_ci.core import wrangler
from rediacc_ci.enterprise import registry
from rediacc_ci.ops import bench_preflight

SELF = "rediacc_ci.enterprise.control_db"
TABLE_PROBE = "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'companies'"


class Completed(NamedTuple):
    rc: int
    stdout: str
    stderr: str


Runner = Callable[..., Completed]


class ControlDbError(RuntimeError):
    """A control database step failed; the message names the database and quotes wrangler's stated cause (`failure_tail`), with the values a query bound masked."""


AUTH_ENV = "CLOUDFLARE_API_TOKEN"
PROFILE = "enterprise"
TAIL_LINES = 3
TAIL_WIDTH = 200
ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def stderr_tail(text: str) -> str:
    """The last meaningful lines of wrangler's stderr, ANSI stripped, joined by ` | `; empty when there are none."""
    lines = [ANSI.sub("", raw).strip() for raw in text.splitlines()]
    kept = [line[:TAIL_WIDTH] for line in lines if line]
    return " | ".join(kept[-TAIL_LINES:])


DEPRECATION = re.compile(r"^Using \"[A-Z_]+\" environment variable\. This is deprecated")


def stdout_error(text: str) -> str:
    """The error wrangler's `--json` mode prints on stdout (`{"error": {"text", "notes"}}`), joined by ` | `; empty when stdout holds none.

    A failed `d1 execute --json` writes its cause there, so a stderr holding only the CF_EMAIL deprecation notice hid it (2026-11-12, `proof signer --bench`)."""
    try:
        doc = parse_json(text)
    except ControlDbError:
        return ""
    err = doc.get("error") if isinstance(doc, dict) else None
    if not isinstance(err, dict):
        return ""
    parts = [str(err.get("text") or "")]
    parts += [str(n.get("text") or "") for n in err.get("notes") or [] if isinstance(n, dict)]
    return " | ".join(p[:TAIL_WIDTH] for p in parts if p)


def failure_tail(stdout: str, stderr: str) -> str:
    """wrangler's stated cause: the `--json` stdout error then the stderr tail without the CF_EMAIL deprecation line, joined by ` | `; empty when neither holds one."""
    kept = "\n".join(
        line for line in stderr.splitlines() if not DEPRECATION.match(ANSI.sub("", line).strip())
    )
    return " | ".join(t for t in (stdout_error(stdout), stderr_tail(kept)) if t)


def mask_values(text: str, params: Sequence[object]) -> str:
    """`text` with every string value in `params` replaced by `<value>`, as written raw or with its single quotes doubled."""
    for value in params:
        if isinstance(value, str) and value:
            for form in (value.replace("'", "''"), value):
                text = text.replace(form, "<value>")
    return text


def _failure(what: str, done: Completed, params: Sequence[object] = ()) -> ControlDbError:
    tail = mask_values(failure_tail(done.stdout, done.stderr), params)
    return ControlDbError("%s exited %d%s" % (what, done.rc, ": " + tail if tail else ""))


def require_token(environ: Mapping[str, str] | None = None) -> None:
    """Refuse up front, naming the profile, when CLOUDFLARE_API_TOKEN is absent: wrangler cannot authenticate non-interactively without it."""
    if not (os.environ if environ is None else environ).get(AUTH_ENV):
        raise ControlDbError(
            "%s is not set: wrangler needs it non-interactively; run under "
            "`PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile %s -- <command>`"
            % (AUTH_ENV, PROFILE)
        )


class Ensured(NamedTuple):
    database: str
    uuid: str
    created: bool
    migrated: bool


def wrangler_env(
    environ: Mapping[str, str] | None = None, root: pathlib.Path | None = None
) -> dict[str, str]:
    """`environ` (default: this process's) with the repo's local wrangler `.bin` directories (`workers/signer`, then `workers/account`) at the front of PATH, so `npx --no-install wrangler` finds the pinned binary from any working directory, a neutral temporary one included."""
    env = dict(os.environ if environ is None else environ)
    base = root or paths.repo_root()
    found = [wrangler.local_binary(base / "workers" / name) for name in ("signer", "account")]
    bins = [str(b.parent) for b in found if b is not None]
    if bins:
        env["PATH"] = os.pathsep.join([*bins, *([env["PATH"]] if env.get("PATH") else [])])
    return env


def run_wrangler(
    argv: list[str], *, cwd: pathlib.Path | str | None = None, root: pathlib.Path | None = None
) -> Completed:
    """The production runner: both streams captured, wrangler resolved through `wrangler_env` and run by its absolute path (`wrangler.resolve`), since npx ignores PATH and finds nothing from a neutral directory. `cwd=None` runs from a fresh empty directory."""
    env = wrangler_env(root=root)
    if cwd is not None:
        proc = subprocess.run(
            wrangler.resolve(argv, pathlib.Path(cwd), env),
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return Completed(proc.returncode, proc.stdout, proc.stderr)
    with tempfile.TemporaryDirectory(prefix="control-db-") as tmp:
        proc = subprocess.run(
            wrangler.resolve(argv, pathlib.Path(tmp), env),
            cwd=tmp,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
    return Completed(proc.returncode, proc.stdout, proc.stderr)


def _call(runner: Runner, argv: list[str]) -> Completed:
    with tempfile.TemporaryDirectory(prefix="control-db-") as tmp:
        try:
            return runner(argv, cwd=pathlib.Path(tmp))
        except OSError as exc:
            raise ControlDbError("wrangler could not run: %s" % (exc.strerror or exc)) from None
        except wrangler.WranglerNotInstalledError as exc:
            raise ControlDbError(str(exc)) from None


def location(region: str, root: pathlib.Path | None = None) -> str:
    """The D1 location hint of a region, from regions.json."""
    data = json.loads(((root or paths.repo_root()) / "regions.json").read_text(encoding="utf-8"))
    for entry in data["regions"]:
        if str(entry["id"]) == region:
            return str(entry["d1"]["location"])
    raise ControlDbError("no region %r in regions.json" % region)


def jurisdiction(region: str, *, bench: bool = False, root: pathlib.Path | None = None) -> str:
    """The D1 jurisdiction a new database of REGION is created under ("" for a location hint only).

    A shared region takes its regions.json `d1.jurisdiction`; bench has no row and takes the jurisdiction wrangler.bench.toml declares for its buckets, so the whole bench is one jurisdiction (PLAN-d1-eu-jurisdiction Design 1).
    """
    if bench:
        return bench_preflight.bench_names(
            (root or paths.repo_root()).joinpath(*bench_preflight.BENCH_CONFIG_REL)
        ).config_jurisdiction
    data = json.loads(((root or paths.repo_root()) / "regions.json").read_text(encoding="utf-8"))
    for entry in data["regions"]:
        if str(entry["id"]) == region:
            return str(entry["d1"].get("jurisdiction") or "")
    raise ControlDbError("no region %r in regions.json" % region)


def list_argv() -> list[str]:
    return [*wrangler.ARGV, "d1", "list", "--json"]


def create_argv(name: str, where: str, jurisdiction: str = "") -> list[str]:
    """`wrangler d1 create`: `--jurisdiction <j>` when the region has one (the location hint is ignored then), else `--location <where>`."""
    if jurisdiction:
        return [*wrangler.ARGV, "d1", "create", name, "--jurisdiction", jurisdiction]
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
        raise _failure("wrangler d1 list", done)
    rows = parse_json(done.stdout)
    if not isinstance(rows, list):
        raise ControlDbError("wrangler d1 list did not print a list")
    return {str(r["name"]): str(r["uuid"]) for r in rows if isinstance(r, dict) and "name" in r}


def ensure_database(
    name: str, region: str, *, runner: Runner, bench: bool = False
) -> tuple[str, bool]:
    """`(uuid, created)` for the D1 database `name`, created in the region's jurisdiction (else its location) when missing."""
    known = database_ids(runner)
    if name in known:
        return known[name], False
    done = _call(runner, create_argv(name, location(region), jurisdiction(region, bench=bench)))
    if done.rc != 0:
        raise _failure("wrangler d1 create %s" % name, done)
    uuid = database_ids(runner).get(name)
    if not uuid:
        raise ControlDbError("%s was created but is not listed afterwards" % name)
    return uuid, True


def query(database: str, sql: str, params: Sequence[object], *, runner: Runner) -> list[dict]:
    """The rows of one statement on a remote D1 database. Raises ControlDbError (a RuntimeError, so the registry names the region)."""
    done = _call(runner, execute_argv(database, sql=bind(sql, list(params))))
    if done.rc != 0:
        raise _failure("wrangler d1 execute on %s" % database, done, params)
    answer = parse_json(done.stdout)
    rows: list[dict] = []
    for part in answer if isinstance(answer, list) else [answer]:
        if isinstance(part, dict):
            rows.extend(r for r in part.get("results") or [] if isinstance(r, dict))
    return rows


def transport(runner: Runner = run_wrangler) -> registry.Query:
    """The registry's `Query` over wrangler. Over the production runner it refuses a missing token before returning."""
    if runner is run_wrangler:
        require_token()

    def run(database: str, sql: str, params: list) -> list[dict]:
        return query(database, sql, params, runner=runner)

    return run


def migrated(database: str, *, runner: Runner) -> bool:
    return bool(query(database, TABLE_PROBE, [], runner=runner))


def apply_migration(database: str, *, runner: Runner, root: pathlib.Path | None = None) -> None:
    path = (root or paths.repo_root()) / registry.MIGRATION_REL
    done = _call(runner, execute_argv(database, file=str(path)))
    if done.rc != 0:
        raise _failure("applying the control migration to %s" % database, done)


def ensure(region: str, *, bench: bool, runner: Runner = run_wrangler) -> Ensured:
    """Create the region's control database when missing, and migrate it when it has no schema."""
    if runner is run_wrangler:
        require_token()
    database = registry.control_database(region, bench)
    uuid, created = ensure_database(database, region, runner=runner, bench=bench)
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
    if runner is run_wrangler:
        try:
            require_token()
        except ControlDbError as exc:
            print("%s: %s" % (SELF, exc), file=sys.stderr)
            return 1
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
