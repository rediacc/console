"""`./run.sh enterprise add` (box C1): the resumable onboarding run, its live steps over fakes, and the CLI. Nothing here reaches Cloudflare, bws or AWS."""

from __future__ import annotations

import email.message
import http.client
import io
import json
import os
import shutil
import sqlite3
import types
import urllib.error
from typing import Any, NoReturn, cast

import pytest

from rediacc_ci import __main__ as entry
from rediacc_ci import paths
from rediacc_ci.core import run_verbs, wrangler
from rediacc_ci.enterprise import cli, dns, lab, onboarding, registry

T0 = "2026-11-09T00:00:00Z"
IDS = iter("c%016x" % n for n in range(1, 10_000))


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(registry.migration_sql())
    return conn


class World:
    """Every control database of one environment, as in-memory sqlite behind the registry's Query shape."""

    def __init__(self, bench: bool = False, down: frozenset[str] = frozenset()):
        self.dbs = {db: _db() for db in registry.databases(bench).values()}
        self.down = set(down)

    def query(self, database, sql, params):
        if database in self.down:
            raise ConnectionError("no route to %s" % database)
        cur = self.dbs[database].execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
        self.dbs[database].commit()
        return rows

    def rows(self, database, sql):
        return [dict(r) for r in self.dbs[database].execute(sql).fetchall()]


class Recorder:
    """One action per step, recording the order; `fail` names steps that raise once."""

    def __init__(self, fail: set[str] | None = None, raise_with=None):
        self.calls: list[str] = []
        self.fail = set(fail or ())
        self.raise_with = raise_with or (lambda step: onboarding.OnboardingError("%s broke" % step))
        self.contexts: list[onboarding.Context] = []

    def actions(self) -> dict:
        def make(step):
            def act(ctx):
                self.calls.append(step)
                self.contexts.append(ctx)
                if step in self.fail:
                    self.fail.discard(step)
                    raise self.raise_with(step)
                if step == "control-row":
                    return onboarding.write_control_row(ctx)
                if step == "audit":
                    return onboarding.write_audit(ctx)
                if step == "d1":
                    return "00000000-0000-4000-8000-000000000001"
                return ""

            return act

        return {step: make(step) for step in onboarding.STEPS}


def _note(seen: list, item: object, result: Any) -> Any:
    """Record `item` and return `result`: a recording stand-in in one expression."""
    seen.append(item)
    return result


def _never(*_args: object) -> NoReturn:
    raise AssertionError("the add ran although the arguments were refused")


def _req(**kw) -> onboarding.Request:
    base: dict[str, Any] = {
        "name": "acme",
        "region": "eu",
        "owner": "owner@acme.example",
        "storage_gb": 100,
    }
    base.update(kw)
    return onboarding.Request(**base)


def _run(world, req, rec, **kw):
    return onboarding.run(
        req,
        query=world.query,
        actions=rec.actions(),
        new_id=lambda: next(IDS),
        now=lambda: T0,
        **kw,
    )


# --- validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kw", "needle"),
    [
        ({"name": "eu"}, "reserved"),
        ({"name": "Acme"}, "DNS label"),
        ({"region": "mars"}, "region"),
        ({"owner": "not-an-address"}, "owner"),
        ({"storage_gb": 0}, "storage"),
        ({"lookup_domain": "gmail.com"}, "free-mail"),
        ({"owner": "boss@gmail.com"}, "free-mail"),
        ({"bench": True, "region": "asia"}, "bench"),
        ({"allow_ips": ("not-an-ip",)}, "allow"),
    ],
)
def test_a_bad_request_is_refused_before_anything_runs(kw, needle):
    world, rec = World(bench=bool(kw.get("bench"))), Recorder()
    out = _run(world, _req(**kw), rec)
    assert out.rc == 1
    assert needle in out.error
    assert rec.calls == []


def test_an_unlisted_company_may_have_a_free_mail_owner():
    world, rec = World(), Recorder()
    out = _run(world, _req(owner="boss@gmail.com", unlisted=True), rec)
    assert out.rc == 0, out.error


def test_the_lookup_domain_defaults_to_the_owner_domain():
    assert _req().lookup == "acme.example"
    assert _req(lookup_domain="Corp.Example.").lookup == "corp.example"


# --- the run ---------------------------------------------------------------------


def test_a_fresh_add_runs_every_step_in_order_and_activates():
    world, rec = World(), Recorder()
    out = _run(world, _req(), rec)
    assert out.rc == 0, out.error
    assert rec.calls == list(onboarding.STEPS)
    assert out.changed == onboarding.STEPS
    rows = world.rows("control-eu", "SELECT id, name, state, unlisted FROM companies")
    assert rows == [{"id": out.company_id, "name": "acme", "state": "active", "unlisted": 0}]
    steps = world.rows("control-eu", "SELECT step, status FROM onboarding ORDER BY step")
    assert {s["step"] for s in steps} == set(onboarding.STEPS)
    assert {s["status"] for s in steps} == {"done"}
    audit = world.rows("control-eu", "SELECT company_id, action FROM audit")
    assert audit == [{"company_id": out.company_id, "action": "add"}]
    # Only the company's own region holds it.
    assert world.rows("control-us", "SELECT * FROM companies") == []


def test_a_rerun_changes_nothing():
    world = World()
    first = _run(world, _req(), Recorder())
    rec = Recorder()
    again = _run(world, _req(), rec)
    assert again.rc == 0
    assert again.company_id == first.company_id
    assert again.changed == ()
    assert rec.calls == []


def test_a_stop_after_d1_resumes_from_the_next_step_with_the_same_id():
    world = World()
    killed = _run(world, _req(), Recorder(), stop_after="d1")
    assert killed.rc == 1
    assert "stopped after d1" in killed.error
    rec = Recorder()
    resumed = _run(world, _req(), rec)
    assert resumed.rc == 0, resumed.error
    assert resumed.company_id == killed.company_id
    assert rec.calls == list(onboarding.STEPS[onboarding.STEPS.index("d1") + 1 :])
    # The d1 detail recorded by the killed run reaches the resumed steps.
    assert rec.contexts[0].details["d1"] == "00000000-0000-4000-8000-000000000001"


def test_a_failed_step_is_recorded_and_retried_on_resume():
    world = World()
    out = _run(world, _req(), Recorder(fail={"buckets"}))
    assert out.rc == 1
    assert "buckets" in out.error
    status = world.rows("control-eu", "SELECT status FROM onboarding WHERE step = 'buckets'")
    assert status == [{"status": "failed"}]
    rec = Recorder()
    assert _run(world, _req(), rec).rc == 0
    assert rec.calls[0] == "buckets"


def test_a_not_built_seam_stops_the_add_naming_its_box():
    world = World()
    actions = Recorder().actions()
    actions["bootstrap"] = onboarding.not_built("A1", "the company bootstrap endpoint")
    out = onboarding.run(
        _req(), query=world.query, actions=actions, new_id=lambda: next(IDS), now=lambda: T0
    )
    assert out.rc == 1
    assert "not built yet: A1" in out.error
    assert "bootstrap" in out.error


def test_an_unexpected_exception_propagates():
    world = World()
    rec = Recorder(fail={"configs"}, raise_with=KeyError)
    with pytest.raises(KeyError):
        _run(world, _req(), rec)


def test_an_unlisted_company_skips_the_lookup_writer():
    world, rec = World(), Recorder()
    out = _run(world, _req(unlisted=True), rec)
    assert out.rc == 0
    assert "lookup" not in rec.calls
    assert "lookup" in out.changed
    detail = world.rows("control-eu", "SELECT detail FROM onboarding WHERE step = 'lookup'")
    assert detail == [{"detail": "unlisted"}]
    assert world.rows("control-eu", "SELECT unlisted FROM companies") == [{"unlisted": 1}]


def test_a_name_held_in_another_region_is_refused():
    world = World()
    assert _run(world, _req(region="us"), Recorder()).rc == 0
    rec = Recorder()
    out = _run(world, _req(region="eu"), rec)
    assert out.rc == 1
    assert "already registered in us" in out.error
    assert rec.calls == []


def test_an_unreachable_region_refuses_the_add_and_names_it():
    world = World(down=frozenset({"control-asia"}))
    rec = Recorder()
    out = _run(world, _req(), rec)
    assert out.rc == 1
    assert "asia" in out.error
    assert rec.calls == []


def test_a_removed_company_name_may_be_taken_again():
    world = World()
    first = _run(world, _req(), Recorder())
    world.query(
        "control-eu",
        "UPDATE companies SET state = 'removed', name = ? WHERE id = ?",
        ["acme-gone", first.company_id],
    )
    out = _run(world, _req(), Recorder())
    assert out.rc == 0
    assert out.company_id != first.company_id


def test_bench_uses_the_bench_control_database_signer_and_environment():
    world, rec = World(bench=True), Recorder()
    out = _run(world, _req(bench=True, region="us"), rec)
    assert out.rc == 0, out.error
    plan = rec.contexts[0].plan
    assert plan.database == "control-bench-us"
    assert plan.signer == "signer-bench-us"
    assert plan.environment == "bench"
    assert world.rows("control-bench-us", "SELECT name FROM companies") == [{"name": "acme"}]


def test_production_plan_names_the_regional_signer_and_stable():
    plan = onboarding.plan_for(_req(region="asia"), "c0123456789abcdef")
    assert plan.database == "control-asia"
    assert plan.signer == "signer-asia"
    assert plan.environment == "stable"
    assert plan.hosts[0].startswith("acme.")
    assert plan.hosts[1].startswith("acme-proxy.")


def test_the_outcome_lines_carry_the_opaque_id_not_the_label():
    world = World()
    lines: list[str] = []
    out = _run(world, _req(), Recorder(), out=lines.append)
    assert lines
    assert all(out.company_id in line for line in lines)
    assert not any("acme" in line for line in lines)


# --- live steps over fakes ---------------------------------------------------------


class Proc:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _tree(tmp_path):
    for sub in ("workers/proxy", "workers/account"):
        (tmp_path / sub).mkdir(parents=True)
    shutil.copy(paths.repo_root() / "regions.json", tmp_path / "regions.json")
    return tmp_path


def _ctx(world, details=None, **kw):
    plan = onboarding.plan_for(_req(**kw), "c0123456789abcdef")
    return onboarding.Context(plan=plan, query=world.query, details=dict(details or {}), now=T0)


def test_live_d1_step_creates_the_company_database_through_control_db(monkeypatch):
    seen = []

    def ensure(name, region, *, runner):
        del runner
        seen.append((name, region))
        return "11111111-2222-4333-8444-555555555555", True

    monkeypatch.setattr(onboarding.control_db, "ensure_database", ensure)
    actions = onboarding.live_actions(runner=lambda *_a, **_k: Proc())
    assert actions["d1"](_ctx(World())) == "11111111-2222-4333-8444-555555555555"
    assert seen == [("account-acme", "eu")]


def test_live_configs_step_writes_both_files_and_bench_sets_the_environment(tmp_path):
    _tree(tmp_path)
    actions = onboarding.live_actions(runner=None, out_root=tmp_path)
    d1 = {"d1": "11111111-2222-4333-8444-555555555555"}
    actions["configs"](_ctx(World(bench=True), d1, bench=True))
    account = (tmp_path / "workers/account/enterprise.acme.toml").read_text()
    assert 'ENVIRONMENT = "bench"' in account
    assert (tmp_path / "workers/proxy/enterprise.acme.toml").exists()
    actions["configs"](_ctx(World(), d1))
    assert (
        'ENVIRONMENT = "stable"' in (tmp_path / "workers/account/enterprise.acme.toml").read_text()
    )


def test_live_configs_step_refuses_without_a_d1_id(tmp_path):
    actions = onboarding.live_actions(runner=None, out_root=tmp_path)
    with pytest.raises(onboarding.OnboardingError, match="d1"):
        actions["configs"](_ctx(World()))


def test_live_buckets_step_creates_buckets_and_queues():
    calls = []

    def runner(argv, *, cwd=None):
        del cwd
        calls.append(argv[len(wrangler.ARGV) :])
        return Proc(0)

    onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))
    assert ["r2", "bucket", "list", "--jurisdiction", "eu"] in calls
    assert ["r2", "bucket", "create", "configs-acme", "--jurisdiction", "eu"] in calls
    assert ["r2", "bucket", "create", "backups-acme", "--jurisdiction", "eu"] in calls
    assert ["queues", "create", "backup-replicate-acme"] in calls
    assert ["queues", "create", "backup-replicate-acme-dlq"] in calls


def test_live_buckets_step_reuses_what_the_list_shows_and_never_creates_it():
    calls = []

    def runner(argv, *, cwd=None):
        del cwd
        args = argv[len(wrangler.ARGV) :]
        calls.append(args)
        if "list" in args and args[0] == "r2":
            return Proc(0, "name: configs-acme\nname: backups-acme\n")
        if "list" in args:
            return Proc(0, "backup-replicate-acme-dlq\n")
        return Proc(0)

    onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))
    created = [c for c in calls if "create" in c]
    # only the queue is created: its -dlq sibling is listed, and must not match it
    assert created == [["queues", "create", "backup-replicate-acme"]]


def test_live_buckets_step_control_creates_when_the_list_is_empty():
    """THE CONTROL: with an empty list every resource is created, so the reuse test above can go red."""
    calls = []

    def runner(argv, *, cwd=None):
        del cwd
        calls.append(argv[len(wrangler.ARGV) :])
        return Proc(0)

    onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))
    assert len([c for c in calls if "create" in c]) == 4


def test_live_buckets_step_does_not_read_exists_from_a_create_error():
    def runner(argv, *, cwd=None):
        del cwd
        if "create" in argv:
            return Proc(1, "", "The bucket you tried to create already exists")
        return Proc(0)

    with pytest.raises(onboarding.OnboardingError, match="already exists"):
        onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))


def test_live_buckets_step_names_the_cause_of_a_create_failure_with_the_label_masked():
    def runner(argv, *, cwd=None):
        del cwd
        if "create" in argv:
            out = '{"error": {"text": "bucket configs-acme is taken", "notes": [{"text": "see docs"}]}}'
            err = 'Using "CF_EMAIL" environment variable. This is deprecated\nrate limited'
            return Proc(1, out, err)
        return Proc(0)

    with pytest.raises(onboarding.OnboardingError) as err:
        onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))
    text = str(err.value)
    assert "bucket configs-<name> is taken | see docs | rate limited" in text
    assert "acme" not in text
    assert "deprecated" not in text


def test_live_buckets_step_names_the_cause_of_a_list_failure():
    def runner(argv, *, cwd=None):
        del cwd
        return Proc(1, "", "not authorized") if "list" in argv else Proc(0)

    with pytest.raises(onboarding.OnboardingError, match=r"listing.*exited 1.*not authorized"):
        onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))


def test_live_migrate_step_names_the_cause_of_a_failure():
    def runner(*_args, **_kwargs):
        return Proc(1, "", "d1 acme says no")

    with pytest.raises(onboarding.OnboardingError) as err:
        onboarding.live_actions(runner=runner)["migrate"](_ctx(World()))
    assert "d1 <name> says no" in str(err.value)


def _local_only_npx(tmp_path, *, install: bool):
    """A fake `npx` that resolves as npm 11.21.0 does: only a node_modules/.bin/wrangler at or above the cwd counts, never PATH. Returns (PATH dir, repository root with or without the account worker's install)."""
    stub = tmp_path / "bin"
    stub.mkdir()
    npx = stub / "npx"
    npx.write_text(
        '#!/bin/sh\nd=$(pwd -P)\nwhile [ ! -e "$d/node_modules/.bin/wrangler" ]; do\n'
        "  if [ \"$d\" = / ]; then echo 'npm error npx canceled due to missing packages' >&2; exit 1; fi\n"
        '  d=$(dirname "$d")\ndone\nexit 0\n',
        encoding="utf-8",
    )
    npx.chmod(0o755)
    root = tmp_path / "repo"
    worker = root.joinpath(*onboarding.pc.ACCOUNT_REL)
    worker.mkdir(parents=True)
    if install:
        (worker / "node_modules" / ".bin").mkdir(parents=True)
        (worker / "node_modules" / ".bin" / "wrangler").write_text("#!/bin/sh\n", encoding="utf-8")
    return str(stub), root


def test_live_buckets_step_finds_the_pinned_wrangler_as_npm_resolves_it(tmp_path, monkeypatch):
    """Finding e69747ea: the buckets step ran from an empty temporary directory, where npx finds no wrangler."""
    stub, root = _local_only_npx(tmp_path, install=True)
    monkeypatch.setenv("PATH", stub + os.pathsep + os.environ["PATH"])
    onboarding.live_actions(runner=None, out_root=root)["buckets"](_ctx(World()))


def test_live_buckets_step_control_fails_without_the_install(tmp_path, monkeypatch):
    """THE CONTROL: with no install in the account worker the same fake refuses, so the test above can go red."""
    stub, root = _local_only_npx(tmp_path, install=False)
    monkeypatch.setenv("PATH", stub + os.pathsep + os.environ["PATH"])
    with pytest.raises(onboarding.OnboardingError):
        onboarding.live_actions(runner=None, out_root=root)["buckets"](_ctx(World()))


def test_live_buckets_step_runs_from_the_account_worker():
    seen = []

    def runner(_argv, *, cwd=None):
        seen.append(str(cwd))
        return Proc(0)

    onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))
    assert seen
    assert all(cwd.endswith("workers/account") for cwd in seen), seen


def test_live_buckets_step_names_a_failure_without_the_label():
    def runner(*_args, **_kwargs):
        return Proc(1, "", "acme exploded")

    with pytest.raises(onboarding.OnboardingError) as err:
        onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))
    assert "acme" not in str(err.value)
    assert "c0123456789abcdef" in str(err.value)


def test_live_migrate_step_runs_from_the_account_worker_with_the_company_config():
    seen = []

    def runner(argv, *, cwd=None):
        seen.append((argv[len(wrangler.ARGV) :], str(cwd)))
        return Proc(0)

    onboarding.live_actions(runner=runner)["migrate"](_ctx(World()))
    argv, cwd = seen[0]
    assert argv == [
        "d1", "migrations", "apply", "account-acme", "--remote", "--config", "enterprise.acme.toml",
    ]  # fmt: skip
    assert cwd.endswith("workers/account")


def test_live_lookup_step_puts_the_owner_domain_to_the_account_host():
    puts = []

    def lookup_put(domain, host, namespace_id):
        puts.append((domain, host, namespace_id))
        return 0

    actions = onboarding.live_actions(runner=None, lookup_put=lookup_put, lookup_namespace="ns1")
    actions["lookup"](_ctx(World()))
    assert puts
    assert puts[0][0] == "acme.example"
    assert puts[0][1].startswith("acme.")
    assert puts[0][2] == "ns1"


def test_live_lookup_step_turns_a_refusal_into_an_onboarding_error():
    def lookup_put(*_args):
        raise onboarding.enterprise_lookup.LookupRefusedError("set ENTERPRISE_LOOKUP_PEPPER")

    actions = onboarding.live_actions(runner=None, lookup_put=lookup_put)
    with pytest.raises(onboarding.OnboardingError, match="PEPPER"):
        actions["lookup"](_ctx(World()))


def _portal_ok(_tree, _env):
    return 0


def test_live_deploy_step_deploys_proxy_then_account_with_each_own_config(tmp_path):
    _tree(tmp_path)
    actions = onboarding.live_actions(runner=None, out_root=tmp_path)
    d1 = {"d1": "11111111-2222-4333-8444-555555555555"}
    ctx = _ctx(World(), d1)
    actions["configs"](ctx)
    ran = []

    def deploy(module, argv):
        ran.append((module, argv))
        return 0

    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        portal=_portal_ok,
        deploy=deploy,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    actions["deploy"](ctx)
    assert [m for m, _ in ran] == [
        "rediacc_ci.deploy.deploy_proxy",
        "rediacc_ci.deploy.deploy_account",
        "rediacc_ci.deploy.deploy_proxy",
    ]
    proxy_argv, account_argv = ran[0][1], ran[1][1]
    assert "--proxy-config" in proxy_argv
    assert "--account-config" not in proxy_argv
    assert "--account-config" in account_argv
    assert "--proxy-config" not in account_argv
    assert account_argv[account_argv.index("--company-id") + 1] == "c0123456789abcdef"


def test_live_deploy_step_claims_the_wildcard_before_the_proxy_smoke_runs(tmp_path):
    """The proxy deploy smoke-tests the company's proxy host, whose record the wildcard claim creates: a first deploy cannot pass when the claim waits for the route step."""
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    order = []

    def ensure(_check_only):
        order.append("dns")
        return "ok"

    def deploy(module, _argv):
        order.append(module.rsplit(".", 1)[1])
        return 0

    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        portal=_portal_ok,
        deploy=deploy,
        root=tmp_path,
        ensure_dns=ensure,
    )
    actions["deploy"](ctx)
    assert order == ["dns", "deploy_proxy", "deploy_account", "deploy_proxy"]


def test_live_deploy_step_smokes_the_proxy_only_after_the_account_worker_is_deployed(tmp_path):
    """A first deploy's /v1/ready asks the company account Worker's ExecutorIssuer, so the first proxy run defers its smoke and a --smoke-only run follows the account deploy (bench run 6 failed 503 issuer-probe-failed for 300 s). Control: the account run never carries either flag."""
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    ran = []

    def deploy(module, argv):
        ran.append((module.rsplit(".", 1)[1], argv))
        return 0

    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        portal=_portal_ok,
        deploy=deploy,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    actions["deploy"](ctx)
    (_, first), (_, account), (_, last) = ran
    assert "--defer-smoke" in first
    assert "--smoke-only" not in first
    assert "--smoke-only" in last
    assert "--defer-smoke" not in last
    assert "--defer-smoke" not in account
    assert "--smoke-only" not in account


def test_live_deploy_step_deploys_nothing_when_the_wildcard_claim_fails(tmp_path):
    """The control: a refused claim stops the step before any module runs."""
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)

    def deploy(_m, _a):
        raise AssertionError("deployed")

    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        portal=_portal_ok,
        deploy=deploy,
        root=tmp_path,
        ensure_dns=RouteWorld({}, dns.DnsClaimError("Universal SSL is not enabled")).ensure,
    )
    with pytest.raises(onboarding.OnboardingError, match="Universal SSL is not enabled"):
        actions["deploy"](ctx)


def test_live_deploy_step_names_the_failed_module(tmp_path):
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        portal=_portal_ok,
        deploy=lambda _m, _a: 1,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    with pytest.raises(onboarding.OnboardingError, match="deploy_proxy exited 1"):
        actions["deploy"](ctx)


def test_live_smoke_step_requires_both_hosts_to_answer():
    seen = []

    def fetch(url):
        seen.append(url)
        return 200 if "-proxy." not in url else 502

    actions = onboarding.live_actions(runner=None, fetch=fetch)
    with pytest.raises(onboarding.OnboardingError, match="proxy host answered 502"):
        actions["smoke"](_ctx(World()))
    assert len(seen) == 2


class RouteWorld:
    """The route step's two seams: the wildcard ensure and the Worker a host routes to."""

    def __init__(self, routes: dict[str, str], dns_error: Exception | None = None):
        self.routes = routes
        self.dns_error = dns_error
        self.ensured: list[bool] = []

    def ensure(self, check_only):
        self.ensured.append(check_only)
        if self.dns_error:
            raise self.dns_error
        return "ok"

    def actions(self):
        return onboarding.live_actions(
            runner=None, ensure_dns=self.ensure, route_of=lambda host: self.routes.get(host, "")
        )


def _route_ctx():
    ctx = _ctx(World())
    return ctx, ctx.plan.hosts, ctx.plan.name


def test_live_route_step_passes_when_both_hosts_route_to_the_company_workers():
    ctx, (account, proxy), name = _route_ctx()
    rw = RouteWorld({account: "account-%s" % name, proxy: "proxy-%s" % name})
    assert rw.actions()["route"](ctx) == ""
    assert rw.ensured == [False]


@pytest.mark.parametrize("missing", [0, 1])
def test_live_route_step_refuses_a_host_without_its_route(missing):
    ctx, hosts, name = _route_ctx()
    routes = {hosts[0]: "account-%s" % name, hosts[1]: "proxy-%s" % name}
    del routes[hosts[missing]]
    with pytest.raises(onboarding.OnboardingError, match="no Worker"):
        RouteWorld(routes).actions()["route"](ctx)


def test_live_route_step_refuses_a_host_routed_to_another_worker():
    ctx, (account, proxy), name = _route_ctx()
    rw = RouteWorld({account: "account-%s" % name, proxy: "proxy-eu"})
    with pytest.raises(onboarding.OnboardingError, match="not proxy-%s" % name):
        rw.actions()["route"](ctx)


def test_live_route_step_refuses_when_the_wildcard_claim_fails_before_reading_routes():
    ctx, _hosts, _name = _route_ctx()

    def never(_host):
        raise AssertionError("routes were read")

    actions = onboarding.live_actions(
        runner=None,
        ensure_dns=RouteWorld({}, dns.DnsClaimError("Universal SSL is not enabled")).ensure,
        route_of=never,
    )
    with pytest.raises(onboarding.OnboardingError, match="Universal SSL is not enabled"):
        actions["route"](ctx)


def test_live_route_step_reads_routes_through_the_lab_matcher_when_none_is_injected(monkeypatch):
    """Review 7f868920.1: the production default is `lab.routed_worker`, bound on first use; a LabError from it names the company by id."""
    ctx, (account, proxy), name = _route_ctx()
    routes = {account: "account-%s" % name, proxy: "proxy-%s" % name}
    monkeypatch.setattr(lab, "routed_worker", lambda host: routes[host])
    actions = onboarding.live_actions(runner=None, ensure_dns=lambda _c: "ok")
    assert actions["route"](ctx) == ""

    def broken(_host):
        raise onboarding.proof.LabError("the zone cannot be read")

    monkeypatch.setattr(lab, "routed_worker", broken)
    with pytest.raises(onboarding.OnboardingError, match="company c0123456789abcdef: the zone"):
        actions["route"](ctx)


def test_a_company_onboarded_before_the_route_step_reruns_only_route():
    world = World()
    out = _run(world, _req(), Recorder())
    database = registry.control_database("eu", False)
    world.dbs[database].execute(
        "DELETE FROM onboarding WHERE company_id = ? AND step = 'route'", (out.company_id,)
    )
    world.dbs[database].commit()
    rec = Recorder()
    again = _run(world, _req(), rec)
    assert rec.calls == ["route"]
    assert again.changed == ("route",)


def test_live_secrets_step_hands_the_company_to_the_provisioner():
    got = []

    def provision(company):
        got.append(company)
        return types.SimpleNamespace(created=["A"], reused=[], pushed=["A", "B"])

    actions = onboarding.live_actions(runner=None, provision=provision)
    detail = actions["secrets"](_ctx(World()))
    assert got[0].id == "c0123456789abcdef"
    assert got[0].worker == "account-acme"
    assert got[0].r2_jurisdiction == "eu"
    assert "1 created" in detail


def test_live_secrets_step_without_a_provisioner_refuses_by_name():
    with pytest.raises(onboarding.OnboardingError, match="--bws-project"):
        onboarding.live_actions(runner=None)["secrets"](_ctx(World()))


def test_live_provision_names_every_missing_secrets_input_at_once():
    provision = onboarding.live_provision("proj", env={})
    co = types.SimpleNamespace(id="c0123456789abcdef", region="eu")
    with pytest.raises(onboarding.OnboardingError) as caught:
        provision(cast("Any", co))
    message = str(caught.value)
    for name in (
        "CF_MANAGEMENT_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SES_FROM",
        "OBS_OTLP_CREDENTIALS_EU",
    ):
        assert name in message
    assert message.startswith("company %s: " % co.id)


class FakeAccount:
    def __init__(self, status: int = 201, payload: dict | None = None):
        self.status = status
        self.payload = payload or {}
        self.calls: list[tuple[str, str, dict]] = []

    def __call__(self, url, key, body):
        self.calls.append((url, key, body))
        return self.status, self.payload


def _account_actions(fake, key="k-secret"):
    return onboarding.live_actions(runner=None, post=fake, api_key_of=lambda _company: key)


def _seeded_ctx(world):
    """A context whose control database already holds the company's row and scope, as after the control-row step."""
    ctx = _ctx(world)
    onboarding.write_control_row(ctx)
    return ctx


def test_control_row_registers_the_scope_the_signer_reads_and_bootstrap_sends_its_subscription_id():
    world = World()
    ctx = _ctx(world)
    onboarding.write_control_row(ctx)
    onboarding.write_control_row(ctx)
    rows = world.rows(ctx.plan.database, "SELECT * FROM scope")
    assert len(rows) == 1
    assert rows[0]["company_id"] == "c0123456789abcdef"
    assert rows[0]["renewal_host"] == ctx.plan.hosts[0]
    assert rows[0]["max_expiry_days"] > 365
    fake = FakeAccount(201)
    _account_actions(fake)["bootstrap"](ctx)
    sent = fake.calls[0][2]
    assert sent["subscriptionId"] == rows[0]["subscription_id"]
    assert sent["maxActivations"] == rows[0]["max_machines"] == onboarding.SCOPE_MAX_MACHINES
    assert sent["maxRepositorySizeGb"] == rows[0]["max_storage_gb"]
    assert sent["maxActivations"] != 1


def test_bootstrap_sends_the_limits_a_changed_scope_row_holds():
    world = World()
    ctx = _ctx(world)
    onboarding.write_control_row(ctx)
    world.query(ctx.plan.database, "UPDATE scope SET max_machines = 7, max_storage_gb = 30", [])
    fake = FakeAccount(201)
    _account_actions(fake)["bootstrap"](ctx)
    assert fake.calls[0][2]["maxActivations"] == 7
    assert fake.calls[0][2]["maxRepositorySizeGb"] == 30


def test_bootstrap_without_a_scope_row_refuses_before_calling_the_worker():
    fake = FakeAccount(201)
    with pytest.raises(onboarding.OnboardingError, match="no scope"):
        _account_actions(fake)["bootstrap"](_ctx(World()))
    assert fake.calls == []


def test_live_bootstrap_creates_through_the_account_route():
    fake = FakeAccount(201)
    detail = _account_actions(fake)["bootstrap"](_seeded_ctx(World()))
    url, key, body = fake.calls[0]
    assert url.endswith("/account/api/v1/subscriptions/enterprise/bootstrap")
    assert url.startswith("https://")
    assert key == "k-secret"
    assert body["companyId"] == "c0123456789abcdef"
    assert set(body) == {
        "companyId",
        "ownerEmail",
        "storageGb",
        "subscriptionId",
        "maxActivations",
        "maxRepositorySizeGb",
    }
    assert detail == "created"


def test_live_bootstrap_rerun_is_success():
    assert (
        _account_actions(FakeAccount(200))["bootstrap"](_seeded_ctx(World()))
        == "already bootstrapped"
    )


def test_live_bootstrap_owner_change_refuses_with_its_status_and_code():
    fake = FakeAccount(409, {"code": "OWNER_MISMATCH"})
    with pytest.raises(onboarding.OnboardingError, match=r"HTTP 409 \(OWNER_MISMATCH\)"):
        _account_actions(fake)["bootstrap"](_seeded_ctx(World()))


def test_live_bootstrap_and_invite_refuse_naming_the_missing_key():
    fake = FakeAccount()
    for step in ("bootstrap", "invite"):
        with pytest.raises(onboarding.OnboardingError, match=onboarding.ACCOUNT_KEY_ENV):
            _account_actions(fake, key="")[step](_seeded_ctx(World()))
    assert fake.calls == []


def test_live_bootstrap_uses_the_company_key_not_the_environment_key(monkeypatch):
    # Run 8 of region-loss: the shared key in the caller's environment got HTTP 401 from the company Worker.
    monkeypatch.setenv(onboarding.ACCOUNT_KEY_ENV, "shared-key")
    fake = FakeAccount(201)
    asked = []

    def company_key(company_id):
        asked.append(company_id)
        return "company-key"

    onboarding.live_actions(runner=None, post=fake, api_key_of=company_key)["bootstrap"](
        _seeded_ctx(World())
    )
    assert fake.calls[0][1] == "company-key"
    assert asked == ["c0123456789abcdef"]


def test_live_bootstrap_without_a_company_key_source_never_falls_back_to_the_environment(
    monkeypatch,
):
    monkeypatch.setenv(onboarding.ACCOUNT_KEY_ENV, "shared-key")
    fake = FakeAccount()
    with pytest.raises(onboarding.OnboardingError, match="bws-project"):
        onboarding.live_actions(runner=None, post=fake)["bootstrap"](_seeded_ctx(World()))
    assert fake.calls == []


def test_live_api_key_reads_the_company_entry_from_the_project(monkeypatch):
    class Store:
        def read(self, names):
            assert names == ["c0123456789abcdef_ACCOUNT_SERVER_API_KEY"]
            return {names[0]: "k-company"}

    monkeypatch.setattr(onboarding.secrets.BwsStore, "from_env", lambda *_a, **_k: Store())
    assert onboarding.live_api_key("proj", {})("c0123456789abcdef") == "k-company"


def test_live_invite_posts_the_owner_mail_route():
    fake = FakeAccount(200, {"sent": True})
    _account_actions(fake)["invite"](_ctx(World()))
    url, _key, body = fake.calls[0]
    assert url.endswith("/enterprise/owner-mail")
    assert set(body) == {"companyId", "ownerEmail"}


@pytest.mark.parametrize("status", [202, 204])
def test_live_account_call_accepts_any_2xx(status):
    fake = FakeAccount(status)
    _account_actions(fake)["bootstrap"](_seeded_ctx(World()))
    assert len(fake.calls) == 1


@pytest.mark.parametrize(
    ("status", "payload", "tail"),
    [(500, {}, ""), (302, {}, ""), (403, {"code": "NOPE"}, " (NOPE)")],
)
def test_live_account_call_refuses_a_non_2xx_with_or_without_a_code(status, payload, tail):
    with pytest.raises(onboarding.OnboardingError) as caught:
        _account_actions(FakeAccount(status, payload))["bootstrap"](_seeded_ctx(World()))
    assert ("refused with HTTP %d%s on POST " % (status, tail)) in str(caught.value)


def test_live_account_call_names_the_path_and_the_body_of_a_refusal():
    body = {"error": "D1_ERROR: no such table: company_orgs"}
    with pytest.raises(onboarding.OnboardingError) as caught:
        _account_actions(FakeAccount(500, body))["bootstrap"](_seeded_ctx(World()))
    message = str(caught.value)
    assert "HTTP 500" in message
    assert "POST /account/api/v1/subscriptions/enterprise/bootstrap" in message
    assert "no such table: company_orgs" in message


def test_live_account_call_truncates_the_body_and_masks_the_key():
    body = {"_text": "boom k-secret " + "x" * 2000}
    with pytest.raises(onboarding.OnboardingError) as caught:
        _account_actions(FakeAccount(500, body))["bootstrap"](_seeded_ctx(World()))
    message = str(caught.value)
    assert "k-secret" not in message
    assert "<redacted>" in message
    assert len(message) < 800


def test_live_account_call_control_a_bodyless_refusal_adds_no_tail():
    with pytest.raises(onboarding.OnboardingError) as caught:
        _account_actions(FakeAccount(500, {}))["bootstrap"](_seeded_ctx(World()))
    assert str(caught.value).endswith("/enterprise/bootstrap")


def test_account_post_keeps_a_non_json_error_body(monkeypatch):
    class Reply(io.BytesIO):
        pass

    def refuse(*_a, **_k):
        raise urllib.error.HTTPError(
            "https://h/x", 500, "err", email.message.Message(), Reply(b"Internal Server Error")
        )

    monkeypatch.setattr(onboarding.https, "urlopen", refuse)
    assert onboarding.account_post("https://h/x", "k", {}) == (
        500,
        {"_text": "Internal Server Error"},
    )


def test_account_post_names_the_status_when_the_error_body_cannot_be_read(monkeypatch):
    class Broken(io.BytesIO):
        def read(self, *_a):
            raise OSError("reset")

    def refuse(*_a, **_k):
        raise urllib.error.HTTPError(
            "https://h", 502, "bad gateway", email.message.Message(), Broken()
        )

    monkeypatch.setattr(onboarding.https, "urlopen", refuse)
    assert onboarding.account_post("https://h/x", "k", {}) == (502, {})


def test_account_post_survives_an_incomplete_read_of_the_error_body(monkeypatch):
    class Cut(io.BytesIO):
        def read(self, *_a):
            raise http.client.IncompleteRead(b"par", 10)

    def refuse(*_a, **_k):
        raise urllib.error.HTTPError(
            "https://h", 502, "bad gateway", email.message.Message(), Cut()
        )

    monkeypatch.setattr(onboarding.https, "urlopen", refuse)
    assert onboarding.account_post("https://h/x", "k", {}) == (502, {})


def test_account_post_closes_the_error_response_it_read(monkeypatch):
    """An HTTPError owns its response; left open it is finalised later as a ResourceWarning in an unrelated test."""
    err = urllib.error.HTTPError(
        "https://h", 403, "no", email.message.Message(), io.BytesIO(b'{"code": "NOPE"}')
    )

    def refuse(*_a, **_k):
        raise err

    monkeypatch.setattr(onboarding.https, "urlopen", refuse)
    assert onboarding.account_post("https://h/x", "k", {}) == (403, {"code": "NOPE"})
    assert err.fp is None or err.fp.closed


def test_http_status_closes_the_error_response(monkeypatch):
    err = urllib.error.HTTPError("https://h", 404, "gone", email.message.Message(), io.BytesIO(b""))

    def refuse(*_a, **_k):
        raise err

    monkeypatch.setattr(onboarding.https, "urlopen", refuse)
    assert onboarding.http_status("https://h/x") == 404
    assert err.fp is None or err.fp.closed


def test_http_status_of_a_plain_answer_is_its_status(monkeypatch):
    class Reply:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(onboarding.https, "urlopen", lambda *_a, **_k: Reply())
    assert onboarding.http_status("https://h/x") == 204


def test_account_post_keeps_the_status_of_a_success_whose_body_was_cut_off(monkeypatch):
    """Review 9bfbbb2f.1: the server answered 200, so the call is not "no answer" (0)."""

    class Reply:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def read(self):
            raise http.client.IncompleteRead(b"par", 10)

    monkeypatch.setattr(onboarding.https, "urlopen", lambda *_a, **_k: Reply())
    assert onboarding.account_post("https://h/x", "k", {}) == (200, {})


def test_live_account_calls_accept_a_success_with_an_empty_body():
    """Review f2446371.2: a cut-off 200 reads as (200, {}), which both callers take as success."""
    assert _account_actions(FakeAccount(200, {}))["invite"](_ctx(World())) == ""
    assert (
        _account_actions(FakeAccount(200, {}))["bootstrap"](_seeded_ctx(World()))
        == "already bootstrapped"
    )


def test_live_account_call_with_no_answer_refuses():
    with pytest.raises(onboarding.OnboardingError, match="no answer"):
        _account_actions(FakeAccount(0))["invite"](_ctx(World()))


def test_live_actions_cover_every_step():
    assert set(onboarding.live_actions(runner=None)) == set(onboarding.STEPS)


# --- the CLI ---------------------------------------------------------------------


def test_cli_help_is_rc_0(capsys):
    assert cli.main(["--help"]) == 0
    out = capsys.readouterr().out
    for word in ("add", "proof", "control"):
        assert word in out


def test_cli_no_subcommand_is_usage():
    assert cli.main([]) == 2


def test_cli_add_parses_into_a_request():
    got = []

    def add(req, opts):
        got.append((req, opts))
        return onboarding.Outcome(0, "c0123456789abcdef", ("d1",))

    rc = cli.main(
        [
            "add", "acme", "--region", "us", "--owner", "o@acme.example", "--storage-gb", "50",
            "--allow-ip", "192.0.2.1", "--allow-ip", "192.0.2.0/24", "--unlisted",
            "--lookup-domain", "acme.example", "--bench", "--bws-project", "p1",
        ],
        add=add,
    )  # fmt: skip
    assert rc == 0
    req, opts = got[0]
    assert req == onboarding.Request(
        name="acme",
        region="us",
        owner="o@acme.example",
        storage_gb=50,
        allow_ips=("192.0.2.1", "192.0.2.0/24"),
        unlisted=True,
        lookup_domain="acme.example",
        bench=True,
    )
    assert opts.bws_project == "p1"


def test_cli_add_returns_the_outcome_rc_and_prints_the_error(capsys):
    def add(_req, _opts):
        return onboarding.Outcome(1, "", (), "refused: free-mail")

    assert (
        cli.main(
            ["add", "acme", "--region", "eu", "--owner", "o@x.example", "--storage-gb", "1"],
            add=add,
        )
        == 1
    )
    assert "free-mail" in capsys.readouterr().err


def test_cli_add_missing_flag_is_usage():
    assert cli.main(["add", "acme", "--region", "eu"], add=_never) == 2


def test_cli_proof_hands_off_to_the_proof_module(monkeypatch):
    seen: list[Any] = []
    monkeypatch.setattr(cli.proof, "main", lambda argv: _note(seen, argv, 0))
    assert cli.main(["proof", "signer", "--bench"]) == 0
    assert seen == [["signer", "--bench"]]


@pytest.mark.parametrize(("verb", "box"), [("list", "C2"), ("remove", "C2"), ("release", "K2")])
def test_cli_unbuilt_verbs_refuse_naming_their_box(verb, box, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_module", lambda _name: None)
    assert cli.main([verb]) == 2
    assert "not built yet: %s" % box in capsys.readouterr().err


class FakeLifecycle(types.SimpleNamespace):
    """The C2 lifecycle surface the CLI calls, recording each call."""

    class LifecycleError(RuntimeError):
        pass

    def __init__(self):
        super().__init__(calls=[])
        self.Context = types.SimpleNamespace
        for verb in ("list", "update", "suspend", "export", "remove"):
            setattr(self, "cmd_" + verb, self._recorder(verb))

    def _recorder(self, verb):
        def record(ctx, *args, **kw):
            self.calls.append((verb, ctx, args, kw))
            return 0

        return record


def _lifecycle(monkeypatch):
    fake = FakeLifecycle()
    monkeypatch.setattr(cli, "_module", lambda name: fake if name == cli.LIFECYCLE else None)
    return fake


@pytest.mark.parametrize(
    ("argv", "verb", "args", "kw"),
    [
        (["list", "--all"], "list", (), {"include_removed": True}),
        (["suspend", "acme", "--resume"], "suspend", ("acme",), {"resume": True}),
        (["export", "acme"], "export", ("acme",), {}),
        (
            ["remove", "acme", "--delete-data", "--confirm", "acme"],
            "remove",
            ("acme",),
            {"delete_data": True, "confirm": "acme"},
        ),
        (
            ["update", "acme", "--max-machines", "12", "--ring", "small", "--ring-reason", "pilot"],
            "update",
            ("acme",),
            {
                "max_machines": 12, "max_storage_gb": None, "max_expiry_days": None,
                "allow_ips": None, "ring": "small", "ring_reason": "pilot",
            },
        ),
        (
            ["update", "acme", "--clear-allow-ips"],
            "update",
            ("acme",),
            {
                "max_machines": None, "max_storage_gb": None, "max_expiry_days": None,
                "allow_ips": [], "ring": None, "ring_reason": None,
            },
        ),
    ],
)  # fmt: skip
def test_cli_lifecycle_verbs_call_the_c2_commands(monkeypatch, argv, verb, args, kw):
    fake = _lifecycle(monkeypatch)
    built = []

    def context(_lifecycle, **opts):
        built.append(opts)
        return "ctx"

    assert cli.main(argv, context=context) == 0
    assert fake.calls == [(verb, "ctx", args, kw)]
    assert built[0]["bench"] is False


def test_cli_lifecycle_bench_flag_reaches_the_context(monkeypatch):
    _lifecycle(monkeypatch)
    built: list[Any] = []
    cli.main(["list", "--bench"], context=lambda _lc, **o: _note(built, o, "ctx"))
    assert built[0]["bench"] is True


def test_lifecycle_context_binds_the_registry_and_the_live_adapters_lazily(tmp_path):
    fake = FakeLifecycle()
    ctx = cli.lifecycle_context(
        fake, bench=True, query=lambda _d, _s, _p: [], export_root=tmp_path, env={}
    )
    assert ctx.registry.bench is True
    assert ctx.export_root == tmp_path
    company = types.SimpleNamespace(region="eu")
    for seam, call in ((ctx.exporter, "dump_d1"), (ctx.teardown, "undeploy")):
        with pytest.raises(FakeLifecycle.LifecycleError, match="CLOUDFLARE_API_TOKEN"):
            getattr(seam, call)(company)
    with pytest.raises(FakeLifecycle.LifecycleError, match="--bws-project"):
        ctx.store.read(["x"])


def test_cli_lifecycle_usage_is_rc_2(monkeypatch):
    _lifecycle(monkeypatch)
    assert cli.main(["suspend"], context=lambda _lc, **_o: "ctx") == 2


def test_cli_control_ensure_hands_off(monkeypatch):
    seen: list[Any] = []
    monkeypatch.setattr(cli.control_db, "main", lambda argv: _note(seen, argv, 0))
    assert cli.main(["control", "ensure", "--bench"]) == 0
    assert seen == [["ensure", "--bench"]]


def test_cli_dns_hands_off(monkeypatch):
    seen: list[Any] = []
    monkeypatch.setattr(cli.dns, "main", lambda argv: _note(seen, argv, 0))
    assert cli.main(["dns", "ensure", "--check"]) == 0
    assert seen == [["ensure", "--check"]]


def test_the_run_sh_verb_is_registered():
    row = next(v for v in entry.VERBS if v.name == "enterprise")
    assert entry._resolve(row) is run_verbs.enterprise_main
    assert "enterprise add" in run_verbs.HELP
    assert "enterprise proof" in run_verbs.HELP


def test_live_deploy_step_builds_the_portal_with_the_sitekey_before_deploy_account(tmp_path):
    """Bench run 7: deploy_account refused a dist built without the Turnstile sitekey. The build runs after the proxy deploy and before the account deploy, handed the environment that carries the key."""
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    order = []
    seen = {}

    def deploy(module, _argv):
        order.append(module.rsplit(".", 1)[1])
        return 0

    def portal(tree, env):
        order.append("portal")
        seen["tree"], seen["key"] = tree, env.get("TURNSTILE_SITE_KEY")
        return 0

    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        deploy=deploy,
        portal=portal,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
        env={"TURNSTILE_SITE_KEY": "0xKEY"},
    )
    actions["deploy"](ctx)
    assert order.index("portal") < order.index("deploy_account")
    assert seen == {"tree": tmp_path, "key": "0xKEY"}


def test_live_deploy_step_stops_when_the_portal_build_fails(tmp_path):
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    ran: list[str] = []

    def record_deploy(module: str, _argv: Any) -> int:
        ran.append(module)
        return 0

    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        deploy=record_deploy,
        portal=lambda _t, _e: 2,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    with pytest.raises(onboarding.OnboardingError, match="portal build exited 2"):
        actions["deploy"](ctx)
    assert "rediacc_ci.deploy.deploy_account" not in ran


def test_build_portal_refuses_a_missing_sitekey_by_name_and_runs_the_release_row(
    tmp_path, monkeypatch
):
    with pytest.raises(onboarding.OnboardingError, match="TURNSTILE_SITE_KEY"):
        onboarding.build_portal(tmp_path, {"TURNSTILE_SITE_KEY": " "})
    calls: list[tuple[Any, Any, Any]] = []

    def record_call(argv: Any, cwd: Any, env: Any) -> int:
        calls.append((argv, cwd, env))
        return 0

    monkeypatch.setattr(onboarding.subprocess, "call", record_call)
    assert onboarding.build_portal(tmp_path, {"TURNSTILE_SITE_KEY": "0xKEY"}) == 0
    argv, cwd, env = calls[0]
    assert "workers/account/dist/account" in " ".join(argv)
    assert cwd == str(tmp_path / "private/account/web")
    assert env["VITE_TURNSTILE_SITE_KEY"] == "0xKEY"
    assert env["VITE_CI_MODE"] == "false"


def _rollback_world(tmp_path, previous, fail):
    """A deploy step whose fake proxy run records `previous` and whose `fail` module (or `--smoke-only` run) exits 1."""
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    ran = []

    def deploy(module, argv):
        ran.append((module.rsplit(".", 1)[1], argv))
        if "--defer-smoke" in argv:
            record = argv[argv.index("--record") + 1]
            with open(record, "w", encoding="utf-8") as fh:
                json.dump({"previous_version_id": previous}, fh)
        if "--rollback" in argv:
            return 0
        if fail == "account" and module.endswith("deploy_account"):
            return 1
        if fail == "smoke" and "--smoke-only" in argv:
            return 1
        return 0

    actions = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        deploy=deploy,
        portal=_portal_ok,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    return actions, ctx, ran


@pytest.mark.parametrize("fail", ["account", "smoke"])
def test_live_deploy_step_rolls_the_proxy_back_to_the_recorded_version_on_a_later_failure(
    tmp_path, fail
):
    """Review d39e851d.1: a deferred-smoke proxy deploy leaves the new version live and unsmoked, so a failing account deploy or --smoke-only run returns it to the recorded previous version."""
    actions, ctx, ran = _rollback_world(tmp_path, "aaaaaaaa-1111-4222-8333-444444444444", fail)
    with pytest.raises(onboarding.OnboardingError, match="exited 1"):
        actions["deploy"](ctx)
    last_module, last_argv = ran[-1]
    assert last_module == "deploy_proxy"
    assert last_argv[last_argv.index("--rollback") + 1] == "aaaaaaaa-1111-4222-8333-444444444444"


def test_live_deploy_step_with_no_previous_version_fails_without_a_rollback(tmp_path, capsys):
    actions, ctx, ran = _rollback_world(tmp_path, None, "account")
    with pytest.raises(onboarding.OnboardingError, match="deploy_account exited 1"):
        actions["deploy"](ctx)
    assert not any("--rollback" in argv for _m, argv in ran)
    assert "no earlier proxy version to roll back to" in capsys.readouterr().err


def test_live_deploy_step_with_an_unreadable_proxy_record_says_so_instead_of_no_earlier_version(
    tmp_path, capsys
):
    """Review a597b802.1: a corrupt record is not a first deploy, so the run names the live unsmoked version."""
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    inner = []

    def deploy(module, argv):
        inner.append((module.rsplit(".", 1)[1], argv))
        if "--defer-smoke" in argv:
            with open(argv[argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                fh.write("{not json")
        return 1 if module.endswith("deploy_account") else 0

    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    live = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        deploy=deploy,
        portal=_portal_ok,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    with pytest.raises(onboarding.OnboardingError, match="deploy_account exited 1"):
        live["deploy"](ctx)
    err = capsys.readouterr().err
    assert "cannot be read" in err
    assert "no earlier proxy version" not in err
    assert not any("--rollback" in argv for _m, argv in inner)


def test_live_deploy_step_reports_a_failed_proxy_rollback(tmp_path, capsys):
    """Review a597b802.2: a rollback that itself exits non-zero is named, with the version it tried."""
    previous = "aaaaaaaa-1111-4222-8333-444444444444"
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)

    def deploy(module, argv):
        if "--defer-smoke" in argv:
            with open(argv[argv.index("--record") + 1], "w", encoding="utf-8") as fh:
                json.dump({"previous_version_id": previous}, fh)
        if "--rollback" in argv:
            return 3
        return 1 if module.endswith("deploy_account") else 0

    live = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        deploy=deploy,
        portal=_portal_ok,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    with pytest.raises(onboarding.OnboardingError, match="deploy_account exited 1"):
        live["deploy"](ctx)
    assert "the proxy rollback to %s exited 3" % previous in capsys.readouterr().err


def test_live_deploy_step_removes_its_proxy_record_directory(tmp_path):
    """Review a597b802.4: the record's scratch directory does not outlive the step."""
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    seen = []

    def deploy(_module, argv):
        seen.append(argv[argv.index("--record") + 1] if "--record" in argv else None)
        return 0

    live = onboarding.live_actions(
        runner=None,
        out_root=tmp_path,
        deploy=deploy,
        portal=_portal_ok,
        root=tmp_path,
        ensure_dns=lambda _c: "ok",
    )
    live["deploy"](ctx)
    records = [r for r in seen if r]
    assert records
    assert not os.path.exists(os.path.dirname(records[0]))


def test_build_portal_binds_the_sitekey_stripped(tmp_path, monkeypatch):
    """Review 324e02dd.1: the guard tests the stripped key, so the build gets the stripped key."""
    calls = []

    def call(_argv, *, cwd, env):
        del cwd
        calls.append(env)
        return 0

    monkeypatch.setattr(onboarding.subprocess, "call", call)
    assert onboarding.build_portal(tmp_path, {"TURNSTILE_SITE_KEY": "  0xKEY\n"}) == 0
    assert calls[0]["VITE_TURNSTILE_SITE_KEY"] == "0xKEY"
