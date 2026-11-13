"""`rediacc_ci.ops.d1_relocate` over local SQLite files standing in for D1 (no Cloudflare call): the fence, the copy and its verify, reverse, create against a fake D1 API, and retire's refusals."""

from __future__ import annotations

import io
import json
import sqlite3
from typing import TYPE_CHECKING, Any, TextIO, cast

import pytest

from rediacc_ci.ops import d1_relocate as rel
from rediacc_ci.ops import d1_shard_move as dsm

if TYPE_CHECKING:
    from pathlib import Path

T0 = "2026-11-13T10:00:00.000Z"
LATER = "2026-11-13T10:05:00.000Z"
ENV = {"CLOUDFLARE_API_TOKEN": "tok-fixture", "CLOUDFLARE_ACCOUNT_ID": "acct-fixture"}

SCHEMA = """
CREATE TABLE d1_migrations (id INTEGER PRIMARY KEY, name TEXT, applied_at TEXT);
CREATE TABLE _write_fence (id INTEGER PRIMARY KEY CHECK (id = 1), reason TEXT, set_at TEXT);
CREATE TABLE organizations (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE subscriptions (id TEXT PRIMARY KEY, org_id TEXT REFERENCES organizations(id), blob BLOB);
CREATE TABLE backup_upload_leases (id TEXT PRIMARY KEY, subscription_id TEXT, expires_at TEXT);
CREATE TABLE backup_sessions (id TEXT PRIMARY KEY, subscription_id TEXT, expires_at TEXT);
CREATE TABLE notes (body TEXT);
CREATE TABLE _cf_KV (key TEXT PRIMARY KEY, value BLOB);
"""
ROWS = """
INSERT INTO d1_migrations VALUES (1, '0000_init.sql', 'x'), (2, '0001_fence.sql', 'y');
INSERT INTO organizations VALUES ('o1', 'Org ''one'''), ('o2', NULL);
INSERT INTO subscriptions VALUES ('s1', 'o1', X'00ff'), ('s2', 'o2', NULL);
INSERT INTO backup_upload_leases VALUES ('l1', 's1', '2026-11-13T09:00:00.000Z');
INSERT INTO notes VALUES ('line one
line two'), ('plain');
INSERT INTO _cf_KV VALUES ('k', X'01');
"""


def text(stream: TextIO) -> str:
    assert isinstance(stream, io.StringIO)
    return stream.getvalue()


def last(ctx: rel.Ctx, name: str, event: str) -> dict[str, Any]:
    found = rel.last_event(ctx.records.load(name), event)
    assert found is not None
    return found


class Clock:
    def __init__(self, now: str = T0) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


def make_source(path: Path, *, fence: bool = True) -> Path:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA if fence else SCHEMA.replace("CREATE TABLE _write_fence", "-- "))
    conn.executescript(ROWS)
    conn.commit()
    conn.close()
    return path


def make_ctx(root: Path, clock: Clock | None = None, run=None) -> rel.Ctx:
    clock = clock or Clock()
    ctx = rel.Ctx(
        root,
        rel.Records(root, clock),
        io.StringIO(),
        io.StringIO(),
        clock=clock,
        sleep=lambda _s: None,
    )
    if run is not None:
        ctx.run = run
    return ctx


def call(ctx: rel.Ctx, *argv: str, transport=None) -> int:
    return rel.main(list(argv), env=ENV, transport=transport, ctx=ctx)


def sq(src: Path, dst: Path) -> list[str]:
    return ["--sqlite", "account-x=%s" % src, "--sqlite", "account-x-j=%s" % dst]


def rows(path: Path, sql: str) -> list[tuple]:
    conn = sqlite3.connect(path)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path, rel.Ctx, Clock]:
    src = make_source(tmp_path / "src.db")
    dst = tmp_path / "dst.db"
    sqlite3.connect(dst).close()
    clock = Clock()
    return src, dst, make_ctx(tmp_path, clock), clock


def fence_and_drain(ctx: rel.Ctx, clock: Clock, src: Path) -> None:
    assert (
        call(ctx, "fence", "--db", "account-x", "--on", "--write", "--sqlite", "account-x=%s" % src)
        == 0
    )
    clock.now = LATER


# --- the fence ----------------------------------------------------------------------------------


def test_fence_without_write_changes_nothing(pair) -> None:
    src, _dst, ctx, _clock = pair
    assert call(ctx, "fence", "--db", "account-x", "--on", "--sqlite", "account-x=%s" % src) == 0
    assert rows(src, "SELECT * FROM _write_fence") == []
    assert "dry run, would run on account-x: INSERT INTO" in text(ctx.out)
    assert not ctx.records.path("account-x").exists()


def test_fence_on_drains_then_off(pair) -> None:
    src, _dst, ctx, _clock = pair
    slept: list[float] = []
    ctx.sleep = slept.append
    assert (
        call(
            ctx,
            "fence",
            "--db",
            "account-x",
            "--on",
            "--write",
            "--reason",
            "move",
            "--sqlite",
            "account-x=%s" % src,
        )
        == 0
    )
    assert rows(src, "SELECT id, reason, set_at FROM _write_fence") == [(1, "move", T0)]
    assert slept == [rel.DRAIN_S] == [50]
    assert "live leases after the drain: none" in text(ctx.out)
    assert last(ctx, "account-x", "fence-on")["reason"] == "move"
    assert (
        call(
            ctx, "fence", "--db", "account-x", "--off", "--write", "--sqlite", "account-x=%s" % src
        )
        == 0
    )
    assert rows(src, "SELECT * FROM _write_fence") == []


def test_fence_refuses_a_database_without_the_fence_table(tmp_path: Path) -> None:
    src = make_source(tmp_path / "src.db", fence=False)
    ctx = make_ctx(tmp_path)
    assert (
        call(ctx, "fence", "--db", "account-x", "--on", "--write", "--sqlite", "account-x=%s" % src)
        == 2
    )
    assert "no _write_fence table" in text(ctx.err)


def test_plan_names_the_fence_state_and_live_leases(pair) -> None:
    src, dst, ctx, _clock = pair
    conn = sqlite3.connect(src)
    conn.execute("INSERT INTO backup_sessions VALUES ('b1', 's2', '2026-11-13T11:00:00.000Z')")
    conn.commit()
    conn.close()
    assert call(ctx, "plan", "--from", "account-x", "--to", "account-x-j", *sq(src, dst)) == 0
    out = text(ctx.out)
    assert "fence table: present, empty" in out
    assert "backup_sessions b1 (expires 2026-11-13T11:00:00.000Z)" in out
    assert "l1" not in out, "an expired lease is not live"


# --- copy and verify ----------------------------------------------------------------------------


def test_copy_moves_every_row_and_never_the_fence_row_or_cf_tables(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    ), text(ctx.err)
    assert rows(src, "SELECT count(*) FROM _write_fence") == [(1,)], "the source stays fenced"
    assert rows(dst, "SELECT count(*) FROM _write_fence") == [(0,)], (
        "a fence row never reaches the target"
    )
    tables = {r[0] for r in rows(dst, "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "_cf_KV" not in tables
    assert "_write_fence" in tables, "the fence table itself arrives, empty"
    assert rows(dst, "SELECT * FROM subscriptions ORDER BY id") == rows(
        src, "SELECT * FROM subscriptions ORDER BY id"
    )
    assert rows(dst, "SELECT body FROM notes ORDER BY rowid") == [
        ("line one\nline two",),
        ("plain",),
    ]
    assert "verified account-x -> account-x-j" in text(ctx.out)
    assert last(ctx, "account-x", "copy")["verify"] == 0


def test_copy_without_write_changes_nothing(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", *sq(src, dst)) == 0
    assert rows(dst, "SELECT count(*) FROM sqlite_master") == [(0,)]
    assert "dry run, nothing copied" in text(ctx.out)


def test_copy_refuses_an_unfenced_source(pair) -> None:
    src, dst, ctx, _clock = pair
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 2
    )
    assert "account-x is not fenced (present, empty)" in text(ctx.err)
    assert rows(dst, "SELECT count(*) FROM sqlite_master") == [(0,)]


def test_copy_refuses_inside_the_drain_window(pair) -> None:
    src, dst, ctx, clock = pair
    assert (
        call(ctx, "fence", "--db", "account-x", "--on", "--write", "--sqlite", "account-x=%s" % src)
        == 0
    )
    clock.now = "2026-11-13T10:00:30.000Z"
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 2
    )
    assert "less than the 50 s drain ago" in text(ctx.err)


def test_copy_refuses_a_target_that_holds_tables(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    sqlite3.connect(dst).execute("CREATE TABLE stray (x)").connection.close()
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 2
    )
    assert "already holds tables (stray)" in text(ctx.err)


def test_planted_row_drift_exits_3(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    )
    conn = sqlite3.connect(dst)
    conn.execute("UPDATE organizations SET name = 'drifted' WHERE id = 'o2'")
    conn.commit()
    conn.close()
    assert call(ctx, "verify", "--from", "account-x", "--to", "account-x-j", *sq(src, dst)) == 3
    err = text(ctx.err)
    assert "mismatch organizations: source 2 rows" in err
    assert "subscriptions" not in err


def test_a_missing_row_and_a_migration_difference_exit_3(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    )
    conn = sqlite3.connect(dst)
    conn.execute("DELETE FROM d1_migrations WHERE id = 2")
    conn.commit()
    conn.close()
    assert call(ctx, "verify", "--from", "account-x", "--to", "account-x-j", *sq(src, dst)) == 3
    assert (
        "d1_migrations: source ['0000_init.sql', '0001_fence.sql'], target ['0000_init.sql']"
        in text(ctx.err)
    )


def test_a_fence_row_on_the_target_fails_verify(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    )
    conn = sqlite3.connect(dst)
    conn.execute("INSERT INTO _write_fence VALUES (1, 'x', 'y')")
    conn.commit()
    conn.close()
    assert call(ctx, "verify", "--from", "account-x", "--to", "account-x-j", *sq(src, dst)) == 3
    assert "fence row on the target: ('x', 'y'), expected None" in text(ctx.err)


def test_a_foreign_key_violation_exits_3(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    )
    for path in (src, dst):
        conn = sqlite3.connect(path)
        conn.execute("INSERT INTO subscriptions VALUES ('s3', 'ghost', NULL)")
        conn.commit()
        conn.close()
    assert call(ctx, "verify", "--from", "account-x", "--to", "account-x-j", *sq(src, dst)) == 3
    assert '"parent": "organizations"' in text(ctx.err)


class FailingFk:
    """A database whose `PRAGMA foreign_key_check` call fails, as a D1 call that errored does."""

    def __init__(self, inner: rel.SqliteDb) -> None:
        self.inner = inner
        self.name = inner.name

    def query(self, sql: str) -> list[dict]:
        if sql == "PRAGMA foreign_key_check":
            raise rel.RelocateError("query answered 500")
        return self.inner.query(sql)


def test_a_failed_fk_call_exits_1_not_zero_violations(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    )
    ctx.out = io.StringIO()
    status = rel.step_verify(
        ctx, rel.SqliteDb("account-x", src), cast("rel.Db", FailingFk(rel.SqliteDb("account-x-j", dst))), None
    )
    assert status == 1
    assert (
        "PRAGMA foreign_key_check on account-x-j failed: query answered 500" in text(ctx.err)
    )
    assert "verified" not in text(ctx.out), "a check that could not run is not a pass"


def test_a_failed_d1_fk_call_exits_1(pair) -> None:
    """The same over the D1 REST path: the query API answering 500 is a failed verify, never a pass."""
    src, _dst, ctx, _clock = pair

    def transport(method: str, _url: str, _headers, body):
        if method == "GET":
            return 200, {"success": True, "result": [{"name": "account-x-j", "uuid": "u1"}]}
        if body == {"sql": "PRAGMA foreign_key_check"}:
            return 500, {"success": False, "errors": [{"message": "boom"}]}
        local = rel.SqliteDb("account-x", src)
        return 200, {"success": True, "result": [{"results": local.query(body["sql"])}]}

    d1 = rel.D1Db("account-x-j", dsm.D1Executor(transport, {}, "acct", "account-x-j"))
    assert rel.step_verify(ctx, rel.SqliteDb("account-x", src), d1, None) == 1
    assert "PRAGMA foreign_key_check on account-x-j failed" in text(ctx.err)


def test_pending_migrations_fail_verify(pair, tmp_path: Path) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    mdir = tmp_path / "drizzle"
    mdir.mkdir()
    for name in ("0000_init.sql", "0001_fence.sql", "0002_new.sql"):
        (mdir / name).write_text("SELECT 1;\n", encoding="utf-8")
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    )
    status = rel.step_verify(
        ctx, rel.SqliteDb("account-x", src), rel.SqliteDb("account-x-j", dst), mdir
    )
    assert status == 3
    assert "migrations pending on the target: 0002_new.sql" in text(ctx.err)


def test_config_for_finds_the_toml_and_its_migrations_dir(tmp_path: Path) -> None:
    toml = tmp_path / "workers" / "account" / "wrangler.bench.toml"
    toml.parent.mkdir(parents=True)
    toml.write_text(
        'name = "account-bench"\n[[d1_databases]]\nbinding = "DB"\ndatabase_name = "account-bench"\n'
        'migrations_dir = "../../private/account/drizzle"\n',
        encoding="utf-8",
    )
    config, mdir = rel.config_for(tmp_path, ["account-bench", "account-bench-j"], None)
    assert config == str(toml)
    assert mdir == (tmp_path / "private" / "account" / "drizzle").resolve()
    assert rel.config_for(tmp_path, ["control-bench-eu"], None)[1] is None


def test_strip_export_refuses_a_multi_line_statement_it_would_cut(tmp_path: Path) -> None:
    path = tmp_path / "export.sql"
    path.write_text('INSERT INTO "_write_fence" VALUES(1,\'a\n', encoding="utf-8")
    with pytest.raises(rel.RelocateError, match="multi-line"):
        rel.strip_export(str(path))
    path.write_text(
        "CREATE TABLE _cf_KV (k);\nINSERT INTO \"_write_fence\" VALUES(1,'a','b');\n"
        'INSERT INTO "_write_fence_log" VALUES(1);\nINSERT INTO "users" VALUES(1);\n',
        encoding="utf-8",
    )
    assert rel.strip_export(str(path)) == 2
    assert path.read_text(encoding="utf-8") == (
        'INSERT INTO "_write_fence_log" VALUES(1);\nINSERT INTO "users" VALUES(1);\n'
    )


# --- reverse ------------------------------------------------------------------------------------


def test_reverse_copies_back_and_keeps_the_old_fence(pair) -> None:
    src, dst, ctx, clock = pair
    fence_and_drain(ctx, clock, src)
    assert (
        call(ctx, "copy", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    )
    conn = sqlite3.connect(dst)
    conn.execute("INSERT INTO organizations VALUES ('o3', 'written after cutover')")
    conn.commit()
    conn.close()
    clock.now = "2026-11-13T11:00:00.000Z"
    # The new database must be fenced before the reverse.
    assert (
        call(ctx, "reverse", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 2
    )
    assert (
        call(
            ctx,
            "fence",
            "--db",
            "account-x-j",
            "--on",
            "--write",
            "--sqlite",
            "account-x-j=%s" % dst,
        )
        == 0
    )
    clock.now = "2026-11-13T11:05:00.000Z"
    assert (
        call(ctx, "reverse", "--from", "account-x", "--to", "account-x-j", "--write", *sq(src, dst))
        == 0
    ), text(ctx.err)
    assert rows(src, "SELECT id FROM organizations ORDER BY id") == [("o1",), ("o2",), ("o3",)]
    assert rows(src, "SELECT reason, set_at FROM _write_fence") == [("d1_relocate", T0)], (
        "the old fence stays"
    )


# --- create -------------------------------------------------------------------------------------


class FakeD1Api:
    def __init__(self, databases: dict[str, dict]) -> None:
        self.databases = databases

    def __call__(self, method: str, url: str, _headers, _body):
        assert method == "GET"
        tail = url.split("/d1/database", 1)[1]
        if tail.startswith("?name="):
            name = tail[len("?name=") :]
            found = [{"name": name, "uuid": "u-" + name}] if name in self.databases else []
            return 200, {"success": True, "result": found}
        name = tail.lstrip("/")[2:]
        return 200, {
            "success": True,
            "result": {"uuid": "u-" + name, "name": name, **self.databases[name]},
        }


def test_create_runs_wrangler_and_requires_the_api_to_report_eu(tmp_path: Path) -> None:
    api = FakeD1Api({})
    ran: list[list[str]] = []

    def run(argv: list[str]) -> int:
        ran.append(argv)
        api.databases["account-x-j"] = {"jurisdiction": "eu", "running_in_region": "EEUR"}
        return 0

    ctx = make_ctx(tmp_path, run=run)
    argv = ["create", "--from", "account-x", "--to", "account-x-j", "--jurisdiction", "eu"]
    assert call(ctx, *argv, transport=api) == 0
    assert ran == [], "without --write nothing is created"
    assert call(ctx, *argv, "--write", transport=api) == 0
    assert ran == [
        ["npx", "--no-install", "wrangler", "d1", "create", "account-x-j", "--jurisdiction", "eu"]
    ]
    assert last(ctx, "account-x", "create")["jurisdiction"] == "eu"


def test_create_exits_1_when_the_api_does_not_report_eu(tmp_path: Path) -> None:
    api = FakeD1Api({})

    def run(_argv: list[str]) -> int:
        api.databases["account-x-j"] = {"jurisdiction": None, "running_in_region": "EEUR"}
        return 0

    ctx = make_ctx(tmp_path, run=run)
    argv = [
        "create",
        "--from",
        "account-x",
        "--to",
        "account-x-j",
        "--jurisdiction",
        "eu",
        "--write",
    ]
    assert call(ctx, *argv, transport=api) == 1
    assert "not jurisdiction eu" in text(ctx.err)
    # An existing database outside the jurisdiction is refused the same way, and nothing runs.
    ctx2 = make_ctx(tmp_path, run=lambda _a: pytest.fail("must not run"))
    assert call(ctx2, *argv, transport=api) == 2
    assert "already exists outside jurisdiction eu" in text(ctx2.err)


def test_create_exits_1_when_wrangler_fails(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path, run=lambda _a: 7)
    argv = [
        "create",
        "--from",
        "account-x",
        "--to",
        "account-x-j",
        "--jurisdiction",
        "eu",
        "--write",
    ]
    assert call(ctx, *argv, transport=FakeD1Api({})) == 1
    assert "exited 7" in text(ctx.err)


def test_a_failed_api_lookup_exits_1(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    argv = ["create", "--from", "a", "--to", "a-j", "--jurisdiction", "eu"]
    assert call(ctx, *argv, transport=lambda *_a: (403, {"success": False})) == 1
    assert "D1 API" in text(ctx.err)


# --- record and retire --------------------------------------------------------------------------


def retire_root(tmp_path: Path, *, cutover: str, export_stamp: str | None) -> rel.Ctx:
    clock = Clock(cutover)
    ctx = make_ctx(tmp_path, clock)
    assert call(ctx, "record", "--from", "account-old", "--event", "cutover", "--write") == 0
    if export_stamp:
        backups = tmp_path / ".backups" / "shared"
        backups.mkdir(parents=True, exist_ok=True)
        (backups / ("account-old-%s.sql" % export_stamp)).write_text(
            "CREATE TABLE t (x);\n", encoding="utf-8"
        )
    clock.now = "2026-12-20T00:00:00.000Z"
    return ctx


RETIRE = ["retire", "--from", "account-old", "--to", "account-old-j", "--yes-delete", "account-old"]


def test_record_without_write_stamps_nothing(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    assert call(ctx, "record", "--from", "account-old", "--event", "cutover") == 0
    assert not ctx.records.path("account-old").exists()
    assert json.loads(text(ctx.out).split("\n", 1)[1])["events"] == []


def test_retire_refuses_a_name_still_in_a_toml(tmp_path: Path) -> None:
    ctx = retire_root(
        tmp_path, cutover="2026-11-13T10:00:00.000Z", export_stamp="2026-11-14T00-00-00"
    )
    toml = tmp_path / "workers" / "account" / "wrangler.eu.toml"
    toml.parent.mkdir(parents=True)
    toml.write_text(
        'name = "account-eu"\n[[d1_databases]]\ndatabase_name = "account-old"\n', encoding="utf-8"
    )
    ctx.run = lambda _a: pytest.fail("must not delete")
    assert call(ctx, *RETIRE, "--write") == 2
    assert (
        "still named by: workers/account/wrangler.eu.toml (d1_databases database_name)"
        in text(ctx.err)
    )


def test_retire_refuses_a_name_in_regions_json_but_not_a_worker_name(tmp_path: Path) -> None:
    ctx = retire_root(
        tmp_path, cutover="2026-11-13T10:00:00.000Z", export_stamp="2026-11-14T00-00-00"
    )
    regions: dict[str, Any] = {
        "regions": [{"id": "x", "workerName": "account-old", "d1": {"name": "account-old-j"}}]
    }
    (tmp_path / "regions.json").write_text(json.dumps(regions), encoding="utf-8")
    assert call(ctx, *RETIRE) == 0, text(ctx.err)
    regions["regions"][0]["d1"]["name"] = "account-old"
    (tmp_path / "regions.json").write_text(json.dumps(regions), encoding="utf-8")
    assert call(ctx, *RETIRE) == 2
    assert "regions.json (x d1.name)" in text(ctx.err)


def test_retire_refuses_a_protected_database(tmp_path: Path) -> None:
    ctx = retire_root(tmp_path, cutover="2026-11-13T10:00:00.000Z", export_stamp=None)
    argv = ["retire", "--from", "account-eu", "--to", "account-eu-j", "--yes-delete", "account-eu"]
    assert call(ctx, "record", "--from", "account-eu", "--event", "cutover", "--write") == 0
    cast("Clock", ctx.clock).now = "2027-02-01T00:00:00.000Z"
    assert call(ctx, *argv) == 2
    assert "deploy_www.PROTECTED_DATABASES" in text(ctx.err)


def test_retire_refuses_before_30_days(tmp_path: Path) -> None:
    ctx = retire_root(
        tmp_path, cutover="2026-12-01T00:00:00.000Z", export_stamp="2026-12-02T00-00-00"
    )
    assert call(ctx, *RETIRE, "--write") == 2
    assert "19 day(s) ago; retire waits 30 days" in text(ctx.err)


def test_retire_refuses_without_a_cutover_or_the_exact_name(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path)
    assert call(ctx, *RETIRE) == 2
    assert "has no cutover" in text(ctx.err)
    assert call(ctx, *RETIRE[:-1], "account-old-j") == 2
    assert "must repeat the database name exactly" in text(ctx.err)


def test_retire_refuses_without_a_final_export_taken_after_the_cutover(tmp_path: Path) -> None:
    ctx = retire_root(
        tmp_path, cutover="2026-11-13T10:00:00.000Z", export_stamp="2026-11-01T00-00-00"
    )
    assert call(ctx, *RETIRE) == 2
    assert "no backup_d1 export of account-old taken after" in text(ctx.err)


def test_retire_deletes_only_with_write(tmp_path: Path) -> None:
    ctx = retire_root(
        tmp_path, cutover="2026-11-13T10:00:00.000Z", export_stamp="2026-11-14T00-00-00"
    )
    ran: list[list[str]] = []

    def record_run(argv: list[str]) -> int:
        ran.append(argv)
        return 0

    ctx.run = record_run
    assert call(ctx, *RETIRE) == 0
    assert ran == []
    assert (
        "dry run, would run: npx --no-install wrangler d1 delete account-old" in text(ctx.out)
    )
    assert call(ctx, *RETIRE, "--write") == 0
    assert ran == [
        ["npx", "--no-install", "wrangler", "d1", "delete", "account-old", "--skip-confirmation"]
    ]
    assert (
        last(ctx, "account-old", "retire")["replaced_by"] == "account-old-j"
    )


def test_the_config_reaches_the_wrangler_export_and_import(monkeypatch, tmp_path: Path) -> None:
    """fb92c369.1: --config rides on the export and the import, not only on the migrations lookup."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(
        rel.clone_d1,
        "export_redacted",
        lambda *_a, **_k: seen.update(export=list(_a[2])),
    )
    monkeypatch.setattr(rel, "run_wrangler", lambda argv: seen.update(argv=argv) or 0)
    d1 = rel.D1Db("account-x-j", dsm.D1Executor(None, {}, "acct", "account-x-j"), "w.toml")
    d1.export_into(str(tmp_path))
    d1.import_file(str(tmp_path / "i.sql"))
    assert seen["export"] == ["--config", "w.toml"]
    assert seen["argv"][seen["argv"].index("--config") : -1] == ["--config", "w.toml"]


def test_no_config_adds_no_config_words(monkeypatch, tmp_path: Path) -> None:
    """Control: an empty config contributes no argument."""
    seen: dict[str, object] = {}
    monkeypatch.setattr(rel, "run_wrangler", lambda argv: seen.update(argv=argv) or 0)
    d1 = rel.D1Db("account-x-j", dsm.D1Executor(None, {}, "acct", "account-x-j"))
    d1.import_file(str(tmp_path / "i.sql"))
    assert "--config" not in seen["argv"]
