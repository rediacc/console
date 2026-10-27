"""Tests for `rediacc_ci.ops.mirror_config_store`.

The planner and the generated SQL run against two sqlite databases built from `private/account/drizzle/*.sql` (M1-M3). The apply path runs end to end against a fake `npx` on PATH that answers `wrangler d1 execute` from those same sqlite files and `wrangler r2 object get|put` from a scratch directory, recording every argv (M4). No Cloudflare credential and no network.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sqlite3
import stat
import typing

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import cf_auth
from rediacc_ci.ops import mirror_config_store as mod

if typing.TYPE_CHECKING:
    import pathlib

ROOT = paths.repo_root()
DRIZZLE = ROOT / "private" / "account" / "drizzle"
NOW = "2026-10-27T10:00:00.000Z"

STORE = "store000-aaaa-4bbb-8ccc-000000000001"
ORG = "org00000-aaaa-4bbb-8ccc-000000000001"
CUST = "cust0000-aaaa-4bbb-8ccc-000000000001"
OWNER = "user0000-aaaa-4bbb-8ccc-00000000000a"
OTHER = "user0000-aaaa-4bbb-8ccc-00000000000b"
EDGE_USER = "edgeuser-aaaa-4bbb-8ccc-00000000000e"
TEAM = "team0000-aaaa-4bbb-8ccc-000000000001"
TEAM_UNUSED = "team0000-aaaa-4bbb-8ccc-000000000002"
SUB = "sub00000-aaaa-4bbb-8ccc-000000000001"
SUB_OLD = "sub00000-aaaa-4bbb-8ccc-000000000002"
ENTRY_TEAM = "entry000-aaaa-4bbb-8ccc-000000000001"
ENTRY_ORG = "entry000-aaaa-4bbb-8ccc-000000000002"
VER_OWNER = "ver00000-aaaa-4bbb-8ccc-000000000001"
VER_OTHER = "ver00000-aaaa-4bbb-8ccc-000000000002"

EMAIL = "operator@example.com"
EMAIL_HASH = hashlib.sha256(EMAIL.encode()).hexdigest()
SECRETS = {
    "server_secret": "SERVER-SECRET-VALUE-zz",
    "sdk_master": "SDK-MASTER-VALUE-zz",
    "encrypted_org_passphrase": "ENC-PASSPHRASE-VALUE-zz",
    "server_recoverable_org_passphrase": "SRV-PASSPHRASE-VALUE-zz",
}
WRAPPED = {"passkey": "WRAPPED-PK-zz", "password": "WRAPPED-PW-zz", "recovery": "WRAPPED-RC-zz"}
BLOBS = {
    "s/%s/%s/cfg-1/v/3-a.enc" % (STORE, TEAM): b"blob-team-v3",
    "s/%s/_default/cfg-2/v/1-b.enc" % STORE: b"blob-org-v1",
    "s/%s/%s/cfg-1/v/2-c.enc" % (STORE, TEAM): b"blob-team-v2",
    "s/%s/_default/cfg-2/v/0-d.enc" % STORE: b"blob-org-v0",
}
KEYS = list(BLOBS)
NEVER_SHOWN = [*SECRETS.values(), *WRAPPED.values(), EMAIL, EMAIL_HASH, "PWHASH-zz"]

SRC = mod.End(
    "eu-stable",
    "stable",
    "eu",
    "wrangler.eu.toml",
    "account-db-eu",
    "rediacc-configs-eu",
    "eu",
    "rediacc-account-eu",
)
DST = mod.End(
    "eu-edge",
    "edge",
    "eu",
    "wrangler.edge-eu.toml",
    "edge-account-db-eu",
    "edge-rediacc-configs-eu",
    "eu",
    "edge-rediacc-account-eu",
)


# ---- sqlite fixtures ---------------------------------------------------------

OPENED: list[sqlite3.Connection] = []


@pytest.fixture(autouse=True)
def _close_connections() -> typing.Iterator[None]:
    yield
    while OPENED:
        OPENED.pop().close()


def connect(path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    OPENED.append(conn)
    return conn


def build_db(path: pathlib.Path) -> sqlite3.Connection:
    conn = connect(path)
    files = sorted(DRIZZLE.glob("*.sql"))
    for f in files:
        conn.executescript(f.read_text(encoding="utf-8").replace("--> statement-breakpoint", ""))
    conn.execute(
        "CREATE TABLE d1_migrations "
        "(id integer PRIMARY KEY AUTOINCREMENT, name text UNIQUE, applied_at text)"
    )
    conn.executemany(
        "INSERT INTO d1_migrations (name, applied_at) VALUES (?, ?)", [(f.name, NOW) for f in files]
    )
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ins(conn: sqlite3.Connection, table: str, **row: object) -> None:
    cols = list(row)
    conn.execute(
        mod.q(
            "INSERT INTO @T@ (@COLS@) VALUES (@MARKS@)",
            t=mod.ident(table),
            cols=", ".join(mod.ident(c) for c in cols),
            marks=", ".join("?" for _ in cols),
        ),
        [row[c] for c in cols],
    )


def user(conn: sqlite3.Connection, uid: str, email: str) -> None:
    ins(
        conn,
        "users",
        id=uid,
        email=email,
        email_hash=hashlib.sha256(email.encode()).hexdigest(),
        password_hash="PWHASH-zz",
        created_at=NOW,
        updated_at=NOW,
    )


def edge_org(conn: sqlite3.Connection, org_id: str, cust: str) -> None:
    ins(
        conn,
        "organizations",
        id=org_id,
        name="edge",
        owner_user_id="edge-owner",
        customer_id=cust,
        created_at=NOW,
        updated_at=NOW,
    )


def seed_stable(conn: sqlite3.Connection, **store_extra: object) -> None:
    user(conn, OWNER, EMAIL)
    user(conn, OTHER, "other@example.com")
    ins(
        conn,
        "organizations",
        id=ORG,
        name="Rediacc Ops",
        owner_user_id=OWNER,
        customer_id=CUST,
        created_at=NOW,
        updated_at=NOW,
    )
    ins(
        conn,
        "subscriptions",
        id=SUB,
        customer_id=CUST,
        type="subscription",
        status="active",
        max_activations=5,
        plan_code="BUSINESS",
        org_id=ORG,
        created_at=NOW,
        updated_at=NOW,
    )
    ins(
        conn,
        "subscriptions",
        id=SUB_OLD,
        customer_id=CUST,
        type="trial",
        status="expired",
        max_activations=1,
        created_at=NOW,
        updated_at=NOW,
    )
    for mid, uid, role in (("om-owner-0001", OWNER, "root"), ("om-other-0001", OTHER, "member")):
        ins(conn, "org_memberships", id=mid, org_id=ORG, user_id=uid, role=role, joined_at=NOW)
    for tid, slug in ((TEAM, "default"), (TEAM_UNUSED, "unused")):
        ins(conn, "teams", id=tid, org_id=ORG, name=slug, slug=slug, created_at=NOW, updated_at=NOW)
    for mid, uid in (("tm-owner-0001", OWNER), ("tm-other-0001", OTHER)):
        ins(
            conn, "team_memberships", id=mid, team_id=TEAM, user_id=uid, role="admin", joined_at=NOW
        )
    store = {
        "id": STORE,
        "org_id": ORG,
        "sdk_window_seconds": 300,
        "require_passkey": 1,
        "cek_generation": 2,
        "created_at": NOW,
        "updated_at": NOW,
        **SECRETS,
    }
    store.update(store_extra)
    ins(conn, "config_stores", **store)
    for uid, n in ((OWNER, "1"), (OTHER, "2")):
        ins(
            conn,
            "config_user_identities",
            id="ident-000" + n,
            config_store_id=STORE,
            user_id=uid,
            x25519_public_key="X25519-PUB-" + n,
            storage_key_id="SK-" + n,
            passkey_credential_id="CRED-" + n,
            passkey_public_key="PKPUB-" + n,
            passkey_counter=7,
            passkey_transports='["internal"]',
            passkey_device_type="multiDevice",
            passkey_backed_up=1,
            created_at=NOW,
        )
    slots = [("slot-owner-" + m, OWNER, m, WRAPPED[m]) for m in ("passkey", "password", "recovery")]
    slots.append(("slot-other-password", OTHER, "password", "WRAPPED-OTHER-zz"))
    for sid, uid, method, wrapped in slots:
        ins(
            conn,
            "config_key_slots",
            id=sid,
            config_store_id=STORE,
            user_id=uid,
            method=method,
            kdf_params='{"salt":"s-%s","iterations":600000}' % method,
            wrapped_cek=wrapped,
            cek_generation=2,
            created_at=NOW,
        )
    for eid, team, cfg, version, key, epoch in (
        (ENTRY_TEAM, TEAM, "cfg-1", 3, KEYS[0], 5901),
        (ENTRY_ORG, None, "cfg-2", 1, KEYS[1], 5902),
    ):
        ins(
            conn,
            "config_entries",
            id=eid,
            config_store_id=STORE,
            team_id=team,
            config_id=cfg,
            version=version,
            last_modified=NOW,
            r2_key=key,
            sdk_epoch=epoch,
            envelope_json='{"envelopeVersion":3,"id":"%s"}' % cfg,
            created_at=NOW,
        )
    for vid, eid, version, key, epoch, by in (
        (VER_OWNER, ENTRY_TEAM, 2, KEYS[2], 5800, OWNER),
        (VER_OTHER, ENTRY_ORG, 0, KEYS[3], 5700, OTHER),
    ):
        ins(
            conn,
            "config_versions",
            id=vid,
            config_entry_id=eid,
            version=version,
            r2_key=key,
            sdk_epoch=epoch,
            created_at=NOW,
            created_by_user_id=by,
        )
    ins(
        conn,
        "config_tokens",
        id="tok-1",
        user_id=OWNER,
        config_store_id=STORE,
        token_hash="TH",
        encrypted_org_passphrase="E",
        expires_at=NOW,
        created_at=NOW,
    )
    conn.commit()


class Sqlite:
    """A `mod.Reader` over one sqlite connection, answering like D1's JSON."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def query_many(self, sql: str) -> list[list[dict]]:
        return [
            [dict(r) for r in self.conn.execute(s).fetchall()] for s in sql.split(";") if s.strip()
        ]

    def query(self, sql: str) -> list[dict]:
        return [r for g in self.query_many(sql) for r in g]


class NoDefault(Sqlite):
    """Reports one column as having no default, the shape sqlite's ALTER TABLE cannot build."""

    def __init__(self, conn: sqlite3.Connection, column: str) -> None:
        super().__init__(conn)
        self.column = column

    def query_many(self, sql: str) -> list[list[dict]]:
        out = super().query_many(sql)
        if "table_info" in sql:
            for group in out:
                for r in group:
                    if r["name"] == self.column:
                        r["dflt_value"] = None
        return out


@pytest.fixture
def dbs(tmp_path: pathlib.Path) -> tuple[sqlite3.Connection, sqlite3.Connection]:
    src = build_db(tmp_path / "account-db-eu.sqlite")
    dst = build_db(tmp_path / "edge-account-db-eu.sqlite")
    seed_stable(src)
    return src, dst


def plan_for(src: sqlite3.Connection, dst: sqlite3.Connection) -> mod.Plan:
    source = mod.read_source(Sqlite(src), STORE, NOW)
    target = mod.read_target(Sqlite(dst), source)
    return mod.build_plan(source, target, SRC, DST, NOW, "evt0000000000001")


def apply_sql(conn: sqlite3.Connection, sql: str) -> None:
    """One transaction, as D1 runs a --file: any failing statement leaves nothing written."""
    try:
        conn.executescript("BEGIN;\n" + sql + "COMMIT;\n")
    except sqlite3.Error:
        conn.rollback()
        raise


def rows(conn: sqlite3.Connection, sql: str, *params: object) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def count(conn: sqlite3.Connection, table: str) -> int:
    return rows(conn, mod.q("SELECT COUNT(*) AS n FROM @T@", t=mod.ident(table)))[0]["n"]


# ---- M1: the planner ---------------------------------------------------------


def test_plan_names_counts_and_prefixes_only(dbs) -> None:
    plan = plan_for(*dbs)
    text = "\n".join(plan.lines)
    for secret in [*NEVER_SHOWN, STORE, ORG, OWNER]:
        assert secret not in text
    assert mod.prefix(STORE) in text
    assert "identity: case A" in text
    assert "slots copied: password 1, recovery 1" in text
    assert (
        "passkey slots 1, other members' slots 1, other members' identities 1, other members 1"
        in text
    )
    assert "config_tokens 1" in text
    assert "require_passkey: 1 on eu-stable, written 0 on eu-edge" in text
    assert "r2: 4 object(s)" in text
    assert sorted(plan.r2_keys) == sorted(KEYS)
    assert [r["id"] for r in plan.rows("subscriptions")] == [SUB]
    assert [r["id"] for r in plan.rows("teams")] == [TEAM]
    assert [r["id"] for r in plan.rows("team_memberships")] == ["tm-owner-0001"]
    assert [r["id"] for r in plan.rows("org_memberships")] == ["om-owner-0001"]
    assert [r["id"] for r in plan.rows("users")] == [OWNER]


def test_list_stores_prints_prefixes_members_methods_and_no_org_name(dbs) -> None:
    (line,) = mod.list_stores(Sqlite(dbs[0]))
    assert line.startswith(mod.prefix(STORE))
    assert STORE not in line
    # A personal org is named after its owner's email, so the name never prints.
    assert "Rediacc Ops" not in line
    assert "@" not in line
    assert "org " in line
    assert "members 2" in line
    assert "slots passkey,password,recovery" in line


# ---- M2: pre-checks, each refusing -------------------------------------------


def test_pending_rotation_refuses(dbs) -> None:
    src, dst = dbs
    ins(
        src,
        "config_cek_rotations",
        id="rot-1",
        config_store_id=STORE,
        initiated_by_user_id=OWNER,
        status="pending",
        snapshot="[]",
        created_at=NOW,
        expires_at=NOW,
    )
    with pytest.raises(mod.RefusedError, match="pending CEK rotation"):
        plan_for(src, dst)


def test_operator_without_a_fresh_password_or_recovery_slot_refuses(dbs) -> None:
    src, dst = dbs
    src.execute(
        "UPDATE config_key_slots SET cek_generation = 1 WHERE user_id = ? AND method != 'passkey'",
        (OWNER,),
    )
    with pytest.raises(mod.RefusedError, match="no password or recovery slot at CEK generation 2"):
        plan_for(src, dst)


def test_missing_or_malformed_store_refuses(dbs) -> None:
    with pytest.raises(mod.RefusedError, match="does not exist"):
        mod.read_source(Sqlite(dbs[0]), "nostore-0000-0000", NOW)
    with pytest.raises(mod.RefusedError, match="full store id"):
        mod.read_source(Sqlite(dbs[0]), "short", NOW)
    with pytest.raises(mod.RefusedError, match="full store id"):
        mod.read_source(Sqlite(dbs[0]), "x' OR '1'='1", NOW)


def _seed_sub(conn: sqlite3.Connection) -> None:
    ins(
        conn,
        "subscriptions",
        id=SUB,
        customer_id="x-cust",
        type="trial",
        status="active",
        max_activations=1,
        created_at=NOW,
        updated_at=NOW,
    )


def _seed_team(conn: sqlite3.Connection) -> None:
    edge_org(conn, "edge-org-0001", "edge-cust-1")
    ins(
        conn,
        "teams",
        id=TEAM,
        org_id="edge-org-0001",
        name="t",
        slug="t",
        created_at=NOW,
        updated_at=NOW,
    )


def _seed_store(conn: sqlite3.Connection) -> None:
    edge_org(conn, "edge-org-0001", "edge-cust-1")
    ins(
        conn,
        "config_stores",
        id=STORE,
        org_id="edge-org-0001",
        sdk_master="m",
        server_secret="s",
        encrypted_org_passphrase="e",
        created_at=NOW,
        updated_at=NOW,
    )


COLLISIONS = [
    ("org id", lambda c: edge_org(c, ORG, "other-cust-1")),
    ("customer id", lambda c: edge_org(c, "edge-org-0001", CUST)),
    ("subscription id", _seed_sub),
    ("team id", _seed_team),
    ("store id", _seed_store),
]


@pytest.mark.parametrize(("label", "seed"), COLLISIONS, ids=[c[0] for c in COLLISIONS])
def test_collision_refuses_with_nothing_written(dbs, label, seed) -> None:
    src, dst = dbs
    seed(dst)
    dst.commit()
    before = {t: count(dst, t) for t in mod.TABLE_ORDER}
    with pytest.raises(mod.RefusedError, match="edge already holds rows.*%s" % label):
        plan_for(src, dst)
    assert {t: count(dst, t) for t in mod.TABLE_ORDER} == before


def test_case_a_user_id_taken_under_another_email_refuses(dbs) -> None:
    src, dst = dbs
    user(dst, OWNER, "someone-else@example.com")
    with pytest.raises(mod.RefusedError, match="under another email"):
        plan_for(src, dst)


def test_server_key_presence_mismatch_refuses() -> None:
    assert "absent on both" in mod.check_server_key(
        {SRC.worker: False, DST.worker: False}, SRC, DST
    )
    assert "set on both" in mod.check_server_key({SRC.worker: True, DST.worker: True}, SRC, DST)
    with pytest.raises(
        mod.RefusedError, match="CONFIG_SERVER_KEY is set on rediacc-account-eu and absent"
    ):
        mod.check_server_key({SRC.worker: True, DST.worker: False}, SRC, DST)
    with pytest.raises(mod.RefusedError, match="unknown"):
        mod.check_server_key({SRC.worker: True}, SRC, DST)


def test_server_key_presence_reads_names_through_the_survey(monkeypatch) -> None:
    def fetch(_method, path, _token, _body=None):
        if "edge-" in path:
            return [{"name": "API_KEY", "type": "secret_text"}]
        return [{"name": "CONFIG_SERVER_KEY", "type": "secret_text"}]

    monkeypatch.setattr(mod.prune, "http_fetch", fetch)
    found = mod.secret_presence("tok", "acct", [SRC.worker, DST.worker])
    assert found == {SRC.worker: True, DST.worker: False}


def test_server_key_presence_refuses_when_the_survey_fails(monkeypatch) -> None:
    def fetch(_method, _path, _token, _body=None):
        raise mod.prune.ApiError("HTTP 403")

    monkeypatch.setattr(mod.prune, "http_fetch", fetch)
    with pytest.raises(mod.RefusedError, match="could not be read"):
        mod.secret_presence("tok", "acct", [SRC.worker, DST.worker])


def test_schema_parity_passes_on_identical_schemas(dbs) -> None:
    (line,) = mod.schema_parity(Sqlite(dbs[0]), Sqlite(dbs[1]))
    assert "all applied on edge" in line


def test_schema_parity_refuses_a_stable_migration_edge_lacks(dbs) -> None:
    src, dst = dbs
    ins(src, "d1_migrations", name="9999_future.sql", applied_at=NOW)
    with pytest.raises(mod.RefusedError, match=r"not applied on edge.*9999_future"):
        mod.schema_parity(Sqlite(src), Sqlite(dst))


def test_schema_parity_refuses_a_stable_column_edge_lacks(dbs) -> None:
    src, dst = dbs
    src.execute("ALTER TABLE config_entries ADD COLUMN future_col text")
    with pytest.raises(mod.RefusedError, match=r"config_entries\.future_col is missing on edge"):
        mod.schema_parity(Sqlite(src), Sqlite(dst))


def test_schema_parity_refuses_an_edge_only_not_null_column_without_default(dbs) -> None:
    src, dst = dbs
    dst.execute("ALTER TABLE config_key_slots ADD COLUMN edge_only text NOT NULL DEFAULT 'x'")
    mod.schema_parity(Sqlite(src), Sqlite(dst))
    with pytest.raises(
        mod.RefusedError,
        match=r"config_key_slots\.edge_only is NOT NULL with no default on edge only",
    ):
        mod.schema_parity(Sqlite(src), NoDefault(dst, "edge_only"))


def test_ends_refuse_a_stable_write_target() -> None:
    src = mod.resolve_end(ROOT, "eu-stable")
    dst = mod.resolve_end(ROOT, "eu-edge")
    assert (src.database, src.bucket, src.jurisdiction) == (
        "account-db-eu",
        "rediacc-configs-eu",
        "eu",
    )
    assert (dst.database, dst.bucket, dst.worker) == (
        "edge-account-db-eu",
        "edge-rediacc-configs-eu",
        "edge-rediacc-account-eu",
    )
    mod.check_ends(ROOT, src, dst)
    with pytest.raises(mod.RefusedError, match="must be an edge end"):
        mod.check_ends(ROOT, src, src)
    with pytest.raises(mod.RefusedError, match="must be a stable end"):
        mod.check_ends(ROOT, dst, dst)
    with pytest.raises(mod.RefusedError, match="one region"):
        mod.check_ends(ROOT, src, mod.resolve_end(ROOT, "us-edge"))
    with pytest.raises(mod.RefusedError, match="stable bucket"):
        mod.check_ends(ROOT, src, dataclasses.replace(dst, bucket="rediacc-configs-us"))
    with pytest.raises(mod.RefusedError, match="stable database"):
        mod.check_ends(ROOT, src, dataclasses.replace(dst, database="account-db-us"))
    with pytest.raises(mod.RefusedError, match="known region"):
        mod.resolve_end(ROOT, "mars-edge")


# ---- M3: case A and case B on two sqlite databases --------------------------

STORE_COLS = (
    "id",
    "org_id",
    "sdk_master",
    "server_secret",
    "encrypted_org_passphrase",
    "server_recoverable_org_passphrase",
    "cek_generation",
    "sdk_window_seconds",
)


def _assert_mirrored(src: sqlite3.Connection, dst: sqlite3.Connection, edge_user: str) -> None:
    store_s = rows(src, "SELECT * FROM config_stores")[0]
    store_d = rows(dst, "SELECT * FROM config_stores")[0]
    for col in STORE_COLS:
        assert store_d[col] == store_s[col], col
    assert store_s["require_passkey"] == 1
    assert store_d["require_passkey"] == 0
    slots_s = {r["id"]: r for r in rows(src, "SELECT * FROM config_key_slots")}
    slots_d = rows(dst, "SELECT * FROM config_key_slots ORDER BY id")
    assert sorted(r["method"] for r in slots_d) == ["password", "recovery"]
    for r in slots_d:
        assert r["user_id"] == edge_user
        for col in ("wrapped_cek", "kdf_params", "cek_generation", "config_store_id"):
            assert r[col] == slots_s[r["id"]][col]
    (ident,) = rows(dst, "SELECT * FROM config_user_identities")
    assert ident["user_id"] == edge_user
    assert ident["x25519_public_key"] == "X25519-PUB-1"
    assert ident["storage_key_id"] == "SK-1"
    for col in (
        "passkey_credential_id",
        "passkey_public_key",
        "passkey_transports",
        "passkey_device_type",
    ):
        assert ident[col] is None, col
    assert ident["passkey_counter"] == 0
    assert ident["passkey_backed_up"] == 0
    entries = "SELECT * FROM config_entries ORDER BY id"
    assert rows(dst, entries) == rows(src, entries)
    vers = {r["id"]: r for r in rows(dst, "SELECT * FROM config_versions")}
    assert vers[VER_OWNER]["created_by_user_id"] == edge_user
    assert vers[VER_OTHER]["created_by_user_id"] is None
    for vid in (VER_OWNER, VER_OTHER):
        src_v = rows(src, "SELECT * FROM config_versions WHERE id = ?", vid)[0]
        src_v.pop("created_by_user_id")
        got = dict(vers[vid])
        got.pop("created_by_user_id")
        assert got == src_v
    assert rows(dst, "SELECT owner_user_id FROM organizations")[0]["owner_user_id"] == edge_user
    assert [r["user_id"] for r in rows(dst, "SELECT user_id FROM org_memberships")] == [edge_user]
    assert [r["user_id"] for r in rows(dst, "SELECT user_id FROM team_memberships")] == [edge_user]
    assert count(dst, "config_tokens") == 0
    assert rows(dst, "SELECT id FROM users WHERE id = ?", OTHER) == []
    (event,) = rows(dst, "SELECT * FROM event_log")
    assert event["type"] == "config.store.mirrored"
    assert STORE not in event["data"]
    assert rows(dst, "PRAGMA foreign_key_check") == []


def test_case_a_copies_the_operator_with_the_same_id(dbs) -> None:
    src, dst = dbs
    plan = plan_for(src, dst)
    assert plan.case == "A"
    sql = mod.plan_sql(plan)
    assert "OR REPLACE" not in sql
    assert "WRAPPED-PK-zz" not in sql
    assert "WRAPPED-OTHER-zz" not in sql
    apply_sql(dst, sql)
    _assert_mirrored(src, dst, OWNER)
    (u,) = rows(dst, "SELECT * FROM users")
    assert u == rows(src, "SELECT * FROM users WHERE id = ?", OWNER)[0]
    mod.verify(plan, Sqlite(dst), set())


def test_case_b_remaps_the_operator_to_the_edge_user(dbs) -> None:
    src, dst = dbs
    user(dst, EDGE_USER, EMAIL)
    dst.commit()
    plan = plan_for(src, dst)
    assert plan.case == "B"
    assert plan.rows("users") == []
    assert any("case B" in line and mod.prefix(EDGE_USER) in line for line in plan.lines)
    sql = mod.plan_sql(plan)
    assert OWNER not in sql
    apply_sql(dst, sql)
    _assert_mirrored(src, dst, EDGE_USER)
    assert [r["id"] for r in rows(dst, "SELECT id FROM users")] == [EDGE_USER]
    mod.verify(plan, Sqlite(dst), set())


def test_require_passkey_off_on_stable_is_kept(tmp_path) -> None:
    src = build_db(tmp_path / "s.sqlite")
    dst = build_db(tmp_path / "d.sqlite")
    seed_stable(src, require_passkey=0)
    plan = plan_for(src, dst)
    assert not plan.require_passkey_reset
    assert not any("require_passkey" in line for line in plan.lines)


def test_a_collision_at_write_time_aborts_with_nothing_written(dbs) -> None:
    src, dst = dbs
    plan = plan_for(src, dst)
    # A row lands on edge between the plan and the write: plain INSERT fails and the batch writes nothing.
    edge_org(dst, "edge-org-0009", "edge-cust-9")
    ins(
        dst,
        "teams",
        id=TEAM,
        org_id="edge-org-0009",
        name="t",
        slug="t",
        created_at=NOW,
        updated_at=NOW,
    )
    dst.commit()
    with pytest.raises(sqlite3.IntegrityError):
        apply_sql(dst, mod.plan_sql(plan))
    assert count(dst, "config_stores") == 0
    assert count(dst, "users") == 0
    assert count(dst, "organizations") == 1


def test_verify_catches_a_differing_row(dbs) -> None:
    src, dst = dbs
    plan = plan_for(src, dst)
    apply_sql(dst, mod.plan_sql(plan))
    dst.execute("UPDATE config_key_slots SET wrapped_cek = 'tampered' WHERE method = 'password'")
    with pytest.raises(mod.RefusedError, match="differs after the write in wrapped_cek"):
        mod.verify(plan, Sqlite(dst), set())


def test_rollback_sql_undoes_the_mirror(dbs) -> None:
    src, dst = dbs
    plan = plan_for(src, dst)
    apply_sql(dst, mod.plan_sql(plan))
    apply_sql(dst, mod.rollback_sql(plan))
    for table in mod.TABLE_ORDER:
        assert count(dst, table) == 0, table


# ---- M4: the apply path against a fake npx -----------------------------------

FAKE_NPX = r"""#!/usr/bin/env python3
import json, os, pathlib, shutil, sqlite3, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps(["npx"] + argv) + "\n")
assert argv[0] == "wrangler"
args = argv[1:]
def opt(name):
    return args[args.index(name) + 1]
dbdir = pathlib.Path(os.environ["FAKE_DB_DIR"])
if args[:2] == ["d1", "time-travel"]:
    if os.environ.get("FAKE_NO_BOOKMARK"):
        sys.exit(1)
    print(json.dumps({"bookmark": "00000001-00000002-00000003-0123456789abcdef"}))
    sys.exit(0)
if args[:2] == ["d1", "execute"]:
    conn = sqlite3.connect(dbdir / (args[2] + ".sqlite"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if "--file" in args:
        if os.environ.get("FAKE_FILE_FAIL"):
            sys.stderr.write("D1_ERROR: simulated\n")
            sys.exit(1)
        try:
            conn.executescript("BEGIN;\n" + open(opt("--file")).read() + "COMMIT;\n")
        except sqlite3.Error as exc:
            conn.rollback()
            sys.stderr.write("D1_ERROR: %s\n" % exc)
            sys.exit(1)
        print(json.dumps([{"success": True, "results": []}]))
        sys.exit(0)
    out = []
    for stmt in [s for s in opt("--command").split(";") if s.strip()]:
        out.append({"success": True, "results": [dict(r) for r in conn.execute(stmt).fetchall()]})
    print(json.dumps(out))
    sys.exit(0)
if args[:2] == ["r2", "object"]:
    verb, path = args[2], args[3]
    bucket, key = path.split("/", 1)
    if "--jurisdiction" in args:
        bucket = opt("--jurisdiction") + "__" + bucket
    obj = pathlib.Path(os.environ["FAKE_R2_DIR"]) / bucket / key
    if verb == "get":
        if not obj.is_file():
            sys.exit(1)
        shutil.copyfile(obj, opt("--file"))
    elif verb == "put":
        obj.parent.mkdir(parents=True, exist_ok=True)
        data = open(opt("--file"), "rb").read()
        if os.environ.get("FAKE_R2_CORRUPT"):
            data += b"!"
        obj.write_bytes(data)
    sys.exit(0)
sys.exit(2)
"""


@pytest.fixture
def fake(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, dbs) -> dict:
    for conn in dbs:
        conn.close()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npx = bin_dir / "npx"
    npx.write_text(FAKE_NPX, encoding="utf-8")
    npx.chmod(npx.stat().st_mode | stat.S_IXUSR)
    r2 = tmp_path / "r2"
    for key, data in BLOBS.items():
        obj = r2 / "eu__rediacc-configs-eu" / key
        obj.parent.mkdir(parents=True, exist_ok=True)
        obj.write_bytes(data)
    log = tmp_path / "calls.jsonl"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_DB_DIR", str(tmp_path))
    monkeypatch.setenv("FAKE_R2_DIR", str(r2))
    monkeypatch.setenv("CF_MANAGEMENT_TOKEN", "cf-token-secret-value")
    for name in ("CF_GLOBAL_API_KEY", "CF_EMAIL", "REDIACC_BWS_PROFILES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        mod, "secret_presence", lambda _t, _a, workers: dict.fromkeys(workers, False)
    )
    return {"log": log, "r2": r2, "dir": tmp_path}


def _calls(log: pathlib.Path) -> list[list]:
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def _db(fake: dict, name: str) -> sqlite3.Connection:
    return connect(fake["dir"] / (name + ".sqlite"))


BASE = ["--from", "eu-stable", "--to", "eu-edge"]


def _apply_argv(fake: dict) -> list[str]:
    return [
        *BASE,
        "--store",
        STORE,
        "--apply",
        "--i-understand-edge-write",
        "--out-dir",
        str(fake["dir"] / "out"),
    ]


def _kind(call: list) -> str:
    if "time-travel" in call:
        return "bookmark"
    if call[2:4] == ["r2", "object"]:
        return "r2-" + call[4]
    if "--file" in call:
        return "file"
    return "read"


def test_dry_run_reads_only(fake, capsys) -> None:
    assert mod.main([*BASE, "--store", STORE]) == 0
    kinds = {_kind(c) for c in _calls(fake["log"])}
    assert kinds == {"read"}
    out = capsys.readouterr()
    text = out.out + out.err
    assert "dry run: nothing written" in text
    for secret in [*NEVER_SHOWN, "cf-token-secret-value"]:
        assert secret not in text
    assert count(_db(fake, "edge-account-db-eu"), "config_stores") == 0


def test_apply_takes_the_bookmark_first_then_r2_then_one_file(fake, capsys) -> None:
    assert mod.main(_apply_argv(fake)) == 0
    calls = _calls(fake["log"])
    kinds = [_kind(c) for c in calls]
    writes = [k for k in kinds if k != "read"]
    assert writes[0] == "bookmark"
    assert kinds.index("bookmark") < kinds.index("r2-put") < kinds.index("file")
    assert kinds.count("file") == 1
    assert kinds.count("r2-put") == len(BLOBS)
    for c in calls:
        if _kind(c) == "r2-put":
            assert c[5].startswith("edge-rediacc-configs-eu/")
            assert c[c.index("--jurisdiction") + 1] == "eu"
            assert "--remote" in c
        if _kind(c) == "file":
            assert c[4] == "edge-account-db-eu"
            assert "--remote" in c
    for key, data in BLOBS.items():
        assert (fake["r2"] / "eu__edge-rediacc-configs-eu" / key).read_bytes() == data
    _assert_mirrored(_db(fake, "account-db-eu"), _db(fake, "edge-account-db-eu"), OWNER)
    out = fake["dir"] / "out"
    assert (out / "rollback.sh").is_file()
    assert not (out / "insert.sql").exists()
    assert (out / "rollback.sql").stat().st_mode & 0o777 == 0o600
    sh = (out / "rollback.sh").read_text(encoding="utf-8")
    assert sh.count("r2 object delete edge-rediacc-configs-eu/") == len(BLOBS)
    assert " rediacc-configs-eu/" not in sh
    text = capsys.readouterr()
    shown = text.out + text.err
    assert (
        "time-travel restore edge-account-db-eu --bookmark=00000001-00000002-00000003-0123456789abcdef"
        in shown
    )
    assert "verified:" in shown
    for secret in [*NEVER_SHOWN, "cf-token-secret-value"]:
        assert secret not in shown


def test_no_bookmark_writes_nothing(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_NO_BOOKMARK", "1")
    assert mod.main(_apply_argv(fake)) == 1
    kinds = {_kind(c) for c in _calls(fake["log"])}
    assert "r2-put" not in kinds
    assert "file" not in kinds


def test_r2_read_back_mismatch_stops_before_d1(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_R2_CORRUPT", "1")
    assert mod.main(_apply_argv(fake)) == 1
    assert "file" not in {_kind(c) for c in _calls(fake["log"])}
    assert count(_db(fake, "edge-account-db-eu"), "config_stores") == 0


def test_bad_arguments_touch_nothing(fake) -> None:
    assert mod.main([*BASE, "--store", STORE, "--apply"]) == 2
    assert (
        mod.main([*BASE, "--store", STORE, "--apply", "--dry-run", "--i-understand-edge-write"])
        == 2
    )
    assert mod.main(BASE) == 2
    assert mod.main(["--from", "eu-edge", "--to", "eu-stable", "--store", STORE]) == 1
    assert _calls(fake["log"]) == []


def test_list_stores_is_read_only(fake, capsys) -> None:
    assert mod.main([*BASE, "--list-stores"]) == 0
    (call,) = _calls(fake["log"])
    assert call[4] == "account-db-eu"
    text = capsys.readouterr()
    assert mod.prefix(STORE) in text.out + text.err
    assert STORE not in text.out + text.err


def test_a_minted_token_is_destroyed_in_finally_when_the_write_fails(fake, monkeypatch) -> None:
    monkeypatch.delenv("CF_MANAGEMENT_TOKEN")
    monkeypatch.setenv("CF_GLOBAL_API_KEY", "gk")
    monkeypatch.setenv("CF_EMAIL", "ops@example.com")
    minted = cf_auth.Auth(token="minted-token-value", created=True)
    seen: dict[str, object] = {}

    def resolve_scoped(purpose, *_args, **_kwargs):
        seen["purpose"] = purpose
        return minted

    monkeypatch.setattr(cf_auth, "resolve_scoped", resolve_scoped)
    monkeypatch.setattr(cf_auth, "await_propagation", lambda _auth: 0.0)
    monkeypatch.setattr(cf_auth, "self_destruct", lambda auth: seen.setdefault("destroyed", auth))
    monkeypatch.setenv("FAKE_FILE_FAIL", "1")
    assert mod.main(_apply_argv(fake)) == 1
    assert seen["purpose"] == "mirror-config-store"
    assert seen["destroyed"] is minted
    assert "file" in {_kind(c) for c in _calls(fake["log"])}


@pytest.mark.usefixtures("fake")
def test_a_supplied_token_is_not_destroyed(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(cf_auth, "self_destruct", called.append)
    assert mod.main([*BASE, "--list-stores"]) == 0
    assert called == []


# ---- M5: wiring --------------------------------------------------------------


def test_cf_auth_group_and_secret_supply_consumer_are_wired() -> None:
    assert cf_auth.SCOPED_GROUPS["mirror-config-store"] == (
        "D1 Write",
        "Workers R2 Storage Write",
        "Workers Scripts Read",
    )
    spec = json.loads((ROOT / ".ci" / "config" / "secret-supply.json").read_text(encoding="utf-8"))
    consumer = spec["consumers"]["mirror-config-store"]
    assert consumer["required"] == ["CF_GLOBAL_API_KEY", "CF_EMAIL"]
    assert consumer["optional"] == []
    assert mod.PURPOSE == mod.PROFILE == "mirror-config-store"
    assert "python3 -m rediacc_ci.ops.mirror_config_store --from eu-stable --to eu-edge" in (
        mod.__doc__ or ""
    )


def test_read_source_resolves_the_listed_prefix(dbs) -> None:
    source = mod.read_source(Sqlite(dbs[0]), mod.prefix(STORE), NOW)
    assert source["store"]["id"] == STORE


def test_wrangler_json_error_shows_its_message_not_the_closing_brace() -> None:
    out = '{\n  "error": {\n    "text": "D1_ERROR: no such column: foo",\n    "notes": [{"text": "at offset 7"}]\n  }\n}\n'
    assert mod._wrangler_error(out) == "D1_ERROR: no such column: foo | at offset 7"
    assert mod._wrangler_error("plain failure\n") == "plain failure"


def test_read_source_tolerates_a_source_without_the_newest_tables(dbs) -> None:
    dbs[0].execute("DROP TABLE config_executor_grants")
    dbs[0].commit()
    source = mod.read_source(Sqlite(dbs[0]), STORE, NOW)
    assert source["store"]["id"] == STORE
