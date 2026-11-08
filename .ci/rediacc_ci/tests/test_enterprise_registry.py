"""enterprise.registry and the control schema: all regions read, an unreachable one named."""

from __future__ import annotations

import sqlite3

import pytest

from rediacc_ci.enterprise import registry

NOW = "2026-11-08T00:00:00Z"


def _db(rows: list[tuple[str, str, str, str]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(registry.migration_sql())
    for cid, name, region, state in rows:
        conn.execute(
            "INSERT INTO companies (id, name, region, state, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (cid, name, region, state, NOW, NOW),
        )
    return conn


def _transport(dbs: dict[str, sqlite3.Connection], down: frozenset[str] = frozenset()):
    def query(database, sql, params):
        if database in down:
            raise ConnectionError("no route to %s" % database)
        return [dict(r) for r in dbs[database].execute(sql, params).fetchall()]

    return query


def _world(down: frozenset[str] = frozenset()):
    dbs = {
        "control-eu": _db([("c0a1b2c3d4", "acme", "eu", "active")]),
        "control-us": _db(
            [("c1a2b3c4d5", "globex", "us", "active"), ("c2a2b3c4d5", "gone", "us", "removed")]
        ),
        "control-asia": _db([]),
    }
    return registry.Registry(_transport(dbs, down))


def test_schema_has_every_table_and_applies():
    conn = _db([])
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {
        "companies",
        "scope",
        "ring",
        "ring_override",
        "upgrade_window",
        "onboarding",
        "rollout",
        "audit",
    } <= tables


def test_schema_refuses_a_non_opaque_company_id():
    conn = _db([])
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO companies (id, name, region, created_at, updated_at) VALUES ('acme','acme','eu',?,?)",
            (NOW, NOW),
        )


def test_databases_per_region_and_bench():
    assert registry.databases()["eu"] == "control-eu"
    assert set(registry.databases()) >= {"eu", "us", "asia"}
    assert registry.databases(bench=True) == {"eu": "control-bench-eu", "us": "control-bench-us"}


def test_reads_all_regions():
    names = {c["name"]: c["region"] for c in _world().companies()}
    assert names == {"acme": "eu", "globex": "us", "gone": "us"}


def test_name_free_and_taken_across_regions():
    reg = _world()
    assert reg.name_free("newco")
    assert not reg.name_free("acme")
    assert not reg.name_free("globex")
    assert reg.name_free("gone")  # a removed company's name is free


def test_unreachable_region_is_named_and_refuses_name_free():
    reg = _world(down=frozenset({"control-us"}))
    with pytest.raises(registry.RegistryUnreachableError) as err:
        reg.name_free("newco")
    assert err.value.regions == ["us"]
    assert "control-us" in str(err.value) or "us (" in str(err.value)


def test_every_unreachable_region_is_listed():
    reg = _world(down=frozenset({"control-us", "control-asia"}))
    with pytest.raises(registry.RegistryUnreachableError) as err:
        reg.companies()
    assert err.value.regions == ["asia", "us"]
