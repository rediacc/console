"""`rediacc_ci.housekeeping.cf_leftovers` against a fake Cloudflare API (no network, no credentials)."""

from __future__ import annotations

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cf_leftovers as cfl

ROOT = paths.repo_root()
TOKEN = "tok-SECRET-123"


def fake_api(scripts, d1, routes, domains=(), calls=None):
    def get(path, token):
        if calls is not None:
            calls.append((path, token))
        base = path.split("?")[0]
        if base.endswith("/workers/scripts"):
            res = [{"id": s} for s in scripts]
        elif base.endswith("/d1/database"):
            res = [{"name": n, "uuid": "u-" + n} for n in d1]
        elif base == "/zones":
            res = [{"id": "z1", "name": "rediacc.com"}]
        elif base.endswith("/workers/routes"):
            res = list(routes)
        elif base.endswith("/workers/domains"):
            res = list(domains)
        else:
            raise cfl.CfError("unexpected " + path)
        return {"success": True, "result": res, "result_info": {"total_pages": 1}}

    return get


CONFIGURED = "rediacc-account-eu"  # workers/account/wrangler.eu.toml
BOUND_DB = "edge-account-db-eu"  # workers/account/wrangler.edge-eu.toml


def run(scripts, d1, routes, domains=()):
    return cfl.find_leftovers(ROOT, "acct", TOKEN, fake_api(scripts, d1, routes, domains))


def kinds(found):
    return {(k, n) for k, n, _ in found}


def test_unknown_script_listed_configured_and_pr_not():
    found = run([CONFIGURED, "pr-12", "stray-worker"], [], [])
    assert kinds(found) == {("script", "stray-worker")}


def test_unbound_bench_and_edge_databases_listed_bound_and_other_not():
    found = run([], [BOUND_DB, "old-bench", "edge-forgotten", "account-db-pr-5"], [])
    assert kinds(found) == {("d1", "old-bench"), ("d1", "edge-forgotten")}


def test_dangling_route_and_scriptless_route_listed():
    routes = [
        {"pattern": "gone.rediacc.com/*", "script": "deleted-worker"},
        {"pattern": "live.rediacc.com/*", "script": CONFIGURED},
        {"pattern": "none.rediacc.com/*"},
    ]
    found = run([CONFIGURED], [], routes)
    assert kinds(found) == {("route", "gone.rediacc.com/*"), ("route", "none.rediacc.com/*")}


def test_dangling_custom_domain_listed():
    found = run([CONFIGURED], [], [], [{"hostname": "x.rediacc.com", "service": "nope"},
                                       {"hostname": "eu.rediacc.com", "service": CONFIGURED}])
    assert kinds(found) == {("domain", "x.rediacc.com")}


def test_main_exits_zero_with_findings_prints_them_and_never_the_token(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    rc = cfl.main([], get=fake_api(["stray-worker"], ["x-bench"], []))
    out = capsys.readouterr()
    assert rc == 0
    assert "LEFTOVER script" in out.out and "stray-worker" in out.out and "x-bench" in out.out
    assert TOKEN not in out.out + out.err


def test_unreadable_listing_is_an_error_not_an_empty_report(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")

    def get(path, token):
        raise cfl.CfError("GET %s: denied" % path)

    assert cfl.main([], get=get) == 1
    assert TOKEN not in capsys.readouterr().err


def test_missing_env_is_an_error(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert cfl.main([], get=fake_api([], [], [])) == 1


def test_only_get_listings_are_requested():
    calls: list = []
    cfl.find_leftovers(ROOT, "acct", TOKEN, fake_api([CONFIGURED], [], [], calls=calls))
    assert calls and all(t == TOKEN for _, t in calls)
    assert all("/workers/scripts" in p or "/d1/database" in p or p.startswith("/zones")
               or "/workers/domains" in p for p, _ in calls)


def test_pagination_follows_total_pages():
    pages = {1: [{"id": "a"}], 2: [{"id": "b"}]}

    def get(path, token):
        n = int(path.split("&page=")[1])
        return {"success": True, "result": pages[n], "result_info": {"total_pages": 2}}

    assert [i["id"] for i in cfl.listing("/x", TOKEN, get)] == ["a", "b"]


def test_configured_reads_env_blocks(tmp_path):
    (tmp_path / "workers" / "w").mkdir(parents=True)
    (tmp_path / "workers" / "w" / "wrangler.toml").write_text(
        'name = "top"\n[env.staging]\nname = "top-staging"\n[[env.staging.d1_databases]]\n'
        'binding = "DB"\ndatabase_name = "stage-bench"\n'
    )
    scripts, dbs = cfl.configured(tmp_path)
    assert scripts == {"top", "top-staging"} and dbs == {"stage-bench"}


def test_no_config_is_an_error(tmp_path):
    with pytest.raises(cfl.CfError):
        cfl.configured(tmp_path)


def test_report_states_how_many_items_were_scanned(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    cfl.main([], get=fake_api([CONFIGURED, "pr-1"], [BOUND_DB], [{"pattern": "p", "script": CONFIGURED}]))
    assert "scanned 2 scripts, 1 d1, 1 routes, 0 domains" in capsys.readouterr().out
