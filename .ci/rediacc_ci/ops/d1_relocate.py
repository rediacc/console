"""Move a D1 database into a Cloudflare jurisdiction without losing a row (agent/plans/PLAN-d1-eu-jurisdiction.md, Design 3).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate plan     --from A --to B [--jurisdiction eu] [--config TOML]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate create   --from A --to B --jurisdiction eu [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate fence    --db A (--on [--reason R] | --off) [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate bookmark --from A [--config TOML] [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate copy     --from A --to B [--config TOML] [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate verify   --from A --to B [--config TOML]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate record   --from A [--event cutover] [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate reverse  --from A --to B [--config TOML] [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_relocate retire   --from A --to B --yes-delete A [--write]

WHY. D1 jurisdiction is chosen when a database is created and there is no rename, so moving `account-eu` into jurisdiction eu means a new database (`account-eu-j`), a lossless copy under a write freeze, and a repoint. This is the one path for every step of that move; bench rehearses it first.

WITHOUT `--write` EVERY SUBCOMMAND PRINTS WHAT IT WOULD DO AND CHANGES NOTHING. Reads (the API lookups, row counts, a time-travel bookmark) still run, because the printout is built from them.

THE STEPS.
  plan      read-only: size, table count, region and jurisdiction of both databases (the D1 API), the fence table state (`fence table: present, empty`), live backup leases.
  create    `wrangler d1 create <to> --jurisdiction <j>`; the API must then report that jurisdiction, else exit 1. A target that already exists in the right jurisdiction is accepted as it is.
  fence     `--on` writes the one `_write_fence` row (Design 2: the account Worker refuses every write while it is present), waits 2 x the fence cache TTL + 30 s for every isolate to see it, then lists live leases; `--off` deletes the row.
  bookmark  `deploy_record.d1_bookmark` (the Time Travel restore point) into the run record.
  copy      refuses an unfenced source, a source fenced less than the drain window ago, and a target that already holds tables; then the `clone_d1` export, the `_cf_*` statements and the fence row stripped from it, the `clone_d1` deferred-FK import, then `verify`.
  verify    per table the row count and a canonical sha256 (`d1_shard_move.digest`) over rows read in primary-key order, `d1_migrations` equal, `PRAGMA foreign_key_check` on the target (a call that fails exits 1, never "0 violations"), no fence row on the target, and no migration file pending on it.
  record    prints `.ci/state/d1-relocate/<from>.json`; `--event cutover --write` stamps the cutover the 30-day retention counts from.
  reverse   the rollback after writes resumed on the new database (Design 6): the new one must be fenced, its rows are copied back over the old one, and the old one's fence row is kept until the repoint back is deployed.
  retire    deletes the old database, only when the cutover is at least 30 days old, no wrangler toml, regions.json `d1.name` or `deploy_www.PROTECTED_DATABASES` names it, a `backup_d1` export of it taken after its fence is under `.backups/`, and `--yes-delete` repeats its name exactly.

EXIT CODES. 0 done (or a dry run); 1 usage, or a call that failed (API, wrangler, a query); 2 refused by a pre-check, nothing changed; 3 verification found a difference.

DATABASES are D1 names, reached through wrangler (export, import, create, delete, time travel) and the D1 REST query API (reads, the fence row), with CLOUDFLARE_API_TOKEN or the Global API Key pair and CLOUDFLARE_ACCOUNT_ID as the other ops modules read them; the bws profile is `deploy-workers` (production) or `deploy-bench` (bench). `--sqlite NAME=PATH` maps a name to a local SQLite file instead, which is how the tests drive every step offline. No secret reaches argv or output.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from rediacc_ci.core import wrangler
from rediacc_ci.deploy import clone_d1, deploy_record, deploy_www
from rediacc_ci.ops import d1_shard_move as dsm
from rediacc_ci.ops import observability_volume as ov
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

SELF = "d1_relocate"
ROOT = Path(__file__).resolve().parents[3]

EXIT_FAILED = 1
EXIT_REFUSED = 2
EXIT_VERIFY = 3

JURISDICTIONS = ("eu", "fedramp")
FENCE_TABLE = "_write_fence"
# The account Worker caches the fence row per isolate for this long (Design 2); after `fence --on` every isolate has seen it once 2 x TTL + 30 s have passed.
FENCE_TTL_S = 10
DRAIN_S = 2 * FENCE_TTL_S + 30
RETENTION = timedelta(days=30)
PAGE = dsm.PAGE
STATE_REL = (".ci", "state", "d1-relocate")
BACKUPS_REL = ".backups"
# `backup_d1` names an export `<db>-<UTC stamp>.sql` with this stamp.
BACKUP_STAMP = "%Y-%m-%dT%H-%M-%S"
BACKUP_STAMP_RE = r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}"

USER_TABLES_SQL = (
    "SELECT name FROM sqlite_master WHERE type = 'table' "
    "AND name NOT LIKE 'sqlite\\_%' ESCAPE '\\' AND name NOT LIKE '\\_cf\\_%' ESCAPE '\\' "
    "ORDER BY name"
)
# A statement of the export that the copy drops: Cloudflare's internal `_cf_*` tables (D1 refuses writes to them) and the fence row, which must never reach the target.
STRIPPED_STATEMENT = re.compile(
    r"^(?:(?:CREATE TABLE|INSERT INTO)\s+(?:IF NOT EXISTS\s+)?[`\"\[]?_cf_"
    r"|INSERT INTO\s+[`\"\[]?%s\b)" % FENCE_TABLE
)


class RelocateError(Exception):
    """A call or a read the step cannot go on without; the message is what the operator sees."""


class RefusedError(Exception):
    """A pre-check refused the step before anything changed."""


# --- databases ------------------------------------------------------------------------------------


class Db(Protocol):
    name: str

    def query(self, sql: str) -> list[dict]: ...

    def batch(self, statements: list[str]) -> None: ...

    def export_into(self, tmpdir: str) -> None: ...

    def import_file(self, path: str) -> None: ...


class SqliteDb:
    """A local SQLite file standing in for a D1 database: the same reads, an `iterdump` export, an `executescript` import."""

    def __init__(self, name: str, path: str | Path) -> None:
        self.name = name
        self.executor = dsm.SqliteExecutor(path)

    def query(self, sql: str) -> list[dict]:
        return self.executor.query(sql)

    def batch(self, statements: list[str]) -> None:
        self.executor.batch(statements)

    def export_into(self, tmpdir: str) -> None:
        with open(os.path.join(tmpdir, "export.sql"), "w", encoding="utf-8") as out:
            out.writelines("%s\n" % line for line in self.executor.conn.iterdump())

    def import_file(self, path: str) -> None:
        with open(path, encoding="utf-8") as handle:
            self.executor.conn.executescript(handle.read())


class D1Db:
    """A D1 database: reads and the fence row over the REST query API, export and import through `clone_d1`'s wrangler path."""

    def __init__(self, name: str, executor: dsm.D1Executor) -> None:
        self.name = name
        self.executor = executor

    def query(self, sql: str) -> list[dict]:
        try:
            return self.executor.query(sql)
        except dsm.MoveError as exc:
            raise RelocateError(str(exc)) from exc

    def batch(self, statements: list[str]) -> None:
        try:
            self.executor.batch(statements)
        except dsm.MoveError as exc:
            raise RelocateError(str(exc)) from exc

    def export_into(self, tmpdir: str) -> None:
        try:
            clone_d1.export_redacted(self.name, tmpdir)
        except clone_d1.BashExitError as exc:
            raise RelocateError("export of %s failed (exit %d)" % (self.name, exc.code)) from exc

    def import_file(self, path: str) -> None:
        status = run_wrangler(clone_d1.execute_file_argv(self.name, [], path))
        if status:
            raise RelocateError("import into %s failed (wrangler exit %d)" % (self.name, status))


def run_wrangler(argv: list[str]) -> int:
    """One wrangler command from the worker directory (where the pinned install is), both streams inherited."""
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.run(argv, cwd=clone_d1.wrangler_cwd(), check=False).returncode


class Api:
    """The D1 database API: one database's details by name, or None when it does not exist."""

    def __init__(self, transport: ov.Transport, headers: Mapping[str, str], account: str) -> None:
        self.transport = transport
        self.headers = headers
        self.account = account

    def _get(self, path: str) -> object:
        url = "%s/accounts/%s/d1/database%s" % (CF_API_BASE, self.account, path)
        status, body = self.transport("GET", url, self.headers, None)
        if status != 200 or not isinstance(body, dict) or not body.get("success"):
            raise RelocateError("D1 API %s answered %s" % (path or "/", status or "nothing"))
        return body.get("result")

    def find(self, name: str) -> dict | None:
        listed = self._get("?name=%s" % name)
        for item in listed if isinstance(listed, list) else []:
            if isinstance(item, dict) and item.get("name") == name and item.get("uuid"):
                detail = self._get("/%s" % item["uuid"])
                if not isinstance(detail, dict):
                    raise RelocateError("D1 API: no details for %s" % name)
                return detail
        return None


def describe(info: dict | None) -> str:
    if info is None:
        return "absent"
    return "size %s bytes, %s tables, region %s, jurisdiction %s" % (
        info.get("file_size", "?"),
        info.get("num_tables", "?"),
        info.get("running_in_region") or "?",
        info.get("jurisdiction") or "none",
    )


# --- reads ----------------------------------------------------------------------------------------


def q(ident: str) -> str:
    return dsm.q(ident)


def user_tables(db: Db) -> list[str]:
    return [str(r["name"]) for r in db.query(USER_TABLES_SQL)]


def fence_state(db: Db) -> tuple[bool, dict | None]:
    """(the fence table exists, its row or None)."""
    if FENCE_TABLE not in user_tables(db):
        return False, None
    rows = db.query(dsm.sql("SELECT id, reason, set_at FROM ", q(FENCE_TABLE), " WHERE id = 1"))
    return True, (rows[0] if rows else None)


def fence_text(present: bool, row: dict | None) -> str:
    if not present:
        return "absent"
    if row is None:
        return "present, empty"
    return "present, set (reason %s, set at %s)" % (row.get("reason"), row.get("set_at"))


def live_leases(db: Db, now: str) -> list[str]:
    """Live backup leases and sessions (`d1_shard_move.live_rows`) across every subscription; empty on a database without those tables (the control databases)."""
    if not set(dsm.LIVE_TABLES) <= set(user_tables(db)):
        return []
    subs = db.query(
        " UNION ".join(
            dsm.sql("SELECT DISTINCT subscription_id AS s FROM ", q(t), " WHERE expires_at > ")
            + dsm.lit(now)
            for t in dsm.LIVE_TABLES
        )
    )
    names = sorted({str(r["s"]) for r in subs if r.get("s") is not None})
    return dsm.live_rows(db, names, now) if names else []


def order_columns(db: Db, table: str) -> tuple[list[str], str]:
    """(every column, the ORDER BY text): the primary key columns in key order, else rowid."""
    info = db.query("PRAGMA table_info(%s)" % q(table))
    columns = [str(c["name"]) for c in info]
    keys = [str(c["name"]) for c in sorted(info, key=lambda c: c["pk"]) if c["pk"]]
    return columns, ", ".join(q(k) for k in keys) if keys else "rowid"


def table_rows(db: Db, table: str, order: str) -> list[dict]:
    rows: list[dict] = []
    while True:
        page = db.query(
            dsm.sql("SELECT * FROM ", q(table), " ORDER BY ", order)
            + dsm.sql(" LIMIT ", PAGE, " OFFSET ", len(rows))
        )
        rows += page
        if len(page) < PAGE:
            return rows


@dataclass(frozen=True)
class TableState:
    count: int
    sha256: str


def snapshot(db: Db, skip: Iterable[str] = ()) -> dict[str, TableState]:
    """Every user table's row count and canonical sha256, minus `skip`."""
    out: dict[str, TableState] = {}
    for table in user_tables(db):
        if table in skip:
            continue
        columns, order = order_columns(db, table)
        rows = table_rows(db, table, order)
        out[table] = TableState(len(rows), dsm.digest(rows, columns))
    return out


def snapshot_differences(src: dict[str, TableState], dst: dict[str, TableState]) -> list[str]:
    lines: list[str] = []
    for table in sorted(set(src) | set(dst)):
        if table not in dst:
            lines.append("%s: missing in the target (source %d rows)" % (table, src[table].count))
        elif table not in src:
            lines.append("%s: only in the target (%d rows)" % (table, dst[table].count))
        elif src[table] != dst[table]:
            lines.append(
                "%s: source %d rows %s, target %d rows %s"
                % (
                    table,
                    src[table].count,
                    src[table].sha256[:12],
                    dst[table].count,
                    dst[table].sha256[:12],
                )
            )
    return lines


def applied_migrations(db: Db) -> list[str] | None:
    if "d1_migrations" not in user_tables(db):
        return None
    return [str(r["name"]) for r in db.query("SELECT name FROM d1_migrations ORDER BY id")]


# --- configuration ----------------------------------------------------------------------------------


def toml_entries(root: Path) -> list[tuple[Path, dict]]:
    """(toml path, `[[d1_databases]]` entry) for every wrangler toml under workers/."""
    found: list[tuple[Path, dict]] = []
    for path in sorted((root / "workers").glob("**/wrangler*.toml")):
        if "node_modules" in path.parts:
            continue
        try:
            doc = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        found += [(path, e) for e in doc.get("d1_databases") or [] if isinstance(e, dict)]
    return found


def config_for(root: Path, names: Iterable[str], given: str | None) -> tuple[str, Path | None]:
    """(the wrangler config to pass, the migrations directory) for the first of `names` a toml declares. `given` narrows the search to that one file."""
    entries = toml_entries(root)
    if given:
        wanted = Path(given).resolve()
        entries = [(p, e) for p, e in entries if p.resolve() == wanted]
    for name in names:
        for path, entry in entries:
            if entry.get("database_name") == name:
                mdir = entry.get("migrations_dir")
                return str(path), ((path.parent / mdir).resolve() if mdir else None)
    return (given or str(root / "workers" / "account" / "wrangler.eu.toml")), None


def pending_migrations(mdir: Path | None, applied: list[str] | None) -> list[str] | None:
    """Migration files the target has not applied; None when there is nothing to compare."""
    if mdir is None or applied is None or not mdir.is_dir():
        return None
    done = set(applied)
    return sorted(p.name for p in mdir.glob("*.sql") if p.name not in done)


def referrers(root: Path, name: str) -> list[str]:
    """Every place that still names `name` as a live database."""
    found = [
        "%s (d1_databases database_name)" % p.relative_to(root)
        for p, e in toml_entries(root)
        if e.get("database_name") == name
    ]
    regions = root / "regions.json"
    if regions.is_file():
        try:
            doc = json.loads(regions.read_text(encoding="utf-8"))
        except ValueError:
            found.append("regions.json (unreadable)")
        else:
            for region in doc.get("regions") or []:
                d1 = region.get("d1") if isinstance(region, dict) else None
                if isinstance(d1, dict) and d1.get("name") == name:
                    found.append("regions.json (%s d1.name)" % region.get("id"))
    if name in deploy_www.PROTECTED_DATABASES:
        found.append("deploy_www.PROTECTED_DATABASES")
    return found


# --- the run record ---------------------------------------------------------------------------------


def now_iso() -> str:
    return dsm.now_iso()


def parse_iso(text: object) -> datetime | None:
    if not isinstance(text, str):
        return None
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


class Records:
    """`.ci/state/d1-relocate/<database>.json`: one record per moved database, an append-only `events` list."""

    def __init__(self, root: Path, clock: Callable[[], str] = now_iso) -> None:
        self.dir = root.joinpath(*STATE_REL)
        self.clock = clock

    def path(self, name: str) -> Path:
        return self.dir / ("%s.json" % name)

    def load(self, name: str) -> dict:
        path = self.path(name)
        if not path.is_file():
            return {"database": name, "events": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def note(self, name: str, event: str, **fields: object) -> dict:
        record = self.load(name)
        record.setdefault("events", []).append({"event": event, "at": self.clock(), **fields})
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path(name).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        return record


def last_event(record: dict, event: str) -> dict | None:
    hits = [e for e in record.get("events") or [] if e.get("event") == event]
    return hits[-1] if hits else None


# --- the steps --------------------------------------------------------------------------------------


@dataclass
class Ctx:
    root: Path
    records: Records
    out: object
    err: object
    clock: Callable[[], str] = now_iso
    sleep: Callable[[float], None] = time.sleep
    run: Callable[[list[str]], int] = run_wrangler

    def say(self, text: str) -> None:
        print("%s: %s" % (SELF, text), file=self.out, flush=True)

    def warn(self, text: str) -> None:
        print("%s: %s" % (SELF, text), file=self.err, flush=True)


def step_plan(ctx: Ctx, api: Api | None, src: Db, to: str, jurisdiction: str | None) -> int:
    if api is not None:
        ctx.say("%s: %s" % (src.name, describe(api.find(src.name))))
        target = api.find(to)
        ctx.say("%s: %s" % (to, describe(target)))
        if target is not None and jurisdiction and target.get("jurisdiction") != jurisdiction:
            ctx.warn("%s exists outside jurisdiction %s" % (to, jurisdiction))
    ctx.say("%s: %d user tables" % (src.name, len(user_tables(src))))
    ctx.say("fence table: %s" % fence_text(*fence_state(src)))
    live = live_leases(src, ctx.clock())
    ctx.say("live leases: %s" % ("; ".join(live) if live else "none"))
    return 0


def step_create(ctx: Ctx, api: Api, src: str, to: str, jurisdiction: str, write: bool) -> int:
    existing = api.find(to)
    if existing is not None:
        if existing.get("jurisdiction") == jurisdiction:
            ctx.say("%s already exists: %s" % (to, describe(existing)))
            return 0
        ctx.warn(
            "%s already exists outside jurisdiction %s: %s" % (to, jurisdiction, describe(existing))
        )
        return EXIT_FAILED
    argv = [*wrangler.ARGV, "d1", "create", to, "--jurisdiction", jurisdiction]
    if not write:
        ctx.say("dry run, would run: %s" % " ".join(argv))
        return 0
    status = ctx.run(argv)
    if status:
        ctx.warn("wrangler d1 create %s exited %d" % (to, status))
        return EXIT_FAILED
    made = api.find(to)
    if made is None or made.get("jurisdiction") != jurisdiction:
        ctx.warn("the API reports %s %s, not jurisdiction %s" % (to, describe(made), jurisdiction))
        return EXIT_FAILED
    ctx.records.note(src, "create", target=to, jurisdiction=jurisdiction, uuid=made.get("uuid"))
    ctx.say("created %s: %s" % (to, describe(made)))
    return 0


def step_fence(ctx: Ctx, db: Db, on: bool, reason: str, write: bool) -> int:
    present, row = fence_state(db)
    if not present:
        raise RefusedError(
            "%s has no %s table: ship the fence migration (boxes W1, W4) first"
            % (db.name, FENCE_TABLE)
        )
    if on and row is not None:
        ctx.say("%s is already fenced: %s" % (db.name, fence_text(present, row)))
        return 0
    if not on and row is None:
        ctx.say("%s is not fenced" % db.name)
        return 0
    if on:
        statement = dsm.sql(
            "INSERT INTO ", q(FENCE_TABLE), " (id, reason, set_at) VALUES (1, "
        ) + dsm.sql(dsm.lit(reason), ", ", dsm.lit(ctx.clock()), ") ON CONFLICT(id) DO NOTHING")
    else:
        statement = dsm.sql("DELETE FROM ", q(FENCE_TABLE), " WHERE id = 1")
    if not write:
        ctx.say("dry run, would run on %s: %s" % (db.name, statement))
        return 0
    db.batch([statement])
    _, after = fence_state(db)
    if (after is not None) != on:
        ctx.warn("%s: the fence row reads back %s" % (db.name, fence_text(True, after)))
        return EXIT_FAILED
    ctx.records.note(db.name, "fence-on" if on else "fence-off", reason=reason if on else None)
    if not on:
        ctx.say("%s unfenced" % db.name)
        return 0
    ctx.say("%s fenced; waiting %d s for every isolate to see it" % (db.name, DRAIN_S))
    ctx.sleep(DRAIN_S)
    live = live_leases(db, ctx.clock())
    ctx.say("live leases after the drain: %s" % ("; ".join(live) if live else "none"))
    return 0


def step_bookmark(
    ctx: Ctx, name: str, config: str, write: bool, reader: Callable[[str, str], str]
) -> int:
    try:
        bookmark = reader(name, config)
    except deploy_record.RecordError as exc:
        raise RelocateError(str(exc)) from exc
    ctx.say("%s bookmark %s" % (name, bookmark))
    if write:
        ctx.records.note(name, "bookmark", bookmark=bookmark, config=config)
        ctx.say("recorded in %s" % ctx.records.path(name))
    else:
        ctx.say("dry run, not recorded (pass --write to record it)")
    return 0


def strip_export(path: str) -> int:
    """Drop the `_cf_*` statements and the fence row from an export, in place; returns how many lines went. A dropped statement must end on its own line."""
    with open(path, encoding="utf-8", errors="surrogateescape") as handle:
        lines = handle.readlines()
    kept: list[str] = []
    dropped = 0
    for line in lines:
        if STRIPPED_STATEMENT.match(line):
            if not line.rstrip("\n").endswith(";"):
                raise RelocateError(
                    "the export holds a multi-line statement this copy cannot strip: %s" % line[:80]
                )
            dropped += 1
            continue
        kept.append(line)
    with open(path, "w", encoding="utf-8", errors="surrogateescape") as handle:
        handle.writelines(kept)
    return dropped


def source_fenced(ctx: Ctx, src: Db) -> None:
    present, row = fence_state(src)
    if not present or row is None:
        raise RefusedError(
            "%s is not fenced (%s): run `fence --db %s --on --write` first"
            % (src.name, fence_text(present, row), src.name)
        )
    set_at = parse_iso(row.get("set_at"))
    now = parse_iso(ctx.clock())
    if set_at is not None and now is not None and (now - set_at).total_seconds() < DRAIN_S:
        raise RefusedError(
            "%s was fenced at %s, less than the %d s drain ago" % (src.name, row["set_at"], DRAIN_S)
        )


def fence_insert(row: dict) -> str:
    return dsm.sql("INSERT INTO ", q(FENCE_TABLE), " (id, reason, set_at) VALUES (1, ") + dsm.sql(
        dsm.lit(row.get("reason")), ", ", dsm.lit(row.get("set_at")), ");\n"
    )


def transfer(ctx: Ctx, src: Db, dst: Db, keep_target_fence: dict | None) -> None:
    """Export `src`, strip it, wrap it in the `clone_d1` deferred-FK import and run it on `dst`. The fence table arrives empty, then holds `keep_target_fence` when given."""
    tmpdir = tempfile.mkdtemp(prefix="d1-relocate.")
    try:
        src.export_into(tmpdir)
        dropped = strip_export(os.path.join(tmpdir, "export.sql"))
        ctx.say("export stripped of %d _cf_* or fence statement(s)" % dropped)
        try:
            clone_d1.build_import_sql(tmpdir, [FENCE_TABLE])
        except clone_d1.BashExitError as exc:
            raise RelocateError("preparing the import failed (exit %d)" % exc.code) from exc
        import_sql = os.path.join(tmpdir, "import.sql")
        if keep_target_fence is not None:
            with open(import_sql, "a", encoding="utf-8") as handle:
                handle.write(fence_insert(keep_target_fence))
        ctx.say("importing into %s" % dst.name)
        dst.import_file(import_sql)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def step_verify(
    ctx: Ctx, src: Db, dst: Db, mdir: Path | None, *, target_fence: dict | None = None
) -> int:
    """Exit 0 when `dst` holds `src` exactly; 3 on a difference; 1 when a read failed. `target_fence` is the fence row the target must hold (None: no row)."""
    try:
        problems = snapshot_differences(
            snapshot(src, skip=(FENCE_TABLE,)), snapshot(dst, skip=(FENCE_TABLE,))
        )
        src_mig, dst_mig = applied_migrations(src), applied_migrations(dst)
        if src_mig != dst_mig:
            problems.append("d1_migrations: source %s, target %s" % (src_mig, dst_mig))
        try:
            violations = dst.query("PRAGMA foreign_key_check")
        except (RelocateError, sqlite3.Error) as exc:
            raise RelocateError(
                "PRAGMA foreign_key_check on %s failed: %s" % (dst.name, exc)
            ) from exc
        problems += [
            "foreign key violation: %s" % json.dumps(v, sort_keys=True, default=str)
            for v in violations
        ]
        _, fence_row = fence_state(dst)
        want = (
            None
            if target_fence is None
            else (target_fence.get("reason"), target_fence.get("set_at"))
        )
        got = None if fence_row is None else (fence_row.get("reason"), fence_row.get("set_at"))
        if got != want:
            problems.append("fence row on the target: %s, expected %s" % (got, want))
        pending = pending_migrations(mdir, dst_mig)
        tables = len(user_tables(src))
    except (RelocateError, sqlite3.Error) as exc:
        ctx.warn("verify could not run: %s" % exc)
        return EXIT_FAILED
    if pending:
        problems.append("migrations pending on the target: %s" % ", ".join(pending))
    for line in problems:
        ctx.warn("mismatch %s" % line)
    if problems:
        ctx.warn("%d difference(s) between %s and %s" % (len(problems), src.name, dst.name))
        return EXIT_VERIFY
    ctx.say(
        "verified %s -> %s: %d tables equal, d1_migrations equal, 0 foreign key violations, %s"
        % (
            src.name,
            dst.name,
            tables,
            "nothing pending" if pending is not None else "pending not checked (no migrations_dir)",
        )
    )
    return 0


def step_copy(ctx: Ctx, src: Db, dst: Db, mdir: Path | None, write: bool) -> int:
    source_fenced(ctx, src)
    occupied = [t for t in user_tables(dst) if t != FENCE_TABLE]
    if occupied:
        raise RefusedError(
            "%s already holds tables (%s): the copy goes into a new, empty database"
            % (dst.name, ", ".join(occupied[:5]))
        )
    tables = [t for t in user_tables(src) if t != FENCE_TABLE]
    ctx.say("%s -> %s: %d tables" % (src.name, dst.name, len(tables)))
    if not write:
        ctx.say("dry run, nothing copied (pass --write to copy)")
        return 0
    transfer(ctx, src, dst, None)
    status = step_verify(ctx, src, dst, mdir)
    ctx.records.note(src.name, "copy", target=dst.name, verify=status)
    return status


def step_reverse(ctx: Ctx, old: Db, new: Db, mdir: Path | None, write: bool) -> int:
    """Copy `new` back over `old`; the old one keeps its fence row until the repoint back is deployed."""
    source_fenced(ctx, new)
    _, old_fence = fence_state(old)
    ctx.say(
        "reverse %s -> %s; %s keeps fence %s"
        % (new.name, old.name, old.name, fence_text(True, old_fence))
    )
    if not write:
        ctx.say("dry run, nothing copied (pass --write to reverse)")
        return 0
    transfer(ctx, new, old, old_fence)
    status = step_verify(ctx, new, old, mdir, target_fence=old_fence)
    ctx.records.note(old.name, "reverse", source=new.name, verify=status)
    return status


def step_record(ctx: Ctx, name: str, event: str | None, write: bool) -> int:
    if event and write:
        ctx.records.note(name, event)
    elif event:
        ctx.say("dry run, would stamp %s on %s" % (event, ctx.records.path(name)))
    print(json.dumps(ctx.records.load(name), indent=2), file=ctx.out)
    return 0


def final_exports(root: Path, name: str, since: datetime) -> list[Path]:
    """`backup_d1` exports of `name` (`.backups/<set>/<name>-<stamp>.sql`), non-empty and stamped at or after `since`."""
    pattern = re.compile(r"^%s-(%s)\.sql$" % (re.escape(name), BACKUP_STAMP_RE))
    found: list[Path] = []
    for path in sorted((root / BACKUPS_REL).glob("*/*.sql")):
        match = pattern.match(path.name)
        if not match or path.stat().st_size == 0:
            continue
        stamp = datetime.strptime(match.group(1), BACKUP_STAMP).replace(tzinfo=UTC)
        if stamp >= since:
            found.append(path)
    return found


def step_retire(ctx: Ctx, name: str, to: str, yes_delete: str | None, write: bool) -> int:
    if yes_delete != name:
        raise RefusedError("--yes-delete must repeat the database name exactly: %s" % name)
    record = ctx.records.load(name)
    cutover = parse_iso((last_event(record, "cutover") or {}).get("at"))
    if cutover is None:
        raise RefusedError(
            "%s has no cutover in %s: `record --from %s --event cutover --write` stamps it"
            % (name, ctx.records.path(name), name)
        )
    now = parse_iso(ctx.clock()) or datetime.now(UTC)
    if now - cutover < RETENTION:
        raise RefusedError(
            "%s was cut over at %s, %d day(s) ago; retire waits %d days"
            % (name, cutover.isoformat(), (now - cutover).days, RETENTION.days)
        )
    named = referrers(ctx.root, name)
    if named:
        raise RefusedError("%s is still named by: %s" % (name, "; ".join(named)))
    fenced = parse_iso((last_event(record, "fence-on") or {}).get("at")) or cutover
    exports = final_exports(ctx.root, name, fenced)
    if not exports:
        raise RefusedError(
            "no backup_d1 export of %s taken after %s under %s/"
            % (name, fenced.isoformat(), BACKUPS_REL)
        )
    argv = [*wrangler.ARGV, "d1", "delete", name, "--skip-confirmation"]
    if not write:
        ctx.say("dry run, would run: %s (final export %s)" % (" ".join(argv), exports[-1]))
        return 0
    status = ctx.run(argv)
    if status:
        ctx.warn("wrangler d1 delete %s exited %d" % (name, status))
        return EXIT_FAILED
    ctx.records.note(name, "retire", replaced_by=to, final_export=str(exports[-1]))
    ctx.say("deleted %s" % name)
    return 0


# --- command line -----------------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=SELF, description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="step", required=True)

    def add(name: str, *, pair: bool = True, write: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name)
        p.add_argument("--sqlite", action="append", default=[], metavar="NAME=PATH")
        p.add_argument("--config", help="the wrangler toml declaring the database")
        if pair:
            p.add_argument("--from", dest="src", required=True)
            p.add_argument("--to", dest="dst", required=True)
        if write:
            p.add_argument("--write", action="store_true", help="change things (default: print)")
        return p

    add("plan", write=False).add_argument("--jurisdiction", choices=JURISDICTIONS)
    add("create").add_argument("--jurisdiction", choices=JURISDICTIONS, required=True)
    fence = add("fence", pair=False)
    fence.add_argument("--db", required=True)
    side = fence.add_mutually_exclusive_group(required=True)
    side.add_argument("--on", action="store_true")
    side.add_argument("--off", action="store_true")
    fence.add_argument("--reason", default=SELF)
    add("bookmark", pair=False).add_argument("--from", dest="src", required=True)
    add("copy")
    add("verify", write=False)
    record = add("record", pair=False)
    record.add_argument("--from", dest="src", required=True)
    record.add_argument("--event", choices=("cutover",))
    add("reverse")
    add("retire").add_argument("--yes-delete")
    return ap


def open_db(
    name: str, sqlite: Mapping[str, str], env: Mapping[str, str], transport: ov.Transport
) -> Db:
    if name in sqlite:
        return SqliteDb(name, sqlite[name])
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
    return D1Db(name, dsm.D1Executor(transport, ov.cf_headers(env), account, name))


def open_api(env: Mapping[str, str], transport: ov.Transport) -> Api:
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
    return Api(transport, ov.cf_headers(env), account)


def default_bookmark(name: str, config: str) -> str:
    return deploy_record.d1_bookmark(Path(clone_d1.wrangler_cwd()), name, config)


def dispatch(
    args: argparse.Namespace, ctx: Ctx, env: Mapping[str, str], transport: ov.Transport
) -> int:
    sqlite: dict[str, str] = {}
    for spec in args.sqlite:
        name, sep, path = spec.partition("=")
        if not sep or not name or not path:
            raise RelocateError("--sqlite takes NAME=PATH, got %r" % spec)
        sqlite[name] = path

    def db(name: str) -> Db:
        return open_db(name, sqlite, env, transport)

    names = [n for n in (getattr(args, "src", None), getattr(args, "dst", None)) if n]
    config, mdir = config_for(ctx.root, names, args.config)
    step = args.step
    if step == "plan":
        api = None if sqlite else open_api(env, transport)
        return step_plan(ctx, api, db(args.src), args.dst, args.jurisdiction)
    if step == "create":
        if sqlite:
            raise RelocateError("create needs the D1 API, not a --sqlite database")
        return step_create(
            ctx, open_api(env, transport), args.src, args.dst, args.jurisdiction, args.write
        )
    if step == "fence":
        return step_fence(ctx, db(args.db), args.on, args.reason, args.write)
    if step == "bookmark":
        if args.src in sqlite:
            raise RelocateError("a bookmark needs a D1 database, not a --sqlite one")
        return step_bookmark(ctx, args.src, config, args.write, default_bookmark)
    if step == "copy":
        return step_copy(ctx, db(args.src), db(args.dst), mdir, args.write)
    if step == "verify":
        return step_verify(ctx, db(args.src), db(args.dst), mdir)
    if step == "record":
        return step_record(ctx, args.src, args.event, args.write)
    if step == "reverse":
        return step_reverse(ctx, db(args.src), db(args.dst), mdir, args.write)
    return step_retire(ctx, args.src, args.dst, args.yes_delete, args.write)


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    transport: ov.Transport | None = None,
    ctx: Ctx | None = None,
) -> int:
    args = parser().parse_args(argv)
    env = env if env is not None else os.environ
    ctx = ctx or Ctx(ROOT, Records(ROOT), sys.stdout, sys.stderr)
    try:
        return dispatch(args, ctx, env, transport or ov.real_transport)
    except RefusedError as exc:
        ctx.warn("refused: %s" % exc)
        return EXIT_REFUSED
    except (RelocateError, ov.VolumeError, dsm.MoveError, sqlite3.Error, OSError) as exc:
        ctx.warn("failed: %s" % exc)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
