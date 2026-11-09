"""enterprise.control_db: the regional control databases created and migrated through wrangler, driven by a fake wrangler over in-memory sqlite so nothing reaches Cloudflare."""

from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest

from rediacc_ci.core import wrangler
from rediacc_ci.enterprise import control_db, registry


class FakeWrangler:
    """`wrangler d1 list|create|execute` over in-memory sqlite. Records every argv and cwd."""

    def __init__(self, existing: dict[str, str] | None = None, down: frozenset[str] = frozenset()):
        self.dbs: dict[str, sqlite3.Connection] = {}
        self.uuids: dict[str, str] = dict(existing or {})
        for name in self.uuids:
            self.dbs[name] = self._conn()
        self.down = down
        self.calls: list[list[str]] = []
        self.cwds: list[object] = []

    @staticmethod
    def _conn() -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn

    def __call__(self, argv, *, cwd=None):
        self.calls.append(list(argv))
        self.cwds.append(cwd)
        assert argv[: len(wrangler.ARGV)] == wrangler.ARGV, argv
        rest = argv[len(wrangler.ARGV) :]
        if rest[:2] == ["d1", "list"]:
            body = [{"uuid": u, "name": n} for n, u in self.uuids.items()]
            return control_db.Completed(0, "wrangler banner\n" + json.dumps(body), "")
        if rest[:2] == ["d1", "create"]:
            name = rest[2]
            self.uuids[name] = "0000000%d-0000-4000-8000-000000000000" % len(self.uuids)
            self.dbs[name] = self._conn()
            return control_db.Completed(0, "created %s" % name, "")
        if rest[:2] == ["d1", "execute"]:
            name = rest[2]
            if name in self.down:
                return control_db.Completed(1, "", "authentication error")
            conn = self.dbs[name]
            if "--file" in rest:
                conn.executescript(
                    pathlib.Path(rest[rest.index("--file") + 1]).read_text(encoding="utf-8")
                )
                return control_db.Completed(0, json.dumps([{"results": [], "success": True}]), "")
            sql = rest[rest.index("--command") + 1]
            try:
                rows = [dict(r) for r in conn.execute(sql).fetchall()]
            except sqlite3.Error as exc:
                return control_db.Completed(1, "", "SQLITE_ERROR: %s" % exc)
            conn.commit()
            return control_db.Completed(0, json.dumps([{"results": rows, "success": True}]), "")
        raise AssertionError("unexpected wrangler call: %r" % argv)


def test_bind_inlines_each_placeholder_as_a_literal():
    sql = control_db.bind("SELECT ? , '?' , ?, ?, ?", ["o'neil", None, 3, True])
    assert sql == "SELECT 'o''neil' , '?' , NULL, 3, 1"


def test_bind_refuses_a_count_mismatch():
    with pytest.raises(control_db.ControlDbError, match="2 placeholder"):
        control_db.bind("SELECT ?, ?", ["one"])


def test_bind_refuses_an_unsupported_value_type():
    with pytest.raises(control_db.ControlDbError, match="cannot bind"):
        control_db.bind("SELECT ?", [object()])


def test_parse_json_skips_a_banner():
    assert control_db.parse_json("wrangler 4\n---\n[1, 2]") == [1, 2]


def test_parse_json_refuses_no_document():
    with pytest.raises(control_db.ControlDbError, match="no JSON"):
        control_db.parse_json("nothing here")


def test_location_comes_from_regions_json():
    assert control_db.location("eu") == "eeur"
    assert control_db.location("us") == "enam"
    with pytest.raises(control_db.ControlDbError, match="no region"):
        control_db.location("mars")


def test_ensure_creates_migrates_and_reports_for_bench_eu():
    fake = FakeWrangler()
    result = control_db.ensure("eu", bench=True, runner=fake)
    assert result.database == "control-bench-eu"
    assert result.created
    assert result.migrated
    assert [*wrangler.ARGV, "d1", "create", "control-bench-eu", "--location", "eeur"] in fake.calls
    tables = {
        r["name"]
        for r in fake.dbs["control-bench-eu"].execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"companies", "scope", "onboarding", "audit", "rollout"} <= tables
    # Every call runs from a neutral directory, never a worker directory with a config.
    assert all(cwd is not None and "workers" not in str(cwd) for cwd in fake.cwds)


def test_ensure_again_changes_nothing():
    fake = FakeWrangler()
    control_db.ensure("us", bench=False, runner=fake)
    fake.calls.clear()
    again = control_db.ensure("us", bench=False, runner=fake)
    assert not again.created
    assert not again.migrated
    assert not any("create" in c for c in fake.calls)
    assert not any("--file" in c for c in fake.calls)


def test_ensure_all_covers_every_region_of_the_environment():
    fake = FakeWrangler()
    out = control_db.ensure_all(bench=True, runner=fake)
    assert [r.database for r in out] == ["control-bench-eu", "control-bench-us"]
    prod = control_db.ensure_all(bench=False, runner=FakeWrangler())
    assert [r.database for r in prod] == ["control-%s" % r for r in registry.region_ids()]


def test_a_failed_create_is_named_without_its_output():
    def runner(argv, *, cwd=None):
        del cwd
        if "list" in argv:
            return control_db.Completed(0, "[]", "")
        return control_db.Completed(1, "", "token secret-ish text")

    with pytest.raises(control_db.ControlDbError) as err:
        control_db.ensure_database("control-eu", "eu", runner=runner)
    assert "control-eu" in str(err.value)
    assert "secret-ish" not in str(err.value)


def test_a_create_that_lists_nothing_afterwards_is_refused():
    def runner(argv, *, cwd=None):
        del cwd
        if "list" in argv:
            return control_db.Completed(0, "[]", "")
        return control_db.Completed(0, "ok", "")

    with pytest.raises(control_db.ControlDbError, match="not listed"):
        control_db.ensure_database("control-eu", "eu", runner=runner)


def test_query_returns_rows_and_the_transport_feeds_the_registry():
    fake = FakeWrangler()
    for region in ("eu", "us"):
        control_db.ensure(region, bench=True, runner=fake)
    query = control_db.transport(fake)
    query(
        "control-bench-us",
        "INSERT INTO companies (id, name, region, state, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        ["c0123456789abcdef", "acme", "us", "active", "t", "t"],
    )
    reg = registry.Registry(query, bench=True)
    row = reg.find("acme")
    assert row is not None
    assert row["region"] == "us"
    assert reg.name_free("globex")


def test_an_unreachable_database_raises_and_the_registry_names_it():
    fake = FakeWrangler()
    control_db.ensure_all(bench=True, runner=fake)
    fake.down = frozenset({"control-bench-us"})
    reg = registry.Registry(control_db.transport(fake), bench=True)
    with pytest.raises(registry.RegistryUnreachableError) as err:
        reg.name_free("acme")
    assert err.value.regions == ["us"]


def test_a_failed_statement_is_a_control_db_error():
    fake = FakeWrangler({"control-eu": "u"})
    with pytest.raises(control_db.ControlDbError, match="control-eu"):
        control_db.query("control-eu", "SELECT * FROM missing", [], runner=fake)


def test_main_ensure_bench_region(capsys):
    fake = FakeWrangler()
    assert control_db.main(["ensure", "--bench", "--region", "eu"], runner=fake) == 0
    out = capsys.readouterr().out
    assert "control-bench-eu: created, migrated" in out


def test_main_usage_is_rc_2():
    assert control_db.main(["bogus"], runner=FakeWrangler()) == 2


def test_main_refuses_a_region_outside_bench():
    assert control_db.main(["ensure", "--bench", "--region", "asia"], runner=FakeWrangler()) == 2
