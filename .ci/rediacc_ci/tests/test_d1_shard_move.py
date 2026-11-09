"""Tests for `rediacc_ci.ops.d1_shard_move` (PLAN-d1-scaling box H2).

Every test runs on local SQLite files built by applying private/account/drizzle/*.sql in journal order, with foreign keys enforced as D1 enforces them. Shard 0 is the directory; shard 1 is a second database built from the same migrations. No Cloudflare credential and no network.
"""

from __future__ import annotations

import io
import json
import shutil
import sqlite3
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import d1_shard_move as mod

if typing.TYPE_CHECKING:
    import pathlib
    from collections.abc import Iterator

ROOT = paths.repo_root()
DRIZZLE = ROOT / "private" / "account" / "drizzle"
PAST = "2026-01-01T00:00:00.000Z"
FUTURE = "2999-01-01T00:00:00.000Z"
NOW = "2026-11-09T12:00:00.000Z"

U1, U2 = "user-1", "user-2"
O1, O2 = "org-1", "org-2"
T1 = "team-1"
S1, S2, S3 = "sub-1", "sub-2", "sub-3"
STORE = "store-1"
ENTRY = "entry-1"


def clock() -> str:
    return NOW


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> pathlib.Path:
    path = tmp_path_factory.mktemp("d1") / "template.db"
    conn = sqlite3.connect(path)
    journal = json.loads((DRIZZLE / "meta" / "_journal.json").read_text(encoding="utf-8"))
    for entry in journal["entries"]:
        sql = (DRIZZLE / ("%s.sql" % entry["tag"])).read_text(encoding="utf-8")
        conn.executescript(sql.replace("--> statement-breakpoint", ""))
    conn.commit()
    conn.close()
    return path


class Row:
    """Inserts a row, filling every NOT NULL column without a default with a unique placeholder."""

    def __init__(self, db: mod.SqliteExecutor) -> None:
        self.db = db
        self.n = 0

    def __call__(self, table: str, **values: object) -> None:
        for col in self.db.query("PRAGMA table_info(%s)" % mod.q(table)):
            name = col["name"]
            if (
                name in values
                or not col["notnull"]
                or col["dflt_value"] is not None
                or col["pk"] > 1
            ):
                continue
            self.n += 1
            kind = (col["type"] or "").upper()
            values[name] = (
                self.n if "INT" in kind or "REAL" in kind else "%s-%s-%d" % (table, name, self.n)
            )
        self.db.batch([mod.insert_sql(table, values)])


def seed(db: mod.SqliteExecutor) -> None:
    add = Row(db)
    add("users", id=U1, email="u1@example.com")
    add("users", id=U2, email="u2@example.com")
    add("organizations", id=O1, owner_user_id=U1)
    add("organizations", id=O2, owner_user_id=U2)
    add("teams", id=T1, org_id=O1)
    for sub, org in ((S1, O1), (S2, O1), (S3, O2)):
        add("subscriptions", id=sub, org_id=org, type="subscription", status="active")
    for sub in (S1, S2, S3):
        add("subscription_activations", subscription_id=sub, org_id=O1)
        add("backup_usage", subscription_id=sub)
        add("api_tokens", id="tok-" + sub, subscription_id=sub, scopes='["a"]')
        add("issuance_ledger", sequence=1, subscription_id=sub, chain_hash="c-" + sub)
        add("event_log", id="ev-" + sub, subscription_id=sub, data="it's é")
    add("backup_upload_leases", id="lease-old", subscription_id=S1, expires_at=PAST)
    add("backup_sessions", id="sess-old", subscription_id=S1, expires_at=PAST)
    add("delegation_certs", id="cert-1", subscription_id=S2, created_by_user_id=U1)
    add("event_log", id="ev-org", subscription_id=None, org_id=O1)
    add("event_log", id="ev-org2", subscription_id=None, org_id=O2)
    add("config_stores", id=STORE, org_id=O1)
    add("config_entries", id=ENTRY, config_store_id=STORE, team_id=T1, hmac="h")
    add("config_versions", id="ver-1", config_entry_id=ENTRY, created_by_user_id=U2)
    add("config_key_slots", id="slot-1", config_store_id=STORE, user_id=U2)


@pytest.fixture
def shards(
    template: pathlib.Path, tmp_path: pathlib.Path
) -> Iterator[dict[int, mod.SqliteExecutor]]:
    dbs = {}
    for index in (0, 1):
        path = tmp_path / ("shard%d.db" % index)
        shutil.copyfile(template, path)
        dbs[index] = mod.SqliteExecutor(path)
    seed(dbs[0])
    yield dbs
    for db in dbs.values():
        db.close()


def dump(db: mod.SqliteExecutor) -> list[str]:
    return list(db.conn.iterdump())


def counts(db: mod.SqliteExecutor, where_sub: tuple[str, ...]) -> dict[str, int]:
    """Rows per tenant table that belong to the given subscriptions (or to their org)."""
    tenant = mod.load_tenant_tables()
    schema = mod.read_schema(db)
    scope = mod.Scope(sorted(where_sub), [O1] if S1 in where_sub else [O2])
    exported = mod.export(db, mod.parents_first(tenant, schema, strict=True), schema, scope)
    return {t.table: t.count for t in exported if t.count}


def run(shards, subs, target=1, **kw) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    rc = mod.move(shards, subs, target, clock=clock, out=out, err=err, **kw)
    return rc, out.getvalue(), err.getvalue()


# --- the registry and the schema reader -------------------------------------------------------------


def test_tenant_set_follows_the_router_and_every_table_scopes(template: pathlib.Path) -> None:
    tenant = mod.load_tenant_tables()
    assert len(tenant) == 30
    assert len(set(tenant)) == 30
    db = mod.SqliteExecutor(template)
    schema = mod.read_schema(db)
    scope = mod.Scope([S1], [O1], {STORE}, {ENTRY})
    for table in tenant:
        assert table in schema.columns, table
        assert mod.scope_where(table, schema.columns[table], scope), table
    order = mod.parents_first(tenant, schema, strict=True)
    assert (
        order.index("config_stores")
        < order.index("config_entries")
        < order.index("config_versions")
    )
    db.close()


def test_references_from_create_text_match_sqlite(template: pathlib.Path) -> None:
    """D1 refuses pragma_foreign_key_list; the CREATE-text parser must agree with it on every table."""
    conn = sqlite3.connect(template)
    db = mod.SqliteExecutor(template)
    schema = mod.read_schema(db)
    for table in schema.columns:
        expected = sorted(
            {(r[3], r[2], r[4]) for r in conn.execute("PRAGMA foreign_key_list(%s)" % mod.q(table))}
        )
        assert schema.refs[table] == expected, table
    conn.close()
    db.close()


def test_literals_round_trip(template: pathlib.Path) -> None:
    db = mod.SqliteExecutor(template)
    values = [None, 0, -7, 2**53, 1.5, "it's", "é中", b"\x00\xff", True]
    got = db.query(
        "SELECT %s" % ", ".join("%s AS c%d" % (mod.lit(v), i) for i, v in enumerate(values))
    )
    assert list(got[0].values()) == [None, 0, -7, 2**53, 1.5, "it's", "é中", b"\x00\xff", 1]
    with pytest.raises(mod.MoveError):
        mod.lit("a\x00b")
    db.close()


# --- the move ---------------------------------------------------------------------------------------


def test_dry_run_changes_nothing(shards) -> None:
    before = [dump(shards[0]), dump(shards[1])]
    rc, out, _ = run(shards, [S1, S2])
    assert rc == 0
    assert "dry run" in out
    assert "config_versions" in out
    assert [dump(shards[0]), dump(shards[1])] == before


def test_move_copies_verifies_flips_and_deletes(shards) -> None:
    directory, target = shards[0], shards[1]
    tenant = mod.load_tenant_tables()
    schema = mod.read_schema(directory)
    order = mod.parents_first(tenant, schema, strict=True)
    before = mod.export(directory, order, schema, mod.Scope([S1, S2], [O1]))
    bystander = counts(directory, (S3,))
    assert directory.query("SELECT * FROM subscription_shards") == []

    rc, out, err = run(shards, [S2, S1], write=True)
    assert (rc, err) == (0, "")
    assert "moved" in out

    after = mod.export(target, order, schema, mod.Scope([S1, S2], [O1]))
    assert [(t.table, t.count, t.sha256) for t in after] == [
        (t.table, t.count, t.sha256) for t in before
    ]
    assert sum(t.count for t in after) >= 17
    assert counts(directory, (S1, S2)) == {}
    assert counts(directory, (S3,)) == bystander
    assert counts(target, (S3,)) == {}
    rows = directory.query("SELECT * FROM subscription_shards ORDER BY subscription_id")
    assert [(r["subscription_id"], r["shard"], r["moved_at"]) for r in rows] == [
        (S1, "1", NOW),
        (S2, "1", NOW),
    ]
    # Parent rows copied, so the shard satisfies every reference with foreign keys on.
    assert target.query("PRAGMA foreign_key_check") == []
    assert {r["id"] for r in target.query("SELECT id FROM users")} == {U1, U2}
    assert {r["id"] for r in target.query("SELECT id FROM subscriptions")} == {S1, S2}
    assert {r["id"] for r in target.query("SELECT id FROM teams")} == {T1}
    # The directory keeps every global row.
    assert len(directory.query("SELECT id FROM subscriptions")) == 3


def test_shard_enforces_the_global_references(shards) -> None:
    """The control for the parent copies: a tenant row without its global parent is refused."""
    with pytest.raises(sqlite3.IntegrityError):
        shards[1].batch(
            [mod.insert_sql("backup_usage", {"subscription_id": S1, "stored_bytes": 0})]
        )


def test_move_back_to_the_directory(shards) -> None:
    before = counts(shards[0], (S1, S2))
    assert run(shards, [S1, S2], write=True)[0] == 0
    rc, _, err = run(shards, [S1, S2], target=0, write=True)
    assert (rc, err) == (0, "")
    assert counts(shards[0], (S1, S2)) == before
    assert counts(shards[1], (S1, S2)) == {}
    rows = shards[0].query("SELECT shard FROM subscription_shards")
    assert {r["shard"] for r in rows} == {"0"}


def test_org_with_two_subscriptions_moves_together(shards) -> None:
    before = [dump(shards[0]), dump(shards[1])]
    rc, _, err = run(shards, [S1], write=True)
    assert rc == mod.EXIT_REFUSED
    assert S2 in err
    assert [dump(shards[0]), dump(shards[1])] == before


@pytest.mark.parametrize("table", ["backup_upload_leases", "backup_sessions"])
def test_live_lease_or_session_refuses(shards, table: str) -> None:
    Row(shards[0])(table, id="live", subscription_id=S2, expires_at=FUTURE)
    before = [dump(shards[0]), dump(shards[1])]
    rc, _, err = run(shards, [S1, S2], write=True)
    assert rc == mod.EXIT_REFUSED
    assert "%s live" % table in err
    assert [dump(shards[0]), dump(shards[1])] == before


def test_hash_mismatch_aborts_before_the_flip(shards) -> None:
    shards[1].conn.executescript(
        "CREATE TRIGGER tamper AFTER INSERT ON config_entries "
        "BEGIN UPDATE config_entries SET hmac = 'tampered' WHERE id = NEW.id; END;"
    )
    before = counts(shards[0], (S1, S2))
    rc, _, err = run(shards, [S1, S2], write=True)
    assert rc == mod.EXIT_VERIFY
    assert "mismatch config_entries" in err
    assert counts(shards[1], (S1, S2)) == {}
    assert counts(shards[0], (S1, S2)) == before
    rows = shards[0].query("SELECT shard, moved_at FROM subscription_shards")
    assert [(r["shard"], r["moved_at"]) for r in rows] == [("0", None), ("0", None)]


class WritesAfterFlip:
    """The directory, plus an event_log row landing on it as the flip runs."""

    def __init__(self, inner: mod.SqliteExecutor) -> None:
        self.inner = inner

    def query(self, sql: str) -> list[dict]:
        return self.inner.query(sql)

    def batch(self, statements: list[str]) -> None:
        self.inner.batch(statements)
        if statements and statements[0].startswith("UPDATE subscription_shards"):
            Row(self.inner)("event_log", id="ev-late", subscription_id=S1)


def test_source_written_during_the_move_is_kept(shards) -> None:
    wrapped = {0: WritesAfterFlip(shards[0]), 1: shards[1]}
    rc, _, err = run(wrapped, [S1, S2], write=True)
    assert rc == mod.EXIT_SOURCE_CHANGED
    assert "event_log" in err
    kept = {
        r["id"] for r in shards[0].query("SELECT id FROM event_log WHERE subscription_id = 'sub-1'")
    }
    assert kept == {"ev-sub-1", "ev-late"}
    assert shards[1].query("SELECT id FROM event_log WHERE id = 'ev-sub-1'")
    assert {r["shard"] for r in shards[0].query("SELECT shard FROM subscription_shards")} == {"1"}


def test_autoincrement_key_collision_refuses(shards) -> None:
    """A shard numbers its own activations from 1, so a directory-born id can already be taken."""
    target = shards[1]
    add = Row(target)
    add("users", id=U2, email="u2@example.com")
    add("organizations", id=O2, owner_user_id=U2)
    add("subscriptions", id="sub-on-shard", org_id=O2, type="subscription", status="active")
    taken = shards[0].query(
        "SELECT min(id) AS id FROM subscription_activations WHERE subscription_id = 'sub-1'"
    )
    add("subscription_activations", id=taken[0]["id"], subscription_id="sub-on-shard")
    before = [dump(shards[0]), dump(target)]
    rc, _, err = run(shards, [S1, S2], write=True)
    assert rc == mod.EXIT_REFUSED
    assert "subscription_activations.id=%d" % taken[0]["id"] in err
    assert [dump(shards[0]), dump(target)] == before


def test_unknown_subscription_and_same_shard_refuse(shards) -> None:
    assert run(shards, ["nope"])[0] == mod.EXIT_REFUSED
    assert "already on shard 0" in run(shards, [S1, S2], target=0)[2]


# --- the D1 executor and the command line -----------------------------------------------------------


def test_d1_executor_sends_queries_and_batches() -> None:
    calls: list[tuple[str, str, dict]] = []

    def transport(method, url, _headers, body):
        calls.append((method, url, body))
        if method == "GET":
            return 200, {"success": True, "result": [{"name": "account-eu-s1", "uuid": "u-1"}]}
        return 200, {"success": True, "result": [{"results": [{"n": 1}]}]}

    db = mod.D1Executor(transport, {"Authorization": "Bearer t"}, "acct", "account-eu-s1")
    assert db.query("SELECT 1 AS n") == [{"n": 1}]
    db.batch(["DELETE FROM x WHERE 1"] * (mod.BATCH + 1))
    posts = [c for c in calls if c[0] == "POST"]
    assert posts[0][1].endswith("/accounts/acct/d1/database/u-1/query")
    assert posts[0][2] == {"sql": "SELECT 1 AS n"}
    assert [len(p[2]["batch"]) for p in posts[1:]] == [mod.BATCH, 1]
    assert len([c for c in calls if c[0] == "GET"]) == 1


def test_d1_executor_failure_names_the_database() -> None:
    def transport(method, _url, _headers, _body):
        if method == "GET":
            return 200, {"success": True, "result": [{"name": "db", "uuid": "u"}]}
        return 400, {"success": False, "errors": [{"message": "FOREIGN KEY constraint failed"}]}

    with pytest.raises(mod.MoveError, match="db: query answered 400"):
        mod.D1Executor(transport, {}, "a", "db").query("SELECT 1")


def test_cli_dry_run_on_sqlite_files(shards, tmp_path: pathlib.Path, capsys) -> None:
    for db in shards.values():
        db.conn.commit()
    paths_ = [tmp_path / "shard0.db", tmp_path / "shard1.db"]
    rc = mod.main(
        ["--db", "0=sqlite:%s" % paths_[0], "--db", "1=sqlite:%s" % paths_[1], "--to", "1", S1, S2],
        env={},
    )
    assert rc == 0
    assert "dry run" in capsys.readouterr().out
    assert mod.main(["--db", "0=ftp:x", "--to", "1", S1], env={}) == mod.EXIT_USAGE
