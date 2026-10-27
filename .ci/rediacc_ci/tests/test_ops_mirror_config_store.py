"""Tests for `rediacc_ci.ops.mirror_config_store`.

The planner and the generated SQL run against two sqlite databases built from `private/account/drizzle/*.sql` (M1-M3). The apply path runs end to end against a fake `npx` on PATH that answers `wrangler d1 execute` from those same sqlite files and `wrangler r2 object get|put` from a scratch directory, recording every argv (M4). No Cloudflare credential and no network.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shlex
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
    assert "  org %s  " % mod.prefix(ORG) in line
    assert ORG not in line
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


CONFLICT = "edge holds identity rows that conflict with this copy: "
COLLISIONS = [
    (
        "org id, other customer",
        lambda c: edge_org(c, ORG, "other-cust-1"),
        CONFLICT + r"organizations row org00000 differs in owner_user_id",
    ),
    (
        "customer id under another org id",
        lambda c: edge_org(c, "edge-org-0001", CUST),
        CONFLICT + r"organizations \(customer_id\) is held by another edge row",
    ),
    (
        "subscription id, other org",
        _seed_sub,
        CONFLICT + r"subscriptions row sub00000 differs in org_id",
    ),
    ("team id, other org", _seed_team, CONFLICT + r"teams row team0000 differs in org_id, slug"),
    ("store id", _seed_store, r"edge already holds rows this copy would write: store id"),
]
VALUES_NEVER_SHOWN = ("other-cust-1", "x-cust", "edge-org-0001", "edge-owner", EMAIL_HASH)


@pytest.mark.parametrize(
    ("seed", "message"), [c[1:] for c in COLLISIONS], ids=[c[0] for c in COLLISIONS]
)
def test_collision_refuses_with_nothing_written(dbs, seed, message) -> None:
    src, dst = dbs
    seed(dst)
    dst.commit()
    before = {t: count(dst, t) for t in mod.TABLE_ORDER}
    with pytest.raises(mod.RefusedError, match=message) as caught:
        plan_for(src, dst)
    for value in VALUES_NEVER_SHOWN:
        assert value not in str(caught.value)
    assert {t: count(dst, t) for t in mod.TABLE_ORDER} == before


def test_case_a_user_id_taken_under_another_email_refuses(dbs) -> None:
    src, dst = dbs
    user(dst, OWNER, "someone-else@example.com")
    with pytest.raises(mod.RefusedError, match="under another email"):
        plan_for(src, dst)


LEGACY_ROW = "SRV-PASSPHRASE-VALUE-zz"
EDGE_KID = "abcdef12"
EDGE_KEY_ENV = "ACCOUNT_CONFIG_SERVER_KEY_EU_EDGE"
NEW = {"ACCOUNT_CONFIG_SERVER_KEY"}


def _no_kid() -> tuple[str, str | None]:
    raise AssertionError("the edge kid must not be computed here")


def _edge(kid: str | None):
    return lambda: (EDGE_KEY_ENV, kid)


def _check(src_names: set[str], dst_names: set[str], value: object, kid=_no_kid) -> str:
    return mod.check_server_key(
        {SRC.worker: src_names, DST.worker: dst_names}, SRC, DST, value, kid
    )


def test_server_key_presence_mismatch_refuses() -> None:
    assert "absent on both" in _check(set(), set(), LEGACY_ROW)
    assert "set on both" in _check({"CONFIG_SERVER_KEY"}, {"CONFIG_SERVER_KEY"}, LEGACY_ROW)
    with pytest.raises(
        mod.RefusedError, match="CONFIG_SERVER_KEY is set on rediacc-account-eu and absent"
    ):
        _check({"CONFIG_SERVER_KEY"}, set(), LEGACY_ROW)
    with pytest.raises(mod.RefusedError, match="unknown"):
        mod.check_server_key({SRC.worker: set()}, SRC, DST, LEGACY_ROW, _no_kid)


def test_new_key_on_one_worker_only_refuses() -> None:
    with pytest.raises(
        mod.RefusedError, match="ACCOUNT_CONFIG_SERVER_KEY is absent on rediacc-account-eu and set"
    ):
        _check(set(), NEW, LEGACY_ROW)


def test_untagged_row_refuses_once_both_workers_hold_the_key() -> None:
    with pytest.raises(
        mod.RefusedError,
        match=r"untagged: run PYTHONPATH=\.ci python3 -m rediacc_ci\.ops\.rewrap_config_server_key "
        r"--target stable --region eu --apply --verify first",
    ):
        _check(NEW, NEW, LEGACY_ROW)


def test_untagged_row_passes_while_both_workers_lack_the_key() -> None:
    assert "built-in fallback key" in _check(set(), set(), LEGACY_ROW)


def test_tagged_row_without_the_key_on_either_worker_refuses() -> None:
    with pytest.raises(mod.RefusedError, match="neither Worker holds"):
        _check(set(), set(), "csk1.%s.Zm9v" % EDGE_KID)


def test_a_row_not_sealed_under_the_edge_key_refuses() -> None:
    """Each channel holds its own key, so a row sealed under the stable key (any kid but edge's) cannot open on edge."""
    with pytest.raises(
        mod.RefusedError,
        match="kid 99999999, not the edge key's kid abcdef12: it would not open on edge-rediacc-account-eu",
    ):
        _check(NEW, NEW, "csk1.99999999.Zm9v", _edge(EDGE_KID))


def test_a_row_sealed_under_the_edge_key_passes() -> None:
    line = _check(NEW, NEW, "csk1.%s.Zm9v" % EDGE_KID, _edge(EDGE_KID))
    assert "sealed under the edge key (kid abcdef12)" in line


def test_tagged_row_without_the_edge_key_in_the_environment_names_the_variable_read() -> None:
    with pytest.raises(
        mod.RefusedError, match="edge key is not in the environment.*" + EDGE_KEY_ENV
    ):
        _check(NEW, NEW, "csk1.%s.Zm9v" % EDGE_KID, _edge(None))


def test_store_without_a_passphrase_needs_no_kid() -> None:
    assert "no server-recoverable passphrase" in _check(NEW, NEW, None)


def test_key_kid_comes_from_the_rewrap_helper(monkeypatch) -> None:
    seen = {}

    def helper(_root, key, mode, payload, _secrets):
        seen.update(key=key, mode=mode, payload=payload)
        return {"kid": EDGE_KID}

    monkeypatch.setattr(mod.rewrap, "run_helper", helper)
    monkeypatch.setenv(EDGE_KEY_ENV, "edge-key-value")
    assert mod.key_kid(paths.repo_root(), DST) == (EDGE_KEY_ENV, EDGE_KID)
    assert seen == {"key": "edge-key-value", "mode": "kid", "payload": None}
    monkeypatch.delenv(EDGE_KEY_ENV)
    assert mod.key_kid(paths.repo_root(), DST) == (EDGE_KEY_ENV, None)


def test_key_kid_names_the_variable_from_the_region_secret_suffix(tmp_path, monkeypatch) -> None:
    """The name comes from regions.json secretSuffix, not from the upper-cased region id."""
    (tmp_path / "regions.json").write_text(
        json.dumps({"regions": [{"id": "eu", "secretSuffix": "EUR"}]}), encoding="utf-8"
    )
    monkeypatch.delenv("ACCOUNT_CONFIG_SERVER_KEY_EUR_EDGE", raising=False)
    assert mod.key_kid(tmp_path, DST) == ("ACCOUNT_CONFIG_SERVER_KEY_EUR_EDGE", None)


def test_secret_names_reads_the_listing(monkeypatch) -> None:
    def fetch(_method, path, _token, _body=None):
        if "edge-" in path:
            return [{"name": "API_KEY", "type": "secret_text"}]
        return [{"name": "CONFIG_SERVER_KEY", "type": "secret_text"}]

    monkeypatch.setattr(mod.prune, "http_fetch", fetch)
    found = mod.secret_names("tok", "acct", [SRC.worker, DST.worker])
    assert found == {SRC.worker: {"CONFIG_SERVER_KEY"}, DST.worker: {"API_KEY"}}


def test_secret_names_refuses_when_the_listing_fails(monkeypatch) -> None:
    def fetch(_method, _path, _token, _body=None):
        raise mod.prune.ApiError("HTTP 403")

    monkeypatch.setattr(mod.prune, "http_fetch", fetch)
    with pytest.raises(mod.RefusedError, match="could not be read"):
        mod.secret_names("tok", "acct", [SRC.worker, DST.worker])


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


# ---- reuse on match, refuse on conflict (the identity tables) ---------------

CLONE_ORDER = (
    ("users", "id = ?", OWNER),
    ("organizations", "id = ?", ORG),
    ("subscriptions", "id = ?", SUB),
    ("org_memberships", "id = ?", "om-owner-0001"),
    ("teams", "id = ?", TEAM),
    ("team_memberships", "id = ?", "tm-owner-0001"),
)


def clone_identity(src: sqlite3.Connection, dst: sqlite3.Connection, tables: set[str]) -> None:
    """Copy the operator's identity rows of `tables` from stable to edge under the same ids, as an edge D1 once cloned from stable holds them."""
    for table, where, value in CLONE_ORDER:
        if table in tables:
            (row,) = rows(src, mod.q("SELECT * FROM @T@ WHERE ", t=mod.ident(table)) + where, value)
            ins(dst, table, **row)
    dst.commit()


ALL_IDENTITY = {t for t, _, _ in CLONE_ORDER}


def test_identity_rows_matching_on_edge_are_reused_not_written(dbs) -> None:
    src, dst = dbs
    clone_identity(src, dst, ALL_IDENTITY)
    before = {
        t: rows(dst, mod.q("SELECT * FROM @T@ ORDER BY id", t=mod.ident(t))) for t in ALL_IDENTITY
    }
    plan = plan_for(src, dst)
    assert plan.case == "B"
    assert plan.edge_user_id == OWNER
    for table in ALL_IDENTITY:
        assert plan.rows(table) == [], table
    assert sorted(plan.reused) == sorted(
        [("users", OWNER), ("organizations", ORG), ("subscriptions", SUB),
         ("org_memberships", "om-owner-0001"), ("teams", TEAM), ("team_memberships", "tm-owner-0001")]
    )  # fmt: skip
    text = "\n".join(plan.lines)
    assert (
        "reused on edge (never updated): users 1, organizations 1, subscriptions 1, "
        "org_memberships 1, teams 1, team_memberships 1" in text
    )
    sql = mod.plan_sql(plan)
    for table in ALL_IDENTITY:
        assert "INSERT INTO %s " % mod.ident(table) not in sql
    apply_sql(dst, sql)
    after = {
        t: rows(dst, mod.q("SELECT * FROM @T@ ORDER BY id", t=mod.ident(t))) for t in ALL_IDENTITY
    }
    assert after == before
    assert count(dst, "config_stores") == 1
    assert rows(dst, "PRAGMA foreign_key_check") == []
    mod.verify(plan, Sqlite(dst), set())


MISMATCHES = [
    (
        "organizations",
        "owner_user_id",
        "UPDATE organizations SET owner_user_id = 'someone-else-0001'",
    ),
    ("subscriptions", "org_id", "UPDATE subscriptions SET org_id = 'someone-else-0001'"),
    ("org_memberships", "user_id", "UPDATE org_memberships SET user_id = 'someone-else-0001'"),
    ("teams", "slug", "UPDATE teams SET slug = 'renamed-slug'"),
    ("team_memberships", "user_id", "UPDATE team_memberships SET user_id = 'someone-else-0001'"),
]


@pytest.mark.parametrize(
    ("table", "column", "doctor"), MISMATCHES, ids=[m[0] + "." + m[1] for m in MISMATCHES]
)
def test_a_mismatched_identity_column_refuses_naming_table_and_column(
    dbs, table, column, doctor
) -> None:
    src, dst = dbs
    clone_identity(src, dst, ALL_IDENTITY)
    dst.execute("PRAGMA foreign_keys = OFF")
    dst.execute(doctor)
    dst.commit()
    with pytest.raises(mod.RefusedError) as caught:
        plan_for(src, dst)
    message = str(caught.value)
    assert message.startswith(CONFLICT)
    assert "%s row " % table in message
    assert column in message.split("%s row " % table, 1)[1]
    for value in ("someone-else-0001", "cust-other-0001", "renamed-slug", CUST, OWNER):
        assert value not in message
    assert count(dst, "config_stores") == 0


def test_a_unique_key_held_under_another_id_refuses(dbs) -> None:
    src, dst = dbs
    clone_identity(src, dst, {"users", "organizations"})
    ins(
        dst,
        "org_memberships",
        id="om-edge-other-id",
        org_id=ORG,
        user_id=OWNER,
        role="root",
        joined_at=NOW,
    )
    dst.commit()
    with pytest.raises(
        mod.RefusedError, match=r"org_memberships \(org_id, user_id\) is held by another edge row"
    ):
        plan_for(src, dst)


def test_a_mix_of_reused_and_inserted_identity_rows(dbs) -> None:
    src, dst = dbs
    clone_identity(src, dst, {"users", "organizations", "subscriptions", "org_memberships"})
    plan = plan_for(src, dst)
    assert {t for t, _ in plan.reused} == {
        "users",
        "organizations",
        "subscriptions",
        "org_memberships",
    }
    assert [r["id"] for r in plan.rows("teams")] == [TEAM]
    assert [r["id"] for r in plan.rows("team_memberships")] == ["tm-owner-0001"]
    assert plan.rows("organizations") == []
    text = "\n".join(plan.lines)
    assert "teams 1, team_memberships 1" in text
    assert (
        "reused on edge (never updated): users 1, organizations 1, subscriptions 1, org_memberships 1"
        in text
    )
    apply_sql(dst, mod.plan_sql(plan))
    assert count(dst, "teams") == 1
    assert count(dst, "organizations") == 1
    assert rows(dst, "PRAGMA foreign_key_check") == []
    mod.verify(plan, Sqlite(dst), set())


def test_rollback_deletes_only_inserted_rows_and_keeps_reused_ones(dbs) -> None:
    src, dst = dbs
    clone_identity(src, dst, {"users", "organizations", "subscriptions", "org_memberships"})
    kept = {
        t: rows(dst, mod.q("SELECT * FROM @T@", t=mod.ident(t)))
        for t in ("users", "organizations", "subscriptions", "org_memberships")
    }
    plan = plan_for(src, dst)
    rollback = mod.rollback_sql(plan)
    for table, rid in plan.reused:
        assert "'%s'" % rid not in rollback.replace(
            mod.q("DELETE FROM config_stores WHERE id = @ID@;", id=mod.lit(STORE)), ""
        ), table
    apply_sql(dst, mod.plan_sql(plan))
    apply_sql(dst, rollback)
    for table, before in kept.items():
        assert rows(dst, mod.q("SELECT * FROM @T@", t=mod.ident(table))) == before, table
    for table in ("config_stores", "config_entries", "config_versions", "config_key_slots",
                  "config_user_identities", "teams", "team_memberships", "event_log"):  # fmt: skip
        assert count(dst, table) == 0, table


def test_a_reused_subscription_not_live_on_edge_is_noted(dbs) -> None:
    src, dst = dbs
    clone_identity(src, dst, {"users", "organizations", "subscriptions"})
    dst.execute("UPDATE subscriptions SET status = 'cancelled' WHERE id = ?", (SUB,))
    dst.commit()
    plan = plan_for(src, dst)
    assert ("subscriptions", SUB) in plan.reused
    assert any(
        "subscriptions: reused %s is cancelled on edge (not live)" % mod.prefix(SUB) in line
        for line in plan.lines
    )
    apply_sql(dst, mod.plan_sql(plan))
    assert rows(dst, "SELECT status FROM subscriptions")[0]["status"] == "cancelled"


def test_edge_subscriptions_of_the_customer_without_the_org_refuse(dbs) -> None:
    src, dst = dbs
    ins(dst, "subscriptions", id="sub-edge-stray-0001", customer_id=CUST, type="trial", status="active",
        max_activations=1, created_at=NOW, updated_at=NOW)  # fmt: skip
    dst.commit()
    with pytest.raises(mod.RefusedError, match=r"subscriptions \(customer_id\) has 1 edge row"):
        plan_for(src, dst)


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
            sys.stderr.write(os.environ.get("FAKE_FILE_ERR", "D1_ERROR: simulated") + "\n")
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
        if os.environ.get("FAKE_R2_GET_FAIL"):
            sys.stderr.write(os.environ.get("FAKE_R2_GET_ERR", "Authentication error [code: 10000]") + "\n")
            sys.exit(1)
        if not obj.is_file():
            sys.stderr.write("The specified key does not exist.\n")
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
    monkeypatch.setattr(mod, "secret_names", lambda _t, _a, workers: {w: set() for w in workers})
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
    # The edge-object probe is a read-only get; nothing is put, bookmarked or written.
    assert kinds == {"read", "r2-get"}
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
    writes = [k for k in kinds if k not in ("read", "r2-get")]
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


def test_an_ambiguous_prefix_refuses(dbs) -> None:
    src = dbs[0]
    ins(src, "config_stores", id=mod.prefix(STORE) + "-second-store", org_id=ORG, sdk_master="m",
        server_secret="s", encrypted_org_passphrase="e", created_at=NOW, updated_at=NOW)  # fmt: skip
    with pytest.raises(mod.RefusedError, match="matches 2 stores on the source"):
        mod.read_source(Sqlite(src), mod.prefix(STORE), NOW)
    # The full id still names exactly one store.
    assert mod.read_source(Sqlite(src), STORE, NOW)["store"]["id"] == STORE


@pytest.mark.parametrize("typed", ["store_00", "STORE000"])
def test_a_prefix_is_exact_and_case_sensitive(dbs, typed) -> None:
    # LIKE would read `_` as a wildcard and ignore case, so each of these resolved to STORE before; `%` never passes the id pattern.
    with pytest.raises(mod.RefusedError, match="does not exist on the source"):
        mod.read_source(Sqlite(dbs[0]), typed, NOW)


def test_wrangler_json_error_shows_its_message_not_the_closing_brace() -> None:
    out = '{\n  "error": {\n    "text": "D1_ERROR: no such column: foo",\n    "notes": [{"text": "at offset 7"}]\n  }\n}\n'
    assert mod._wrangler_error(out) == "D1_ERROR: no such column: foo | at offset 7"
    assert mod._wrangler_error("plain failure\n") == "plain failure"


def test_wrangler_json_error_survives_a_banner_holding_a_brace() -> None:
    out = 'Using config {wrangler.edge-eu.toml}\n{\n  "error": {"text": "D1_ERROR: boom"}\n}\n'
    assert mod._wrangler_error(out) == "D1_ERROR: boom"


@pytest.mark.parametrize("notes", ["7", '"a string"', "null", '{"text": "x"}'])
def test_wrangler_json_error_tolerates_notes_that_are_not_a_list(notes) -> None:
    out = '{"error": {"text": "D1_ERROR: boom", "notes": %s}}' % notes
    assert mod._wrangler_error(out) == "D1_ERROR: boom"


def test_a_failed_write_never_shows_a_secret(tmp_path) -> None:
    wrangler = mod.Wrangler(tmp_path, {})
    wrangler.mask = ["SERVER-SECRET-VALUE-zz", "WRAPPED-PW-zz"]
    wrangler.redact = [STORE]
    echoed = 'D1_ERROR: UNIQUE constraint failed: INSERT INTO "config_stores" VALUES (\'SERVER-SECRET-VALUE'
    assert "SERVER-SECRET" not in wrangler._shown(echoed)
    assert "withheld" in wrangler._shown(echoed)
    shown = wrangler._shown('{"error": {"text": "bad slot WRAPPED-PW-zz in store %s"}}' % STORE)
    assert "WRAPPED-PW-zz" not in shown
    assert "<redacted>" in shown
    assert STORE not in shown
    assert mod.prefix(STORE) in shown


def test_secret_values_cover_the_store_the_operator_and_every_slot(dbs) -> None:
    values = set(mod.secret_values(mod.read_source(Sqlite(dbs[0]), STORE, NOW)))
    assert set(SECRETS.values()) <= values
    assert set(WRAPPED.values()) | {"WRAPPED-OTHER-zz"} <= values
    assert {EMAIL, EMAIL_HASH, "PWHASH-zz"} <= values


def test_a_failed_write_echoing_sql_prints_no_secret(fake, monkeypatch, capsys) -> None:
    monkeypatch.setenv("FAKE_FILE_FAIL", "1")
    monkeypatch.setenv(
        "FAKE_FILE_ERR", "D1_ERROR: INSERT INTO config_stores VALUES ('SERVER-SECRET-VALUE-zz')"
    )
    assert mod.main(_apply_argv(fake)) == 1
    text = capsys.readouterr()
    for secret in NEVER_SHOWN:
        assert secret not in text.out + text.err
    assert "withheld" in text.out + text.err


def test_write_private_creates_the_file_with_its_mode_from_the_first_byte(
    tmp_path, monkeypatch
) -> None:
    seen = []
    real_open = os.open

    def spy(path, flags, mode=0o777):
        seen.append(mode)
        return real_open(path, flags, mode)

    monkeypatch.setattr(mod.os, "open", spy)
    old = os.umask(0)
    try:
        mod.write_private(tmp_path / "insert.sql", "secret", 0o600)
    finally:
        os.umask(old)
    assert seen == [0o600]
    assert (tmp_path / "insert.sql").stat().st_mode & 0o777 == 0o600
    (tmp_path / "wide").write_text("x", encoding="utf-8")
    (tmp_path / "wide").chmod(0o644)
    mod.write_private(tmp_path / "wide", "secret", 0o600)
    assert (tmp_path / "wide").stat().st_mode & 0o777 == 0o600


def test_rollback_sh_quotes_and_uses_an_absolute_sql_path(dbs, tmp_path, monkeypatch) -> None:
    plan = plan_for(*dbs)
    monkeypatch.chdir(tmp_path)
    sh = mod.rollback_sh(plan, DST, mod.pathlib.Path("out dir/rollback.sql"))
    (d1_line,) = [ln for ln in sh.splitlines() if " d1 execute " in ln]
    words = shlex.split(d1_line)
    assert words[words.index("--file") + 1] == str(tmp_path / "out dir" / "rollback.sql")


def test_an_object_already_on_edge_refuses_before_any_write(fake, capsys) -> None:
    key = KEYS[0]
    obj = fake["r2"] / "eu__edge-rediacc-configs-eu" / key
    obj.parent.mkdir(parents=True, exist_ok=True)
    obj.write_bytes(b"pre-existing")
    assert mod.main(_apply_argv(fake)) == 1
    kinds = {_kind(c) for c in _calls(fake["log"])}
    assert not kinds & {"bookmark", "r2-put", "file"}
    assert obj.read_bytes() == b"pre-existing"
    text = capsys.readouterr()
    assert "already holds 1 of the 4 object(s)" in text.out + text.err


def test_an_unclassifiable_r2_probe_refuses(fake, monkeypatch) -> None:
    monkeypatch.setenv("FAKE_R2_GET_FAIL", "1")
    assert mod.main([*BASE, "--store", STORE]) == 1
    assert not {_kind(c) for c in _calls(fake["log"])} & {"r2-put", "file"}


def test_a_missing_edge_bucket_refuses_instead_of_reading_as_absent(
    fake, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("FAKE_R2_GET_FAIL", "1")
    monkeypatch.setenv("FAKE_R2_GET_ERR", "The specified bucket does not exist. [code: 10006]")
    assert mod.main([*BASE, "--store", STORE]) == 1
    assert not {_kind(c) for c in _calls(fake["log"])} & {"r2-put", "file"}
    text = capsys.readouterr()
    assert "bucket edge-rediacc-configs-eu does not exist" in text.out + text.err


def test_a_short_secret_value_is_still_masked(dbs) -> None:
    source = mod.read_source(Sqlite(dbs[0]), STORE, NOW)
    source["operator"]["totp_secret"] = "abc"
    values = mod.secret_values(source)
    assert "abc" in values
    assert "" not in values


def test_server_key_line_says_values_cannot_be_compared() -> None:
    line = _check({"CONFIG_SERVER_KEY"}, {"CONFIG_SERVER_KEY"}, LEGACY_ROW)
    assert "cannot be read back" in line


def test_read_source_tolerates_a_source_without_the_newest_tables(dbs) -> None:
    dbs[0].execute("DROP TABLE config_executor_grants")
    dbs[0].commit()
    source = mod.read_source(Sqlite(dbs[0]), STORE, NOW)
    assert source["store"]["id"] == STORE


def test_edge_billing_ids_differ_and_the_identity_rows_are_still_reused(dbs) -> None:
    """Edge bills through a separate Stripe account, so the same org and subscription carry another customer_id there."""
    src, dst = dbs
    clone_identity(src, dst, ALL_IDENTITY)
    dst.execute("PRAGMA foreign_keys = OFF")
    dst.execute("UPDATE organizations SET customer_id = 'cust-edge-0001'")
    dst.execute("UPDATE subscriptions SET customer_id = 'cust-edge-0001'")
    dst.commit()
    plan = plan_for(src, dst)
    assert not plan.rows("organizations")
    assert not plan.rows("subscriptions")


# ---- bench as a target -------------------------------------------------------

BENCH = mod.End(
    "bench",
    "bench",
    "eu",
    "wrangler.bench.toml",
    "account-db-bench",
    "rediacc-configs-bench",
    "",
    "rediacc-account-bench",
    "bench.rediacc.com",
)
BENCH_KEY_ENV = "ACCOUNT_CONFIG_SERVER_KEY_BENCH"
BENCH_KID = "bbbbbbbb"
SRC_RP = dataclasses.replace(SRC, rp_id="eu.rediacc.com")


def test_bench_resolves_from_its_own_wrangler_config() -> None:
    """regions.json does not list bench: its database, bucket, Worker, REGION and RP ID come from wrangler.bench.toml."""
    assert mod.resolve_end(ROOT, "bench") == BENCH
    src = mod.resolve_end(ROOT, "eu-stable")
    assert src == SRC_RP
    mod.check_ends(ROOT, src, BENCH)
    with pytest.raises(mod.RefusedError, match="must be a stable end"):
        mod.check_ends(ROOT, BENCH, BENCH)
    with pytest.raises(mod.RefusedError, match="one region"):
        mod.check_ends(ROOT, mod.resolve_end(ROOT, "us-stable"), BENCH)
    with pytest.raises(mod.RefusedError, match="stable bucket"):
        mod.check_ends(ROOT, src, dataclasses.replace(BENCH, bucket="rediacc-configs-eu"))
    with pytest.raises(mod.RefusedError, match="stable database"):
        mod.check_ends(ROOT, src, dataclasses.replace(BENCH, database="account-db-eu"))
    with pytest.raises(mod.RefusedError, match="names no Worker"):
        mod.check_ends(ROOT, src, dataclasses.replace(BENCH, worker=""))
    with pytest.raises(mod.RefusedError, match="or bench"):
        mod.resolve_end(ROOT, "eu-bench")


def bench_plan(src: sqlite3.Connection, dst: sqlite3.Connection) -> mod.Plan:
    source = mod.read_source(Sqlite(src), STORE, NOW)
    target = mod.read_target(Sqlite(dst), source)
    return mod.build_plan(source, target, SRC_RP, BENCH, NOW, "evt0000000000001")


def test_a_bench_plan_names_bench_and_both_rp_ids(dbs) -> None:
    plan = bench_plan(*dbs)
    text = "\n".join(plan.lines)
    assert "mirror eu-stable -> bench" in text
    assert (
        "require_passkey: 1 on eu-stable, written 0 on bench (bench is password/recovery only)"
        in text
    )
    assert (
        "passkeys do not carry over: WebAuthn RP ID eu.rediacc.com on eu-stable, "
        "bench.rediacc.com on bench" in text
    )
    assert "r2: 4 object(s) rediacc-configs-eu -> rediacc-configs-bench (no jurisdiction)" in text
    assert "customer_id copied from eu-stable as it is" in text
    assert all(r["passkey_credential_id"] is None for r in plan.rows("config_user_identities"))
    assert {r["method"] for r in plan.rows("config_key_slots")} == {"password", "recovery"}
    for secret in [*NEVER_SHOWN, STORE, ORG, OWNER, CUST]:
        assert secret not in text


def test_bench_customer_ids_are_not_compared_and_the_rows_are_reused(dbs) -> None:
    """Bench runs without Stripe, so a reused org may carry a bench customer_id; it is noted, never compared."""
    src, dst = dbs
    clone_identity(src, dst, ALL_IDENTITY)
    dst.execute("PRAGMA foreign_keys = OFF")
    dst.execute("UPDATE organizations SET customer_id = 'cust-bench-0001'")
    dst.execute("UPDATE subscriptions SET customer_id = 'cust-bench-0001'")
    dst.commit()
    plan = bench_plan(src, dst)
    assert not plan.rows("organizations")
    assert not plan.rows("subscriptions")
    text = "\n".join(plan.lines)
    assert "reused on bench (never updated): users 1, organizations 1" in text
    assert "organizations: reused %s carries its own bench customer_id" % mod.prefix(ORG) in text
    assert "customer_id copied from" not in text
    assert "cust-bench-0001" not in text


def test_bench_conflicts_name_bench(dbs) -> None:
    src, dst = dbs
    edge_org(dst, ORG, "other-cust-1")
    with pytest.raises(
        mod.RefusedError,
        match=r"bench holds identity rows that conflict with this copy: organizations row",
    ):
        bench_plan(src, dst)


def test_bench_schema_parity_names_bench(dbs) -> None:
    src, dst = dbs
    assert "all applied on bench" in mod.schema_parity(Sqlite(src), Sqlite(dst), "bench")[0]
    ins(src, "d1_migrations", name="9999_future.sql", applied_at=NOW)
    with pytest.raises(mod.RefusedError, match=r"not applied on bench.*deploy bench first"):
        mod.schema_parity(Sqlite(src), Sqlite(dst), "bench")


def _bench_check(src_names: set[str], dst_names: set[str], value: object, kid=_no_kid) -> str:
    return mod.check_server_key(
        {SRC.worker: src_names, BENCH.worker: dst_names}, SRC, BENCH, value, kid
    )


def _bench_kid() -> tuple[str, str | None]:
    return BENCH_KEY_ENV, BENCH_KID


def test_bench_server_key_checks_read_the_bench_worker_and_key() -> None:
    assert "absent on both" in _bench_check(set(), set(), LEGACY_ROW)
    with pytest.raises(
        mod.RefusedError,
        match=r"ACCOUNT_CONFIG_SERVER_KEY is absent on rediacc-account-eu and set on "
        r"rediacc-account-bench.*decrypt on bench",
    ):
        _bench_check(set(), NEW, LEGACY_ROW)
    line = _bench_check(NEW, NEW, "csk1.%s.Zm9v" % BENCH_KID, _bench_kid)
    assert "sealed under the bench key (kid bbbbbbbb)" in line
    with pytest.raises(
        mod.RefusedError,
        match="not the bench key's kid bbbbbbbb: it would not open on rediacc-account-bench",
    ):
        _bench_check(NEW, NEW, "csk1.99999999.Zm9v", _bench_kid)
    with pytest.raises(
        mod.RefusedError, match="bench key is not in the environment.*" + BENCH_KEY_ENV
    ):
        _bench_check(NEW, NEW, "csk1.%s.Zm9v" % BENCH_KID, lambda: (BENCH_KEY_ENV, None))


def test_key_kid_for_bench_reads_the_bench_variable(monkeypatch) -> None:
    monkeypatch.setattr(mod.rewrap, "run_helper", lambda *_a: {"kid": BENCH_KID})
    monkeypatch.setenv(BENCH_KEY_ENV, "bench-key-value")
    assert mod.key_kid(ROOT, BENCH) == (BENCH_KEY_ENV, BENCH_KID)
    monkeypatch.delenv(BENCH_KEY_ENV)
    assert mod.key_kid(ROOT, BENCH) == (BENCH_KEY_ENV, None)


def _bench_db(fake: dict) -> None:
    build_db(fake["dir"] / "account-db-bench.sqlite").close()


BENCH_BASE = ["--from", "eu-stable", "--to", "bench"]


def test_a_bench_dry_run_reads_only(fake, capsys) -> None:
    _bench_db(fake)
    assert mod.main([*BENCH_BASE, "--store", STORE]) == 0
    assert {_kind(c) for c in _calls(fake["log"])} == {"read", "r2-get"}
    shown = "".join(capsys.readouterr())
    assert "r2: none of the 4 object(s) exists on rediacc-configs-bench yet" in shown
    assert count(_db(fake, "account-db-bench"), "config_stores") == 0


def test_a_bench_apply_writes_bench_without_a_jurisdiction(fake, capsys) -> None:
    _bench_db(fake)
    argv = [*BENCH_BASE, "--store", STORE, "--apply", "--i-understand-edge-write",
            "--out-dir", str(fake["dir"] / "out")]  # fmt: skip
    assert mod.main(argv) == 0
    calls = _calls(fake["log"])
    kinds = [_kind(c) for c in calls]
    assert kinds.index("bookmark") < kinds.index("r2-put") < kinds.index("file")
    for c in calls:
        if _kind(c) == "r2-put":
            assert c[5].startswith("rediacc-configs-bench/")
            assert "--jurisdiction" not in c
            assert c[c.index("--config") + 1] == "wrangler.bench.toml"
        if _kind(c) in ("file", "bookmark"):
            assert "account-db-bench" in c
    for key, data in BLOBS.items():
        assert (fake["r2"] / "rediacc-configs-bench" / key).read_bytes() == data
    _assert_mirrored(_db(fake, "account-db-eu"), _db(fake, "account-db-bench"), OWNER)
    sh = (fake["dir"] / "out" / "rollback.sh").read_text(encoding="utf-8")
    assert sh.count("r2 object delete rediacc-configs-bench/") == len(BLOBS)
    assert "--jurisdiction" not in sh
    assert "--config wrangler.bench.toml" in sh
    shown = "".join(capsys.readouterr())
    assert "bench D1 bookmark taken before any write" in shown
    assert "time-travel restore account-db-bench --bookmark=" in shown
    for secret in [*NEVER_SHOWN, "cf-token-secret-value"]:
        assert secret not in shown


def test_a_bench_apply_without_the_ack_names_the_target(fake, capsys) -> None:
    assert mod.main([*BENCH_BASE, "--store", STORE, "--apply"]) == 2
    assert "--apply writes the bench database and bucket" in "".join(capsys.readouterr())
    assert _calls(fake["log"]) == []
