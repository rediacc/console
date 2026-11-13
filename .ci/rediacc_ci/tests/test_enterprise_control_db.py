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


def test_create_argv_prefers_the_jurisdiction_over_the_location_hint():
    assert control_db.create_argv("c", "eeur")[-2:] == ["--location", "eeur"]
    assert control_db.create_argv("c", "eeur", "eu")[-2:] == ["--jurisdiction", "eu"]
    assert "--location" not in control_db.create_argv("c", "eeur", "eu")


def _jurisdictional_root(tmp_path: pathlib.Path) -> pathlib.Path:
    rows = [
        {"id": "eu", "d1": {"name": "account-eu-j", "location": "eeur", "jurisdiction": "eu"}},
        {"id": "us", "d1": {"name": "account-us", "location": "enam", "jurisdiction": None}},
    ]
    (tmp_path / "regions.json").write_text(json.dumps({"regions": rows}), encoding="utf-8")
    bench = tmp_path.joinpath(*control_db.bench_preflight.BENCH_CONFIG_REL)
    bench.parent.mkdir(parents=True)
    bench.write_text(
        '[[d1_databases]]\nbinding = "DB"\ndatabase_name = "account-bench-j"\n'
        '[[r2_buckets]]\nbinding = "CONFIG_BUCKET"\nbucket_name = "configs-bench"\n'
        'jurisdiction = "eu"\n',
        encoding="utf-8",
    )
    return tmp_path


def test_jurisdiction_comes_from_the_region_row_and_the_bench_toml(tmp_path):
    root = _jurisdictional_root(tmp_path)
    assert control_db.jurisdiction("eu", root=root) == "eu"
    assert control_db.jurisdiction("us", root=root) == ""
    # Bench has no row: the bench toml's jurisdiction applies to both bench control databases.
    assert control_db.jurisdiction("us", bench=True, root=root) == "eu"
    with pytest.raises(control_db.ControlDbError, match="no region"):
        control_db.jurisdiction("mars", root=root)


def test_the_real_tree_creates_under_a_location_hint_until_the_repoint():
    assert control_db.jurisdiction("eu") == ""
    assert control_db.jurisdiction("us", bench=True) == ""


def test_a_jurisdictional_region_creates_its_control_database_with_the_jurisdiction(
    monkeypatch, tmp_path
):
    root = _jurisdictional_root(tmp_path)
    monkeypatch.setattr(control_db.paths, "repo_root", lambda: root)
    fake = FakeWrangler()
    control_db.ensure_database("control-eu", "eu", runner=fake)
    assert [*wrangler.ARGV, "d1", "create", "control-eu", "--jurisdiction", "eu"] in fake.calls
    bench = FakeWrangler()
    control_db.ensure_database("control-bench-us", "us", runner=bench, bench=True)
    assert [
        *wrangler.ARGV,
        "d1",
        "create",
        "control-bench-us",
        "--jurisdiction",
        "eu",
    ] in bench.calls


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


def test_a_failed_create_is_named_with_its_stderr_and_never_its_stdout():
    def runner(argv, *, cwd=None):
        del cwd
        if "list" in argv:
            return control_db.Completed(0, "[]", "")
        return control_db.Completed(1, "stdout-secret-ish", "token rejected")

    with pytest.raises(control_db.ControlDbError) as err:
        control_db.ensure_database("control-eu", "eu", runner=runner)
    assert "control-eu" in str(err.value)
    assert "token rejected" in str(err.value)
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


def _failing(stderr: str, rc: int = 1):
    def run(argv, *, cwd=None):
        del argv, cwd
        return control_db.Completed(rc, "STDOUT-ROW-acme", stderr)

    return run


NO_TOKEN = (
    "\x1b[31m\u2718 ERROR\x1b[0m In a non-interactive environment, it's necessary to set a "
    "CLOUDFLARE_API_TOKEN environment variable"
)


def test_a_failed_list_carries_wrangler_stderr_without_ansi_or_stdout():
    with pytest.raises(control_db.ControlDbError) as err:
        control_db.database_ids(_failing("banner\n\n" + NO_TOKEN + "\n\n"))
    text = str(err.value)
    assert "wrangler d1 list exited 1" in text
    assert "CLOUDFLARE_API_TOKEN environment variable" in text
    assert "\x1b" not in text
    assert "STDOUT-ROW" not in text


def test_every_wrangler_failure_site_carries_the_stderr_tail():
    run = _failing("l1\nl2\nl3\nreason four")
    calls = [
        lambda: control_db.query("control-eu", "SELECT 1", [], runner=run),
        lambda: control_db.apply_migration("control-eu", runner=run),
    ]
    for call in calls:
        with pytest.raises(control_db.ControlDbError, match="reason four") as err:
            call()
        assert "l1" not in str(err.value)


def test_a_failed_query_masks_the_values_it_bound_when_wrangler_echoes_the_sql():
    """D1 can echo the inlined SQL in its error: the bound label never reaches the message (review 51f22f73.2)."""
    run = _failing("near \"WHERE name = 'acme''corp'\": syntax error")
    with pytest.raises(control_db.ControlDbError) as err:
        control_db.query("control-eu", "SELECT 1 WHERE name = ?", ["acme'corp"], runner=run)
    assert "acme" not in str(err.value)
    assert "syntax error" in str(err.value)


def test_a_failed_query_leaves_a_cause_that_quotes_no_bound_value_alone():
    """THE CONTROL: the masking touches only what was bound."""
    run = _failing("no such table: companies")
    with pytest.raises(control_db.ControlDbError, match="no such table: companies"):
        control_db.query("control-eu", "SELECT 1 WHERE name = ?", ["acme"], runner=run)


def test_a_failed_create_carries_the_stderr_tail():
    state = {"n": 0}

    def run(argv, *, cwd=None):
        del cwd
        if argv[len(wrangler.ARGV) : len(wrangler.ARGV) + 2] == ["d1", "list"]:
            return control_db.Completed(0, "[]", "")
        state["n"] += 1
        return control_db.Completed(1, "", "quota exceeded")

    with pytest.raises(control_db.ControlDbError, match="quota exceeded"):
        control_db.ensure_database("control-eu", "eu", runner=run)


def test_a_silent_failure_keeps_the_bare_message():
    with pytest.raises(control_db.ControlDbError) as err:
        control_db.database_ids(_failing(""))
    assert str(err.value) == "wrangler d1 list exited 1"


def test_stderr_tail_is_trimmed():
    assert control_db.stderr_tail("a\n\n  b  \nc\nd") == "b | c | d"
    assert len(control_db.stderr_tail("x" * 900)) == control_db.TAIL_WIDTH


def test_a_missing_token_is_refused_up_front_naming_the_profile(monkeypatch, capsys):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    with pytest.raises(control_db.ControlDbError, match="--profile enterprise"):
        control_db.transport()
    with pytest.raises(control_db.ControlDbError, match="--profile enterprise"):
        control_db.ensure("eu", bench=True)
    assert control_db.main(["ensure", "--bench"]) == 1
    assert "--profile enterprise" in capsys.readouterr().err


def test_a_present_token_passes_the_guard(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    control_db.require_token()
    assert callable(control_db.transport())


def test_the_enterprise_profile_binds_the_token_the_guard_names():
    root = pathlib.Path(__file__).resolve().parents[3]
    spec = json.loads((root / ".ci/config/secret-supply.json").read_text(encoding="utf-8"))
    profile = spec["consumers"][control_db.PROFILE]
    assert control_db.AUTH_ENV in profile["required"]
    assert "CLOUDFLARE_ACCOUNT_ID" in profile["required"]


def test_a_json_mode_error_on_stdout_is_named_and_the_deprecation_notice_dropped():
    body = {
        "error": {
            "text": "A request to the Cloudflare API failed.",
            "notes": [{"text": "no such table: audit [code: 7500]"}],
        }
    }

    def run(argv, *, cwd=None):
        del argv, cwd
        return control_db.Completed(
            1,
            json.dumps(body),
            'Using "CF_EMAIL" environment variable. This is deprecated. Please use "CLOUDFLARE_EMAIL", instead.\n',
        )

    with pytest.raises(control_db.ControlDbError) as err:
        control_db.query("control-eu", "SELECT 1", [], runner=run)
    text = str(err.value)
    assert "no such table: audit" in text
    assert "A request to the Cloudflare API failed." in text
    assert "CF_EMAIL" not in text
