"""Move subscriptions' tenant rows from one D1 shard to another (PLAN-d1-scaling Z8, box H2).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_shard_move --db 0=d1:account-eu --db 1=d1:account-eu-s1 --to 1 <subscription-id>... [--write]
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.d1_shard_move --db 0=sqlite:dir.db --db 1=sqlite:s1.db --to 1 <subscription-id>...

WHY IT EXISTS. Each region has a directory database (shard 0, where every global table lives and where `subscription_shards` names each subscription's shard) and N tenant shards. src/db/shard-router.ts routes a subscription's tenant rows to its shard; this tool moves those rows when N changes (H4 bench proof, H5 cutover).

THE TENANT SET is read from `SHARD_CLASS` in private/account/src/db/shard-router.ts at run time, each export name mapped to its SQL table through schema.ts and config-schema.ts, so the tool follows the router and never carries a second list. Each tenant table is selected by the first rule its columns fit:
  - a `subscription_id` column: the moved subscriptions (`event_log` also takes its org-level rows: no subscription, a moved org);
  - `config_stores`: `org_id` in the moved orgs (`subscriptions.org_id` is the subscription-to-org relation);
  - a `config_store_id` column: the moved stores; `config_entry_id`: the moved entries.
A tenant table no rule fits refuses the run: the registry grew a table this tool cannot scope.

THE ORG RULE. The config tables carry no subscription id; they hang off the org's config store. So every subscription of a moved org moves in the same run, or the run refuses and names the ones left behind.

FOREIGN KEYS. Tenant tables reference global tables (`subscriptions`, `users`, `teams`, `organizations`) and D1 enforces foreign keys with no off switch (reset_bench.py measured it). Every shard is built from the same drizzle migrations as the directory, so the shard schema keeps those references and the tool copies the parent rows: before the import it walks the references of the exported rows, transitively, reads each parent row from the directory and inserts it into the target with `ON CONFLICT DO NOTHING` (never REPLACE, which would cascade-delete children). The copies are inert: the router reads global tables only from the directory. Moving back to shard 0 copies nothing. References are read from each table's `CREATE` text, because D1 refuses `pragma_foreign_key_list`.

THE MOVE, in order (`--write`; without it the run stops after the plan and writes nothing):
  1. pre-checks: the subscriptions exist, the org rule holds, they share one source shard that is not the target, source and target agree on every tenant table's columns, the target holds none of the rows and uses none of their single-column primary keys (`subscription_activations.id` is an AUTOINCREMENT integer assigned per database), and the source holds no live `backup_upload_leases` or `backup_sessions` row (`expires_at` after now).
  2. the plan: per table the row count and a sha256 over the rows (canonical JSON, sorted), printed.
  3. a directory row at the source shard for any subscription without one (Z8: the tool writes the row before it moves anything).
  4. parent copies, then the tenant rows in reference order, as literal INSERT statements (the D1 query API's params are strings only, so NULL and integers cannot be bound).
  5. verify: the target re-read must match the plan's counts and hashes; a mismatch deletes the imported rows from the target and exits 3, before the flip. The lease check runs again here.
  6. flip: `subscription_shards.shard` = target, `moved_at` = now.
  7. the source is re-hashed; a row written between the export and the flip makes it differ, and the source is then kept (exit 4) for the operator to reconcile. Otherwise the source rows are deleted, children first, and the delete is counted back to zero.

EXIT CODES. 0 planned (dry run) or moved; 1 usage; 2 refused by a pre-check, nothing moved; 3 verification failed, target rolled back, no flip; 4 flipped, source kept because it changed.

DATABASES are `<shard>=d1:<database name>` (the D1 REST query API, with CLOUDFLARE_API_TOKEN or the Global API Key pair and CLOUDFLARE_ACCOUNT_ID, as the other ops modules read them) or `<shard>=sqlite:<path>`. Shard 0 must be given: it is the directory. No secret reaches argv or output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from rediacc_ci.ops import observability_volume as ov
from rediacc_ci.well_known import CF_API_BASE

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[3]

EXIT_USAGE = 1
EXIT_REFUSED = 2
EXIT_VERIFY = 3
EXIT_SOURCE_CHANGED = 4

PAGE = 500
BATCH = 50
# D1 refuses a statement over 100,000 bytes; refuse it here, by row, before anything is written.
MAX_STATEMENT_BYTES = 100_000
LIVE_TABLES = ("backup_upload_leases", "backup_sessions")


class MoveError(Exception):
    """A pre-check refused the move; the message names the reason."""


class Executor(Protocol):
    """One database. `query` returns rows as dicts; `batch` runs statements in order."""

    def query(self, sql: str) -> list[dict]: ...

    def batch(self, statements: list[str]) -> None: ...


class SqliteExecutor:
    """A local SQLite file with foreign keys enforced, as D1 enforces them."""

    def __init__(self, path: str | Path) -> None:
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def query(self, sql: str) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    def batch(self, statements: list[str]) -> None:
        with self.conn:
            for statement in statements:
                self.conn.execute(statement)

    def close(self) -> None:
        self.conn.close()


class D1Executor:
    """One D1 database over the REST query API."""

    def __init__(
        self, transport: ov.Transport, headers: Mapping[str, str], account: str, database: str
    ) -> None:
        self.transport = transport
        self.headers = headers
        self.account = account
        self.database = database
        self._uuid: str | None = None

    def _resolve(self) -> str:
        if self._uuid:
            return self._uuid
        url = "%s/accounts/%s/d1/database?name=%s" % (CF_API_BASE, self.account, self.database)
        status, body = self.transport("GET", url, self.headers, None)
        if status != 200 or not isinstance(body, dict) or not body.get("success"):
            raise MoveError(
                "%s: database lookup answered %s" % (self.database, status or "nothing")
            )
        for item in body.get("result") or []:
            if isinstance(item, dict) and item.get("name") == self.database and item.get("uuid"):
                self._uuid = str(item["uuid"])
                return self._uuid
        raise MoveError("%s: database not found" % self.database)

    def _post(self, body: dict) -> list:
        url = "%s/accounts/%s/d1/database/%s/query" % (CF_API_BASE, self.account, self._resolve())
        status, answer = self.transport("POST", url, self.headers, body)
        if status != 200 or not isinstance(answer, dict) or not answer.get("success"):
            errors = answer.get("errors") if isinstance(answer, dict) else None
            raise MoveError(
                "%s: query answered %s %s" % (self.database, status or "nothing", errors or "")
            )
        result = answer.get("result")
        if not isinstance(result, list) or not result:
            raise MoveError("%s: query returned no result" % self.database)
        return result

    def query(self, sql: str) -> list[dict]:
        first = self._post({"sql": sql})[0]
        if not isinstance(first, dict):
            raise MoveError("%s: query returned no result" % self.database)
        return list(first.get("results") or [])

    def batch(self, statements: list[str]) -> None:
        for start in range(0, len(statements), BATCH):
            self._post({"batch": [{"sql": s} for s in statements[start : start + BATCH]]})


# --- SQL text -------------------------------------------------------------------------------------


def sql(*parts: object) -> str:
    """A statement from fixed text plus pieces this module built: identifiers through `q`, values through `lit`, clauses from `scope_where`, and ints. Nothing comes from a request."""
    return "".join(str(p) for p in parts)


def q(ident: str) -> str:
    """A SQLite double-quoted identifier."""
    return '"%s"' % ident.replace('"', '""')


def lit(value: object) -> str:
    """A SQLite literal for a value read back from a database."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MoveError("a non-finite REAL cannot be written as a literal: %r" % value)
        return repr(value)
    if isinstance(value, bytes):
        return "X'%s'" % value.hex()
    if isinstance(value, str):
        if "\x00" in value:
            raise MoveError("a TEXT value holds a NUL byte, which a literal cannot carry")
        return "'%s'" % value.replace("'", "''")
    raise MoveError("unsupported value type %s" % type(value).__name__)


def in_list(values: Iterable[object]) -> str:
    return "(%s)" % ", ".join(lit(v) for v in sorted(set(values), key=str))


def now_iso() -> str:
    """The JS `toISOString()` form the account server writes, so text comparison orders it."""
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)


# --- the tenant set, from the router ----------------------------------------------------------------

SHARD_CLASS_BLOCK = re.compile(r"export const SHARD_CLASS = \{(.*?)\}\s*as const", re.DOTALL)
SHARD_CLASS_ENTRY = re.compile(r"^\s*(\w+):\s*'(global|tenant)'", re.MULTILINE)
TABLE_EXPORT = re.compile(r"export const (\w+)\s*=\s*sqliteTable\(\s*'([a-z0-9_]+)'")


def load_tenant_tables(root: Path | None = None) -> list[str]:
    """SQL names of the tables `SHARD_CLASS` marks tenant, in the router's order."""
    db_dir = (root or ROOT) / "private" / "account" / "src" / "db"
    router = (db_dir / "shard-router.ts").read_text(encoding="utf-8")
    block = SHARD_CLASS_BLOCK.search(router)
    if not block:
        raise MoveError("shard-router.ts carries no SHARD_CLASS map")
    names: dict[str, str] = {}
    for schema in ("schema.ts", "config-schema.ts"):
        names.update(TABLE_EXPORT.findall((db_dir / schema).read_text(encoding="utf-8")))
    tenant: list[str] = []
    for export, shard_class in SHARD_CLASS_ENTRY.findall(block.group(1)):
        if shard_class != "tenant":
            continue
        if export not in names:
            raise MoveError("SHARD_CLASS names %s, which no sqliteTable export defines" % export)
        tenant.append(names[export])
    if not tenant:
        raise MoveError("SHARD_CLASS marks no table tenant")
    return tenant


# --- schema, read through the executor ------------------------------------------------------------

_IDENT = r'[`"\[]?(\w+)[`"\]]?'
FK_CLAUSE = re.compile(
    r"FOREIGN\s+KEY\s*\(\s*%s\s*\)\s*REFERENCES\s+%s\s*\(\s*%s" % (_IDENT, _IDENT, _IDENT),
    re.IGNORECASE,
)
INLINE_FK = re.compile(
    r"(?:^|[(,])\s*%s\s+\w+[^,(]*?\bREFERENCES\s+%s\s*\(\s*%s" % (_IDENT, _IDENT, _IDENT),
    re.IGNORECASE,
)


def parse_references(create_sql: str) -> list[tuple[str, str, str]]:
    """(column, parent table, parent column) for every reference in a CREATE TABLE text."""
    found = {(c, p, pc) for c, p, pc in FK_CLAUSE.findall(create_sql)}
    rest = FK_CLAUSE.sub("", create_sql)
    rest = rest[rest.find("(") + 1 :]
    found |= {(c, p, pc) for c, p, pc in INLINE_FK.findall(rest)}
    return sorted(found)


@dataclass
class Schema:
    columns: dict[str, list[str]] = field(default_factory=dict)
    refs: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    keys: dict[str, list[str]] = field(default_factory=dict)


def read_schema(db: Executor) -> Schema:
    schema = Schema()
    rows = db.query(
        "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' AND name <> 'd1_migrations'"
    )
    for row in rows:
        name = row["name"]
        info = db.query("PRAGMA table_info(%s)" % q(name))
        schema.columns[name] = [c["name"] for c in info]
        schema.keys[name] = [c["name"] for c in sorted(info, key=lambda c: c["pk"]) if c["pk"]]
        schema.refs[name] = parse_references(row.get("sql") or "")
    return schema


def parents_first(tables: list[str], schema: Schema, *, strict: bool) -> list[str]:
    """Tables ordered so each comes after the tables of the set it references.

    A cycle refuses when `strict` (the tenant set, whose delete order depends on it); among the
    copied global parents (no cycle today) it falls back to name order.
    """
    inside = set(tables)
    deps = {t: {p for _, p, _ in schema.refs.get(t, []) if p in inside and p != t} for t in tables}
    ordered: list[str] = []
    while len(ordered) < len(tables):
        ready = [t for t in tables if t not in ordered and deps[t] <= set(ordered)]
        if not ready:
            remaining = sorted(t for t in tables if t not in ordered)
            if strict:
                raise MoveError("tables reference each other in a cycle: %s" % ", ".join(remaining))
            ready = remaining[:1]
        ordered += ready
    return ordered


# --- the plan ---------------------------------------------------------------------------------------


@dataclass
class Scope:
    subscriptions: list[str]
    orgs: list[str]
    stores: set[str] = field(default_factory=set)
    entries: set[str] = field(default_factory=set)


def scope_where(table: str, columns: list[str], scope: Scope) -> str | None:
    """The WHERE clause selecting the moved rows of a tenant table; None when the set is empty."""
    if "subscription_id" in columns:
        clause = "subscription_id IN %s" % in_list(scope.subscriptions)
        if table == "event_log" and scope.orgs:
            clause = "(%s OR (subscription_id IS NULL AND org_id IN %s))" % (
                clause,
                in_list(scope.orgs),
            )
        return clause
    if table == "config_stores":
        return "org_id IN %s" % in_list(scope.orgs) if scope.orgs else None
    if "config_store_id" in columns:
        return "config_store_id IN %s" % in_list(scope.stores) if scope.stores else None
    if "config_entry_id" in columns:
        return "config_entry_id IN %s" % in_list(scope.entries) if scope.entries else None
    raise MoveError("tenant table %s has no column this tool can scope by" % table)


def fetch(db: Executor, table: str, where: str | None) -> list[dict]:
    if where is None:
        return []
    rows: list[dict] = []
    while True:
        page = db.query(
            sql("SELECT * FROM ", q(table), " WHERE ", where)
            + sql(" ORDER BY rowid LIMIT ", PAGE, " OFFSET ", len(rows))
        )
        rows += page
        if len(page) < PAGE:
            return rows


def digest(rows: list[dict], columns: list[str]) -> str:
    cols = sorted(columns)
    lines = sorted(json.dumps([r.get(c) for c in cols], separators=(",", ":")) for r in rows)
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


@dataclass
class TableExport:
    table: str
    where: str | None
    rows: list[dict]
    count: int
    sha256: str


@dataclass
class Plan:
    subscriptions: list[str]
    orgs: list[str]
    source: int
    target: int
    missing_rows: list[str]
    tables: list[TableExport]


def export(db: Executor, order: list[str], schema: Schema, scope: Scope) -> list[TableExport]:
    out: list[TableExport] = []
    for table in order:
        where = scope_where(table, schema.columns[table], scope)
        rows = fetch(db, table, where)
        if table == "config_stores":
            scope.stores = {r["id"] for r in rows}
        elif table == "config_entries":
            scope.entries = {r["id"] for r in rows}
        out.append(TableExport(table, where, rows, len(rows), digest(rows, schema.columns[table])))
    return out


def live_rows(db: Executor, subscriptions: list[str], now: str) -> list[str]:
    found: list[str] = []
    for table in LIVE_TABLES:
        rows = db.query(
            sql("SELECT id, expires_at FROM ", q(table), " WHERE subscription_id IN ")
            + sql(in_list(subscriptions), " AND expires_at > ", lit(now))
        )
        found += ["%s %s (expires %s)" % (table, r["id"], r["expires_at"]) for r in rows]
    return found


def _count(db: Executor, table: str, where: str) -> int:
    rows = db.query(sql("SELECT count(*) AS n FROM ", q(table), " WHERE ", where))
    return int(rows[0]["n"]) if rows else 0


def key_collisions(dst: Executor, exported: list[TableExport], schema: Schema) -> list[str]:
    """Single-column primary keys of the moved rows that the target holds for another row.

    `subscription_activations.id` is an AUTOINCREMENT integer, assigned per database, so a row
    born on the directory can carry the id a shard already gave one of its own rows. A
    composite key always includes `subscription_id`, which the occupied check already covers.
    """
    taken: list[str] = []
    for t in exported:
        keys = schema.keys.get(t.table, [])
        if len(keys) != 1 or not t.rows:
            continue
        values = [r[keys[0]] for r in t.rows]
        for start in range(0, len(values), PAGE):
            chunk = values[start : start + PAGE]
            rows = dst.query(
                sql("SELECT ", q(keys[0]), " AS k FROM ", q(t.table))
                + sql(" WHERE ", q(keys[0]), " IN ", in_list(chunk))
            )
            taken += ["%s.%s=%s" % (t.table, keys[0], r["k"]) for r in rows]
    return taken


def _source_shard(directory: Executor, subs: list[str]) -> tuple[int, list[str]]:
    rows = directory.query(
        sql("SELECT subscription_id, shard FROM subscription_shards WHERE subscription_id IN ")
        + in_list(subs)
    )
    current = {r["subscription_id"]: str(r["shard"]) for r in rows}
    sources: set[int] = set()
    for sub in subs:
        raw = current.get(sub, "0")
        if not raw.isdigit():
            raise MoveError("subscription %s is on shard '%s', not a shard index" % (sub, raw))
        sources.add(int(raw))
    if len(sources) != 1:
        raise MoveError("the subscriptions sit on different shards: %s" % sorted(sources))
    return sources.pop(), sorted(set(subs) - set(current))


def build_plan(
    dbs: Mapping[int, Executor], subscriptions: list[str], target: int, tenant: list[str], now: str
) -> tuple[Plan, Schema]:
    if 0 not in dbs:
        raise MoveError("shard 0 (the directory) is not given")
    if target not in dbs:
        raise MoveError("target shard %d is not given" % target)
    subs = sorted(set(subscriptions))
    if not subs:
        raise MoveError("no subscription named")
    directory = dbs[0]
    found = directory.query(sql("SELECT id, org_id FROM subscriptions WHERE id IN ", in_list(subs)))
    unknown = sorted(set(subs) - {r["id"] for r in found})
    if unknown:
        raise MoveError("unknown subscription(s): %s" % ", ".join(unknown))
    orgs = sorted({r["org_id"] for r in found if r["org_id"]})
    if orgs:
        siblings = directory.query(
            sql("SELECT id FROM subscriptions WHERE org_id IN ", in_list(orgs))
        )
        left = sorted({r["id"] for r in siblings} - set(subs))
        if left:
            raise MoveError(
                "the config tables carry no subscription id and follow the org, so every "
                "subscription of a moved org moves together; name these too: %s" % ", ".join(left)
            )
    source, missing = _source_shard(directory, subs)
    if source == target:
        raise MoveError("already on shard %d" % target)
    if source not in dbs:
        raise MoveError("source shard %d is not given" % source)
    src, dst = dbs[source], dbs[target]
    src_schema, dst_schema = read_schema(src), read_schema(dst)
    for table in tenant:
        for side, schema in (("source", src_schema), ("target", dst_schema)):
            if table not in schema.columns:
                raise MoveError("%s shard has no table %s: apply the migrations" % (side, table))
        if src_schema.columns[table] != dst_schema.columns[table]:
            raise MoveError("%s differs between source and target: apply the migrations" % table)
    live = live_rows(src, subs, now)
    if live:
        raise MoveError("live lease or session on the source: %s" % "; ".join(live))
    order = parents_first(tenant, src_schema, strict=True)
    exported = export(src, order, src_schema, Scope(subs, orgs))
    occupied = []
    for t in exported:
        n = _count(dst, t.table, t.where) if t.where else 0
        if n:
            occupied.append("%s (%d)" % (t.table, n))
    if occupied:
        raise MoveError("the target already holds rows of these: %s" % ", ".join(occupied))
    taken = key_collisions(dst, exported, src_schema)
    if taken:
        raise MoveError(
            "the target already uses these primary keys for other rows: %s" % "; ".join(taken)
        )
    return Plan(subs, orgs, source, target, missing, exported), src_schema


# --- writing ----------------------------------------------------------------------------------------


def insert_sql(table: str, row: dict, *, if_absent: bool = False) -> str:
    cols = list(row)
    statement = sql(
        "INSERT INTO ",
        q(table),
        " (",
        ", ".join(q(c) for c in cols),
        ") VALUES (",
        ", ".join(lit(row[c]) for c in cols),
        ")",
        " ON CONFLICT DO NOTHING" if if_absent else "",
    )
    size = len(statement.encode())
    if size > MAX_STATEMENT_BYTES:
        raise MoveError("a %s row needs a %d-byte statement, over D1's limit" % (table, size))
    return statement


def parent_copies(
    directory: Executor, schema: Schema, tenant: set[str], exported: list[TableExport]
) -> list[str]:
    """INSERT statements for every global row the moved rows reference, transitively, parents first."""
    wanted: list[tuple[str, dict]] = [(t.table, r) for t in exported for r in t.rows]
    seen: set[tuple[str, str, object]] = set()
    fetched: dict[str, dict[str, dict]] = {}
    while wanted:
        table, row = wanted.pop()
        for column, parent, parent_col in schema.refs.get(table, []):
            value = row.get(column)
            if value is None or parent in tenant or (parent, parent_col, value) in seen:
                continue
            seen.add((parent, parent_col, value))
            for prow in directory.query(
                sql("SELECT * FROM ", q(parent), " WHERE ", q(parent_col), " = ", lit(value))
            ):
                key = json.dumps(prow, sort_keys=True)
                if key not in fetched.setdefault(parent, {}):
                    fetched[parent][key] = prow
                    wanted.append((parent, prow))
    order = parents_first(sorted(fetched), schema, strict=False)
    return [insert_sql(t, r, if_absent=True) for t in order for r in fetched[t].values()]


def delete_rows(db: Executor, exported: list[TableExport]) -> None:
    db.batch(
        [sql("DELETE FROM ", q(t.table), " WHERE ", t.where) for t in reversed(exported) if t.where]
    )


def mismatches(db: Executor, exported: list[TableExport], schema: Schema) -> list[str]:
    off: list[str] = []
    for t in exported:
        rows = fetch(db, t.table, t.where)
        got = digest(rows, schema.columns[t.table])
        if len(rows) != t.count or got != t.sha256:
            off.append(
                "%s: %d rows %s, expected %d rows %s"
                % (t.table, len(rows), got[:12], t.count, t.sha256[:12])
            )
    return off


def print_plan(plan: Plan, out) -> None:
    print(
        "d1_shard_move: %s from shard %d to shard %d (orgs: %s)"
        % (", ".join(plan.subscriptions), plan.source, plan.target, ", ".join(plan.orgs) or "none"),
        file=out,
    )
    for t in plan.tables:
        if t.count:
            print("  %-28s %6d  %s" % (t.table, t.count, t.sha256[:16]), file=out)
    total = sum(t.count for t in plan.tables)
    tables = sum(1 for t in plan.tables if t.count)
    print("  %d rows in %d tables" % (total, tables), file=out)


def move(
    dbs: Mapping[int, Executor],
    subscriptions: list[str],
    target: int,
    *,
    write: bool = False,
    tenant: list[str] | None = None,
    clock: Callable[[], str] = now_iso,
    out=None,
    err=None,
) -> int:
    out = out or sys.stdout
    err = err or sys.stderr
    try:
        tenant = tenant if tenant is not None else load_tenant_tables()
        plan, schema = build_plan(dbs, subscriptions, target, tenant, clock())
    except MoveError as exc:
        print("d1_shard_move: refused: %s" % exc, file=err)
        return EXIT_REFUSED
    print_plan(plan, out)
    if not write:
        print("d1_shard_move: dry run, nothing written (pass --write to move)", file=out)
        return 0
    directory, src, dst = dbs[0], dbs[plan.source], dbs[plan.target]
    if plan.missing_rows:
        directory.batch(
            [
                sql("INSERT INTO subscription_shards (subscription_id, shard, moved_at) VALUES (")
                + sql(lit(sub), ", ", lit(str(plan.source)), ", NULL) ON CONFLICT DO NOTHING")
                for sub in plan.missing_rows
            ]
        )
    try:
        statements = []
        if plan.target != 0:
            statements += parent_copies(directory, schema, set(tenant), plan.tables)
        statements += [insert_sql(t.table, r) for t in plan.tables for r in t.rows]
        dst.batch(statements)
        off = mismatches(dst, plan.tables, schema)
        live = live_rows(src, plan.subscriptions, clock())
    except (MoveError, sqlite3.Error) as exc:
        delete_rows(dst, plan.tables)
        print("d1_shard_move: import failed, target rolled back, no flip: %s" % exc, file=err)
        return EXIT_VERIFY
    if off or live:
        delete_rows(dst, plan.tables)
        for line in off:
            print("d1_shard_move: mismatch %s" % line, file=err)
        for line in live:
            print("d1_shard_move: live on the source since the plan: %s" % line, file=err)
        print("d1_shard_move: target rolled back, no flip", file=err)
        return EXIT_VERIFY if off else EXIT_REFUSED
    stamp = clock()
    directory.batch(
        [
            sql("UPDATE subscription_shards SET shard = ", lit(str(plan.target)))
            + sql(", moved_at = ", lit(stamp), " WHERE subscription_id = ", lit(sub))
            for sub in plan.subscriptions
        ]
    )
    print("d1_shard_move: flipped to shard %d at %s" % (plan.target, stamp), file=out)
    changed = mismatches(src, plan.tables, schema)
    if changed:
        for line in changed:
            print("d1_shard_move: source changed since the export: %s" % line, file=err)
        print(
            "d1_shard_move: source rows kept on shard %d; reconcile them by hand" % plan.source,
            file=err,
        )
        return EXIT_SOURCE_CHANGED
    delete_rows(src, plan.tables)
    left = [t.table for t in plan.tables if t.where and _count(src, t.table, t.where)]
    if left:
        print("d1_shard_move: source rows survived the delete: %s" % ", ".join(left), file=err)
        return EXIT_SOURCE_CHANGED
    print("d1_shard_move: moved; source rows deleted from shard %d" % plan.source, file=out)
    return 0


# --- command line -----------------------------------------------------------------------------------


def open_db(spec: str, env: Mapping[str, str], transport: ov.Transport) -> Executor:
    kind, _, where = spec.partition(":")
    if kind == "sqlite" and where:
        if not Path(where).is_file():
            raise MoveError("no SQLite file at %s" % where)
        return SqliteExecutor(where)
    if kind == "d1" and where:
        account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
        return D1Executor(transport, ov.cf_headers(env), account, where)
    raise MoveError("a database is d1:<name> or sqlite:<path>, got %r" % spec)


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    transport: ov.Transport | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="d1_shard_move")
    parser.add_argument("--db", action="append", default=[], metavar="N=KIND:WHERE")
    parser.add_argument("--to", type=int, required=True, help="target shard index")
    parser.add_argument("--write", action="store_true", help="move (default: dry run)")
    parser.add_argument("subscriptions", nargs="+")
    args = parser.parse_args(argv)
    env = env if env is not None else os.environ
    dbs: dict[int, Executor] = {}
    try:
        for spec in args.db:
            index, sep, rest = spec.partition("=")
            if not sep or not index.isdigit():
                raise MoveError("--db takes N=d1:<name> or N=sqlite:<path>, got %r" % spec)
            dbs[int(index)] = open_db(rest, env, transport or ov.real_transport)
    except (MoveError, ov.VolumeError) as exc:
        print("d1_shard_move: %s" % exc, file=sys.stderr)
        return EXIT_USAGE
    return move(dbs, args.subscriptions, args.to, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
