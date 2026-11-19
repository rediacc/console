"""rediacc_ci.ops.root_grants (agent/plans/PLAN-root-grants.md box C1).

The reads run against sqlite databases built from `private/account/drizzle/*.sql`, served by a fake `wrangler` on PATH that answers `d1 execute --command` from those files and `d1 time-travel info` with a fixed bookmark, recording every argv. The POST is a fake account route that runs `plan()` over the same sqlite and writes what the route would write, so a verify re-read sees the result. Every phase runs in process under sentinel profile values; no Cloudflare credential, no bws and no network.
"""

from __future__ import annotations

import atexit
import copy
import functools
import json
import os
import pathlib
import shutil
import sqlite3
import stat
import sys
import tempfile
import typing
import uuid

import pytest

from rediacc_ci import paths
from rediacc_ci.ops import root_grants as mod

ROOT = paths.repo_root()
DRIZZLE = ROOT / "private" / "account" / "drizzle"
NOW = "2026-11-17T00:00:00.000Z"
STAMP = "2026-01-01T00:00:00.000Z"

EMAIL = "root-sentinel-7f3a@example.test"
CF_TOKEN = "cf-sentinel-token-91x7c2"
CF_ACCOUNT = "acct-sentinel-00001111"
ROOT_TOKEN = "rdr_SENTINELroottoken0123456789"
SEED = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
BENCH_PW = "bench-pw-sentinel-5566"
MASTER_PW = "master-sentinel-6677"
SENTINELS = (EMAIL, CF_TOKEN, CF_ACCOUNT, ROOT_TOKEN, SEED, BENCH_PW, MASTER_PW)
BOOKMARK = "00000001-00000002-00000003-0123456789abcdef"

ROOT_ID = "a1b2c3d4-0000-4000-8000-000000000001"
PERSONAL_ORG = "b1b2c3d4-0000-4000-8000-000000000002"
NEAR_IDS = {
    "+tag": "c1b2c3d4-0000-4000-8000-000000000003",
    "domain": "c1b2c3d4-0000-4000-8000-000000000004",
}
NEAR_EMAILS = {
    "+tag": "root-sentinel-7f3a+tag@example.test",
    "domain": "root-sentinel-7f3a@other.test",
}

READ_ENV = {
    "CLOUDFLARE_API_TOKEN": CF_TOKEN,
    "CLOUDFLARE_ACCOUNT_ID": CF_ACCOUNT,
    "ROOT_EMAIL": EMAIL,
}
EDGE_ENV = {
    "ROOT_API_TOKEN_EU": ROOT_TOKEN,
    "ROOT_API_TOKEN_US": ROOT_TOKEN,
    "ROOT_API_TOKEN_ASIA": ROOT_TOKEN,
    "ROOT_TOTP_SEED": SEED,
}
BENCH_ENV = {
    "ROOT_EMAIL": EMAIL,
    "BENCH_ROOT_PASSWORD": BENCH_PW,
    "BENCH_ROOT_TOTP_SEED": SEED,
    "BENCH_STORE_MASTER_PASSWORD": MASTER_PW,
}
ENVS = {
    "root-grants": READ_ENV,
    "root-login": EDGE_ENV,
    "bench-login-eu": BENCH_ENV,
    "bench-login-us": BENCH_ENV,
    "bench-login-asia": BENCH_ENV,
}


# ---- the databases ------------------------------------------------------------------------------


@functools.cache
def _template() -> pathlib.Path:
    directory = pathlib.Path(tempfile.mkdtemp(prefix="root-grants-template-"))
    atexit.register(shutil.rmtree, directory, ignore_errors=True)
    path = directory / "schema.sqlite"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA synchronous = OFF")
    for f in sorted(DRIZZLE.glob("*.sql")):
        conn.executescript(f.read_text(encoding="utf-8").replace("--> statement-breakpoint", ""))
    conn.commit()
    conn.close()
    return path


def _connect(path: pathlib.Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA synchronous = OFF")
    conn.row_factory = sqlite3.Row
    return conn


def add_user(
    conn: sqlite3.Connection,
    user_id: str,
    email: str,
    role: str = "customer",
    hashed: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO users (id, email, email_hash, role, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email, hashed or mod.email_hash(email), role, STAMP, STAMP),
    )


def add_org(
    conn: sqlite3.Connection,
    org_id: str,
    owner: str,
    customer: str,
    region: str = "eu",
    name: str = "Personal",
    blocked: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO organizations (id, name, owner_user_id, customer_id, data_region, console_executor_blocked_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (org_id, name, owner, customer, region, blocked, STAMP, STAMP),
    )


def add_sub(conn: sqlite3.Connection, sub_id: str, customer: str, plan: str, status: str) -> None:
    conn.execute(
        "INSERT INTO subscriptions (id, customer_id, type, status, max_activations, plan_code, created_at, updated_at) VALUES (?, ?, 'subscription', ?, 1, ?, ?, ?)",
        (sub_id, customer, status, plan, STAMP, STAMP),
    )


def add_store(conn: sqlite3.Connection, org_id: str) -> None:
    conn.execute(
        "INSERT INTO config_stores (id, org_id, sdk_master, server_secret, encrypted_org_passphrase, server_recoverable_org_passphrase, created_at, updated_at) VALUES (?, ?, 'm', 's', 'e', 'r', ?, ?)",
        ("store-" + org_id[:8], org_id, STAMP, STAMP),
    )


def add_partner(
    conn: sqlite3.Connection,
    user_id: str,
    tier: str = "registered",
    status: str = "active",
    role: str = "admin",
    region: str = "us",
    profile: bool = True,
    member: bool = True,
) -> str:
    partner = mod.partner_org_id(user_id)
    add_org(conn, partner, user_id, "cust-partner", region, "Rediacc")
    if profile:
        conn.execute(
            "INSERT INTO partner_profiles (id, org_id, status, tier, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("pp-" + partner[:8], partner, status, tier, STAMP, STAMP),
        )
    if member:
        conn.execute(
            "INSERT INTO partner_members (id, org_id, user_id, partner_role, created_at) VALUES (?, ?, ?, ?, ?)",
            ("pm-" + partner[:8], partner, user_id, role, STAMP),
        )
    return partner


def add_near_misses(conn: sqlite3.Connection) -> None:
    """Users one character or one domain away from the root email, each with an org and a COMMUNITY subscription the tool must never touch."""
    for key, user_id in NEAR_IDS.items():
        add_user(conn, user_id, NEAR_EMAILS[key])
        org = "d" + user_id[1:]
        add_org(conn, org, user_id, "cust-near-" + key, "eu")
        add_sub(conn, "sub-near-" + key, "cust-near-" + key, "COMMUNITY", "inactive")


def seed_partial(conn: sqlite3.Connection) -> None:
    """The edge-us state of 2026-11-17: admin missing, the personal org in eu on COMMUNITY inactive, no partner org, no config store."""
    add_user(conn, ROOT_ID, EMAIL)
    add_org(conn, PERSONAL_ORG, ROOT_ID, "cust-root", "eu")
    add_sub(conn, "sub-root-0001", "cust-root", "COMMUNITY", "inactive")
    add_near_misses(conn)


def seed_complete(
    conn: sqlite3.Connection, customer: str = "cust-root", plan: str = "ENTERPRISE"
) -> None:
    add_user(conn, ROOT_ID, EMAIL, "root")
    add_org(conn, PERSONAL_ORG, ROOT_ID, customer, "us")
    add_sub(conn, "sub-root-0001", customer, plan, "active")
    add_store(conn, PERSONAL_ORG)
    add_partner(conn, ROOT_ID, tier="gold")
    add_near_misses(conn)


def snapshot(path: pathlib.Path) -> dict[str, list[str]]:
    """Every row of every table, as the dump lines of each table, sorted."""
    conn = _connect(path)
    try:
        out: dict[str, list[str]] = {}
        for line in conn.iterdump():
            if line.startswith("INSERT INTO "):
                out.setdefault(line.split()[2].strip('"'), []).append(line)
        return {table: sorted(rows) for table, rows in out.items()}
    finally:
        conn.close()


# ---- the fake wrangler and the fake route -------------------------------------------------------

FAKE_WRANGLER = r"""#!/usr/bin/env python3
import json, os, pathlib, sqlite3, sys
args = sys.argv[1:]
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"argv": args, "env": sorted(k for k in os.environ if k.startswith(("CLOUDFLARE", "ROOT", "BENCH")))}) + "\n")
def opt(name):
    return args[args.index(name) + 1]
if args[:3] == ["d1", "time-travel", "info"]:
    if os.environ.get("FAKE_NO_BOOKMARK"):
        sys.stderr.write("Authentication error [code: 10000]\n")
        sys.exit(1)
    print(json.dumps({"bookmark": "00000001-00000002-00000003-0123456789abcdef"}))
    sys.exit(0)
if args[:2] == ["d1", "execute"]:
    db = pathlib.Path(os.environ["FAKE_DB_DIR"]) / (args[2] + ".sqlite")
    if not db.exists():
        print(json.dumps({"error": {"text": "D1_ERROR: no database " + args[2]}}))
        sys.exit(1)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    out = []
    for stmt in [s for s in opt("--command").split(";") if s.strip()]:
        out.append({"success": True, "results": [dict(r) for r in conn.execute(stmt).fetchall()]})
    print(json.dumps(out))
    sys.exit(0)
sys.exit(2)
"""


def calls(log: pathlib.Path) -> list[dict]:
    return [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


class FakeRoute:
    """`POST /admin/root-grants/apply` over one sqlite database: plan() on its rows, then the writes the account services make. `noop` answers without writing."""

    def __init__(self, db: pathlib.Path, log: pathlib.Path, region: str, noop: bool = False):
        self.db, self.log, self.region, self.noop = db, log, region, noop
        self.bodies: list[dict] = []

    def apply(self, body: dict) -> tuple[int, dict]:
        with self.log.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"post": mod.APPLY_ROUTE}) + "\n")
        self.bodies.append(body)
        conn = _connect(self.db)
        try:
            users = [
                dict(r) for r in conn.execute(mod.USER_SQL.replace("@HASH@", mod.email_hash(EMAIL)))
            ]
            users = [u for u in users if u["email"] == EMAIL]
            if not users:
                snap = mod.Snapshot(None)
            else:
                user_id = users[0]["id"]
                partner = mod.partner_org_id(user_id)
                rows = [
                    [
                        dict(r)
                        for r in conn.execute(
                            s.replace("@USER@", user_id).replace("@PARTNER@", partner)
                        )
                    ]
                    for s in mod.GRANTS_SQL
                ]
                snap = mod.Snapshot({"id": user_id, "role": users[0]["role"]}, *rows)
            report = mod.plan(snap, body, self.region, NOW)
            if not self.noop and snap.user is not None:
                self._write(conn, snap, report, body)
            report["applied"] = True
            return 200, report
        finally:
            conn.close()

    def _write(
        self, conn: sqlite3.Connection, snap: mod.Snapshot, report: dict, body: dict
    ) -> None:
        assert snap.user is not None
        user_id = str(snap.user["id"])
        partner = mod.partner_org_id(user_id)
        personal = next(
            (o["id"] for o in snap.orgs if o["id"] != partner and not o["profile_count"]), None
        )
        want = body["partnerOrg"]
        for act in report["actions"]:
            code = act["code"]
            if code == "role.promote":
                conn.execute("UPDATE users SET role = 'root' WHERE id = ?", (user_id,))
            elif code == "org.data_region":
                org = partner if act["subject"]["idPrefix"] == partner[:8] else personal
                conn.execute(
                    "UPDATE organizations SET data_region = ? WHERE id = ?", (act["to"], org)
                )
            elif code == "subscription.raise":
                plan, status = act["to"].split()
                sub = next(
                    s["id"]
                    for s in snap.subscriptions
                    if str(s["id"]).startswith(act["subject"]["idPrefix"])
                )
                conn.execute(
                    "UPDATE subscriptions SET plan_code = ?, status = ? WHERE id = ?",
                    (plan, status, sub),
                )
            elif code == "partner.org_create":
                add_org(
                    conn, partner, user_id, "cust-partner-new", body["dataRegion"], want["name"]
                )
            elif code == "partner.profile_create":
                conn.execute(
                    "INSERT INTO partner_profiles (id, org_id, status, tier, created_at, updated_at) VALUES (?, ?, 'active', ?, ?, ?)",
                    (str(uuid.uuid4()), partner, want["tier"], NOW, NOW),
                )
            elif code == "partner.member_add":
                conn.execute(
                    "INSERT INTO partner_members (id, org_id, user_id, partner_role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), partner, user_id, want["partnerRole"], NOW),
                )
        conn.commit()


class FakeClient:
    def __init__(self, route: FakeRoute):
        self.route = route

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        assert path == mod.APPLY_ROUTE
        return self.route.apply(body)


class FakeBenchApi:
    """The bench account's cookie session: password login with a TOTP challenge, the reauth step-up, then the apply route."""

    def __init__(self, route: FakeRoute):
        self.route = route
        self.seen: list[str] = []

    def post(self, path: str, body: dict | None = None) -> tuple[int, dict]:
        self.seen.append(path)
        if path == "login":
            assert body == {"email": EMAIL, "password": BENCH_PW}
            return 200, {"requiresTwoFactor": True, "challengeToken": "challenge-1"}
        if path in ("2fa/verify", "reauth", "reauth/verify"):
            return 200, {}
        assert path == "/account/api/v1" + mod.APPLY_ROUTE
        assert "reauth/verify" in self.seen, "the apply must follow the step-up"
        assert body is not None
        return self.route.apply(body)


@pytest.fixture
def env(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, typing.Any]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "wrangler"
    stub.write_text(FAKE_WRANGLER, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    # A seeded checkout has a real workers/account install, which `binary` prefers over PATH and would reach Cloudflare.
    monkeypatch.setattr(mod.wrangler, "local_binary", lambda _cwd: None)
    log = tmp_path / "calls.jsonl"
    log.write_text("", encoding="utf-8")
    monkeypatch.setenv(
        "PATH", os.pathsep.join([str(bin_dir), os.path.dirname(sys.executable), os.defpath])
    )
    monkeypatch.setenv("FAKE_LOG", str(log))
    monkeypatch.setenv("FAKE_DB_DIR", str(tmp_path))
    monkeypatch.delenv("FAKE_NO_BOOKMARK", raising=False)
    return {"dir": tmp_path, "log": log}


def make_db(
    env: dict, name: str, seed: typing.Callable[[sqlite3.Connection], None]
) -> pathlib.Path:
    path = env["dir"] / (name + ".sqlite")
    shutil.copyfile(_template(), path)
    conn = _connect(path)
    seed(conn)
    conn.commit()
    conn.close()
    return path


def runner(route: FakeRoute | None = None) -> tuple[mod.Child, mod.Deps]:
    def open_session(target: str, region: str, profile_env: typing.Mapping[str, str]) -> FakeClient:
        assert target == "edge"
        assert profile_env.get("ROOT_API_TOKEN_" + region.upper()) == ROOT_TOKEN
        assert route is not None
        return FakeClient(route)

    def account_api(server: str) -> FakeBenchApi:
        assert route is not None
        assert server.startswith("https://bench-")
        return FakeBenchApi(route)

    deps = mod.Deps(
        open_token_session=open_session,
        account_api=account_api,
        capture=lambda _argv, _env: (0, "reauth-token-1\n"),
        now=lambda: 1_700_000_010.0,
        sleep=lambda _s: None,
    )
    return mod.in_process_child(ENVS, ROOT, deps, now=NOW), deps


# ---- the loader -----------------------------------------------------------------------------------


def _doc() -> dict:
    return json.loads((ROOT / ".ci" / "config" / "root-grants.json").read_text(encoding="utf-8"))


def _regions() -> list[dict]:
    return json.loads((ROOT / "regions.json").read_text(encoding="utf-8"))["regions"]


def test_the_committed_config_loads_six_targets() -> None:
    config = mod.load_config(ROOT)
    assert [t.id for t in config.targets] == [
        "edge-eu",
        "edge-us",
        "edge-asia",
        "bench-eu",
        "bench-us",
        "bench-asia",
    ]
    assert config.targets[1].wrangler_config == "wrangler.us.toml"
    assert config.targets[3].wrangler_config == "wrangler.bench-eu.toml"
    assert config.desired(config.targets[1]) == {
        "role": "root",
        "personalOrg": {"plan": "BUSINESS", "status": "active"},
        "partnerOrg": {
            "name": "Rediacc",
            "tier": "registered",
            "partnerRole": "admin",
            "status": "active",
        },
        "dataRegion": "us",
    }


def _set(doc: dict, dotted: str, value: object) -> dict:
    out = copy.deepcopy(doc)
    node: typing.Any = out
    *parents, last = dotted.split(".")
    for key in parents:
        node = node[int(key)] if key.isdigit() else node[key]
    node[last] = value
    return out


REFUSALS = [
    ("targets.0.kind", "stable", "kind"),
    ("targets.0.kind", "enterprise", "kind"),
    ("targets.0.config", "enterprise.acme.toml", "config"),
    ("targets.0.region", "mars", "region"),
    ("targets.0.data_region", "us", "data_region"),
    ("personal_org.plan", "FREE", "plan"),
    ("partner_org.tier", "diamond", "tier"),
    ("partner_org.partner_role", "sales", "partner_role"),
]


@pytest.mark.parametrize(("key", "value", "named"), REFUSALS)
def test_every_loader_refusal_exits_2_naming_the_key(key: str, value: object, named: str) -> None:
    with pytest.raises(mod.RefusedError) as caught:
        mod.parse_config(_set(_doc(), key, value), _regions())
    assert caught.value.rc == 2
    assert named in str(caught.value)


def test_a_bench_region_that_is_not_deployable_is_refused() -> None:
    regions = copy.deepcopy(_regions())
    next(r for r in regions if r["id"] == "asia")["bench"]["deployable"] = False
    with pytest.raises(mod.RefusedError) as caught:
        mod.parse_config(_doc(), regions)
    assert caught.value.rc == 2
    assert "targets[5].region" in str(caught.value)
    assert "deployable" in str(caught.value)


def test_a_refused_config_file_exits_2_before_any_child(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "root-grants.json"
    bad.write_text(json.dumps(_set(_doc(), "targets.0.kind", "stable")), encoding="utf-8")

    def child(*_a: object) -> tuple[int, str]:
        raise AssertionError("no child may run on a refused config")

    assert mod.run([], ROOT, child, bad) == 2
    assert "kind" in capsys.readouterr().err


def test_an_unknown_target_id_is_refused() -> None:
    with pytest.raises(mod.RefusedError):
        mod.select_targets(mod.load_config(ROOT), "stable-eu")


# ---- the planner over the drizzle schema --------------------------------------------------------


def test_an_absent_user_prints_absent_skipped_with_rc_0(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    make_db(env, "account-us", add_near_misses)
    child, _ = runner()
    assert mod.run(["--target", "edge-us"], ROOT, child) == 0
    assert "edge-us user absent, skipped" in capsys.readouterr().out


def test_a_near_miss_of_another_case_is_not_the_root_user(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    """The stored email differs only by case, so its hash matches; the exact comparison sign-in makes still refuses it."""

    def seed(conn: sqlite3.Connection) -> None:
        add_user(conn, NEAR_IDS["+tag"], EMAIL.upper(), hashed=mod.email_hash(EMAIL))

    make_db(env, "account-us", seed)
    child, _ = runner()
    assert mod.run(["--target", "edge-us"], ROOT, child) == 0
    captured = capsys.readouterr()
    assert "user absent, skipped" in captured.out
    assert "stored email differs" in captured.err


def test_a_truly_absent_user_prints_no_email_mismatch_note(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    make_db(env, "account-us", add_near_misses)
    child, _ = runner()
    assert mod.run(["--target", "edge-us"], ROOT, child) == 0
    assert "stored email differs" not in capsys.readouterr().err


def test_partial_grants_dry_run_lists_the_actions_and_writes_nothing(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(env, "account-us", seed_partial)
    before = snapshot(db)
    route = FakeRoute(db, env["log"], "us")
    child, _ = runner(route)
    assert mod.run(["--target", "edge-us"], ROOT, child) == 1
    out = capsys.readouterr().out
    assert "edge-us user=%s actions=6 skipped=0 operator=1" % ROOT_ID[:8] in out
    partner = mod.partner_org_id(ROOT_ID)
    for line in (
        "action role.promote user %s customer -> root" % ROOT_ID[:8],
        "action org.data_region org %s eu -> us" % PERSONAL_ORG[:8],
        "action subscription.raise subscription sub-root COMMUNITY inactive -> BUSINESS active",
        "action partner.org_create partner_org %s (none) -> Rediacc" % partner[:8],
        "action partner.profile_create partner_profile %s (none) -> registered" % partner[:8],
        "action partner.member_add partner_member %s (none) -> admin" % partner[:8],
        "AMBER operator: config_store.missing edge-us",
        "remedy: PYTHONPATH=.ci python3 -m rediacc_ci.ops.root_grants --apply --target edge-us",
    ):
        assert line in out, line
    assert snapshot(db) == before
    assert route.bodies == []
    logged = calls(env["log"])
    assert logged
    assert all(c["argv"][:2] == ["d1", "execute"] for c in logged)
    for c in logged:
        for statement in c["argv"][c["argv"].index("--command") + 1].split(";"):
            assert statement.strip().upper().startswith("SELECT"), statement
        assert "ROOT_EMAIL" not in c["env"], "wrangler never receives the root email"


def near_rows(snap: dict[str, list[str]]) -> dict[str, list[str]]:
    """The rows of each table that carry a near-miss user's id, org id or customer id, for tables holding any."""
    marks = (*NEAR_IDS.values(), *("d" + i[1:] for i in NEAR_IDS.values()), "near-")
    out = {t: [r for r in rows if any(m in r for m in marks)] for t, rows in snap.items()}
    return {t: rows for t, rows in out.items() if rows}


def test_apply_bookmarks_before_the_post_then_a_second_run_has_zero_actions(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(env, "account-us", seed_partial)
    near_before = near_rows(snapshot(db))
    assert set(near_before) >= {"users", "organizations", "subscriptions"}
    route = FakeRoute(db, env["log"], "us")
    child, _ = runner(route)
    assert mod.run(["--target", "edge-us", "--apply"], ROOT, child) == 0
    out = capsys.readouterr().out
    assert "BOOKMARK account-us %s" % BOOKMARK in out
    assert "edge-us applied user=%s actions=6" % ROOT_ID[:8] in out
    assert "edge-us verify user=%s actions=0 skipped=0 operator=1" % ROOT_ID[:8] in out
    order = [
        (
            "bookmark"
            if c.get("argv", [""])[:2] == ["d1", "time-travel"]
            else "post"
            if "post" in c
            else "read"
        )
        for c in calls(env["log"])
    ]
    assert order.index("bookmark") < order.index("post")
    assert order.count("post") == 1
    assert order.count("bookmark") == 1
    assert route.bodies == [
        mod.load_config(ROOT).desired(mod.select_targets(mod.load_config(ROOT), "edge-us")[0])
    ]
    near_after = near_rows(snapshot(db))
    assert near_after == near_before, "a near-miss user's rows changed"

    settled = snapshot(db)
    assert mod.run(["--target", "edge-us"], ROOT, child) == 0
    again = capsys.readouterr().out
    assert "actions=0" in again
    assert "AMBER operator: config_store.missing edge-us" in again
    assert snapshot(db) == settled


def test_a_failed_bookmark_exits_2_and_posts_nothing(
    env: dict, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(env, "account-us", seed_partial)
    before = snapshot(db)
    route = FakeRoute(db, env["log"], "us")
    child, _ = runner(route)
    monkeypatch.setenv("FAKE_NO_BOOKMARK", "1")
    assert mod.run(["--target", "edge-us", "--apply"], ROOT, child) == 2
    assert "NO D1 BOOKMARK for account-us" in capsys.readouterr().out
    assert route.bodies == []
    assert snapshot(db) == before


def test_verify_exits_1_when_actions_remain_after_the_apply(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(env, "account-us", seed_partial)
    route = FakeRoute(db, env["log"], "us", noop=True)
    child, _ = runner(route)
    assert mod.run(["--target", "edge-us", "--apply"], ROOT, child) == 1
    assert "edge-us: 6 action(s) remain after the apply" in capsys.readouterr().out


def test_a_complete_target_takes_no_bookmark_and_no_post(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(env, "account-us", seed_complete)
    route = FakeRoute(db, env["log"], "us")
    child, _ = runner(route)
    assert mod.run(["--target", "edge-us", "--apply"], ROOT, child) == 0
    out = capsys.readouterr().out
    assert "actions=0 skipped=0 operator=0" in out
    assert "BOOKMARK" not in out
    assert route.bodies == []
    assert not any(c.get("argv", [""])[:2] == ["d1", "time-travel"] for c in calls(env["log"]))


def test_a_billing_managed_subscription_is_red_and_never_written(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(
        env, "account-us", lambda c: seed_complete(c, customer="cus_stripe1", plan="COMMUNITY")
    )
    before = snapshot(db)
    route = FakeRoute(db, env["log"], "us")
    child, _ = runner(route)
    assert mod.run(["--target", "edge-us", "--apply"], ROOT, child) == 1
    assert "RED subscription.billing_managed" in capsys.readouterr().out
    assert route.bodies == []
    assert snapshot(db) == before


def test_two_personal_orgs_are_ambiguous_and_red(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    def seed(conn: sqlite3.Connection) -> None:
        seed_complete(conn)
        add_org(conn, "e1b2c3d4-0000-4000-8000-000000000009", ROOT_ID, "cust-second", "us")

    make_db(env, "account-us", seed)
    child, _ = runner()
    assert mod.run(["--target", "edge-us"], ROOT, child) == 1
    assert (
        "RED personal_org.ambiguous: owns 2 non-partner orgs: b1b2c3d4, e1b2c3d4; nothing written"
        in capsys.readouterr().out
    )


def test_a_lower_tier_and_suspended_profile_are_raised_and_a_higher_one_kept() -> None:
    desired = mod.load_config(ROOT).desired(mod.select_targets(mod.load_config(ROOT), "edge-us")[0])
    partner = mod.partner_org_id(ROOT_ID)
    orgs = [{"id": partner, "data_region": "us", "profile_count": 1}]
    low = mod.plan(
        mod.Snapshot(
            {"id": ROOT_ID, "role": "root"},
            orgs,
            (),
            [{"org_id": partner, "status": "suspended", "tier": "gold"}],
            [{"org_id": partner, "user_id": ROOT_ID, "partner_role": "sales"}],
        ),
        dict(desired, partnerOrg=dict(desired["partnerOrg"], tier="platinum")),
        "us",
        NOW,
    )
    assert [a["code"] for a in low["actions"]] == [
        "partner.profile_activate",
        "partner.tier_raise",
        "partner.member_role",
    ]
    kept = mod.plan(
        mod.Snapshot(
            {"id": ROOT_ID, "role": "root"},
            orgs,
            (),
            [{"org_id": partner, "status": "active", "tier": "gold"}],
            [{"org_id": partner, "user_id": ROOT_ID, "partner_role": "admin"}],
        ),
        desired,
        "us",
        NOW,
    )
    assert [a["code"] for a in kept["actions"]] == []
    assert [s["code"] for s in kept["skipped"]] == ["personal_org.absent"]


def test_the_partner_id_is_uuid5_of_the_namespace_and_the_user_id() -> None:
    assert str(mod.ROOT_GRANTS_NS) == "62ddf7eb-801c-4b6f-b9a1-17b4dba38b0c"
    assert mod.partner_org_id(ROOT_ID) == str(
        uuid.uuid5(mod.ROOT_GRANTS_NS, "root-grants/partner/" + ROOT_ID)
    )
    assert mod.partner_org_id(ROOT_ID) != mod.partner_org_id(NEAR_IDS["+tag"])
    # The account side's check vector (private/account/src/types/root-grants.ts).
    assert (
        mod.partner_org_id("11111111-2222-4333-8444-555555555555")
        == "3c37d261-cf52-592c-b236-88c454707001"
    )


def test_an_ambiguous_region_plans_no_action_at_all() -> None:
    desired = mod.load_config(ROOT).desired(mod.select_targets(mod.load_config(ROOT), "edge-us")[0])
    orgs = [
        {"id": PERSONAL_ORG, "data_region": "eu", "profile_count": 0},
        {"id": "e1b2c3d4-0000-4000-8000-000000000009", "data_region": "eu", "profile_count": 0},
    ]
    report = mod.plan(mod.Snapshot({"id": ROOT_ID, "role": "customer"}, orgs), desired, "us", NOW)
    assert report["actions"] == []
    assert [s["code"] for s in report["skipped"]] == ["personal_org.ambiguous"]


def test_an_expired_primary_is_raised_and_ranked_by_status_type_newest_id() -> None:
    desired = mod.load_config(ROOT).desired(mod.select_targets(mod.load_config(ROOT), "edge-us")[0])
    orgs = [{"id": PERSONAL_ORG, "customer_id": "c1", "data_region": "us", "store_count": 1}]
    partner = mod.partner_org_id(ROOT_ID)
    complete = (
        [{"id": partner, "data_region": "us", "profile_count": 1}],
        [{"org_id": partner, "status": "active", "tier": "registered"}],
        [{"org_id": partner, "user_id": ROOT_ID, "partner_role": "admin"}],
    )

    def sub(sub_id: str, plan: str, status: str, created: str, expires: str | None = None) -> dict:
        return {
            "id": sub_id,
            "customer_id": "c1",
            "plan_code": plan,
            "status": status,
            "type": "subscription",
            "created_at": created,
            "expires_at": expires,
        }

    def actions(subs: list[dict]) -> list[dict]:
        snap = mod.Snapshot(
            {"id": ROOT_ID, "role": "root"},
            orgs + complete[0],
            subs,
            complete[1],
            complete[2],
        )
        return mod.plan(snap, desired, "us", NOW)["actions"]

    # Active at the floor but past expires_at: raised (expires_at cleared by the route), plan kept.
    past = actions([sub("s-past", "ENTERPRISE", "active", STAMP, "2026-01-02T00:00:00.000Z")])
    assert [(a["code"], a["from"], a["to"]) for a in past] == [
        ("subscription.raise", "ENTERPRISE active", "ENTERPRISE active")
    ]
    assert actions([sub("s-ok", "BUSINESS", "active", STAMP, "2027-01-01T00:00:00.000Z")]) == []
    # An expired row ranks after an inactive one; newest wins a tie, then the lower id.
    ranked = actions(
        [
            sub("s-exp", "ENTERPRISE", "expired", "2026-06-01T00:00:00.000Z"),
            sub("s-old", "COMMUNITY", "inactive", "2026-01-01T00:00:00.000Z"),
            sub("s-new", "PROFESSIONAL", "inactive", "2026-05-01T00:00:00.000Z"),
        ]
    )
    assert [(a["subject"]["idPrefix"], a["to"]) for a in ranked] == [("s-new", "BUSINESS active")]
    assert actions([sub("s-exp", "COMMUNITY", "expired", STAMP)])[0]["to"] == "BUSINESS active"


# ---- the bench POST ------------------------------------------------------------------------------


def test_a_bench_apply_signs_in_steps_up_and_posts(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(env, "account-bench", seed_partial)
    route = FakeRoute(db, env["log"], "eu")
    child, _ = runner(route)
    assert mod.run(["--target", "bench-eu", "--apply"], ROOT, child) == 0
    out = capsys.readouterr().out
    assert "BOOKMARK account-bench %s" % BOOKMARK in out
    assert "bench-eu verify user=%s actions=0" % ROOT_ID[:8] in out


def test_a_missing_edge_token_exits_2_naming_the_mint_page() -> None:
    target = mod.select_targets(mod.load_config(ROOT), "edge-us")[0]
    with pytest.raises(mod.RefusedError) as caught:
        mod.post_edge(target, {}, {"ROOT_TOTP_SEED": SEED}, mod.Deps())
    assert caught.value.rc == 2
    us_domain = {
        r["id"]: r["domain"]
        for r in json.loads((ROOT / "regions.json").read_text(encoding="utf-8"))["regions"]
    }["us"]
    assert us_domain + "/account/admin/root-tokens" in str(caught.value)
    assert "ROOT_API_TOKEN_US" in str(caught.value)


def test_a_missing_bench_seed_exits_2_naming_login_bench() -> None:
    target = mod.select_targets(mod.load_config(ROOT), "bench-us")[0]
    with pytest.raises(mod.RefusedError) as caught:
        mod.post_bench(target, {}, {"ROOT_EMAIL": EMAIL}, mod.Deps())
    assert caught.value.rc == 2
    assert "npm run login:bench -- --region us" in str(caught.value)


# ---- the sentinels -------------------------------------------------------------------------------


def test_no_sentinel_reaches_output_argv_or_a_child_environment(
    env: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    db = make_db(env, "account-us", seed_partial)
    route = FakeRoute(db, env["log"], "us")
    child, _ = runner(route)
    assert mod.run(["--target", "edge-us", "--apply"], ROOT, child) == 0
    assert mod.run(["--target", "edge-us", "--json"], ROOT, child) == 0
    captured = capsys.readouterr()
    logged = env["log"].read_text(encoding="utf-8")
    for value in SENTINELS:
        assert value not in captured.out, value
        assert value not in captured.err, value
        assert value not in logged, value
    assert ROOT_ID not in captured.out, "a full user id was printed"

    bound = {**READ_ENV, **EDGE_ENV, **BENCH_ENV, "REDIACC_BWS_PROFILES": "root-grants"}
    scrubbed = mod.scrubbed_env(ROOT, {**bound, "PATH": "/usr/bin"})
    assert not set(bound) & set(scrubbed)
    assert scrubbed["PYTHONPATH"].startswith(str(ROOT / ".ci"))
    for phase in mod.PHASES:
        argv = mod.child_argv("root-grants", phase, ["edge-us"])
        assert not any(v in " ".join(argv) for v in SENTINELS)
        assert argv[argv.index("--profile") + 1] == "root-grants"


def test_a_phase_document_masks_a_secret_the_server_echoes(env: dict) -> None:
    db = make_db(env, "account-bench", seed_partial)

    class Echo(FakeRoute):
        def apply(self, body: dict) -> tuple[int, dict]:
            status, report = super().apply(body)
            report["skipped"].append({"code": "echo", "reason": "for %s" % EMAIL})
            return status, report

    child, _ = runner(Echo(db, env["log"], "eu"))
    rc, out = child("bench-login-eu", "post", ["bench-eu"])
    assert rc == 0
    assert EMAIL not in out
    assert "for <withheld>" in out
