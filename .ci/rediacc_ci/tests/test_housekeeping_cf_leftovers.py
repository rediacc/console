"""`rediacc_ci.housekeeping.cf_leftovers` against a fake Cloudflare API (no network, no credentials)."""

from __future__ import annotations

import email.message
import io
import urllib.error
from urllib.parse import urlsplit

import pytest

from rediacc_ci import paths
from rediacc_ci.housekeeping import cf_leftovers as cfl
from rediacc_ci.well_known import ACCOUNT_DEFAULT_ORIGIN, APEX_DOMAIN, PUBLIC_DATA_BUCKET

ROOT = paths.repo_root()
TOKEN = "tok-SECRET-123"
ACCOUNT_HOST = urlsplit(ACCOUNT_DEFAULT_ORIGIN).hostname


def fake_api(scripts, d1, routes, domains=(), calls=None, extra=None):
    """A read-only fake. `extra` maps a class to its items: `buckets` ((name, jurisdiction) pairs), `queues`, `containers`, `namespaces`, `pages`, and `bindings` (script -> binding list)."""
    extra = extra or {}

    def get(path, token, jurisdiction=None):
        if calls is not None:
            calls.append((path, token))
        base = path.split("?")[0]
        if base.endswith("/settings"):
            script = base.split("/")[-2]
            bindings = (extra.get("bindings") or {}).get(script, [])
            return {"success": True, "result": {"bindings": bindings}}
        if base.endswith("/r2/buckets"):
            jur = jurisdiction or "default"
            res = [{"name": n} for n, j in extra.get("buckets", ()) if j == jur]
            return {"success": True, "result": {"buckets": res}, "result_info": {}}
        if base.endswith("/containers/applications"):
            return {
                "success": True,
                "result": list(extra.get("containers", ())),
                "result_info": {"total_pages": 1},
            }
        if base.endswith("/workers/scripts"):
            res = [{"id": s} for s in scripts]
        elif base.endswith("/d1/database"):
            res = [{"name": n, "uuid": "u-" + n} for n in d1]
        elif base == "/zones":
            res = [{"id": "z1", "name": APEX_DOMAIN}]
        elif base.endswith("/workers/routes"):
            res = list(routes)
        elif base.endswith("/workers/domains"):
            res = list(domains)
        elif base.endswith("/queues"):
            res = list(extra.get("queues", ()))
        elif base.endswith("/durable_objects/namespaces"):
            res = list(extra.get("namespaces", ()))
        elif base.endswith("/pages/projects"):
            res = list(extra.get("pages", ()))
        else:
            raise cfl.CfError("unexpected " + path)
        return {"success": True, "result": res, "result_info": {"total_pages": 1}}

    return get


CONFIGURED = "account-eu"  # workers/account/wrangler.eu.toml
BOUND_DB = "account-bench"  # workers/account/wrangler.bench-eu.toml


def run(scripts, d1, routes, domains=()):
    return cfl.find_leftovers(ROOT, "acct", TOKEN, fake_api(scripts, d1, routes, domains))


def kinds(found):
    return {(k, n) for k, n, _ in found}


def test_unknown_script_listed_configured_not():
    found = run([CONFIGURED, "stray-worker"], [], [])
    assert kinds(found) == {("script", "stray-worker")}


def test_a_legacy_pr_number_preview_worker_is_a_leftover():
    """Previews deploy under their pv- word name only (PLAN-preview-signer D5), and the PR-close cleanup deletes that name alone, so a pr-<n> Worker is a leftover the report must name."""
    found = run([CONFIGURED, "pr-12"], [], [])
    assert kinds(found) == {("script", "pr-12")}


def test_word_named_previews_and_their_signers_are_owned_not_leftovers():
    """PLAN-preview-signer N3: a `pv-<w>-<w>-<w>` preview and its `-signer` belong to the PR-close cleanup and cleanup_versions Phase 5b; a name with one word too few, or a regional signer no config names, is still a leftover."""
    found = run(
        [
            CONFIGURED,
            "pv-able-baker-charlie",
            "pv-able-baker-charlie-signer",
            "pv-able-baker",
            "signer-zz",
        ],
        [],
        [],
    )
    assert kinds(found) == {("script", "pv-able-baker"), ("script", "signer-zz")}


def test_unbound_bench_and_edge_databases_listed_bound_and_other_not():
    found = run([], [BOUND_DB, "old-bench", "edge-forgotten", "account-pr-5"], [])
    assert kinds(found) == {("d1", "old-bench"), ("d1", "edge-forgotten")}


def test_unbound_jurisdictional_bench_databases_are_listed():
    found = run([], ["old-bench-j", "control-bench-eu-j", "account-pr-5"], [])
    assert kinds(found) == {("d1", "old-bench-j"), ("d1", "control-bench-eu-j")}


def test_the_bound_jurisdictional_bench_database_is_not_a_leftover(tmp_path):
    (tmp_path / "workers" / "account").mkdir(parents=True)
    (tmp_path / "workers" / "account" / "wrangler.test.toml").write_text(
        'name = "account-test"\n[[d1_databases]]\nbinding = "DB"\n'
        'database_name = "account-bench-j"\n'
    )
    found = cfl.find_leftovers(
        tmp_path,
        "acct",
        TOKEN,
        fake_api(["account-test"], ["account-bench-j", "stray-bench-j"], []),
    )
    assert kinds(found) == {("d1", "stray-bench-j")}


def test_a_bound_edge_database_is_not_a_leftover(tmp_path):
    """No checked-in config binds an edge-* database any more, so a scratch root binds one: the exclusion for the edge-* pattern is proven apart from the bench one."""
    (tmp_path / "workers" / "account").mkdir(parents=True)
    (tmp_path / "workers" / "account" / "wrangler.test.toml").write_text(
        'name = "account-test"\n[[d1_databases]]\nbinding = "DB"\ndatabase_name = "edge-bound"\n'
    )
    found = cfl.find_leftovers(
        tmp_path, "acct", TOKEN, fake_api(["account-test"], ["edge-bound", "edge-stray"], [])
    )
    assert kinds(found) == {("d1", "edge-stray")}


def test_dangling_route_and_scriptless_route_listed():
    routes = [
        {"pattern": "gone.rediacc.com/*", "script": "deleted-worker"},
        {"pattern": "live.rediacc.com/*", "script": CONFIGURED},
        {"pattern": "none.rediacc.com/*"},
    ]
    found = run([CONFIGURED], [], routes)
    assert kinds(found) == {("route", "gone.rediacc.com/*"), ("route", "none.rediacc.com/*")}


def test_dangling_custom_domain_listed():
    found = run(
        [CONFIGURED],
        [],
        [],
        [
            {"hostname": "x.rediacc.com", "service": "nope"},
            {"hostname": ACCOUNT_HOST, "service": CONFIGURED},
        ],
    )
    assert kinds(found) == {("domain", "x.rediacc.com")}


def test_main_exits_zero_with_findings_prints_them_and_never_the_token(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    rc = cfl.main([], get=fake_api(["stray-worker"], ["x-bench"], []))
    out = capsys.readouterr()
    assert rc == 0
    assert "LEFTOVER script" in out.out
    assert "stray-worker" in out.out
    assert "x-bench" in out.out
    assert TOKEN not in out.out + out.err


def test_unreadable_listing_is_an_error_not_an_empty_report(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")

    def get(path, _token, **_kw):
        raise cfl.CfError("GET %s: denied" % path)

    assert cfl.main([], get=get) == 1
    assert TOKEN not in capsys.readouterr().err


def test_missing_env_is_an_error(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert cfl.main([], get=fake_api([], [], [])) == 1


def test_only_get_listings_are_requested():
    calls: list = []
    cfl.find_leftovers(ROOT, "acct", TOKEN, fake_api([CONFIGURED], [], [], calls=calls))
    assert calls
    assert all(t == TOKEN for _, t in calls)
    assert all(
        "/workers/scripts" in p
        or "/d1/database" in p
        or p.startswith("/zones")
        or "/workers/domains" in p
        or "/r2/buckets" in p
        or "/queues" in p
        or "/containers/applications" in p
        or "/durable_objects/namespaces" in p
        or "/pages/projects" in p
        for p, _ in calls
    )


def test_pagination_follows_total_pages():
    pages = {1: [{"id": "a"}], 2: [{"id": "b"}]}

    def get(path, _token):
        n = int(path.split("&page=")[1])
        return {"success": True, "result": pages[n], "result_info": {"total_pages": 2}}

    assert [i["id"] for i in cfl.listing("/x", TOKEN, get)] == ["a", "b"]


def test_followed_without_result_info_returns_the_items_as_the_whole_listing():
    calls = []

    def get(path, _token):
        calls.append(path)
        return {"success": True, "result": [{"id": "a"}, {"id": "b"}]}

    assert [i["id"] for i in cfl.followed("/c", TOKEN, get)] == ["a", "b"]
    assert calls == ["/c"]


def test_listing_by_page_without_result_info_returns_the_items():
    def get(_path, _token):
        return {"success": True, "result": [{"id": "a"}]}

    assert [i["id"] for i in cfl.listing_by_page("/p", TOKEN, get)] == ["a"]


def test_followed_with_valid_result_info_paginates():
    pages = {1: [{"id": "a"}], 2: [{"id": "b"}], 3: [{"id": "c"}]}

    def get(path, _token):
        n = int(path.split("page=")[1]) if "page=" in path else 1
        return {"success": True, "result": pages[n], "result_info": {"total_pages": 3}}

    assert [i["id"] for i in cfl.followed("/c", TOKEN, get)] == ["a", "b", "c"]


@pytest.mark.parametrize("info", [{"total_pages": "x"}, "bad", {"count": 1, "per_page": 20}])
def test_followed_with_malformed_result_info_raises(info):
    def get(_path, _token):
        return {"success": True, "result": [{"id": "a"}], "result_info": info}

    with pytest.raises(cfl.CfError):
        cfl.followed("/c", TOKEN, get)


def test_configured_reads_env_blocks(tmp_path):
    (tmp_path / "workers" / "w").mkdir(parents=True)
    (tmp_path / "workers" / "w" / "wrangler.toml").write_text(
        'name = "top"\n[env.staging]\nname = "top-staging"\n[[env.staging.d1_databases]]\n'
        'binding = "DB"\ndatabase_name = "stage-bench"\n'
    )
    scripts, dbs = cfl.configured(tmp_path)
    assert scripts == {"top", "top-staging"}
    assert dbs == {"stage-bench"}


def test_no_config_is_an_error(tmp_path):
    with pytest.raises(cfl.CfError):
        cfl.configured(tmp_path)


def test_a_tree_holding_only_a_template_is_no_config(tmp_path):
    (tmp_path / "workers" / "w").mkdir(parents=True)
    (tmp_path / "workers" / "w" / "wrangler.template.toml").write_text('name = "@@NAME@@"\n')
    with pytest.raises(cfl.CfError):
        cfl.configured(tmp_path)


def test_report_states_how_many_items_were_scanned(monkeypatch, capsys):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    cfl.main(
        [], get=fake_api([CONFIGURED, "pr-1"], [BOUND_DB], [{"pattern": "p", "script": CONFIGURED}])
    )
    assert (
        "scanned 2 scripts, 1 d1, 1 routes, 0 domains, 0 buckets, 0 queues, 0 containers, 0 do, 0 pages"
        in capsys.readouterr().out
    )


class _Resp:
    def __init__(self, body: bytes, fail_read: bool = False, status: int = 200):
        self.body, self.fail_read, self.status = body, fail_read, status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self):
        if self.fail_read:
            raise ConnectionResetError("reset")
        return self.body


def _patch_urlopen(monkeypatch, behaviour):
    seen: list = []

    def build(url, headers=None, method="GET", **_kw):
        seen.append((method, url, dict(headers or {})))
        return object()

    monkeypatch.setattr(cfl.https, "build_request", build)
    monkeypatch.setattr(cfl.https, "urlopen", lambda _req, **_kw: behaviour())
    return seen


def test_fetch_is_a_get_with_the_bearer_and_returns_the_body(monkeypatch):
    seen = _patch_urlopen(monkeypatch, lambda: _Resp(b'{"success": true, "result": []}'))
    assert cfl.fetch("/p", TOKEN)["success"] is True
    assert seen == [("GET", cfl.CF_API_BASE + "/p", {"Authorization": "Bearer " + TOKEN})]


def test_fetch_maps_every_unreadable_answer_to_cf_error(monkeypatch):
    """Review ce7bd2c4.2 and .4: a timeout, a reset mid-body, non-JSON and a refusal are CfErrors, never tracebacks."""

    def timed_out():
        raise TimeoutError("slow")

    def http_403():
        raise urllib.error.HTTPError(
            "u",
            403,
            "no",
            email.message.Message(),
            io.BytesIO(b'{"success": false, "errors": [{"code": 9109}]}'),
        )

    cases = {
        "timeout": timed_out,
        "reset": lambda: _Resp(b"", fail_read=True),
        "html": lambda: _Resp(b"<html>"),
        "403": http_403,
        "url": lambda: (_ for _ in ()).throw(urllib.error.URLError("dns")),
    }
    for label, behaviour in cases.items():
        _patch_urlopen(monkeypatch, behaviour)
        with pytest.raises(cfl.CfError):
            cfl.fetch("/p", TOKEN)
        assert label


def test_an_empty_2xx_delete_answer_is_success(monkeypatch):
    """A Worker custom-domain DELETE answers 200 with an empty body (live 2026-11-13: the first cf_retire run stopped on it)."""
    _patch_urlopen(monkeypatch, lambda: _Resp(b""))
    assert cfl.request("DELETE", "/accounts/a/workers/domains/d", TOKEN)["success"] is True


@pytest.mark.parametrize("status", [200, 201, 204, 299])
def test_an_empty_delete_answer_is_success_across_the_2xx_range(monkeypatch, status):
    _patch_urlopen(monkeypatch, lambda: _Resp(b"", status=status))
    assert cfl.request("DELETE", "/accounts/a/workers/domains/d", TOKEN)["success"] is True


@pytest.mark.parametrize("status", [199, 300, 302])
def test_an_empty_delete_answer_outside_2xx_is_not_success(monkeypatch, status):
    """b28631e8.2: the 200 <= status < 300 gate, not just the default 200."""
    _patch_urlopen(monkeypatch, lambda: _Resp(b"", status=status))
    with pytest.raises(cfl.CfError, match="non-JSON"):
        cfl.request("DELETE", "/accounts/a/workers/domains/d", TOKEN)


def test_an_empty_get_answer_is_not_success(monkeypatch):
    _patch_urlopen(monkeypatch, lambda: _Resp(b"", status=200))
    with pytest.raises(cfl.CfError, match="non-JSON"):
        cfl.request("GET", "/p", TOKEN)


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_each_retryable_status_is_retried_then_succeeds(monkeypatch, status):
    """e4e6087d.2: removing any one of RETRY_STATUSES turns its case red."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                "u", status, "x", email.message.Message(), io.BytesIO(b"<html>x</html>")
            )
        return _Resp(b'{"success": true, "result": null}')

    _patch_urlopen(monkeypatch, flaky)
    monkeypatch.setattr(cfl.time, "sleep", lambda _s: None)
    assert cfl.request("GET", "/p", TOKEN)["success"] is True
    assert calls["n"] == 2


def test_control_an_empty_2xx_delete_elsewhere_is_still_a_failure(monkeypatch):
    """Review b28631e8.1: the empty-body rule is the custom-domain path's only."""
    _patch_urlopen(monkeypatch, lambda: _Resp(b""))
    with pytest.raises(cfl.CfError, match="non-JSON"):
        cfl.request("DELETE", "/accounts/a/r2/buckets/b", TOKEN)


def test_control_an_empty_delete_without_a_status_is_not_success(monkeypatch):
    """Review b28631e8.3, 9900887b.2: a response that carries no status is a CfError, not a 2xx and not a crash."""

    class NoStatus:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            return b""

    _patch_urlopen(monkeypatch, NoStatus)
    with pytest.raises(cfl.CfError, match="no HTTP status"):
        cfl.request("DELETE", "/accounts/a/workers/domains/d", TOKEN)


def _http(code: int, body: bytes = b"<html>x</html>"):
    return urllib.error.HTTPError("u", code, "x", email.message.Message(), io.BytesIO(body))


def test_a_persistent_429_raises_after_the_last_attempt(monkeypatch):
    """Review e4e6087d.1: three pauses, four calls, then the error."""
    calls = {"n": 0}

    def throttled():
        calls["n"] += 1
        raise _http(429)

    _patch_urlopen(monkeypatch, throttled)
    monkeypatch.setattr(cfl.time, "sleep", lambda _s: None)
    with pytest.raises(cfl.CfError) as err:
        cfl.request("GET", "/r2/x", TOKEN)
    assert err.value.status == 429
    assert calls["n"] == len(cfl.RETRY_PAUSES_S) + 1


def test_a_persistent_5xx_raises_after_the_last_attempt(monkeypatch):
    calls = {"n": 0}

    def broken():
        calls["n"] += 1
        raise _http(503)

    _patch_urlopen(monkeypatch, broken)
    monkeypatch.setattr(cfl.time, "sleep", lambda _s: None)
    with pytest.raises(cfl.CfError) as err:
        cfl.request("DELETE", "/r2/x", TOKEN)
    assert err.value.status == 503
    assert calls["n"] == len(cfl.RETRY_PAUSES_S) + 1


def test_a_delete_that_404s_after_a_5xx_retry_is_already_deleted(monkeypatch):
    """Review e4e6087d.3: the first attempt may have taken effect before the gateway answered."""
    answers = iter([_http(502), _http(404, b'{"success": false, "errors": []}')])

    def behaviour():
        raise next(answers)

    _patch_urlopen(monkeypatch, behaviour)
    monkeypatch.setattr(cfl.time, "sleep", lambda _s: None)
    assert cfl.request("DELETE", "/r2/x", TOKEN)["success"] is True


def test_control_a_404_is_an_error_without_a_prior_5xx_or_after_a_429_or_on_a_get(monkeypatch):
    for first in (None, 429):
        answers = iter(([_http(first)] if first else []) + [_http(404, b'{"success": false}')])

        def behaviour(answers=answers):
            raise next(answers)

        _patch_urlopen(monkeypatch, behaviour)
        monkeypatch.setattr(cfl.time, "sleep", lambda _s: None)
        with pytest.raises(cfl.CfError):
            cfl.request("DELETE", "/r2/x", TOKEN)
    answers = iter([_http(502), _http(404, b'{"success": false}')])

    def get_behaviour():
        raise next(answers)

    _patch_urlopen(monkeypatch, get_behaviour)
    with pytest.raises(cfl.CfError):
        cfl.request("GET", "/r2/x", TOKEN)


def test_a_429_is_retried_then_succeeds(monkeypatch):
    """Live 2026-11-13: an R2 object DELETE during a 16-wide bucket emptying got a non-JSON throttle answer and stopped the run."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                "u", 429, "slow", email.message.Message(), io.BytesIO(b"<html>rate</html>")
            )
        return _Resp(b'{"success": true, "result": null}')

    _patch_urlopen(monkeypatch, flaky)
    monkeypatch.setattr(cfl.time, "sleep", lambda _s: None)
    assert cfl.request("DELETE", "/r2/x", TOKEN)["success"] is True
    assert calls["n"] == 2


def test_control_a_403_is_not_retried(monkeypatch):
    calls = {"n": 0}

    def refused():
        calls["n"] += 1
        raise urllib.error.HTTPError(
            "u", 403, "no", email.message.Message(), io.BytesIO(b'{"success": false, "errors": []}')
        )

    _patch_urlopen(monkeypatch, refused)
    monkeypatch.setattr(cfl.time, "sleep", lambda _s: None)
    with pytest.raises(cfl.CfError):
        cfl.request("DELETE", "/r2/x", TOKEN)
    assert calls["n"] == 1


def test_control_an_empty_get_answer_is_still_a_cf_error(monkeypatch):
    _patch_urlopen(monkeypatch, lambda: _Resp(b""))
    with pytest.raises(cfl.CfError, match="non-JSON"):
        cfl.fetch("/p", TOKEN)


def test_a_malformed_wrangler_toml_is_a_cf_error_not_a_traceback(tmp_path):
    (tmp_path / "workers" / "x").mkdir(parents=True)
    (tmp_path / "workers" / "x" / "wrangler.toml").write_text("name = ")
    with pytest.raises(cfl.CfError, match="cannot be read"):
        cfl.configured(tmp_path)


def test_zones_are_listed_for_this_account_only():
    calls: list = []
    base = fake_api([CONFIGURED], [], [], calls=calls)

    def get(path, token, jurisdiction=None):
        if path.startswith("/zones?"):
            calls.append((path, token))
            return {
                "success": True,
                "result": [
                    {"id": "z1", "name": "mine", "account": {"id": "acct"}},
                    {"id": "z2", "name": "theirs", "account": {"id": "other"}},
                ],
                "result_info": {"total_pages": 1},
            }
        if "/zones/z2/" in path:
            raise AssertionError("another account's zone was read")
        return base(path, token, jurisdiction)

    cfl.find_leftovers(ROOT, "acct", TOKEN, get)
    assert any("account.id=acct" in p for p, _ in calls)


# --- the classes PLAN-product-domain-rename L11 needs seen ---------------------------------------


def rows(found):
    return {(k, n): d for k, n, d in found}


def test_buckets_of_both_jurisdictions_are_listed_and_configured_ones_not():
    """An eu bucket is seen only through the jurisdiction header, so a default-only listing would miss it."""
    found = run_extra(buckets=[("old-bucket", "default"), ("old-eu", "eu"), ("configs-eu", "eu")])
    got = rows(found)
    assert ("bucket", "old-bucket") in got
    assert ("bucket", "old-eu") in got
    assert "jurisdiction eu" in got[("bucket", "old-eu")]
    assert ("bucket", "configs-eu") not in got


def test_a_leftover_names_its_id_references_and_bindings():
    found = run_extra(
        buckets=[(PUBLIC_DATA_BUCKET, "default")],
        bindings={CONFIGURED: [{"type": "r2_bucket", "bucket_name": PUBLIC_DATA_BUCKET}]},
    )
    detail = rows(found)[("bucket", PUBLIC_DATA_BUCKET)]
    assert "referenced: .ci/config/" in detail
    assert "bound: r2 binding of %s" % CONFIGURED in detail


def test_queues_containers_namespaces_and_pages_are_listed():
    found = run_extra(
        queues=[
            {"queue_id": "q1", "queue_name": "old-queue", "consumers": [{"script": "w-old"}]},
            {"queue_id": "q2", "queue_name": "backup-replicate-eu"},
        ],
        namespaces=[
            {"id": "ns-old", "name": "w-old_Exec", "script": "w-old", "class": "Exec"},
            {"id": "ns-live", "name": "%s_X" % CONFIGURED, "script": CONFIGURED, "class": "X"},
        ],
        containers=[
            {"id": "c1", "name": "w-old-exec", "durable_objects": {"namespace_id": "ns-old"}},
            {"id": "c2", "name": "gone-exec", "durable_objects": {"namespace_id": "ns-gone"}},
            {"id": "c3", "name": "live-x", "durable_objects": {"namespace_id": "ns-live"}},
        ],
        pages=[{"id": "p1", "name": "oldsite", "domains": ["oldsite.pages.dev"]}],
    )
    got = rows(found)
    assert ("queue", "old-queue") in got
    assert "consumer w-old" in got[("queue", "old-queue")]
    assert ("queue", "backup-replicate-eu") not in got
    assert ("do", "w-old_Exec") in got
    assert ("do", "%s_X" % CONFIGURED) not in got
    assert ("container", "w-old-exec") in got
    assert ("container", "gone-exec") in got
    assert "exists no more" in got[("container", "gone-exec")]
    assert ("container", "live-x") not in got
    assert ("pages", "oldsite") in got
    assert "id p1" in got[("pages", "oldsite")]


def test_a_script_leftover_names_its_custom_domain():
    found = run(["stray-worker"], [], [], [{"hostname": "old.example", "service": "stray-worker"}])
    assert "custom domain old.example" in rows(found)[("script", "stray-worker")]


def test_the_retired_terms_record_is_no_reference():
    texts = cfl.reference_texts(ROOT)
    assert ".ci/config/retired-terms.json" not in texts
    assert any(rel.startswith("workers/") for rel in texts)
    assert cfl.referenced_by("x-y", {"a": "x-y-z", "b": "(x-y)"}) == ["b"]


def run_extra(**extra):
    return cfl.find_leftovers(ROOT, "acct", TOKEN, fake_api([CONFIGURED], [], [], extra=extra))


def _throttle(retry_after=None):
    headers = email.message.Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError("u", 429, "slow", headers, io.BytesIO(b"<html>rate</html>"))


def test_retry_after_is_honoured_on_a_429(monkeypatch):
    """A Retry-After of 40 s outweighs the 4 s first step: the pause is at least 40 s, and no more than the jitter allows."""
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _throttle("40")
        return _Resp(b'{"success": true, "result": null}')

    _patch_urlopen(monkeypatch, flaky)
    pauses: list = []
    monkeypatch.setattr(cfl.time, "sleep", pauses.append)
    assert cfl.request("DELETE", "/r2/x", TOKEN)["success"] is True
    assert len(pauses) == 1
    assert 40.0 <= pauses[0] <= 40.0 * (1 + cfl.JITTER_FRACTION)


def test_a_429_without_retry_after_backs_off_longer_than_a_5xx(monkeypatch):
    pauses: list = []
    monkeypatch.setattr(cfl.time, "sleep", pauses.append)
    for status in (429, 503):
        calls = {"n": 0}

        def flaky(status=status, calls=calls):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.HTTPError(
                    "u", status, "x", email.message.Message(), io.BytesIO(b"<html>")
                )
            return _Resp(b'{"success": true, "result": null}')

        _patch_urlopen(monkeypatch, flaky)
        cfl.request("DELETE", "/r2/x", TOKEN)
    throttle, server = pauses
    assert throttle >= cfl.RETRY_PAUSES_S[0] * cfl.THROTTLE_FACTOR
    assert server == cfl.RETRY_PAUSES_S[0]


def test_retry_after_is_capped_and_a_bad_value_is_ignored():
    assert cfl.retry_after_s("5") == 5.0
    assert cfl.retry_after_s("99999") == cfl.RETRY_AFTER_CAP_S
    assert cfl.retry_after_s("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert cfl.retry_after_s(None) is None


def test_a_retry_after_that_is_not_finite_is_ignored():
    """Review 358dc107.3: nan and inf parse as floats and are no wait."""
    assert cfl.retry_after_s("nan") is None
    assert cfl.retry_after_s("inf") is None
    assert cfl.retry_after_s("-3") == 0.0


def test_pages_listing_without_total_pages_is_an_error_not_a_partial_count():
    """Review 49117485.6."""

    def page(items, info):
        return lambda _path, _token: {"success": True, "result": items, "result_info": info}

    with pytest.raises(cfl.CfError, match="total_pages"):
        cfl.listing_by_page("/p", TOKEN, page([{"name": "a"}], {}))
    with pytest.raises(cfl.CfError, match="total_pages"):
        cfl.listing_by_page("/p", TOKEN, page([], {}))
    seen: list = []

    def counted(path, _token):
        seen.append(path)
        n = int(path.rsplit("=", 1)[1])
        return {
            "success": True,
            "result": [{"n": n}],
            "result_info": {"total_count": 25, "per_page": 10},
        }

    assert [i["n"] for i in cfl.listing_by_page("/p", TOKEN, counted)] == [1, 2, 3]


def test_an_empty_listing_with_a_zero_count_is_an_empty_list_not_an_error():
    """Review 40b07c7e.1: an account with no containers or pages answers `total_pages: 0` or `total_count: 0`."""
    for info in ({"total_pages": 0}, {"total_count": 0, "per_page": 10}, {"total_count": 0}):
        assert (
            cfl.listing_by_page(
                "/p",
                TOKEN,
                lambda _p, _t, info=info: {"success": True, "result": [], "result_info": info},
            )
            == []
        )


def test_containers_listing_with_unusable_paging_metadata_is_an_error_and_with_none_is_whole():
    """Review 9900887b.1: a `result_info` with an unusable page count is refused; a body with no `result_info` at all is the whole listing."""
    with pytest.raises(cfl.CfError, match="total_pages"):
        cfl.followed(
            "/c",
            TOKEN,
            lambda _p, _t: {"success": True, "result": [{"id": 1}], "result_info": {"count": "x"}},
        )
    assert cfl.followed("/c", TOKEN, lambda _p, _t: {"success": True, "result": [{"id": 1}]}) == [
        {"id": 1}
    ]
    assert cfl.followed("/c", TOKEN, lambda _p, _t: {"success": True, "result": []}) == []
    counted = {
        "success": True,
        "result": [{"id": 1}],
        "result_info": {"total_count": 5, "per_page": 10},
    }
    assert cfl.followed("/c", TOKEN, lambda _p, _t: counted) == [{"id": 1}]


def test_containers_follow_pages_counted_from_total_count_and_per_page():
    """Review d2516ba8.1: with no total_pages, ceil(total_count / per_page) pages are read; the one-page case above is the control."""
    seen: list = []

    def get(path, _token):
        seen.append(path)
        n = int(path.rsplit("=", 1)[1]) if "page=" in path else 1
        return {
            "success": True,
            "result": [{"id": n}],
            "result_info": {"total_count": 25, "per_page": 10},
        }

    assert [c["id"] for c in cfl.followed("/c", TOKEN, get)] == [1, 2, 3]
    assert seen == ["/c", "/c?page=2", "/c?page=3"]


def test_containers_follow_every_page_the_listing_reports():
    """Review 49117485.5."""
    seen: list = []

    def get(path, _token):
        seen.append(path)
        n = int(path.rsplit("=", 1)[1]) if "page=" in path else 1
        return {"success": True, "result": [{"id": n}], "result_info": {"total_pages": 3}}

    assert [c["id"] for c in cfl.followed("/c", TOKEN, get)] == [1, 2, 3]
    assert seen == ["/c", "/c?page=2", "/c?page=3"]


def test_containers_listing_with_the_real_empty_result_info_is_complete():
    """Live read 2026-11-26: GET /accounts/<id>/containers/applications answers 7 items and `result_info: {}` (cursor pagination, no next token)."""
    names = ["proxy-eu-orgexecutor", "proxy-us-orgexecutor"]
    calls: list = []

    def get(path, _token):
        calls.append(path)
        return {
            "success": True,
            "result": [{"name": n} for n in names],
            "errors": [],
            "messages": [],
            "result_info": {},
        }

    assert [c["name"] for c in cfl.followed("/c", TOKEN, get)] == names
    assert calls == ["/c"]


def test_containers_cursor_listing_follows_next_page_token_and_refuses_a_loop():
    calls: list = []

    def get(path, _token):
        calls.append(path)
        if "page_token=t1" in path:
            return {"success": True, "result": [{"id": 2}], "result_info": {}}
        return {"success": True, "result": [{"id": 1}], "result_info": {"next_page_token": "t1"}}

    assert [c["id"] for c in cfl.followed("/c", TOKEN, get)] == [1, 2]
    assert calls == ["/c", "/c?page_token=t1"]

    def looping(_path, _token):
        return {"success": True, "result": [{"id": 1}], "result_info": {"next_page_token": "t1"}}

    with pytest.raises(cfl.CfError, match="next_page_token"):
        cfl.followed("/c", TOKEN, looping)


@pytest.mark.parametrize("info", [{"count": 2}, {"total_count": 2}, {"count": 2, "total_count": 2}])
def test_unpaginated_listing_stating_its_complete_count_is_one_page(info):
    """The containers listing answers a `result_info` with no `total_pages`; a count equal to the items returned, with no paging fields, is the whole list."""
    calls: list = []

    def get(path, _token):
        calls.append(path)
        return {"success": True, "result": [{"id": 1}, {"id": 2}], "result_info": info}

    assert cfl.followed("/c", TOKEN, get) == [{"id": 1}, {"id": 2}]
    assert calls == ["/c"]


@pytest.mark.parametrize(
    "info",
    [
        {"count": 5},  # states more items than the result holds: truncated
        {"count": 2, "per_page": 2},  # paginated and no page count
        {"count": 2, "page": 1},
        {"count": "2"},
        {"count": 2, "total_count": 500},  # ca0a/62cc.1: the larger stated count is not ignored
        {"total_count": 500, "count": 2},
        {"count": 2, "cursor": "x"},  # 62cc.2: a continuation field is not a complete list
        {"count": 2, "next_page_token": "x"},
        {"per_page": 20},  # ca0a.1: only per_page is not cursor info
    ],
)
def test_truncated_or_paginated_listing_without_total_pages_still_refuses(info):
    def get(_path, _token):
        return {"success": True, "result": [{"id": 1}, {"id": 2}], "result_info": info}

    with pytest.raises(cfl.CfError, match="total_pages"):
        cfl.followed("/c", TOKEN, get)


def _gone_error():
    return cfl.CfError(
        'GET /settings: [{"code": 10007, "message": "This Worker does not exist"}]', 404
    )


def test_worker_deleted_between_list_and_settings_read_is_skipped_as_gone():
    base = fake_api(["keep", "vanished"], [], [], extra={"bindings": {"keep": [{"type": "d1"}]}})

    def get(path, token, jurisdiction=None):
        if path.endswith("/scripts/vanished/settings"):
            raise _gone_error()
        return base(path, token, jurisdiction)

    inv = cfl.read_inventory("acc", TOKEN, get)
    assert inv.scripts == ["keep"]
    assert "vanished" not in inv.bindings
    assert inv.bindings["keep"] == [{"type": "d1"}]


def test_other_settings_errors_still_abort_the_inventory():
    base = fake_api(["a"], [], [])

    def get(path, token, jurisdiction=None):
        if path.endswith("/scripts/a/settings"):
            raise cfl.CfError('GET /settings: [{"code": 10000, "message": "Authentication"}]', 403)
        return base(path, token, jurisdiction)

    with pytest.raises(cfl.CfError, match="10000"):
        cfl.read_inventory("acc", TOKEN, get)


def test_cursor_info_with_per_page_and_a_token_key_is_still_cursor_pagination():
    """Control for ca0a1f05.1: `per_page` beside a cursor key stays cursor pagination; `per_page` alone is not."""

    def get(path, _token):
        if "page_token=t1" in path:
            return {"success": True, "result": [{"id": 2}], "result_info": {"next_page_token": ""}}
        return {
            "success": True,
            "result": [{"id": 1}],
            "result_info": {"per_page": 1, "next_page_token": "t1"},
        }

    assert [c["id"] for c in cfl.followed("/c", TOKEN, get)] == [1, 2]
    assert cfl._is_cursor_info({"per_page": 1, "next_page_token": "t1"})
    assert not cfl._is_cursor_info({"per_page": 20})


@pytest.mark.parametrize("info", [{"total_pages": False}, {"total_count": False, "per_page": 10}])
def test_a_false_count_is_malformed_not_an_empty_listing(info):
    """db740ebd.1: `False == 0` in Python made `total_pages: false` read as an empty listing."""
    with pytest.raises(cfl.CfError, match="no usable total_pages"):
        cfl._total_pages({"result": [], "result_info": info})
    assert cfl._total_pages({"result": [], "result_info": {"total_pages": 0}}) == 1


@pytest.mark.parametrize(
    "info", [{"next_cursor": None}, {"next_page": 2}, {"next": "x"}, {"per_page": 5, "next": None}]
)
def test_a_continuation_key_the_cursor_loop_does_not_read_is_refused_not_followed(info):
    """90f629d7.1: only `next_page_token` is followed, so a listing that names another continuation key would be cut short silently; `followed` refuses it."""
    assert not cfl._is_cursor_info(info)

    def get(_path, _token):
        return {"success": True, "result": [{"id": 1}], "result_info": info}

    with pytest.raises(cfl.CfError, match="no usable total_pages"):
        cfl.followed("/c", TOKEN, get)
