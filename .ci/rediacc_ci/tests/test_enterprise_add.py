"""`./run.sh enterprise add` (box C1): the resumable onboarding run, its live steps over fakes, and the CLI. Nothing here reaches Cloudflare, bws or AWS."""

from __future__ import annotations

import shutil
import sqlite3
import types
from typing import Any, NoReturn

import pytest

from rediacc_ci import __main__ as entry
from rediacc_ci import paths
from rediacc_ci.core import run_verbs, wrangler
from rediacc_ci.enterprise import cli, onboarding, registry

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


def test_live_buckets_step_creates_buckets_and_queues_and_accepts_existing():
    calls = []

    def runner(argv, *, cwd=None):
        del cwd
        calls.append(argv[len(wrangler.ARGV) :])
        if "backups-acme" in argv:
            return Proc(1, "", "The bucket you tried to create already exists")
        return Proc(0)

    onboarding.live_actions(runner=runner)["buckets"](_ctx(World()))
    assert ["r2", "bucket", "create", "configs-acme", "--jurisdiction", "eu"] in calls
    assert ["r2", "bucket", "create", "backups-acme", "--jurisdiction", "eu"] in calls
    assert ["queues", "create", "backup-replicate-acme"] in calls
    assert ["queues", "create", "backup-replicate-acme-dlq"] in calls


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

    actions = onboarding.live_actions(runner=None, out_root=tmp_path, deploy=deploy, root=tmp_path)
    actions["deploy"](ctx)
    assert [m for m, _ in ran] == [
        "rediacc_ci.deploy.deploy_proxy",
        "rediacc_ci.deploy.deploy_account",
    ]
    proxy_argv, account_argv = ran[0][1], ran[1][1]
    assert "--proxy-config" in proxy_argv
    assert "--account-config" not in proxy_argv
    assert "--account-config" in account_argv
    assert "--proxy-config" not in account_argv
    assert account_argv[account_argv.index("--company-id") + 1] == "c0123456789abcdef"


def test_live_deploy_step_names_the_failed_module(tmp_path):
    _tree(tmp_path)
    ctx = _ctx(World(), {"d1": "11111111-2222-4333-8444-555555555555"})
    onboarding.live_actions(runner=None, out_root=tmp_path)["configs"](ctx)
    actions = onboarding.live_actions(
        runner=None, out_root=tmp_path, deploy=lambda _m, _a: 1, root=tmp_path
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


def test_live_bootstrap_and_invite_are_seams_naming_a1():
    actions = onboarding.live_actions(runner=None)
    for step in ("bootstrap", "invite"):
        with pytest.raises(onboarding.NotBuiltError, match="not built yet: A1"):
            actions[step](_ctx(World()))


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


def test_lifecycle_context_binds_the_registry_and_leaves_the_adapters_unbound(tmp_path):
    fake = FakeLifecycle()
    ctx = cli.lifecycle_context(
        fake, bench=True, query=lambda _d, _s, _p: [], export_root=tmp_path, env={}
    )
    assert ctx.registry.bench is True
    assert ctx.export_root == tmp_path
    for seam, call in ((ctx.exporter, "dump_d1"), (ctx.teardown, "undeploy")):
        with pytest.raises(FakeLifecycle.LifecycleError, match="not built yet"):
            getattr(seam, call)(object())
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


def test_the_run_sh_verb_is_registered():
    row = next(v for v in entry.VERBS if v.name == "enterprise")
    assert entry._resolve(row) is run_verbs.enterprise_main
    assert "enterprise add" in run_verbs.HELP
    assert "enterprise proof" in run_verbs.HELP
