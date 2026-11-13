"""enterprise.lab: the live Lab the proof verbs drive, its seams for the boxes not built yet, and its binding of `enterprise add`. Fakes only."""

from __future__ import annotations

import datetime
import functools
import json
import pathlib
import re
import socket
import subprocess
import sys
import threading
import tomllib
import types
import wsgiref.simple_server
from typing import cast

import pytest

from rediacc_ci import paths
from rediacc_ci.core import https
from rediacc_ci.deploy import deploy_signer
from rediacc_ci.enterprise import lab, onboarding, proof
from rediacc_ci.ops import enterprise_lookup
from rediacc_ci.well_known import BENCH_ORIGIN, GH_API_BASE, PRODUCT_DOMAIN

REAL_URLOPEN = https.urlopen
REAL_CREATE_CONNECTION = socket.create_connection
REAL_RUN = subprocess.run


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test in this file reaches a child process, an HTTPS request or a TLS socket (a loopback connection, the stub server's, is the one allowed): the live readers take fakes."""

    def boom(*_a, **_k):
        raise AssertionError("a test reached a live call")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(https, "urlopen", boom)

    def loopback_only(address, *args, **kwargs):
        if address[0] != "127.0.0.1":
            boom()
        return REAL_CREATE_CONNECTION(address, *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", loopback_only)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.delenv(lab.CONFIG_ENV, raising=False)


def _lab(**kw) -> lab.LiveLab:
    return lab.build(bench=True, **kw)


def test_build_returns_every_method_the_proof_protocol_names():
    built = _lab()
    wanted = {n for n in dir(proof.Lab) if not n.startswith("_")}
    missing = sorted(n for n in wanted if not callable(getattr(built, n, None)))
    assert missing == []


def test_every_protocol_method_has_an_owner():
    wanted = {n for n in dir(proof.Lab) if not n.startswith("_")}
    assert wanted <= set(lab.OWNERS)


def test_load_lab_finds_the_module():
    assert isinstance(proof.load_lab(bench=True), lab.LiveLab)


def test_the_signer_proof_refuses_only_for_the_s2_seam(monkeypatch, capsys):
    monkeypatch.delitem(sys.modules, lab.SEAMS["S2"].module, raising=False)
    monkeypatch.setattr(lab, "_import", lambda _name: None)
    rc = proof.main(["signer", "--bench"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not built yet: S2" in out
    broken = [line for line in out.splitlines() if line.startswith("BROKEN")]
    assert broken
    assert all("not built yet: S2" in line for line in broken)


def test_a_seam_binds_the_module_once_it_exists(monkeypatch):
    fake = types.SimpleNamespace(signers=lambda **_kw: ["signer-bench-eu"])
    monkeypatch.setattr(
        lab, "_import", lambda name: fake if name == lab.SEAMS["S2"].module else None
    )
    assert _lab().signers(bench=True) == ["signer-bench-eu"]


def test_a_built_module_missing_the_function_is_still_named(monkeypatch):
    monkeypatch.setattr(lab, "_import", lambda _name: types.SimpleNamespace())
    with pytest.raises(lab.NotBuiltError, match=r"not built yet: S2 .*has no signers"):
        _lab().signers(bench=True)


@pytest.mark.parametrize(
    ("method", "args", "kwargs", "box"),
    [
        ("export", ("c0123456789abcdef",), {}, "C2"),
        ("remove", ("c0123456789abcdef",), {"delete_data": True, "github_actions": False}, "C2"),
        ("release", (), {}, "K2"),
        ("versions", (["fast"],), {}, "K2"),
        ("issue", ("account-bench", "licence"), {}, "V1"),
        ("fetch", ("acme.example",), {}, "V4"),
        ("mint", ("c0123456789abcdef", "session"), {}, "V6"),
        ("container_app", ("c0123456789abcdef",), {}, "V7"),
        ("read_limits", (), {}, "V8"),
        ("fleet_machine", (), {}, "V9"),
        ("dispatch_release", ("c0123456789abcdef",), {}, "V10"),
        ("captured_mail", ("o@x.example",), {}, "A1"),
    ],
)
def test_unbuilt_parts_raise_a_lab_error_naming_their_box(monkeypatch, method, args, kwargs, box):
    monkeypatch.setattr(lab, "_import", lambda _name: None)
    with pytest.raises(proof.LabError, match="not built yet: %s" % box):
        getattr(_lab(), method)(*args, **kwargs)


def test_not_built_is_a_lab_error_so_the_proof_records_it_broken():
    assert issubclass(lab.NotBuiltError, proof.LabError)


# --- the add binding ---------------------------------------------------------------


class FakeAdd:
    def __init__(self):
        self.calls: list[tuple[onboarding.Request, str]] = []
        self.companies: dict[str, dict] = {}

    def __call__(self, req, stop_after=""):
        self.calls.append((req, stop_after))
        if "gmail" in req.lookup:
            return onboarding.Outcome(1, "", (), "gmail.com is a free-mail domain")
        cid = self.companies.setdefault(req.name, {"id": "c%016x" % (len(self.companies) + 1)})[
            "id"
        ]
        self.companies[req.name].update(name=req.name, region=req.region, state="active")
        if stop_after:
            return onboarding.Outcome(1, cid, ("control-row", "d1"), "stopped after d1 as asked")
        return onboarding.Outcome(0, cid, ())

    def find(self, name):
        return self.companies.get(name)

    def by_id(self, cid):
        return next((c for c in self.companies.values() if c["id"] == cid), None)


def run_partial_verb(verb: str, partial: object, lines: list[str]) -> int:
    """Drive one verb with a lab that implements only the methods that verb calls, as test_enterprise_proof does."""
    return proof.run_verb(verb, cast("proof.Lab", partial), bench=True, out=lines.append)


def _bound(fake: FakeAdd) -> lab.LiveLab:
    return _lab(adder=fake, finder=fake.find, resolver=fake.by_id)


def test_add_maps_the_outcome_and_passes_kill_after():
    fake = FakeAdd()
    got = _bound(fake).add(
        "proof-listed", owner="o@proof-listed.example", unlisted=False,
        lookup_domain="proof-listed.example", kill_after="d1",
    )  # fmt: skip
    assert got.rc == 1
    assert got.company
    assert "stopped" in got.error
    req, stop = fake.calls[0]
    assert stop == "d1"
    assert req.bench is True
    assert req.region == lab.ADD_REGION
    assert req.lookup_domain == "proof-listed.example"


def test_add_refusal_carries_the_free_mail_error():
    got = _bound(FakeAdd()).add(
        "proof-freemail", owner="owner@gmail.com", unlisted=False, lookup_domain="gmail.com"
    )
    assert got.rc == 1
    assert "free-mail" in got.error


def test_ensure_company_adds_once_then_reuses():
    fake = FakeAdd()
    built = _bound(fake)
    first = built.ensure_company("proof-route-a", "eu")
    again = built.ensure_company("proof-route-a", "eu")
    assert first == again
    assert len(fake.calls) == 1
    assert fake.calls[0][0].unlisted is True


def test_ensure_company_raises_a_lab_error_when_the_add_fails():
    def adder(*_args, **_kwargs):
        return onboarding.Outcome(1, "", (), "not built yet: A1")

    built = _lab(adder=adder, finder=lambda _name: None, resolver=lambda _cid: None)
    with pytest.raises(proof.LabError, match="A1"):
        built.ensure_company("proof-route-a", "eu")


def test_ensure_company_with_a_ring_needs_c2(monkeypatch):
    monkeypatch.setattr(lab, "_import", lambda _name: None)
    with pytest.raises(lab.NotBuiltError, match="not built yet: C2"):
        _bound(FakeAdd()).ensure_company("proof-ring-small", "eu", ring="small")


def test_company_hosts_caller_and_words_come_from_the_registry_row():
    fake = FakeAdd()
    built = _bound(fake)
    cid = built.ensure_company("proof-replay-a", "eu")
    account, proxy_host = built.company_hosts(cid)
    assert account.startswith("proof-replay-a.")
    assert proxy_host.startswith("proof-replay-a-proxy.")
    assert built.caller_of(cid) == "account-proof-replay-a"
    assert built.company_words(cid) == ["proof-replay-a", account, proxy_host]


def test_an_unknown_company_id_is_a_lab_error():
    with pytest.raises(proof.LabError, match="no company"):
        _bound(FakeAdd()).company_hosts("cffffffffffffffff")


def test_the_add_proof_runs_through_the_bound_add_and_stops_at_the_a1_seam(monkeypatch, capsys):
    monkeypatch.setattr(lab, "_import", lambda _name: None)
    rc = proof.run_verb("add", _bound(FakeAdd()), bench=True, out=print)
    out = capsys.readouterr().out
    assert rc == 1
    assert "ok      listed company: a killed add exits non-zero" in out
    assert "ok      listed company: the add resumes" in out
    assert "not built yet: A1" in out


# --- the lifecycle binding (box C2) ------------------------------------------------


class FakeLifecycle(types.SimpleNamespace):
    class LifecycleError(RuntimeError):
        pass

    def __init__(self, refuse: set[str] | None = None):
        super().__init__(calls=[], refuse=set(refuse or ()))

    def _maybe(self, verb, ctx, name, **kw):
        self.calls.append((verb, ctx, name, kw))
        if verb in self.refuse or (ctx.env or {}).get("GITHUB_ACTIONS"):
            raise self.LifecycleError("%s refused" % verb)

    def export(self, ctx, name):
        self._maybe("export", ctx, name)

    def remove(self, ctx, name, *, delete_data, confirm=None):
        self._maybe("remove", ctx, name, delete_data=delete_data, confirm=confirm)

    def update(self, ctx, name, **kw):
        self._maybe("update", ctx, name, **kw)


def _with_lifecycle(monkeypatch, fake):
    monkeypatch.setattr(
        lab, "_import", lambda name: fake if name == lab.SEAMS["C2"].module else None
    )
    adder = FakeAdd()
    built = _lab(
        adder=adder,
        finder=adder.find,
        resolver=adder.by_id,
        lifecycle_ctx=lambda _lc, *, bench, env: types.SimpleNamespace(bench=bench, env=env),
    )
    return built, adder


def test_export_and_remove_call_lifecycle_by_name_with_confirm(monkeypatch):
    fake = FakeLifecycle()
    built, _adder = _with_lifecycle(monkeypatch, fake)
    cid = built.ensure_company("proof-remove", "eu")
    assert built.export(cid) == 0
    assert built.remove(cid, delete_data=True, github_actions=False) == 0
    verbs = [(v, n, kw) for v, _ctx, n, kw in fake.calls]
    assert verbs == [
        ("export", "proof-remove", {}),
        ("remove", "proof-remove", {"delete_data": True, "confirm": "proof-remove"}),
    ]
    assert fake.calls[0][1].bench is True


def test_a_lifecycle_refusal_is_a_non_zero_rc(monkeypatch):
    built, _adder = _with_lifecycle(monkeypatch, FakeLifecycle(refuse={"export", "remove"}))
    cid = built.ensure_company("proof-remove", "eu")
    assert built.export(cid) == 1
    assert built.remove(cid, delete_data=True, github_actions=False) == 1


def test_a_lifecycle_refusal_is_printed_to_stderr(monkeypatch, capsys):
    built, _adder = _with_lifecycle(monkeypatch, FakeLifecycle(refuse={"export", "remove"}))
    cid = built.ensure_company("proof-remove", "eu")
    assert built.export(cid) == 1
    assert built.remove(cid, delete_data=True, github_actions=False) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "enterprise export: export refused" in captured.err
    assert "enterprise remove: remove refused" in captured.err


def test_without_github_actions_the_context_inherits_the_environment(monkeypatch):
    fake = FakeLifecycle()
    built, _adder = _with_lifecycle(monkeypatch, fake)
    cid = built.ensure_company("proof-remove", "eu")
    assert built.export(cid) == 0
    assert fake.calls[-1][1].env is None


def test_remove_under_github_actions_carries_the_variable(monkeypatch):
    fake = FakeLifecycle()
    built, _adder = _with_lifecycle(monkeypatch, fake)
    cid = built.ensure_company("proof-remove-ci", "eu")
    assert built.remove(cid, delete_data=True, github_actions=True) == 1
    assert fake.calls[-1][1].env == {"GITHUB_ACTIONS": "true"}


def test_ensure_company_with_a_ring_sets_the_override(monkeypatch):
    fake = FakeLifecycle()
    built, _adder = _with_lifecycle(monkeypatch, fake)
    built.ensure_company("proof-ring-small", "eu", ring="small")
    verb, _ctx, name, kw = fake.calls[-1]
    assert (verb, name, kw["ring"]) == ("update", "proof-ring-small", "small")
    assert kw["ring_reason"]


def test_a_ring_refusal_is_a_lab_error(monkeypatch):
    built, _adder = _with_lifecycle(monkeypatch, FakeLifecycle(refuse={"update"}))
    with pytest.raises(proof.LabError, match="update refused"):
        built.ensure_company("proof-ring-small", "eu", ring="small")


# --- every seam names a module that defines its whole group ------------------------


def _group_missing(box: str) -> list[str]:
    seam = lab.SEAMS[box]
    if seam.module is None:
        return ["<no module>"]
    module = lab._import(seam.module)
    if module is None:
        return ["<%s does not import>" % seam.module]
    # `release` is bound by the lab itself through `lab_release`: rings_run's `release` is its CLI entry.
    wanted = [m for m in lab._GROUPS[box] if not hasattr(lab.LiveLab, m)]
    return [m for m in wanted if not callable(getattr(module, m, None))]


@pytest.mark.parametrize("box", sorted(b for b in lab._GROUPS if b != "C1"))
def test_every_seam_module_defines_each_method_of_its_group(box):
    assert _group_missing(box) == []


def test_the_group_check_sees_a_missing_method_and_a_missing_module(monkeypatch):
    """Control: the check above fails for a method its module lacks, and for a seam with no module."""
    monkeypatch.setitem(lab._GROUPS, "V8", (*lab._GROUPS["V8"], "no_such_reader"))
    assert _group_missing("V8") == ["no_such_reader"]
    monkeypatch.setitem(lab.SEAMS, "V9", lab.Seam(None, "unbuilt"))
    assert _group_missing("V9") == ["<no module>"]


def test_release_binds_lab_release_with_the_proof_arguments(monkeypatch):
    seen = {}

    def lab_release(**kw):
        seen.update(kw)
        return proof.ReleaseResult(1, "c0123456789", "stopped")

    fake = types.SimpleNamespace(lab_release=lab_release)
    monkeypatch.setattr(
        lab, "_import", lambda name: fake if name == lab.SEAMS["K2"].module else None
    )
    got = _lab().release(plant_failure="c0123456789")
    assert got == proof.ReleaseResult(1, "c0123456789", "stopped")
    assert seen == {"skip_pauses": False, "order": "", "plant_failure": "c0123456789", "resume": ""}


def test_release_names_a_module_without_lab_release(monkeypatch):
    fake = types.SimpleNamespace(release=lambda _args, _world: 0)
    monkeypatch.setattr(lab, "_import", lambda _name: fake)
    with pytest.raises(lab.NotBuiltError, match="has no lab_release"):
        _lab().release()


# --- add ---------------------------------------------------------------
# The captured mail and lookup readers: the captured owner mail (box A1's lab group) and the www lookup reader (box V3), over fakes. No test reaches wrangler, D1 or the network.


ROWS_ADD = [
    {"id": "c00000001", "name": "proof-listed", "state": "active"},
    {"id": "c00000002", "name": "proof-unlisted", "state": "active"},
    {"id": "c00000003", "name": "proof-gone", "state": "removed"},
]


def companies_add(_bench):
    return ROWS_ADD


class Mailboxes:
    def __init__(self, mail: dict[str, list[tuple[str, str]]]):
        self.mail = mail
        self.asked: list[str] = []

    def __call__(self, database, sql, params):
        self.asked.append(database)
        assert sql == lab.CAPTURED_SQL
        return [{"subject": s} for to, s in self.mail.get(database, []) if to == params[0]]


def test_captured_mail_reads_each_live_company_database_and_answers_subjects():
    box = Mailboxes({"account-proof-listed": [("owner@a.example", "You are invited")]})
    got = lab.captured_mail("owner@a.example", companies=companies_add, query=box)
    assert got == ["You are invited"]
    assert box.asked == ["account-proof-listed", "account-proof-unlisted"]


def test_captured_mail_for_another_address_is_empty():
    """Control: a mail to someone else is not the owner's."""
    box = Mailboxes({"account-proof-listed": [("someone@b.example", "You are invited")]})
    assert lab.captured_mail("owner@a.example", companies=companies_add, query=box) == []


def test_captured_mail_with_no_live_company_is_a_lab_error():
    with pytest.raises(proof.LabError, match="no live bench company"):
        lab.captured_mail("o@x.example", companies=lambda _b: [ROWS_ADD[2]], query=Mailboxes({}))


def test_a_failed_d1_read_is_a_lab_error_not_an_empty_list():
    def down(_db, _sql, _params):
        raise proof.LabError("wrangler d1 execute account-proof-listed failed")

    with pytest.raises(proof.LabError):
        lab.captured_mail("o@x.example", companies=companies_add, query=down)


class Kv:
    def __init__(self, store: dict[str, str], rc_missing: int = 0):
        self.store = store
        self.rc_missing = rc_missing
        self.argv: list[list[str]] = []

    def __call__(self, argv, cwd, env):
        del cwd, env
        self.argv.append(list(argv))
        key = argv[argv.index("get") + 1]
        if key in self.store:
            return lab.Proc(0, self.store[key] + "\n", "")
        return lab.Proc(self.rc_missing, "Value not found\n", "")


def _key_add(domain: str) -> str:
    return enterprise_lookup.lookup_key("pep", domain)


def test_lookup_hits_the_stored_host():
    kv = Kv({_key_add("acme.example"): "tenant.example.org"})
    assert lab.lookup("ACME.example.", run=kv, pepper="pep") == "tenant.example.org"
    assert "--remote" in kv.argv[0]
    assert "acme.example" not in " ".join(kv.argv[0]), "the domain never reaches argv"


@pytest.mark.parametrize("rc", [0, 1])
def test_lookup_misses_an_absent_key_whatever_wrangler_exits(rc):
    """Control: a domain with no entry misses."""
    assert lab.lookup("other.example", run=Kv({}, rc_missing=rc), pepper="pep") is None


def test_lookup_answers_none_for_free_mail_without_a_read():
    kv = Kv({})
    assert lab.lookup("gmail.com", run=kv, pepper="pep") is None
    assert kv.argv == []


def test_lookup_failure_is_a_lab_error():
    def broken(_argv, _cwd, _env):
        return lab.Proc(1, "", "Authentication error")

    with pytest.raises(proof.LabError, match="exited 1: Authentication error"):
        lab.lookup("acme.example", run=broken, pepper="pep")


def test_lookup_failure_without_a_stated_cause_adds_nothing():
    """THE CONTROL: silent wrangler output leaves the bare exit code, no dangling colon."""

    def broken(_argv, _cwd, _env):
        return lab.Proc(1, "", "")

    with pytest.raises(proof.LabError) as err:
        lab.lookup("acme.example", run=broken, pepper="pep")
    assert str(err.value) == "wrangler kv key get exited 1"


def test_worker_versions_and_rollback_failures_name_wrangler_cause():
    def broken(_argv, _cwd, _env):
        return lab.Proc(1, '{"error": {"text": "no such worker", "notes": []}}', "")

    with pytest.raises(proof.LabError, match="deployments list exited 1: no such worker"):
        lab.worker_versions("account-proof-a", run=broken)
    with pytest.raises(proof.LabError, match="rollback exited 1: no such worker"):
        lab.put_version("account-proof-a", "v1", run=broken)


def test_wrangler_cause_masks_the_worker_the_call_named():
    """Wrangler echoes the Worker it was asked about, and a company's Worker name carries the company name (review 304248ab.1)."""

    def broken(_argv, _cwd, _env):
        return lab.Proc(
            1, '{"error": {"text": "no worker account-acmecorp here", "notes": []}}', ""
        )

    for call in (
        lambda: lab.worker_versions("account-acmecorp", run=broken),
        lambda: lab.put_version("account-acmecorp", "v1", run=broken),
    ):
        with pytest.raises(proof.LabError) as err:
            call()
        assert "acmecorp" not in str(err.value)
        assert "no worker <name> here" in str(err.value)


def test_wrangler_cause_leaves_text_that_names_no_worker_alone():
    """THE CONTROL: a cause that does not quote the Worker is printed as stated."""

    def broken(_argv, _cwd, _env):
        return lab.Proc(1, '{"error": {"text": "Authentication error", "notes": []}}', "")

    with pytest.raises(proof.LabError, match="exited 1: Authentication error"):
        lab.worker_versions("account-acmecorp", run=broken)


def test_lookup_without_the_pepper_is_a_lab_error(monkeypatch):
    monkeypatch.delenv(enterprise_lookup.PEPPER_ENV, raising=False)
    with pytest.raises(proof.LabError, match=enterprise_lookup.PEPPER_ENV):
        lab.lookup("acme.example", run=Kv({}))


def test_the_lab_binds_both_readers_by_name():
    assert lab.SEAMS["A1"].module == lab.__name__
    assert lab.SEAMS["V3"].module == lab.__name__


# --- routing ---------------------------------------------------------------
# The routing readers: who answers a host (live configuration) against who should (the repository), the certificate, the logs and Turnstile (box V4), over fakes. No test reaches Cloudflare, crt.sh or a TLS socket.


D_ROUTING = PRODUCT_DOMAIN


ROWS_ROUTING = [{"id": "c00000001", "name": "acme", "state": "active"}]
DOMAINS_ROUTING = [{"hostname": "eu.%s" % D_ROUTING, "service": "account-eu"}]
ROUTES_ROUTING = [
    {"pattern": "*.%s/*" % D_ROUTING, "script": "catch-all"},
    {"pattern": "acme.%s/*" % D_ROUTING, "script": "account-acme"},
    {"pattern": "acme-proxy.%s/*" % D_ROUTING, "script": "proxy-acme"},
    {"pattern": "dark.%s/*" % D_ROUTING, "script": None},
]


def api_routing(path):
    if path.startswith("/zones?name="):
        return [{"id": "z1"}]
    if path == "/zones/z1/workers/routes":
        return ROUTES_ROUTING
    raise AssertionError(path)


def listing_routing(path):
    assert path == "/accounts/acct/workers/domains"
    return DOMAINS_ROUTING


def worker_routing(host):
    return lab.routed_worker(host, api=api_routing, listing=listing_routing)


def test_a_custom_domain_wins_over_every_route():
    assert worker_routing("eu.%s" % D_ROUTING) == "account-eu"


def test_an_exact_route_wins_over_the_wildcard():
    assert worker_routing("acme.%s" % D_ROUTING) == "account-acme"
    assert worker_routing("acme-proxy.%s" % D_ROUTING) == "proxy-acme"


def test_an_unknown_label_falls_to_the_wildcard_and_a_foreign_host_to_nothing():
    """Control: the specific answers above are not what every host gets."""
    assert worker_routing("nobody.%s" % D_ROUTING) == "catch-all"
    assert worker_routing("example.org") == ""


def test_a_scriptless_route_answers_no_worker():
    assert worker_routing("dark.%s" % D_ROUTING) == ""


def test_fetch_joins_the_probe_and_the_routed_worker():
    got = lab.fetch(
        "acme.%s" % D_ROUTING,
        probe=lambda _h: (200, ("*.%s" % D_ROUTING,)),
        worker_of=lambda _h: "account-acme",
    )
    assert got == proof.Reply(200, "account-acme", ("*.%s" % D_ROUTING,))


CONFIGS_ROUTING = {
    "workers/account/wrangler.bench.toml": (
        'name = "account-bench"\nroutes = [{ pattern = "bench.%s", custom_domain = true }]\n'
    ),
    "workers/proxy/wrangler.bench.toml": (
        'name = "proxy-bench"\nroutes = [{ pattern = "proxy.bench.%s", custom_domain = true }]\n'
    ),
    "workers/ops-health/wrangler.prod.toml": (
        'name = "ops-health"\nroutes = [{ pattern = "status.%s", custom_domain = true }]\n'
    ),
    "workers/proxy/wrangler.template.toml": 'name = "@@NAME@@"\nroutes = [\n  @@ROUTE_ENTRY@@ # x.%s\n]\n',
}


def _declared_routing(tmp_path):
    for rel, text in CONFIGS_ROUTING.items():
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text % D_ROUTING)
    return functools.partial(lab.declared_hosts, tmp_path)


def test_declared_hosts_read_the_tracked_configs_and_skip_the_template(tmp_path):
    assert _declared_routing(tmp_path)() == {
        "bench.%s" % D_ROUTING: "account-bench",
        "proxy.bench.%s" % D_ROUTING: "proxy-bench",
        "status.%s" % D_ROUTING: "ops-health",
    }


def test_a_config_that_does_not_parse_is_a_lab_error(tmp_path):
    """Control: only the template is skipped; any other unreadable config is named, never dropped."""
    declared = _declared_routing(tmp_path)
    (tmp_path / "workers/www/wrangler.prod.toml").parent.mkdir(parents=True)
    (tmp_path / "workers/www/wrangler.prod.toml").write_text("routes = [ @@X@@ ]\n")
    with pytest.raises(proof.LabError, match=r"wrangler\.prod\.toml"):
        declared()


def test_the_tracked_tree_reads(tmp_path):
    del tmp_path
    hosts = lab.declared_hosts()
    assert hosts["bench.%s" % D_ROUTING] == "account-bench"
    assert lab.region_hosts(bench=True) == sorted(
        h for h, w in hosts.items() if w in lab.BENCH_WORKERS
    )


def test_expected_worker_names_a_company_host_and_a_declared_host(tmp_path):
    kw = {"companies": lambda _b: ROWS_ROUTING, "declared": _declared_routing(tmp_path)}
    assert lab.expected_worker("acme.%s" % D_ROUTING, **kw) == "account-acme"
    assert lab.expected_worker("acme-proxy.%s" % D_ROUTING, **kw) == "proxy-acme"
    assert lab.expected_worker("status.%s" % D_ROUTING, **kw) == "ops-health"


def test_expected_worker_refuses_a_host_nothing_names():
    """Control: an unknown host is never compared against an empty expectation."""
    with pytest.raises(proof.LabError, match="names the host"):
        lab.expected_worker(
            "nobody.%s" % D_ROUTING, companies=lambda _b: ROWS_ROUTING, declared=dict
        )


def test_region_and_specific_hosts_split_the_declared_hosts(tmp_path):
    declared = _declared_routing(tmp_path)
    assert lab.region_hosts(bench=True, declared=declared) == [
        "bench.%s" % D_ROUTING,
        "proxy.bench.%s" % D_ROUTING,
    ]
    assert lab.specific_hosts(declared=declared) == ["status.%s" % D_ROUTING]


def test_cert_log_names_split_and_lowercase_each_logged_name():
    body = json.dumps(
        [
            {"name_value": "*.%s\nEU.%s" % (D_ROUTING, D_ROUTING)},
            {"name_value": "eu.%s" % D_ROUTING},
        ]
    )
    assert lab.cert_log_names(fetch_url=lambda _u: (200, body)) == sorted(
        {"*.%s" % D_ROUTING, "eu.%s" % D_ROUTING}
    )


@pytest.mark.parametrize(
    ("status", "body"), [(502, "[]"), (200, "not json"), (200, "[]")], ids=["5xx", "html", "empty"]
)
def test_cert_log_names_never_answer_an_empty_list_for_a_failed_read(status, body):
    """Control: an unreadable or empty log is a lab error, which would otherwise pass the absent-from-logs claim."""
    with pytest.raises(proof.LabError):
        lab.cert_log_names(fetch_url=lambda _u: (status, body))


def test_turnstile_domains_read_the_one_shared_widget():
    bench_host = BENCH_ORIGIN.removeprefix("https://")
    widgets = [
        {"name": "rediacc-console", "domains": [PRODUCT_DOMAIN, bench_host.capitalize()]},
        {"name": "other", "domains": ["example.org"]},
    ]
    got = lab.turnstile_domains(listing=lambda _p: widgets)
    assert got == [PRODUCT_DOMAIN, bench_host]


def test_turnstile_hosts_are_pinned_to_the_literal_domains():
    """Review 09e1a50e.2: the test above derives both sides from well_known, so a wrong host there would still pass; this pins the values to the registry file itself, read independently of the well_known module (a literal copy here is what check:ci-literal-sources refuses)."""
    registry = {}
    for line in (
        (paths.repo_root() / ".ci" / "config" / "well-known.env")
        .read_text(encoding="utf-8")
        .splitlines()
    ):
        key, sep, value = line.partition("=")
        if sep and not key.startswith("#"):
            registry[key.strip()] = value.strip().strip('"')
    assert registry["WK_PRODUCT_DOMAIN"] == PRODUCT_DOMAIN
    assert registry["WK_BENCH_ORIGIN"] == BENCH_ORIGIN
    assert BENCH_ORIGIN == "https://bench." + PRODUCT_DOMAIN


def test_turnstile_refuses_a_missing_or_doubled_widget():
    with pytest.raises(proof.LabError, match="not 1"):
        lab.turnstile_domains(listing=lambda _p: [{"name": "other", "domains": []}])


ROUTE_ROWS_ROUTING = [
    {"id": "c00000001", "name": "proof-route-a", "state": "active"},
    {"id": "c00000002", "name": "proof-route-b", "state": "active"},
]


class RoutingLab:
    """The routing verb's lab with the repository half real and the live half answering what the routes say."""

    def __init__(self, declared, answer):
        self.declared = declared
        self.answer = answer

    def ensure_company(self, label, region, *, ring=None):
        del region, ring
        return next(r["id"] for r in ROUTE_ROWS_ROUTING if r["name"] == label)

    def company_hosts(self, cid):
        name = next(r["name"] for r in ROUTE_ROWS_ROUTING if r["id"] == cid)
        return ("%s.%s" % (name, D_ROUTING), "%s-proxy.%s" % (name, D_ROUTING))

    def turnstile_domains(self):
        return [D_ROUTING]

    def cert_log_names(self):
        return ["*.%s" % D_ROUTING]

    def expected_worker(self, host):
        return lab.expected_worker(
            host, companies=lambda _b: ROUTE_ROWS_ROUTING, declared=self.declared
        )

    def fetch(self, host):
        return proof.Reply(200, self.answer(self, host), ("*.%s" % D_ROUTING,))

    def region_hosts(self, *, bench):
        return lab.region_hosts(bench=bench, declared=self.declared)

    def specific_hosts(self):
        return lab.specific_hosts(declared=self.declared)


def test_routing_proof_holds_when_every_host_reaches_its_worker(tmp_path):
    built = RoutingLab(_declared_routing(tmp_path), lambda lab, host: lab.expected_worker(host))
    lines: list[str] = []
    assert run_partial_verb("routing", built, lines) == 0, lines


def test_routing_proof_breaks_when_a_specific_host_falls_to_a_company_worker(tmp_path):
    """Control: the same verb fails once a declared host is answered by a company Worker."""

    def answer(lab, host):
        return (
            "account-proof-route-a"
            if host == "status.%s" % D_ROUTING
            else lab.expected_worker(host)
        )

    lines: list[str] = []
    built = RoutingLab(_declared_routing(tmp_path), answer)
    assert run_partial_verb("routing", built, lines) == 1
    assert any(line.startswith("BROKEN") and "status." in line for line in lines)


def test_the_cloudflare_credentials_are_required(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    with pytest.raises(proof.LabError, match="CLOUDFLARE_API_TOKEN"):
        lab.account_path("/x")


# --- proxy ---------------------------------------------------------------
# The token readers (box V6) and the proxy readers (box V7): the session presenter, the executor readers, and the drivers that are not built refusing by name. Fakes only.


ROWS_PROXY = [
    {"id": "c0000000a", "name": "proof-a", "state": "active", "region": "eu"},
    {"id": "c0000000b", "name": "proof-b", "state": "active", "region": "eu"},
]


def companies_proxy(_bench):
    return ROWS_PROXY


class Server:
    """Each company host accepts only the session cookie minted for it."""

    def __init__(self, sessions: dict[str, str], status: int | None = None):
        self.sessions = sessions
        self.status = status
        self.sent: list[tuple[str, dict]] = []

    def __call__(self, url, headers):
        self.sent.append((url, headers))
        if self.status is not None:
            return self.status
        host = url.split("/")[2]
        cookie = headers.get("Cookie", "")
        return 200 if cookie == "access_token=%s" % self.sessions.get(host) else 401


def test_a_session_is_admitted_by_its_own_company_and_refused_by_the_other():
    server = Server({"proof-a.%s" % PRODUCT_DOMAIN: "tok-a"})
    own = lab.present("c0000000a", "session", "tok-a", send=server, companies=companies_proxy)
    other = lab.present("c0000000b", "session", "tok-a", send=server, companies=companies_proxy)
    assert own == proof.Answer(True)
    assert other == proof.Answer(False, "HTTP 401")
    assert server.sent[0][0] == "https://proof-a.%s%s" % (PRODUCT_DOMAIN, lab.ME_PATH)


@pytest.mark.parametrize("status", [404, 500, 302])
def test_a_probe_that_is_not_a_yes_or_a_no_is_a_lab_error(status):
    """Control: a broken probe never reads as a refusal, which would pass every refused claim."""
    with pytest.raises(proof.LabError, match="HTTP %d" % status):
        lab.present("c0000000a", "session", "x", send=Server({}, status), companies=companies_proxy)


def test_a_kind_with_no_probe_is_a_lab_error():
    with pytest.raises(proof.LabError, match="no probe presents a cookie-jar"):
        lab.present("c0000000a", "cookie-jar", "x", send=Server({}), companies=companies_proxy)
    with pytest.raises(proof.LabError, match="no minter for a cookie-jar"):
        lab.live_minter("c0000000a", "cookie-jar", session=lambda _c: "s")


HOST_A = "proof-a.%s" % PRODUCT_DOMAIN


class AccountV6:
    """Two bench company Workers and their D1s: owner-mail captures a magic link, verify signs in, api-tokens mints."""

    def __init__(
        self,
        *,
        link=True,
        two_factor=False,
        cookie=True,
        mail_status=200,
        stale=False,
        rival=False,
        early_rival=False,
    ):
        self.early_rival = early_rival
        self.link = link
        self.rival = rival
        self.stale = stale
        self.two_factor = two_factor
        self.cookie = cookie
        self.mail_status = mail_status
        self.mailed = False
        self.posts: list[tuple[str, str, dict]] = []
        self.calls: list[tuple[str, str, dict, dict]] = []
        self.queries: list[tuple[str, str, list]] = []
        self.minted: dict[str, str] = {}
        self.sleeps = 0

    def query(self, database, sql, params):
        self.queries.append((database, sql, list(params)))
        if sql == lab.OWNER_SQL:
            return [{"email": "owner@proof-a.example"}]
        if sql == lab.LINK_SQL:
            # An older link for the same owner, from before the request, stays in the table.
            old = "Sign in: https://%s/account/magic-link/verify?token=tok-old\n" % HOST_A
            rows = [{"text_body": old, "created_at": OLD_AT}] if self.stale else []
            if not (self.link and self.mailed):
                return rows
            body = (
                "Sign in: https://%s/account/magic-link/verify?token=tok-123&next=%%2F\n" % HOST_A
            )
            new = [{"text_body": body, "created_at": NEW_AT}]
            if self.rival:
                rival = "Sign in: https://%s/account/magic-link/verify?token=tok-rival\n" % HOST_A
                new.append({"text_body": rival, "created_at": NEW_AT})
            if self.early_rival:
                # Captured for another sign-in before this request, yet absent from the before-snapshot.
                early = "Sign in: https://%s/account/magic-link/verify?token=tok-early\n" % HOST_A
                new.append({"text_body": early, "created_at": EARLY_AT})
            # Row order is whatever the clocks say: the oldest row may come last or first.
            return new + rows
        if sql == lab.SUBSCRIPTION_SQL:
            return [{"subscription_id": "sub-a"}]
        raise AssertionError(sql)

    def post(self, url, key, body):
        self.posts.append((url, key, body))
        self.mailed = self.mail_status == 200
        return self.mail_status, {}

    def call(self, method, url, headers, body):
        doc = json.loads(body or b"{}")
        self.calls.append((method, url, headers, doc))
        path = url.split(PRODUCT_DOMAIN, 1)[1]
        if path == lab.VERIFY_PATH:
            if doc.get("token") != "tok-123":
                return lab.HttpAnswer(400)
            self.mailed = False  # the link is spent: a later company's baseline sees no mail
            if self.two_factor:
                return lab.HttpAnswer(200, (), b'{"requiresTwoFactor": true}')
            cookies = [("Set-Cookie", "refresh_token=r-1; Path=/")]
            if self.cookie:
                cookies.append(("Set-Cookie", "access_token=sess-a; Path=/; HttpOnly"))
            return lab.HttpAnswer(200, tuple(cookies), b'{"user": {}}')
        if path == lab.TOKENS_PATH:
            if headers.get("Cookie") != "access_token=sess-a":
                return lab.HttpAnswer(401)
            token = "rdt_%s" % doc["scopes"][0]
            self.minted[token] = url.split("/")[2]
            return lab.HttpAnswer(201, (), json.dumps({"token": token}).encode())
        if path == lab.INTROSPECT_PATH:
            bearer = headers.get("Authorization", "")[7:]
            return lab.HttpAnswer(200 if self.minted.get(bearer) == url.split("/")[2] else 401)
        raise AssertionError(path)

    def send(self, url, headers):
        host, path = url.split("/")[2], "/" + url.split("/", 3)[3]
        if path == lab.ME_PATH:
            return 200 if headers.get("Cookie") == "access_token=sess-a" and host == HOST_A else 401
        if path == lab.STATUS_PATH:
            return 200 if self.minted.get(headers.get("Authorization", "")[7:]) == host else 401
        raise AssertionError(path)

    def sleep(self, _s):
        self.sleeps += 1


ASKED_AT = datetime.datetime(2026, 11, 10, 7, 0, 0, tzinfo=datetime.UTC)
OLD_AT = "2026-11-09T07:00:00.000Z"
EARLY_AT = "2026-11-10T06:50:00.000Z"
NEW_AT = "2026-11-10T07:00:05.123Z"


def session_v6(acct: AccountV6) -> str:
    return lab.owner_session(
        "c0000000a",
        companies=companies_proxy,
        query=acct.query,
        post=acct.post,
        api_key=lambda c: "key-%s" % c,
        call=acct.call,
        sleep=acct.sleep,
        clock=ASKED_AT.timestamp,
    )


def test_the_owner_signs_in_through_the_owner_mail_and_its_captured_link():
    acct = AccountV6()
    assert session_v6(acct) == "sess-a"
    ((url, key, body),) = acct.posts
    assert url == "https://%s/account/api/v1/subscriptions/enterprise/owner-mail" % HOST_A
    assert key == "key-c0000000a"
    assert body == {"companyId": "c0000000a", "ownerEmail": "owner@proof-a.example"}
    link = next(q for q in acct.queries if q[1] == lab.LINK_SQL)
    assert link[0] == "account-proof-a"
    assert link[2] == ["owner@proof-a.example"]
    method, verify_url, _headers, doc = acct.calls[0]
    assert (method, verify_url, doc) == (
        "POST",
        "https://%s%s" % (HOST_A, lab.VERIFY_PATH),
        {"token": "tok-123"},
    )


def test_no_captured_link_is_a_lab_error_after_every_try():
    """Control: a mail that never arrived is never a session."""
    acct = AccountV6(link=False)
    with pytest.raises(proof.LabError, match="no magic link"):
        session_v6(acct)
    assert acct.sleeps == lab.MAIL_TRIES - 1
    assert acct.calls == []


def test_an_older_link_for_the_owner_is_never_taken_for_this_requests():
    """Control: a mail that was not captured in time must not fall back to a link from an earlier request."""
    acct = AccountV6(link=False, stale=True)
    with pytest.raises(proof.LabError, match="no magic link"):
        session_v6(acct)
    assert acct.calls == []


def test_the_new_link_is_taken_over_an_older_one_for_the_same_owner():
    acct = AccountV6(stale=True)
    assert session_v6(acct) == "sess-a"
    assert acct.calls[0][3] == {"token": "tok-123"}


def test_two_new_links_are_a_race_and_sign_in_nothing():
    """Review 14377d66.1: a link another sign-in captured in the window is never taken for this request's."""
    acct = AccountV6(stale=True, rival=True)
    with pytest.raises(proof.LabError, match="2 new magic links"):
        session_v6(acct)
    assert acct.calls == []


def test_the_link_read_is_bounded_but_never_to_one_row():
    """Review 12d04dd4.5: the poll reads the newest rows, not the owner's whole history; review 14377d66.2: more than one."""
    limit = re.search(r"LIMIT (\d+)$", lab.LINK_SQL)
    assert limit is not None, lab.LINK_SQL
    assert int(limit.group(1)) == lab.LINK_ROWS
    assert lab.LINK_ROWS > 1


def test_a_link_captured_before_the_request_is_not_taken_for_this_requests():
    """Review 12d04dd4.6: a lone rival whose capture instant precedes the request is disproved, not trusted."""
    acct = AccountV6(early_rival=True)
    assert session_v6(acct) == "sess-a"
    assert acct.calls[0][3] == {"token": "tok-123"}


def test_a_link_without_a_readable_capture_instant_is_never_new():
    rows = [{"text_body": "a", "created_at": "garbage"}, {"text_body": "b"}]
    assert lab._links(rows, 0.0) == set()
    assert lab._links(rows) == {"a", "b"}


def test_a_new_live_lab_starts_with_no_cached_session():
    """Review 14377d66.3: a session lives for one proof run, and constructing the lab is that run."""
    lab._SESSIONS["c0000000a"] = "stale-session"
    lab.LiveLab(bench=True)
    assert lab._SESSIONS == {}


def test_a_refused_owner_mail_signs_in_nothing():
    acct = AccountV6(mail_status=403)
    with pytest.raises(proof.LabError, match="owner-mail call answered HTTP 403"):
        session_v6(acct)
    assert acct.calls == []


@pytest.mark.parametrize(
    ("kw", "match"),
    [({"two_factor": True}, "second factor"), ({"cookie": False}, "no access_token")],
)
def test_a_verify_without_a_session_cookie_is_a_lab_error(kw, match):
    with pytest.raises(proof.LabError, match=match):
        session_v6(AccountV6(**kw))


def minter_v6(acct: AccountV6):
    def minter(company, kind):
        return lab.live_minter(
            company,
            kind,
            session=lambda _c: session_v6(acct),
            companies=companies_proxy,
            query=acct.query,
            call=acct.call,
        )

    return minter


@pytest.mark.parametrize(
    ("kind", "scope"), [("api-token", "license:read"), ("proxy-token", "proxy:exec")]
)
def test_tokens_are_minted_under_the_owner_session_for_the_control_subscription(kind, scope):
    acct = AccountV6()
    token = lab.mint("c0000000a", kind, minter=minter_v6(acct))
    assert token == "rdt_%s" % scope
    created = acct.calls[-1]
    assert created[1] == "https://%s%s" % (HOST_A, lab.TOKENS_PATH)
    assert created[2]["Cookie"] == "access_token=sess-a"
    assert created[3]["scopes"] == [scope]
    assert created[3]["subscriptionId"] == "sub-a"
    assert ("control-bench-eu", lab.SUBSCRIPTION_SQL, ["c0000000a"]) in acct.queries


@pytest.mark.parametrize("kind", ["api-token", "proxy-token"])
def test_a_token_is_admitted_by_its_own_company_and_refused_by_the_other(kind):
    acct = AccountV6()
    token = lab.mint("c0000000a", kind, minter=minter_v6(acct))
    present = functools.partial(
        lab.present, send=acct.send, call=acct.call, companies=companies_proxy
    )
    assert present("c0000000a", kind, token) == proof.Answer(True)
    assert present("c0000000b", kind, token) == proof.Answer(False, "HTTP 401")


def test_the_proxy_token_probe_introspects_its_own_bearer():
    acct = AccountV6()
    lab.present(
        "c0000000a",
        "proxy-token",
        "rdt_x",
        send=acct.send,
        call=acct.call,
        companies=companies_proxy,
    )
    method, url, headers, doc = acct.calls[-1]
    assert (method, url) == ("POST", "https://%s%s" % (HOST_A, lab.INTROSPECT_PATH))
    assert headers["Authorization"] == "Bearer rdt_x"
    assert doc == {"token": "self", "self": True}


@pytest.mark.parametrize("status", [404, 500])
def test_a_token_probe_that_is_not_a_yes_or_a_no_is_a_lab_error(status):
    with pytest.raises(proof.LabError, match="HTTP %d" % status):
        lab.present(
            "c0000000a", "api-token", "x", send=Server({}, status), companies=companies_proxy
        )


def test_two_token_kinds_of_one_company_share_one_owner_sign_in(monkeypatch):
    """Control: without the shared session each kind signs the owner in again."""
    acct = AccountV6()
    signed_in: list[str] = []

    def sign_in(company, **_kw):
        signed_in.append(company)
        return "sess-a"

    monkeypatch.setattr(lab, "owner_session", sign_in)
    shared: dict[str, str] = {}
    for kind in ("api-token", "proxy-token"):
        lab.live_minter(
            "c0000000a",
            kind,
            sessions=shared,
            companies=companies_proxy,
            query=acct.query,
            call=acct.call,
        )
    assert signed_in == ["c0000000a"]


class FakeBws:
    def __init__(self, found):
        self.found = found
        self.asked: list[list[str]] = []

    def read(self, names):
        self.asked.append(list(names))
        return self.found


def test_the_api_key_is_read_under_the_companys_store_name(monkeypatch):
    fake = FakeBws({"c0123456789abcdef_ACCOUNT_SERVER_API_KEY": "key-1"})
    projects: list[str] = []

    def from_env(_cls, project, env=None):
        del env
        projects.append(project)
        return fake

    monkeypatch.setattr(lab.secrets.BwsStore, "from_env", classmethod(from_env))
    env = {lab.BWS_PROJECT_ENV: "proj-1"}
    assert lab.store_api_key("c0123456789abcdef", env=env) == "key-1"
    assert projects == ["proj-1"]
    assert fake.asked == [["c0123456789abcdef_ACCOUNT_SERVER_API_KEY"]]


def test_a_company_with_no_stored_api_key_is_a_lab_error(monkeypatch):
    monkeypatch.setattr(lab.secrets.BwsStore, "from_env", classmethod(lambda _c, _p: FakeBws({})))
    with pytest.raises(proof.LabError, match="no ACCOUNT_SERVER_API_KEY"):
        lab.store_api_key("c0123456789abcdef", env={lab.BWS_PROJECT_ENV: "proj-1"})


STUB_SEEN: list[tuple[str, str, bytes, str]] = []


def stub_app(request, start_response):
    size = int(request.get("CONTENT_LENGTH") or 0)
    body = request["wsgi.input"].read(size) if size else b""
    path = request["PATH_INFO"]
    STUB_SEEN.append((request["REQUEST_METHOD"], path, body, request.get("HTTP_X_PROBE", "")))
    missing = path == "/missing"
    start_response(
        "404 Not Found" if missing else "200 OK", [("Set-Cookie", "access_token=abc; Path=/")]
    )
    return [b"gone" if missing else b'{"ok": true}']


class QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *_args):
        pass


@pytest.fixture
def stub_origin(monkeypatch):
    """A loopback server behind `https.urlopen`: the code under test builds an https URL, the fixture opens it as loopback http."""
    STUB_SEEN.clear()
    server = wsgiref.simple_server.make_server("127.0.0.1", 0, stub_app, handler_class=QuietHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]

    def urlopen(req, *, timeout):
        loop = https.build_request(
            "http://127.0.0.1:%d%s" % (port, req.selector),
            data=req.data,
            headers=dict(req.header_items()),
            method=req.get_method(),
            http="loopback",
        )
        return REAL_URLOPEN(loop, timeout=timeout, http="loopback")

    monkeypatch.setattr(https, "urlopen", urlopen)
    yield
    server.shutdown()
    server.server_close()


@pytest.mark.usefixtures("stub_origin")
def test_http_call_sends_the_method_headers_and_body_and_reads_the_answer():
    answer = lab.http_call("POST", "https://h.example/a/b", {"X-Probe": "p1"}, b'{"n": 1}')
    assert answer.status == 200
    assert answer.json() == {"ok": True}
    assert answer.header_values("Set-Cookie") == ["access_token=abc; Path=/"]
    assert STUB_SEEN == [("POST", "/a/b", b'{"n": 1}', "p1")]


@pytest.mark.usefixtures("stub_origin")
def test_http_call_answers_a_4xx_instead_of_raising():
    answer = lab.http_call("GET", "https://h.example/missing", {}, None)
    assert (answer.status, answer.body) == (404, b"gone")
    assert answer.header_values("Set-Cookie") == ["access_token=abc; Path=/"]


def test_http_call_with_no_answer_is_a_lab_error_naming_the_path_not_the_host(monkeypatch):
    def refused(_req, *, timeout):
        del timeout
        raise ConnectionRefusedError("secret-host.example")

    monkeypatch.setattr(https, "urlopen", refused)
    with pytest.raises(proof.LabError) as raised:
        lab.http_call("GET", "https://secret-host.example/the/path", {}, None)
    assert str(raised.value) == "GET /the/path: ConnectionRefusedError"


def test_the_api_key_needs_the_enterprise_project():
    with pytest.raises(proof.LabError, match=lab.BWS_PROJECT_ENV):
        lab.store_api_key("c0123456789abcdef", env={})


# The config store, the sealed request and the console command (V6 `config-token` and `e2e-envelope`, V7 `console_command`), over a fake of both company Workers and a fake of the shared package's crypto; the real crypto helper is driven at the end of this block, with no network.

HOST_B = "proof-b.%s" % PRODUCT_DOMAIN
SEED = "JBSWY3DPEHPK3PXP"
CEK = "cek-a"
EXEC_VERSION = "1.2.3"


class FakeCrypto:
    """The shared package's crypto, as `ts_crypto` answers it: every operation recorded, nothing encrypted."""

    def __init__(self, *, proxy_capable=True):
        self.proxy_capable = proxy_capable
        self.ops: list[dict] = []

    def __call__(self, request):
        self.ops.append(request)
        op = request["op"]
        if op == "setup":
            return {
                "cek": CEK,
                "body": {"slots": [{"method": "password"}], "pw": request["password"]},
            }
        if op == "unwrap":
            if request["wrappedCek"] != "wrapped:%s" % request["password"]:
                raise proof.LabError("the crypto helper (unwrap) exited 1")
            return {"cek": CEK}
        if op == "push":
            return {"encryptedBlob": "blob", "envelope": {"v": 3}}
        if op == "seal-cek":
            return {"v": 1, "sealed": request["cek"], "to": request["publicKey"]}
        if op == "seal-request":
            return {"v": 1, "to": request["publicKey"], "inner": request["headers"]}
        if op == "contract":
            return {"version": "dev", "proxyCapable": self.proxy_capable}
        raise AssertionError(op)


class StoreV6(AccountV6):
    """AccountV6 plus each company's config store, second factor, tunnel and console."""

    def __init__(
        self, *, configured=False, configs=0, tfa=False, setup_status=201, exec_lines=None, **kw
    ):
        super().__init__(**kw)
        self.configured = configured
        self.configs = configs
        self.tfa = tfa
        self.setup_status = setup_status
        self.elevated = False
        self.reauth_mailed = False
        self.enable_code = ""
        self.disabled_with = ""
        self.config_tokens = {HOST_A: {"rct-old"}, HOST_B: set()}
        self.password = ""
        self.pushed: list[dict] = []
        self.granted: dict | None = None
        self.execs: list[dict] = []
        result = {"kind": "result", "result": {"success": True, "exitCode": 0, "stdout": ""}}
        self.exec_lines = exec_lines if exec_lines is not None else [{"kind": "heartbeat"}, result]

    def query(self, database, sql, params):
        if sql == lab.REAUTH_SQL:
            self.queries.append((database, sql, list(params)))
            if not self.reauth_mailed:
                return []
            body = "Confirm: https://%s/account/reauth/verify?token=re-1\n" % HOST_A
            return [{"text_body": body, "created_at": NEW_AT}]
        return super().query(database, sql, params)

    def _json(self, status, doc):
        return lab.HttpAnswer(status, (), json.dumps(doc).encode())

    def call(self, method, url, headers, body):
        host, path = url.split("/")[2], "/" + url.split("/", 3)[3]
        signed_in = headers.get("Cookie") == "access_token=sess-a" and host == HOST_A
        doc = json.loads(body or b"{}")
        if path == lab.SERVER_INFO_PATH:
            return self._json(
                200, {"e2e": {"keys": [{"keyId": "v1", "publicKeySpki": "pk-%s" % host}]}}
            )
        if path == lab.TUNNEL_PATH:
            if doc.get("to") != "pk-%s" % host:
                return self._json(400, {"error": "Decryption failed"})
            bearer = doc["inner"].get("Authorization", "")[7:]
            inner = 200 if self.minted.get(bearer) == host else 401
            return self._json(200, {"v": 1, "iv": "x", "ct": "y", "status": inner})
        if path == lab.CONFIG_SESSION_PATH:
            token = headers.get("X-Config-Token", "")
            if token not in self.config_tokens[host]:
                return self._json(401, {"error": "Config auth failed"})
            self.config_tokens[host].add("rct-next")
            return self._json(
                200, {"newServerToken": "rct-next", "sdk_derived": "sd", "sdkEpoch": 7}
            )
        if method == "PUT" and path.startswith(lab.CONFIGS_PATH + "/"):
            assert headers.get("X-Config-Token") in self.config_tokens[host]
            self.pushed.append(doc)
            self.configs += 1
            return self._json(201, {"version": 1})
        own = (
            lab.STORE_INFO_PATH,
            lab.REAUTH_PATH,
            lab.REAUTH_VERIFY_PATH,
            lab.TFA_STATUS_PATH,
            lab.TFA_SETUP_PATH,
            lab.TFA_ENABLE_PATH,
            lab.TFA_DISABLE_PATH,
            lab.SETUP_PATH,
            lab.BOOTSTRAP_PATH,
        )
        if path in own or path.startswith(lab.CONSOLE_PATH):
            self.calls.append((method, url, headers, doc))
            if not signed_in:
                return lab.HttpAnswer(401)
            return self._owned(path, headers, doc)
        return super().call(method, url, headers, body)

    def _owned(self, path, headers, doc):
        if path == lab.STORE_INFO_PATH:
            if not self.configured:
                return self._json(200, {"configured": False})
            return self._json(
                200, {"configured": True, "storeId": "st-a", "configCount": self.configs}
            )
        if path == lab.REAUTH_PATH:
            self.reauth_mailed = True
            return self._json(200, {"sent": True})
        if path == lab.REAUTH_VERIFY_PATH:
            self.elevated = doc.get("token") == "re-1"
            return self._json(200 if self.elevated else 400, {"elevated": self.elevated})
        if path == lab.TFA_STATUS_PATH:
            return self._json(200, {"enabled": self.tfa})
        if (
            path in (lab.TFA_SETUP_PATH, lab.TFA_ENABLE_PATH, lab.TFA_DISABLE_PATH)
            and not self.elevated
        ):
            return self._json(403, {"reauthRequired": True})
        if path == lab.TFA_SETUP_PATH:
            return self._json(200, {"secret": SEED})
        if path == lab.TFA_ENABLE_PATH:
            self.tfa, self.enable_code = True, doc["code"]
            return self._json(200, {"enabled": True})
        if path == lab.TFA_DISABLE_PATH:
            if doc["code"] == self.enable_code:
                return self._json(400, {"error": "spent"})
            self.tfa, self.disabled_with = False, doc["code"]
            return self._json(200, {"disabled": True})
        if path == lab.SETUP_PATH:
            assert self.tfa, "setup is 2FA gated"
            assert self.elevated, "setup is elevated gated"
            if self.setup_status != 201:
                return self._json(self.setup_status, {"error": "boom"})
            self.configured, self.password = True, doc["pw"]
            self.config_tokens[HOST_A].add("rct-init")
            return self._json(201, {"store": {"id": "st-a"}, "initialToken": "rct-init"})
        if path == lab.BOOTSTRAP_PATH:
            assert doc == {"storeId": "st-a", "method": "password"}
            self.config_tokens[HOST_A].add("rct-boot")
            slot = {"token": "rct-boot", "serverSecret": "ss", "kdfParams": {"method": "password"}}
            return self._json(200, {**slot, "wrappedCek": "wrapped:%s" % self.password})
        return self._console(path, headers, doc)

    def _console(self, path, headers, doc):
        if path == lab.CONSOLE_PATH + "/session":
            return self._json(201, {"sessionId": "es-1", "publicKey": "epk"})
        if path == lab.CONSOLE_PATH + "/session/es-1/cek":
            self.granted = doc
            return self._json(200, {"ok": True})
        if path == lab.CONSOLE_PATH + "/exec":
            self.execs.append(doc)
            if doc["contractVersion"] != EXEC_VERSION:
                return self._json(
                    409,
                    {"error": "contract_version_mismatch", "executorContractVersion": EXEC_VERSION},
                )
            ready = (
                headers.get("X-Config-Session") == "es-1"
                and self.granted == {"v": 1, "sealed": CEK, "to": "epk"}
                and self.configs > 0
            )
            if not ready:
                return self._json(404, {"code": "EXECUTOR_SESSION_UNKNOWN"})
            stream = "\n".join(json.dumps(line) for line in self.exec_lines) + "\n"
            return lab.HttpAnswer(200, (), stream.encode())
        raise AssertionError(path)


def store_minter(acct: StoreV6, crypto: FakeCrypto):
    def minter(company, kind):
        return lab.live_minter(
            company,
            kind,
            session=lambda _c: session_v6(acct),
            companies=companies_proxy,
            query=acct.query,
            call=acct.call,
            crypto=crypto,
            api_key=lambda c: "key-%s" % c,
            sleep=acct.sleep,
            clock=ASKED_AT.timestamp,
        )

    return minter


def store_present(acct: StoreV6):
    return functools.partial(lab.present, send=acct.send, call=acct.call, companies=companies_proxy)


def test_a_config_token_sets_the_store_up_under_a_second_factor_that_is_dropped_again():
    acct, crypto = StoreV6(), FakeCrypto()
    token = lab.mint("c0000000a", "config-token", minter=store_minter(acct, crypto))
    assert token == "rct-init"
    order = [c[1].split(PRODUCT_DOMAIN, 1)[1] for c in acct.calls if "magic-link" not in c[1]]
    assert order == [
        lab.STORE_INFO_PATH,
        lab.REAUTH_PATH,
        lab.REAUTH_VERIFY_PATH,
        lab.TFA_STATUS_PATH,
        lab.TFA_SETUP_PATH,
        lab.TFA_ENABLE_PATH,
        lab.SETUP_PATH,
        lab.TFA_DISABLE_PATH,
    ]
    assert acct.tfa is False, (
        "the owner's magic-link sign-in must not be left asking for a second factor"
    )
    assert acct.disabled_with
    assert acct.enable_code not in ("", acct.disabled_with)
    assert acct.password == lab.store_password("c0000000a", api_key=lambda c: "key-%s" % c)
    assert ("account-proof-a", lab.REAUTH_SQL, ["owner@proof-a.example"]) in acct.queries


def test_an_existing_store_is_opened_through_its_password_slot_with_no_second_factor():
    acct, crypto = StoreV6(configured=True), FakeCrypto()
    acct.password = lab.store_password("c0000000a", api_key=lambda c: "key-%s" % c)
    token = lab.mint("c0000000a", "config-token", minter=store_minter(acct, crypto))
    assert token == "rct-boot"
    paths = [c[1].split(PRODUCT_DOMAIN, 1)[1] for c in acct.calls]
    assert lab.TFA_ENABLE_PATH not in paths
    assert lab.SETUP_PATH not in paths
    assert [o["op"] for o in crypto.ops] == ["unwrap"]


def test_a_store_whose_slot_the_proof_cannot_open_is_a_lab_error():
    """Control: a store set up by someone else (another password) never yields a token."""
    acct, crypto = StoreV6(configured=True), FakeCrypto()
    acct.password = "someone-elses"
    with pytest.raises(proof.LabError, match="unwrap"):
        lab.mint("c0000000a", "config-token", minter=store_minter(acct, crypto))


def test_an_owner_with_a_second_factor_already_is_refused_before_setup():
    acct = StoreV6(tfa=True)
    with pytest.raises(proof.LabError, match="already has a second factor"):
        lab.mint("c0000000a", "config-token", minter=store_minter(acct, FakeCrypto()))
    assert not acct.configured


def test_a_failed_setup_still_drops_the_second_factor():
    acct = StoreV6(setup_status=500)
    with pytest.raises(proof.LabError, match="config store setup answered HTTP 500"):
        lab.mint("c0000000a", "config-token", minter=store_minter(acct, FakeCrypto()))
    assert acct.tfa is False


def test_the_store_password_is_derived_from_the_server_key_and_differs_per_company():
    first = lab.store_password("c0000000a", api_key=lambda _c: "key-1")
    assert first == lab.store_password("c0000000a", api_key=lambda _c: "key-1")
    assert first != lab.store_password("c0000000b", api_key=lambda _c: "key-2")
    assert "key-1" not in first


def test_a_config_token_is_admitted_by_its_own_company_and_refused_by_the_other():
    acct = StoreV6()
    token = lab.mint("c0000000a", "config-token", minter=store_minter(acct, FakeCrypto()))
    present = store_present(acct)
    assert present("c0000000a", "config-token", token) == proof.Answer(True)
    assert present("c0000000b", "config-token", token) == proof.Answer(False, "HTTP 401")


def test_an_envelope_is_sealed_to_the_companys_published_key_under_a_fresh_token():
    acct, crypto = StoreV6(), FakeCrypto()
    envelope = json.loads(lab.mint("c0000000a", "e2e-envelope", minter=store_minter(acct, crypto)))
    assert envelope["to"] == "pk-%s" % HOST_A
    (sealed,) = [o for o in crypto.ops if o["op"] == "seal-request"]
    assert (sealed["method"], sealed["path"], sealed["keyId"]) == ("GET", lab.STATUS_PATH, "v1")
    assert sealed["headers"] == {"Authorization": "Bearer rdt_license:read"}


def test_an_envelope_opens_on_its_own_company_and_does_not_open_on_the_other():
    acct = StoreV6()
    envelope = lab.mint("c0000000a", "e2e-envelope", minter=store_minter(acct, FakeCrypto()))
    present = store_present(acct)
    assert present("c0000000a", "e2e-envelope", envelope) == proof.Answer(True)
    assert present("c0000000b", "e2e-envelope", envelope) == proof.Answer(
        False, "HTTP 400 (Decryption failed)"
    )


@pytest.mark.parametrize(
    ("status", "doc", "match"),
    [
        (500, {}, "e2e-envelope probe answered HTTP 500"),
        (400, {"error": "Invalid encrypted envelope"}, "HTTP 400"),
        (200, {"v": 1}, "no inner status"),
        (200, {"status": 404}, r"e2e-envelope \(inner\) probe answered HTTP 404"),
    ],
)
def test_a_tunnel_answer_that_is_not_a_yes_or_a_no_is_a_lab_error(status, doc, match):
    """Control: neither a broken tunnel nor a malformed envelope ever reads as the other company's refusal."""

    def call(_method, _url, _headers, _body):
        return lab.HttpAnswer(status, (), json.dumps(doc).encode())

    with pytest.raises(proof.LabError, match=match):
        lab.present("c0000000a", "e2e-envelope", "{}", call=call, companies=companies_proxy)


def test_a_company_publishing_no_e2e_key_is_a_lab_error():
    def call(_method, _url, _headers, _body):
        return lab.HttpAnswer(200, (), b'{"e2e": {"keys": []}}')

    with pytest.raises(proof.LabError, match="0 E2E keys"):
        lab.e2e_envelope(
            "c0000000a", "t", companies=companies_proxy, call=call, crypto=FakeCrypto()
        )


def test_the_replay_proof_holds_for_every_kind():
    acct, crypto = StoreV6(), FakeCrypto()

    class Lab:
        def ensure_company(self, label, region, *, ring=None):
            del region, ring
            return {"proof-replay-a": "c0000000a", "proof-replay-b": "c0000000b"}[label]

        def mint(self, company, kind):
            return lab.mint(company, kind, minter=store_minter(acct, crypto))

        def present(self, company, kind, artifact):
            return store_present(acct)(company, kind, artifact)

    lines: list[str] = []
    assert run_partial_verb("replay", Lab(), lines) == 0, lines
    held = [line for line in lines if line.startswith("ok")]
    for kind in proof.REPLAY_KINDS:
        assert "ok      %s: accepted by its own company" % kind in held
        assert "ok      %s: refused by the other company" % kind in held


def console_v7(acct: StoreV6, crypto: FakeCrypto) -> proof.Answer:
    return lab.console_command(
        "c0000000a",
        session=lambda _c: session_v6(acct),
        companies=companies_proxy,
        query=acct.query,
        call=acct.call,
        crypto=crypto,
        api_key=lambda c: "key-%s" % c,
        sleep=acct.sleep,
        clock=ASKED_AT.timestamp,
    )


NAMESPACES_PROXY = [
    {"id": "ns-a", "script": "proxy-proof-a", "class": "OrgExecutor"},
    {"id": "ns-a2", "script": "proxy-proof-a", "class": "ExecutorCapacity"},
    {"id": "ns-b", "script": "proxy-proof-b", "class": "OrgExecutor"},
]
APPS_PROXY = [
    {"id": "app-a", "durable_objects": {"namespace_id": "ns-a"}},
    {"id": "app-b", "durable_objects": {"namespace_id": "ns-b"}},
]


def listing_proxy(path):
    assert path == "/accounts/acct/workers/durable_objects/namespaces"
    return NAMESPACES_PROXY


def api_proxy(path):
    assert path == "/accounts/acct/containers/applications"
    return APPS_PROXY


def test_each_company_has_its_own_durable_object_and_container_app():
    kw = {"listing": listing_proxy, "companies": companies_proxy}
    assert lab.durable_object("c0000000a", **kw) == "ns-a"
    assert lab.durable_object("c0000000b", **kw) == "ns-b"
    assert lab.container_app("c0000000a", api=api_proxy, **kw) == "app-a"
    assert lab.container_app("c0000000b", api=api_proxy, **kw) == "app-b"


def test_a_company_without_its_namespace_or_app_is_a_lab_error():
    """Control: a missing executor never reads as an id the claim could compare."""
    with pytest.raises(proof.LabError, match="0 OrgExecutor"):
        lab.durable_object("c0000000a", listing=lambda _p: [], companies=companies_proxy)
    with pytest.raises(proof.LabError, match="0 container"):
        lab.container_app(
            "c0000000a", listing=listing_proxy, api=lambda _p: [], companies=companies_proxy
        )


def test_two_apps_on_one_namespace_are_a_lab_error():
    doubled = [*APPS_PROXY, {"id": "app-a2", "durable_objects": {"namespace_id": "ns-a"}}]
    with pytest.raises(proof.LabError, match="2 container"):
        lab.container_app(
            "c0000000a", listing=listing_proxy, api=lambda _p: doubled, companies=companies_proxy
        )


def test_a_console_command_runs_through_a_granted_executor_session():
    acct, crypto = StoreV6(), FakeCrypto()
    assert console_v7(acct, crypto) == proof.Answer(True)
    (pushed,) = acct.pushed
    assert (pushed["version"], pushed["sdkEpoch"]) == (1, 7)
    push = next(o for o in crypto.ops if o["op"] == "push")
    assert (push["config"]["resources"], push["storeId"], push["cek"]) == ({}, "st-a", CEK)
    assert acct.granted == {"v": 1, "sealed": CEK, "to": "epk"}
    # The source tree's contract version is refused once, and the executor's own is sent again.
    assert [e["contractVersion"] for e in acct.execs] == ["dev", EXEC_VERSION]
    assert acct.execs[-1]["pathKey"] == lab.CONSOLE_PATH_KEY


def test_a_store_that_holds_a_config_is_not_pushed_to_again():
    acct, crypto = StoreV6(configured=True, configs=1), FakeCrypto()
    acct.password = lab.store_password("c0000000a", api_key=lambda c: "key-%s" % c)
    assert console_v7(acct, crypto) == proof.Answer(True)
    assert acct.pushed == []


@pytest.mark.parametrize(
    ("lines", "detail"),
    [
        ([{"kind": "result", "result": {"success": False, "exitCode": 2}}], "exit code 2"),
        ([{"kind": "heartbeat"}], "the exec stream ended without a result"),
        ([{"kind": "result", "result": {"success": True, "exitCode": 1}}], "exit code 1"),
    ],
)
def test_a_command_that_did_not_succeed_is_refused_never_admitted(lines, detail):
    """Control: only a result line with success and exit code 0 is a command that ran."""
    acct = StoreV6(exec_lines=lines)
    assert console_v7(acct, FakeCrypto()) == proof.Answer(False, detail)


def test_an_exec_refused_by_the_worker_is_refused_with_its_status(monkeypatch):
    acct = StoreV6()
    acct.granted = None

    def no_grant(path, headers, doc):
        if path.endswith("/cek"):
            return acct._json(200, {"ok": True})
        return StoreV6._console(acct, path, headers, doc)

    monkeypatch.setattr(acct, "_console", no_grant)
    assert console_v7(acct, FakeCrypto()) == proof.Answer(False, "HTTP 404")


def test_a_command_the_contract_does_not_proxy_is_never_sent():
    acct = StoreV6()
    with pytest.raises(proof.LabError, match="not a proxy-capable command"):
        console_v7(acct, FakeCrypto(proxy_capable=False))
    assert acct.calls == []


TSX = paths.repo_root() / "node_modules" / ".bin" / "tsx"


@pytest.fixture
def tsx_only(monkeypatch):
    """The one child process these tests may start is the repository's tsx running the crypto helper, which makes no network call."""

    def run(argv, *args, **kwargs):
        assert argv[0] == str(TSX), argv
        return REAL_RUN(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", run)


@pytest.mark.usefixtures("tsx_only")
@pytest.mark.skipif(not TSX.exists(), reason="the repository's tsx is not installed")
def test_the_real_crypto_helper_wraps_unwraps_seals_and_reads_the_contract():
    """The shared package's own functions, driven through `ts_crypto` with no network."""
    made = lab.ts_crypto({"op": "setup", "password": "pw-proof-1"})
    slot = made["body"]["slots"][0]
    assert (slot["method"], made["body"]["requirePasskey"]) == ("password", False)
    opened = lab.ts_crypto(
        {
            "op": "unwrap",
            "password": "pw-proof-1",
            "kdfParams": slot["kdfParams"],
            "wrappedCek": slot["wrappedCek"],
            "serverSecret": made["body"]["serverSecret"],
        }
    )
    assert opened["cek"] == made["cek"]
    key = made["body"]["x25519PublicKey"]
    sealed = lab.ts_crypto(
        {
            "op": "seal-request",
            "publicKey": key,
            "keyId": "v1",
            "method": "GET",
            "path": lab.STATUS_PATH,
            "headers": {},
            "body": None,
        }
    )
    assert sorted(sealed) == ["ct", "eph", "iv", "kid", "salt", "v"]
    assert sorted(lab.ts_crypto({"op": "seal-cek", "cek": made["cek"], "publicKey": key})) == [
        "ct",
        "eph",
        "iv",
        "salt",
        "v",
    ]
    contract = lab.ts_crypto({"op": "contract", "pathKey": lab.CONSOLE_PATH_KEY})
    assert contract["proxyCapable"] is True
    pushed = lab.ts_crypto(
        {
            "op": "push",
            "config": lab.proof_config("b58c2f1a-9d34-4e6b-8f21-6c0d94a7c0f1"),
            "version": 1,
            "sdkEpoch": 1,
            "sdkDerived": made["body"]["serverSecret"],
            "cek": made["cek"],
            "storeId": "st-1",
        }
    )
    assert pushed["encryptedBlob"]
    assert isinstance(pushed["envelope"], dict)


@pytest.mark.usefixtures("tsx_only")
@pytest.mark.skipif(not TSX.exists(), reason="the repository's tsx is not installed")
def test_a_failing_crypto_operation_is_a_lab_error_that_quotes_no_input():
    """Control: a wrong password fails the unwrap, and the error carries neither the password nor stderr."""
    made = lab.ts_crypto({"op": "setup", "password": "pw-right"})
    slot = made["body"]["slots"][0]
    with pytest.raises(proof.LabError) as raised:
        lab.ts_crypto(
            {
                "op": "unwrap",
                "password": "pw-wrong-never-shown",
                "kdfParams": slot["kdfParams"],
                "wrappedCek": slot["wrappedCek"],
                "serverSecret": made["body"]["serverSecret"],
            }
        )
    assert str(raised.value).startswith("the crypto helper (unwrap) exited ")
    assert "pw-wrong" not in str(raised.value)


def test_egress_ips_read_cloudflares_view_of_each_family():
    def fetch(url):
        if "1.1.1.1" in url:
            return "fl=1\nip=203.0.113.7\nts=1\n"
        raise OSError("no IPv6 route")

    assert lab.egress_ips(fetch=fetch) == ["203.0.113.7"]


def test_no_egress_answer_is_a_lab_error_not_an_empty_list():
    def fetch(_url):
        raise OSError("offline")

    with pytest.raises(proof.LabError, match="public IP"):
        lab.egress_ips(fetch=fetch)


def scope_query(ips):
    def query(database, sql, params):
        assert (database, sql, params) == ("control-bench-eu", lab.SCOPE_IPS_SQL, ["c0000000a"])
        return [{"allow_ips": ips}]

    return query


class Redeploy:
    def __init__(
        self,
        fail: str = "",
        fail_update_to: str | None = None,
        fail_times: int = 1,
        raises: type[BaseException] = onboarding.OnboardingError,
    ):
        self.fail = fail
        self.fail_times = fail_times
        self.raises = raises
        self.fail_update_to = fail_update_to
        self.tries = 0
        self.events: list[str] = []
        self.contexts: list[onboarding.Context] = []

    def update(self, name, ips):
        self.events.append("update:%s:%s" % (name, ",".join(ips)))
        if self.fail_update_to is not None and ",".join(ips) == self.fail_update_to:
            raise proof.LabError("update failed")

    def step(self, name):
        def run(ctx):
            self.events.append(name)
            self.contexts.append(ctx)
            if name == self.fail and self.fail_times > 0:
                self.fail_times -= 1
                self.tries += 1
                raise self.raises("company x: %s exited 1 (try %d)" % (name, self.tries))
            return ""

        return run

    def actions(self):
        return {name: self.step(name) for name in lab.ALLOWLIST_STEPS}


def allow_v7(redeploy: Redeploy, ips, d1=None, before='["198.51.100.1"]'):
    return lab.set_allowlist(
        "c0000000a",
        ips,
        companies=companies_proxy,
        query=scope_query(before),
        update=redeploy.update,
        d1_ids=lambda: {"account-proof-a": "uuid-a"} if d1 is None else d1,
        actions=redeploy.actions(),
        sleep=lambda _s: redeploy.events.append("settle"),
    )


def test_set_allowlist_writes_the_scope_then_regenerates_and_redeploys():
    redeploy = Redeploy()
    allow_v7(redeploy, ["203.0.113.7"])
    assert redeploy.events == ["update:proof-a:203.0.113.7", "configs", "deploy", "settle"]
    assert redeploy.contexts[0].plan.request.name == "proof-a"
    ctx = redeploy.contexts[0]
    assert ctx.plan.request.allow_ips == ("203.0.113.7",)
    assert ctx.plan.request.bench is True
    assert ctx.plan.environment == onboarding.BENCH_ENVIRONMENT
    assert ctx.plan.company_id == "c0000000a"
    assert ctx.details == {"d1": "uuid-a"}


def test_an_empty_list_clears_the_allowlist_through_the_same_redeploy():
    redeploy = Redeploy()
    allow_v7(redeploy, [])
    assert redeploy.events[0] == "update:proof-a:"
    assert redeploy.contexts[0].plan.request.allow_ips == ()


def test_a_company_without_its_d1_changes_nothing():
    """Control: the driver never creates a database or writes a scope it cannot deploy."""
    redeploy = Redeploy()
    with pytest.raises(proof.LabError, match="no account D1"):
        allow_v7(redeploy, ["203.0.113.7"], d1={})
    assert redeploy.events == []


def test_a_failed_redeploy_is_a_lab_error_and_the_previous_allowlist_returns():
    """Control: the control row never keeps an allowlist the Workers did not get."""
    redeploy = Redeploy(fail="deploy")
    with pytest.raises(proof.LabError, match="deploy exited 1"):
        allow_v7(redeploy, ["203.0.113.7"])
    assert "settle" not in redeploy.events
    assert redeploy.events == [
        "update:proof-a:203.0.113.7",
        "configs",
        "deploy",
        "update:proof-a:198.51.100.1",
        # the Workers get the previous list again, so they and the row agree (review 4ec9e6b7.2)
        "configs",
        "deploy",
    ]


def test_a_failed_redeploy_of_the_previous_list_is_a_note_on_the_original_error():
    """Review 4ec9e6b7.2: a row put back while a Worker still serves the new list is named, never silent."""
    redeploy = Redeploy(fail="deploy", fail_times=2)
    with pytest.raises(proof.LabError, match="deploy exited 1") as e:
        allow_v7(redeploy, ["203.0.113.7"])
    (note,) = e.value.__notes__
    assert "redeploying the previous list" in note
    assert "may still serve the new list" in note


@pytest.mark.parametrize("error", [RuntimeError, ValueError, KeyError])
def test_a_step_failure_of_any_kind_puts_the_previous_allowlist_back(error):
    """Review 4ec9e6b7.1: the restore is not limited to a LabError."""
    redeploy = Redeploy(fail="configs", raises=error)
    with pytest.raises(error):
        allow_v7(redeploy, ["203.0.113.7"])
    assert redeploy.events[:3] == [
        "update:proof-a:203.0.113.7",
        "configs",
        "update:proof-a:198.51.100.1",
    ]


def test_a_company_that_had_no_allowlist_gets_none_back():
    redeploy = Redeploy(fail="configs")
    with pytest.raises(proof.LabError, match="configs exited 1"):
        allow_v7(redeploy, ["203.0.113.7"], before=None)
    assert redeploy.events[2] == "update:proof-a:"


def test_a_failed_restore_is_named_with_the_value_it_could_not_put_back():
    redeploy = Redeploy(fail="deploy", fail_update_to="198.51.100.1")
    with pytest.raises(proof.LabError, match="deploy exited 1") as e:
        allow_v7(redeploy, ["203.0.113.7"])
    (note,) = e.value.__notes__
    assert re.search(r"putting scope.allow_ips.*198.*failed", note)
    # Review 12d04dd4.4: a row that could not be put back leaves the Workers on the new list as well.
    assert "may still serve the new list" in note


def test_an_interrupt_during_a_step_restores_nothing():
    """Review 12d04dd4.2: Ctrl-C does not start minutes of redeploy work."""
    redeploy = Redeploy(fail="deploy", raises=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        allow_v7(redeploy, ["203.0.113.7"])
    assert redeploy.events == ["update:proof-a:203.0.113.7", "configs", "deploy"]


def test_a_restore_that_raises_any_error_is_a_note_and_the_original_error_survives():
    """Review 12d04dd4.3: a KeyError out of the previous list's redeploy never replaces the step's own failure."""
    redeploy = Redeploy(fail="deploy", fail_times=2, raises=KeyError)
    with pytest.raises(KeyError, match="try 1") as e:
        allow_v7(redeploy, ["203.0.113.7"])
    (note,) = e.value.__notes__
    assert "redeploying the previous list" in note
    assert "try 2" in note


def test_a_restore_of_the_row_that_raises_any_error_is_a_note_too():
    class Broken(Redeploy):
        def update(self, name, ips):
            super().update(name, ips)
            if ",".join(ips) == "198.51.100.1":
                raise KeyError("row")

    redeploy = Broken(fail="deploy")
    with pytest.raises(proof.LabError, match="deploy exited 1") as e:
        allow_v7(redeploy, ["203.0.113.7"])
    (note,) = e.value.__notes__
    assert "putting scope.allow_ips" in note


class Edge:
    def __init__(self, status: int, error: str = lab.ALLOWLIST_REFUSAL):
        self.status = status
        self.error = error
        self.sent: list[tuple[str, str, dict, bytes | None]] = []

    def __call__(self, method, url, headers, body):
        self.sent.append((method, url, headers, body))
        return lab.HttpAnswer(self.status, (), json.dumps({"error": self.error}).encode())


def test_request_from_sends_from_this_machine_to_the_account_host():
    edge = Edge(200)
    assert (
        lab.request_from("c0000000a", method="GET", path="/", call=edge, companies=companies_proxy)
        == 200
    )
    assert (
        lab.request_from(
            "c0000000a",
            method="POST",
            path=proof.LICENSE_RENEW_PATH,
            call=edge,
            companies=companies_proxy,
        )
        == 200
    )
    (m1, u1, _h1, b1), (m2, u2, h2, b2) = edge.sent
    assert (m1, u1, b1) == ("GET", "https://%s/" % HOST_A, None)
    assert (m2, u2, b2) == ("POST", "https://%s%s" % (HOST_A, proof.LICENSE_RENEW_PATH), b"{}")
    assert h2["Content-Type"] == "application/json"


def test_the_allowlists_403_is_answered_and_any_other_403_is_a_lab_error():
    """Control: a WAF or token 403 never reads as the allowlist blocking."""
    get = functools.partial(
        lab.request_from, "c0000000a", method="GET", path="/", companies=companies_proxy
    )
    assert get(call=Edge(403)) == 403
    with pytest.raises(proof.LabError, match="not the allowlist"):
        get(call=Edge(403, "Forbidden"))


def test_a_non_json_403_is_a_lab_error_naming_the_start_of_the_body():
    def waf(_method, _url, _headers, _body):
        return lab.HttpAnswer(403, (), b"<html>\n  <title>Attention Required</title>" + b"x" * 500)

    with pytest.raises(
        proof.LabError, match=r"body starts: '<html> <title>Attention Required"
    ) as e:
        lab.request_from("c0000000a", method="GET", path="/", call=waf, companies=companies_proxy)
    assert "x" * 100 not in str(e.value)


def test_the_body_start_is_eighty_characters_not_eighty_bytes():
    """Review 4ec9e6b7.3 and .4: the cut is on characters, and the limit is pinned exactly."""

    def waf(_method, _url, _headers, _body):
        return lab.HttpAnswer(403, (), ("\u00e9" * 200).encode())

    with pytest.raises(proof.LabError) as e:
        lab.request_from("c0000000a", method="GET", path="/", call=waf, companies=companies_proxy)
    assert "\u00e9" * lab.BODY_START in str(e.value)
    assert "\u00e9" * (lab.BODY_START + 1) not in str(e.value)
    assert "\ufffd" not in str(e.value)

    def plain(_method, _url, _headers, _body):
        return lab.HttpAnswer(403, (), b"x" * 200)

    with pytest.raises(proof.LabError) as e:
        lab.request_from("c0000000a", method="GET", path="/", call=plain, companies=companies_proxy)
    assert "x" * 80 in str(e.value)
    assert "x" * 81 not in str(e.value)


# --- cost ---------------------------------------------------------------
# The cost readers (box V8): deploy records with durations, company usage rows, the image rebuild timing and the Cloudflare limits re-read, over fakes. Nothing is queried, built or fetched.


def record_cost(taken: str | None, recorded: str | None) -> str:
    doc = {"version": "0.9.1", "good": True}
    if taken:
        doc["taken_at"] = taken
    if recorded:
        doc["recorded_at"] = recorded
    return json.dumps(doc)


def test_deploy_records_take_the_duration_from_the_two_stamps():
    rows = {
        "control-bench-eu": [
            {
                "company_id": "c00000001",
                "detail": record_cost("2026-11-10T10:00:00Z", "2026-11-10T10:04:30Z"),
            }
        ],
        "control-bench-us": [
            {"company_id": "c00000002", "detail": record_cost(None, "2026-11-10T10:00:00Z")}
        ],
    }

    def query(database, sql, params):
        assert sql == lab.RECORDS_SQL
        assert params == ["deploy-record"]
        return rows[database]

    got = lab.deploy_records(bench=True, query=query)
    assert got == [
        {"company": "c00000001", "version": "0.9.1", "duration_s": 270.0},
        {"company": "c00000002", "version": "0.9.1", "duration_s": None},
    ]


def test_a_record_without_a_start_breaks_the_cost_claim():
    """Control: a missing stamp is no duration, and the proof names that record as broken."""

    class Lab:
        def deploy_records(self, *, bench):
            del bench
            return [{"company": "c00000002", "version": "0.9.1", "duration_s": None}]

        def usage_rows(self, *, bench):
            del bench
            return []

        def image_rebuild_seconds(self):
            return 10.0

        def read_limits(self):
            return dict(proof.PLAN_LIMITS)

    lines: list[str] = []
    assert run_partial_verb("cost", Lab(), lines) == 1
    assert any(line.startswith("BROKEN  record c00000002") for line in lines)


ROWS_COST = [
    {"id": "c00000001", "name": "proof-a", "state": "active"},
    {"id": "c00000009", "name": "proof-gone", "state": "removed"},
]
GROUPS_COST = [
    {"dimensions": {"scriptName": "account-proof-a"}, "sum": {"requests": 12, "cpuTimeUs": 3000}},
    {"dimensions": {"scriptName": "proxy-proof-a"}, "sum": {"requests": 2, "cpuTimeUs": 1000}},
    {"dimensions": {"scriptName": "account-eu"}, "sum": {"requests": 900, "cpuTimeUs": 1}},
    {"dimensions": {"scriptName": "account-proof-gone"}, "sum": {"requests": 1, "cpuTimeUs": 1}},
]


def test_usage_rows_keep_only_live_company_workers_by_opaque_id():
    got = lab.usage_rows(bench=True, workers=lambda: GROUPS_COST, companies=lambda _b: ROWS_COST)
    assert got == [
        {"company": "c00000001", "worker": "account", "requests": 12.0, "cpu_ms": 3.0},
        {"company": "c00000001", "worker": "proxy", "requests": 2.0, "cpu_ms": 1.0},
    ]
    assert all("proof" not in str(r) for r in got), "rows carry the id, never the name"


def test_usage_rows_with_no_company_worker_are_empty():
    """Control: shared Workers never count as a company's usage."""
    shared = [g for g in GROUPS_COST if g["dimensions"] == {"scriptName": "account-eu"}]
    assert lab.usage_rows(bench=True, workers=lambda: shared, companies=lambda _b: ROWS_COST) == []


def test_image_rebuild_is_timed_and_the_tag_removed():
    calls: list[list[str]] = []
    ticks = iter([100.0, 172.5])

    def run(argv, cwd, env):
        del cwd, env
        calls.append(list(argv))
        return lab.Proc(0)

    assert lab.image_rebuild_seconds(run=run, clock=lambda: next(ticks)) == 72.5
    assert calls[0][:3] == ["docker", "build", "--no-cache"]
    assert calls[1][:3] == ["docker", "image", "rm"]
    assert calls[0][calls[0].index("-t") + 1] == calls[1][-1]


def test_a_failed_build_is_a_lab_error_not_a_time():
    def run(argv, cwd, env):
        del cwd, env
        return lab.Proc(1 if argv[1] == "build" else 0)

    with pytest.raises(proof.LabError, match="exited 1"):
        lab.image_rebuild_seconds(run=run, clock=lambda: 0.0)


PAGE_COST = """
| Feature | Workers Free | Workers Paid |
| --- | --- | --- |
| [Number of Workers](#number-of-workers) | 100 | 500 |
| **Routes per zone** | 1,000 | 1,000[^1] |
"""


def test_read_limits_takes_the_paid_column_of_each_row():
    got = lab.read_limits(fetch=lambda _u: (200, PAGE_COST))
    assert got == {"workers_scripts": 500, "routes_per_zone": 1000}


# The page's own form, read 2026-11-10: a <sup> footnote link in the Paid cell, and a one-column routes table beside a remote-dev row of the same words.
PAGE_LIVE_FORM = """
| Feature | Workers Free | Workers Paid |
| --- | --- | --- |
| [Number of Workers](#number-of-workers) | 100 | 500<sup>[1](#user-content-fn-1)</sup> |
| [Requests](#daily-requests) | 100,000/day | No limit |

| Limit | Value |
| --- | --- |
| [Routes](https://developers.cloudflare.com/workers/configuration/routing/routes/) per zone | 1,000 |
| Routes per zone ([`wrangler dev --remote`](#routes-remote-dev)) | 50 |
"""


def test_read_limits_reads_the_live_page_form():
    got = lab.read_limits(fetch=lambda _u: (200, PAGE_LIVE_FORM))
    assert got == {"workers_scripts": 500, "routes_per_zone": 1000}


def test_a_paid_cell_without_a_figure_is_a_lab_error_not_the_free_figure():
    """Review 98b2c18f.1: an unlimited Paid cell never reads as the Free column's 100."""
    page = PAGE_LIVE_FORM.replace("500<sup>[1](#user-content-fn-1)</sup>", "No limit")
    with pytest.raises(proof.LabError, match="No limit"):
        lab.read_limits(fetch=lambda _u: (200, page))


def test_a_moved_row_is_a_lab_error_not_a_changed_limit():
    """Control: a page without the row never reads as a different figure."""
    with pytest.raises(proof.LabError, match="Number of Workers"):
        lab.read_limits(fetch=lambda _u: (200, PAGE_COST.replace("Number of Workers", "Scripts")))


def test_a_failed_page_fetch_is_a_lab_error():
    with pytest.raises(proof.LabError, match="answered 404"):
        lab.read_limits(fetch=lambda _u: (404, ""))


# --- renet ---------------------------------------------------------------
# The renet readers (box V9): the released rdc runs the verbs with the renet hold lifted, `./rdc.sh` is refused, and the drivers that are not built refuse by name. Fakes only.


ENV_RENET = {
    lab.RDC_ENV: "/opt/rdc-edge/rdc",
    lab.MACHINE_ENV: "vm-1",
    lab.REPO_ENV: "proofrepo@vm-1",
}


def env_renet(name):
    if name not in ENV_RENET:
        raise proof.LabError("%s is not set" % name)
    return ENV_RENET[name]


class Rdc:
    def __init__(self, out: str = "renet version 0.9.1\n", rc: int = 0):
        self.out = out
        self.rc = rc
        self.calls: list[tuple[list[str], dict | None]] = []

    def __call__(self, argv, cwd, extra):
        del cwd
        self.calls.append((list(argv), extra))
        return lab.Proc(self.rc, self.out, "")


def test_the_read_only_and_mutating_verbs_run_through_the_released_rdc():
    rdc = Rdc()
    assert lab.run_verb("vm-1", mutating=False, run=rdc, env=env_renet) == 0
    assert lab.run_verb("vm-1", mutating=True, run=rdc, env=env_renet) == 0
    (ro, ro_env), (mut, mut_env) = rdc.calls
    assert ro == ["/opt/rdc-edge/rdc", "--config", "eu-bench", "machine", "status", "vm-1"]
    assert mut == ["/opt/rdc-edge/rdc", "--config", "eu-bench", "repo", "up", "proofrepo@vm-1"]
    assert ro_env == mut_env == {lab.HOLD_ENV: ""}


def test_an_inherited_hold_reaches_the_released_rdc_as_empty(monkeypatch):
    """Review 98b2c18f.4: an operator shell's REDIACC_NO_PROVISION=1 is overridden to "", which renetHold reads as no hold for a release build."""
    seen: dict[str, str] = {}

    def fake_run(argv, **kw):
        seen.update(kw["env"])
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setenv(lab.HOLD_ENV, "1")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert lab.run_verb("vm-1", mutating=False, env=env_renet) == 0
    assert seen[lab.HOLD_ENV] == ""


def test_the_checkout_rdc_sh_is_refused_before_anything_runs():
    """Control: a development build holds renet, so it would pass `a read-only verb leaves renet` and fail the rest silently."""
    rdc = Rdc()
    with pytest.raises(proof.LabError, match=r"rdc\.sh"):
        lab.run_verb(
            "vm-1",
            mutating=True,
            run=rdc,
            env=lambda n: "./rdc.sh" if n == lab.RDC_ENV else ENV_RENET[n],
        )
    assert rdc.calls == []


def test_an_unset_variable_is_named():
    with pytest.raises(proof.LabError, match=lab.MACHINE_ENV):
        lab.fleet_machine(env=lambda n: env_renet("missing-" + n))


def test_renet_version_parses_the_machine_answer():
    assert (
        lab.renet_version("vm-1", run=Rdc("Welcome\nrenet version 0.9.1-edge.3\n"), env=env_renet)
        == "0.9.1-edge.3"
    )


@pytest.mark.parametrize(("out", "rc"), [("renet version 0.9.1", 255), ("no renet here", 0)])
def test_renet_version_failures_are_lab_errors(out, rc):
    with pytest.raises(proof.LabError):
        lab.renet_version("vm-1", run=Rdc(out, rc), env=env_renet)


def test_released_renet_is_what_edge_runs():
    assert lab.released_renet(edge=lambda: "0.9.2") == "0.9.2"


ENV_V9 = {
    **ENV_RENET,
    lab.PREVIOUS_RDC_ENV: "/opt/rdc-prev/rdc",
    lab.COMPANY_ENV: "c0000000a",
}
DEPLOYMENTS_V9 = [
    {
        "created_on": "2026-11-01T00:00:00Z",
        "versions": [{"version_id": "v-old", "percentage": 100}],
    },
    {
        "created_on": "2026-11-09T00:00:00Z",
        "versions": [{"version_id": "v-new", "percentage": 100}],
    },
    {
        "created_on": "2026-11-05T00:00:00Z",
        "versions": [
            {"version_id": "v-prev", "percentage": 100},
        ],
    },
    {
        "created_on": "2026-11-08T00:00:00Z",
        "versions": [{"version_id": "v-new", "percentage": 100}],
    },
]


def env_v9(name):
    if name not in ENV_V9:
        raise proof.LabError("%s is not set" % name)
    return ENV_V9[name]


class Fleet:
    """One fleet machine behind a released rdc, and the company's account Worker behind wrangler."""

    def __init__(
        self,
        *,
        renet="0.9.0",
        proxy_uploads=False,
        proxy_rc=0,
        outcome=None,
        deployments=None,
        rollback_fails_to="",
        banner="banner",
    ):
        self.rollback_fails_to = rollback_fails_to
        self.banner = banner
        self.renet = renet
        self.proxy_uploads = proxy_uploads
        self.proxy_rc = proxy_rc
        # (renet, worker version) -> renew JSON; default: every pairing renews.
        self.outcome = outcome or (lambda _r, _w: {"results": [{"outcome": "renewed"}]})
        self.deployments = DEPLOYMENTS_V9 if deployments is None else deployments
        self.worker = "v-new"
        self.calls: list[tuple[list[str], dict | None]] = []
        self.renewed_with: list[tuple[str, str]] = []

    def __call__(self, argv, cwd, extra):
        del cwd
        argv = list(argv)
        self.calls.append((argv, extra))
        if "deployments" in argv:
            return lab.Proc(0, self.banner + "\n" + json.dumps(self.deployments))
        if "rollback" in argv:
            target = argv[argv.index("rollback") + 1]
            if target == self.rollback_fails_to:
                return lab.Proc(1)
            self.worker = target
            return lab.Proc(0)
        if "term" in argv and argv[-1] == "renet version":
            return lab.Proc(0, "renet version %s\n" % self.renet)
        if "term" in argv and argv[-1] == lab.RENEW_COMMAND:
            self.renewed_with.append((self.renet, self.worker))
            doc = json.dumps(self.outcome(self.renet, self.worker))
            return lab.Proc(0, self.banner + " Welcome\n" + doc)
        if argv[-3:-1] == ["repo", "up"]:
            if "--proxy" in argv:
                if self.proxy_uploads:
                    self.renet = "0.9.2"
                return lab.Proc(self.proxy_rc)
            self.renet = "0.9.1" if argv[0] == "/opt/rdc-prev/rdc" else "0.9.2"
            return lab.Proc(0)
        raise AssertionError(argv)


def upload_v9(fleet: Fleet):
    return lab.live_executor_upload(
        "vm-1", run=fleet, env=env_v9, token=lambda c: "rdt_proxy_%s" % c, companies=companies_proxy
    )


def test_the_executor_upload_goes_through_the_company_proxy_with_its_token():
    fleet = Fleet()
    assert upload_v9(fleet) == proof.Answer(False, "the executor left renet at 0.9.0")
    argv, extra = next(c for c in fleet.calls if "--proxy" in c[0])
    assert argv[argv.index("--proxy") + 1] == "https://proof-a-proxy.%s" % PRODUCT_DOMAIN
    assert argv[-3:] == ["repo", "up", "proofrepo@vm-1"]
    assert extra == {lab.HOLD_ENV: "", lab.PROXY_BEARER_ENV: "rdt_proxy_c0000000a"}


def test_an_executor_that_uploads_is_admitted_so_the_refusal_claim_breaks():
    """Control: the driver reports the move it saw, never a refusal it assumed."""
    assert upload_v9(Fleet(proxy_uploads=True)) == proof.Answer(True)


def test_a_proxied_verb_that_failed_proves_nothing():
    with pytest.raises(proof.LabError, match="proxied repo up exited 1"):
        upload_v9(Fleet(proxy_rc=1))


def test_worker_versions_are_the_distinct_full_versions_newest_first():
    assert lab.worker_versions("account-proof-a", run=Fleet()) == ["v-new", "v-prev", "v-old"]


def spread_v9(fleet: Fleet, renet: str, worker: str):
    return lab.live_spread_renew(
        "vm-1",
        renet,
        worker,
        run=fleet,
        env=env_v9,
        released=lambda: "0.9.2",
        companies=companies_proxy,
    )


def test_the_previous_renet_renews_against_the_new_worker():
    fleet = Fleet()
    assert spread_v9(fleet, "previous", "new") == proof.Answer(True)
    assert fleet.renewed_with == [("0.9.1", "v-new")]
    assert not any("rollback" in c[0] for c in fleet.calls)


def test_the_new_renet_renews_against_the_previous_worker_and_the_newest_returns():
    fleet = Fleet()
    assert spread_v9(fleet, "new", "previous") == proof.Answer(True)
    assert fleet.renewed_with == [("0.9.2", "v-prev")]
    rollbacks = [c[0][c[0].index("rollback") + 1] for c in fleet.calls if "rollback" in c[0]]
    assert rollbacks == ["v-prev", "v-new"]
    assert fleet.worker == "v-new"


def test_the_newest_version_is_rolled_back_when_the_renewal_raises():
    fleet = Fleet(outcome=lambda _r, _w: {"results": []})
    with pytest.raises(proof.LabError, match="no installed licence"):
        spread_v9(fleet, "new", "previous")
    rollbacks = [c[0][c[0].index("rollback") + 1] for c in fleet.calls if "rollback" in c[0]]
    assert rollbacks == ["v-prev", "v-new"]
    assert fleet.worker == "v-new"


def test_a_failed_rollback_keeps_the_renewals_own_error_and_names_the_hand_fix():
    """Control: the rollback failure is a note on the renewal's error, never its replacement."""
    fleet = Fleet(outcome=lambda _r, _w: {"results": []}, rollback_fails_to="v-new")
    with pytest.raises(proof.LabError, match="no installed licence") as raised:
        spread_v9(fleet, "new", "previous")
    (note,) = raised.value.__notes__
    assert "account-proof-a" in note
    assert "v-new" in note
    assert "restore it by hand" in note
    assert fleet.worker == "v-prev"


def test_a_failed_rollback_after_a_renewal_is_not_a_clean_answer():
    fleet = Fleet(rollback_fails_to="v-new")
    with pytest.raises(proof.LabError, match=r"renewal answered ok=True.*account-proof-a.*v-new"):
        spread_v9(fleet, "new", "previous")


def test_a_banner_with_brackets_does_not_break_the_json_the_drivers_read():
    banner = "[info] wrangler {4.1} ready"
    assert lab.worker_versions("account-proof-a", run=Fleet(banner=banner)) == [
        "v-new",
        "v-prev",
        "v-old",
    ]
    assert spread_v9(Fleet(banner=banner), "previous", "new") == proof.Answer(True)


def test_the_last_complete_json_value_is_the_one_read():
    text = 'noise [1] more {"a": [2]}\n[{"k": "v"}]\n'
    assert lab._json_value(text, "[") == [{"k": "v"}]
    assert lab._json_value("none here", "[") is None
    assert lab._json_value("[broken", "[") is None


def test_a_refused_renewal_is_refused_with_its_code_and_the_newest_still_returns():
    def outcome(_renet, worker):
        if worker == "v-prev":
            return {"results": [{"outcome": "refused", "code": "SIGNER_SCOPE"}]}
        return {"results": [{"outcome": "renewed"}]}

    fleet = Fleet(outcome=outcome)
    assert spread_v9(fleet, "new", "previous") == proof.Answer(False, "refused code=SIGNER_SCOPE")
    assert fleet.worker == "v-new"


@pytest.mark.parametrize(
    ("doc", "match"),
    [({"results": []}, "no installed licence"), ({"lockBusy": True, "results": []}, "lock")],
)
def test_a_renewal_that_never_ran_is_a_lab_error_not_a_refusal(doc, match):
    with pytest.raises(proof.LabError, match=match):
        spread_v9(Fleet(outcome=lambda _r, _w: doc), "previous", "new")


def test_one_deployed_worker_version_is_a_lab_error_before_anything_moves():
    fleet = Fleet(deployments=DEPLOYMENTS_V9[1:2])
    with pytest.raises(proof.LabError, match="1 deployed version"):
        spread_v9(fleet, "new", "previous")
    assert fleet.renewed_with == []
    assert not any(c[0][-3:-1] == ["repo", "up"] for c in fleet.calls)


def test_a_machine_left_on_the_wrong_renet_is_a_lab_error():
    """Control: renewing on the wrong renet would prove the other direction."""
    with pytest.raises(proof.LabError, match="not the previous one"):
        lab.live_spread_renew(
            "vm-1",
            "previous",
            "new",
            run=Fleet(),
            env=env_v9,
            version=lambda _m: "0.9.2",
            released=lambda: "0.9.2",
            companies=companies_proxy,
        )


def test_the_default_drivers_are_the_live_ones(monkeypatch):
    """Both seams take a driver; with none they run the live drivers, which name an unset variable before anything runs."""
    monkeypatch.delenv(lab.COMPANY_ENV, raising=False)
    with pytest.raises(proof.LabError, match=lab.COMPANY_ENV):
        lab.executor_upload("vm-1")
    with pytest.raises(proof.LabError, match=lab.COMPANY_ENV):
        lab.renew_with("vm-1", renet="previous", worker="new")
    refused = proof.Answer(False, "executor never uploads renet")
    assert lab.executor_upload("vm-1", driver=lambda _m: refused) == refused


# --- gh ---------------------------------------------------------------
# The GitHub readers (box V10): the dispatch refuses without a bench input, finds and waits for its run, and reads all four surfaces. A fake `gh`; nothing is dispatched.


T0_GH = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=datetime.UTC)
CID_GH = "c0123456789"

WITH_BENCH_GH = """on:
  workflow_dispatch:
    inputs:
      version:
        type: string
      bench:
        type: boolean
        default: false
jobs: {}
"""
WITHOUT_BENCH_GH = WITH_BENCH_GH.replace(
    "      bench:\n        type: boolean\n        default: false\n", ""
)


class Gh:
    def __init__(self, statuses=("in_progress", "completed"), runs_after: int = 0):
        self.calls: list[list[str]] = []
        self.statuses = list(statuses)
        self.runs_after = runs_after

    def __call__(self, argv, cwd, env):
        del cwd, env
        args = list(argv[1:])
        self.calls.append(args)
        if args[:2] == ["repo", "view"]:
            return lab.Proc(0, json.dumps({"defaultBranchRef": {"name": "main"}}))
        if args[:2] == ["workflow", "run"]:
            return lab.Proc(0)
        if args[:2] == ["run", "list"]:
            if self.runs_after > 0:
                self.runs_after -= 1
                return lab.Proc(
                    0, json.dumps([{"databaseId": 1, "createdAt": "2026-11-10T11:00:00Z"}])
                )
            return lab.Proc(
                0,
                json.dumps(
                    [
                        {"databaseId": 1, "createdAt": "2026-11-10T11:00:00Z"},
                        {"databaseId": 77, "createdAt": "2026-11-10T12:00:03Z"},
                    ]
                ),
            )
        if args[:2] == ["run", "view"] and "--json" in args:
            return lab.Proc(0, json.dumps({"status": self.statuses.pop(0)}))
        raise AssertionError(args)


def dispatch_gh(gh, text=WITH_BENCH_GH):
    return lab.dispatch_release(
        CID_GH,
        run=gh,
        version=lambda: "0.9.1",
        workflow_text=lambda: text,
        now=lambda: T0_GH,
        sleep=lambda _s: None,
    )


def test_the_dispatch_sends_the_opaque_id_to_bench_and_waits_for_its_run():
    gh = Gh()
    assert dispatch_gh(gh) == "77"
    sent = next(c for c in gh.calls if c[:2] == ["workflow", "run"])
    assert sent[sent.index("--ref") + 1] == "main"
    fields = [sent[i + 1] for i, a in enumerate(sent) if a == "-f"]
    assert fields == ["version=0.9.1", "company=%s" % CID_GH, "bench=true", "dry_run=false"]
    assert sum(1 for c in gh.calls if c[:2] == ["run", "view"]) == 2


def test_a_run_older_than_the_dispatch_is_not_taken_for_it():
    gh = Gh(runs_after=2)
    assert dispatch_gh(gh) == "77"
    assert sum(1 for c in gh.calls if c[:2] == ["run", "list"]) == 3


def test_a_run_that_never_completes_is_a_lab_error_not_an_answer(monkeypatch):
    """Review 98b2c18f.3: the wait loop's only exits are a completed run id and a LabError."""
    monkeypatch.setattr(lab, "RUN_TIMEOUT_S", lab.POLL_S * 2)
    gh = Gh(statuses=["in_progress"] * 10)
    with pytest.raises(proof.LabError, match="did not complete"):
        dispatch_gh(gh)
    assert sum(1 for c in gh.calls if c[:2] == ["run", "view"]) == 3


def test_no_run_after_the_dispatch_is_a_lab_error():
    gh = Gh(runs_after=lab.FIND_TRIES)
    with pytest.raises(proof.LabError, match=r"no .* run appeared"):
        dispatch_gh(gh)


def test_without_a_bench_input_nothing_is_dispatched():
    """Control: the workflow as it stands reads production, so the dispatch is refused before gh runs."""
    gh = Gh()
    with pytest.raises(proof.LabError, match="no bench input"):
        dispatch_gh(gh, WITHOUT_BENCH_GH)
    assert gh.calls == []


def test_the_tracked_workflow_is_scanned_by_the_same_reader():
    text = (lab.root() / ".github" / "workflows" / lab.WORKFLOW).read_text(encoding="utf-8")
    assert lab.declares_bench_input(text) == ("      bench:\n" in text)


def test_the_tracked_workflow_declares_the_bench_input():
    """V10: the dispatch's guard admits the tracked workflow, so `proof github` dispatches to bench."""
    text = lab.root().joinpath(*lab.WORKFLOW_REL).read_text(encoding="utf-8")
    assert lab.declares_bench_input(text)


def test_a_name_is_refused_as_the_dispatch_input():
    with pytest.raises(proof.LabError, match="opaque"):
        lab.dispatch_release("acme", run=Gh(), workflow_text=lambda: WITH_BENCH_GH)


# Review 98b2c18f.2: a job's check run id differs from its job id; only check runs 905 and 906 exist.
CHECK_SUMMARIES = {"905": "sum of job 5", "906": "sum of job 6"}


def _job(job_id: int, check_id: int) -> dict:
    return {
        "id": job_id,
        "check_run_url": GH_API_BASE + "/repos/o/r/check-runs/%d" % check_id,
    }


def test_run_surfaces_reads_logs_both_apis_and_each_job_summary():
    def gh(argv, cwd, env):
        del cwd, env
        args = list(argv[1:])
        if args[:2] == ["run", "view"]:
            return lab.Proc(0, "log line\n")
        if args[1].endswith("/jobs"):
            return lab.Proc(0, json.dumps({"jobs": [_job(5, 905), _job(6, 906)]}))
        if "/check-runs/" in args[1]:
            check = args[1].rsplit("/", 1)[1]
            summary = CHECK_SUMMARIES.get(check)
            if summary is None:
                return lab.Proc(1)
            return lab.Proc(
                0, json.dumps({"output": {"title": None, "summary": summary, "text": ""}})
            )
        return lab.Proc(0, json.dumps({"id": 77, "name": "Enterprise release"}))

    got = lab.run_surfaces("77", run=gh)
    assert set(got) == set(proof.GITHUB_SURFACES)
    assert got["logs"] == "log line\n"
    assert got["step-summary"] == "sum of job 5\nsum of job 6"
    assert '"id": 77' in got["run-api"]


class _FlakyGh:
    """A gh runner answering `outcomes` in order, the last one repeating; `calls` counts attempts."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, argv, cwd, env):
        del argv, cwd, env
        index = min(self.calls, len(self.outcomes) - 1)
        self.calls += 1
        return self.outcomes[index]


@pytest.fixture
def no_retry_sleep(monkeypatch):
    """Stub the retry's clock so the 5 s / 15 s backoff never runs; returns the pauses taken."""
    pauses: list[float] = []
    monkeypatch.setattr(lab.gh_retry, "time", types.SimpleNamespace(sleep=pauses.append))
    return pauses


def test_a_gh_read_retries_a_transient_5xx_then_answers(no_retry_sleep):
    """Review 09e1a50e.1: a 502 then a clean read returns the read, after one backoff."""
    gh = _FlakyGh(lab.Proc(1, "", "gh: Server Error (HTTP 502)"), lab.Proc(0, "ok\n"))
    assert lab._gh_read(gh, "run", "view", "77") == "ok\n"
    assert gh.calls == 2
    assert len(no_retry_sleep) == 1


def test_a_gh_read_gives_up_on_a_persistent_5xx_as_a_lab_error(no_retry_sleep):
    gh = _FlakyGh(lab.Proc(1, "", "gh: Server Error (HTTP 502)"))
    with pytest.raises(proof.LabError, match="gh run exited 1"):
        lab._gh_read(gh, "run", "view", "77")
    assert gh.calls == lab.gh_retry.ATTEMPTS
    assert len(no_retry_sleep) == lab.gh_retry.ATTEMPTS - 1


def test_a_gh_read_never_retries_a_4xx(no_retry_sleep):
    """Control: a 404 is a LabError at once, with no backoff."""
    gh = _FlakyGh(lab.Proc(1, "", "gh: Not Found (HTTP 404)"), lab.Proc(0, "late\n"))
    with pytest.raises(proof.LabError, match="gh api exited 1"):
        lab._gh_read(gh, "api", "x")
    assert gh.calls == 1
    assert no_retry_sleep == []


def test_a_job_without_a_check_run_url_is_a_lab_error():
    """Control: the job id is never used as the check run id."""
    with pytest.raises(proof.LabError, match="check_run_url"):
        lab._check_run_id({"id": 5})
    assert lab._check_run_id(_job(5, 905)) == "905"


def test_a_failed_surface_read_is_a_lab_error_not_an_empty_surface():
    with pytest.raises(proof.LabError, match="gh run exited 1"):
        lab.run_surfaces("77", run=lambda _a, _c, _e: lab.Proc(1))


def test_the_github_proof_breaks_on_a_name_in_a_surface():
    """Control for the verb over these readers: a surface carrying the company's host is a hit."""

    class Lab:
        def ensure_company(self, label, region, *, ring=None):
            del label, region, ring
            return CID_GH

        def company_words(self, cid):
            del cid
            return ["proof-github", "proof-github.rediacc.cloud"]

        def dispatch_release(self, cid):
            del cid
            return "77"

        def run_surfaces(self, run_id):
            del run_id
            clean = dict.fromkeys(proof.GITHUB_SURFACES, "release ok")
            return {**clean, "step-summary": "deployed proof-github.rediacc.cloud"}

    lines: list[str] = []
    assert run_partial_verb("github", Lab(), lines) == 1
    assert any("step-summary: word #" in line for line in lines)


# --- left ---------------------------------------------------------------
# The leftovers reader (box V11): what a company still holds, by kind and never by name, over a fake Cloudflare account. Nothing is listed live.


class Account:
    def __init__(self, *, present: bool):
        self.present = present
        self.jurisdictions: list[str | None] = []

    def listing(self, path):
        if not self.present:
            return []
        if path == "/accounts/acct/workers/scripts":
            return [
                {"id": "account-proof-remove"},
                {"id": "proxy-proof-remove"},
                {"id": "account-eu"},
            ]
        if path.startswith("/accounts/acct/d1/database?name="):
            return [{"name": "account-proof-remove-ci"}, {"name": "account-proof-remove"}]
        if path == "/user/tokens":
            return [{"name": "enterprise-c00000001-backups"}]
        raise AssertionError(path)

    def buckets(self, jurisdiction):
        self.jurisdictions.append(jurisdiction)
        return {"configs-proof-remove", "backups-proof-remove"} if self.present else set()

    def api(self, path):
        if path == "/zones?name=%s" % PRODUCT_DOMAIN:
            return [{"id": "zone-1"}]
        if path == "/zones/zone-1/workers/routes":
            other = [{"pattern": "eu.%s/*" % PRODUCT_DOMAIN, "script": "account-eu"}]
            mine = [
                {"pattern": "proof-remove.%s/*" % PRODUCT_DOMAIN, "script": "proxy-proof-remove"}
            ]
            return other + (mine if self.present else [])
        raise AssertionError(path)


def no_routes(path):
    return [{"id": "zone-1"}] if path.startswith("/zones?name=") else []


def rows_left(state):
    return lambda _b: [
        {"id": "c00000001", "name": "proof-remove", "region": "eu", "state": state, "unlisted": 1}
    ]


def test_a_kept_company_lists_every_piece_by_kind():
    acct = Account(present=True)
    got = lab.leftovers(
        "c00000001",
        companies=rows_left("active"),
        listing=acct.listing,
        api=acct.api,
        buckets=acct.buckets,
    )
    assert got == [
        "control row (state active)",
        "account Worker",
        "proxy Worker",
        "zone route",
        "D1 database",
        "configs bucket",
        "backups bucket",
        "backup token",
    ]
    assert all("proof-remove" not in item for item in got), "kinds, never names"
    assert acct.jurisdictions == ["eu"], "eu buckets are listed under the eu jurisdiction header"


def test_a_removed_company_with_nothing_left_answers_an_empty_list():
    """Control: the list above is not what every company gets."""
    acct = Account(present=False)
    got = lab.leftovers(
        "c00000001",
        companies=rows_left("removed"),
        listing=acct.listing,
        api=acct.api,
        buckets=acct.buckets,
    )
    assert got == [], "another Worker's route is not this company's"


def test_a_route_left_alone_is_reported_by_kind():
    """A removed company whose Workers are gone but whose route survived still leaves something."""
    acct = Account(present=True)
    got = lab.leftovers(
        "c00000001",
        companies=rows_left("removed"),
        listing=lambda _p: [],
        api=acct.api,
        buckets=lambda _j: set(),
    )
    assert got == ["zone route"]


def test_an_unreadable_route_listing_is_a_lab_error_not_an_empty_list():
    def api(path):
        return [{"id": "zone-1"}] if path.startswith("/zones?name=") else None

    with pytest.raises(proof.LabError, match="zone route listing"):
        lab.leftovers(
            "c00000001",
            companies=rows_left("removed"),
            listing=lambda _p: [],
            api=api,
            buckets=lambda _j: set(),
        )


def test_a_similar_database_name_is_not_this_companys():
    def listing(path):
        if path.startswith("/accounts/acct/d1/database?name="):
            return [{"name": "account-proof-remove-ci"}]
        return []

    got = lab.leftovers(
        "c00000001",
        companies=rows_left("removed"),
        listing=listing,
        api=no_routes,
        buckets=lambda _j: set(),
    )
    assert got == []


def test_an_unknown_company_is_a_lab_error():
    with pytest.raises(proof.LabError, match="no company c0000000f"):
        lab.leftovers("c0000000f", companies=rows_left("active"), listing=lambda _p: [])


def test_a_failed_listing_is_a_lab_error_not_an_empty_list():
    def down(_path):
        raise proof.LabError("GET /accounts/acct/workers/scripts: HTTP 403")

    with pytest.raises(proof.LabError, match="403"):
        lab.leftovers("c00000001", companies=rows_left("removed"), listing=down)


class _OSErrorRollback(Fleet):
    """The runner itself fails (an OSError, as a timeout or a missing binary does) on the rollback to `bad`."""

    def __init__(self, bad, **kw):
        super().__init__(**kw)
        self.bad = bad

    def __call__(self, argv, cwd, env):
        if "rollback" in argv and self.bad in argv:
            raise OSError("runner timed out")
        return super().__call__(argv, cwd, env)


def test_a_non_lab_rollback_failure_still_keeps_the_renewal_error_and_names_the_hand_fix():
    """Review e2231d81.1: an OSError from the rollback is a note, never the replacement."""
    fleet = _OSErrorRollback("v-new", outcome=lambda _r, _w: {"results": []})
    with pytest.raises(proof.LabError, match="no installed licence") as raised:
        spread_v9(fleet, "new", "previous")
    (note,) = raised.value.__notes__
    assert "v-new" in note
    assert "restore it by hand" in note


def test_a_non_lab_rollback_failure_after_a_renewal_names_the_hand_fix():
    """Review e2231d81.2."""
    fleet = _OSErrorRollback("v-new")
    with pytest.raises(
        proof.LabError, match=r"renewal answered ok=True.*v-new.*restore it by hand"
    ):
        spread_v9(fleet, "new", "previous")


class _RuntimeRollback(Fleet):
    def __init__(self, bad, **kw):
        super().__init__(**kw)
        self.bad = bad

    def __call__(self, argv, cwd, env):
        if "rollback" in argv and self.bad in argv:
            raise RuntimeError("runner gave up")
        return super().__call__(argv, cwd, env)


def test_a_runtime_error_in_the_rollback_keeps_the_renewal_error():
    """Review 58abac9b.1: a non-listed exception of the rollback is a note, never the replacement."""
    fleet = _RuntimeRollback("v-new", outcome=lambda _r, _w: {"results": []})
    with pytest.raises(proof.LabError, match="no installed licence") as raised:
        spread_v9(fleet, "new", "previous")
    (note,) = raised.value.__notes__
    assert "restore it by hand" in note


def test_a_runtime_error_from_the_success_path_rollback_names_the_hand_fix():
    """Review 58abac9b.2 and 9a92fe49.1: a RuntimeError from the success-path rollback names the hand fix."""
    fleet = _RuntimeRollback("v-new")
    with pytest.raises(
        proof.LabError, match=r"renewal answered ok=True.*v-new.*restore it by hand"
    ):
        spread_v9(fleet, "new", "previous")


class _TypeErrorRollback(Fleet):
    """A rollback that fails with an error outside ROLLBACK_FAILURES (a bug in put_version itself)."""

    def __init__(self, bad, **kw):
        super().__init__(**kw)
        self.bad = bad

    def __call__(self, argv, cwd, env):
        if "rollback" in argv and self.bad in argv:
            raise TypeError("put_version bug")
        return super().__call__(argv, cwd, env)


def test_any_error_from_the_success_path_rollback_names_the_hand_fix():
    """Review 12d04dd4.1: a TypeError after an ok renewal still raises LabError naming the version to restore."""
    fleet = _TypeErrorRollback("v-new")
    with pytest.raises(
        proof.LabError, match=r"renewal answered ok=True.*v-new.*restore it by hand"
    ) as raised:
        spread_v9(fleet, "new", "previous")
    assert isinstance(raised.value.__cause__, TypeError)


def test_the_json_scan_is_linear_in_brackets(monkeypatch):
    """Review e2231d81.3: a value that runs to the end is found without a decode from every inner bracket."""
    calls = []
    real = json.JSONDecoder.raw_decode

    def counting(self, s, idx=0):
        calls.append(idx)
        return real(self, s, idx)

    inner = "[" + ",".join("[1]" for _ in range(200)) + "]"
    text = "noise " + inner
    want = json.loads(inner)
    monkeypatch.setattr(json.JSONDecoder, "raw_decode", counting)
    got = lab._json_value(text, "[")
    assert got == want
    assert len(calls) == 1


def test_the_json_scan_resumes_after_a_decoded_value_followed_by_text(monkeypatch):
    """Review 58abac9b.3: trailing text after the outer value forces the scan branch; one decode, not one per inner bracket."""
    calls = []
    real = json.JSONDecoder.raw_decode

    def counting(self, s, idx=0):
        calls.append(idx)
        return real(self, s, idx)

    inner = "[" + ",".join("[1]" for _ in range(200)) + "]"
    want = json.loads(inner)
    monkeypatch.setattr(json.JSONDecoder, "raw_decode", counting)
    got = lab._json_value("noise " + inner + " trailing words", "[")
    assert got == want
    assert len(calls) == 1


# --- box V1: the caller-side signer probe ----------------------------------------------

PROBE_KEY = "k" * 40
PROBE_URL = BENCH_ORIGIN + lab.SIGNER_PROBE_PATH
SHARED_PROPS = {"tier": "shared", "region": "eu"}
SIGNED = {"payload": "cGF5", "signature": "c2ln", "publicKeyId": "fb37"}


class FakeProbeCall:
    """The bench signer-probe route: one canned JSON answer per kind, recording each request."""

    def __init__(self, answers: dict[str, tuple[int, object]]):
        self.answers = answers
        self.requests: list[tuple[str, str, dict[str, str], dict]] = []

    def __call__(self, method, url, headers, body):
        doc = json.loads(body)
        self.requests.append((method, url, headers, doc))
        status, answer = self.answers[doc["kind"]]
        return lab.HttpAnswer(status, (), json.dumps(answer).encode())


def _probe(answers: dict[str, tuple[int, object]]):
    call = FakeProbeCall(answers)
    env = {lab.SERVER_API_KEY_ENV: PROBE_KEY}

    def probe(caller, kind, signed):
        return lab.signer_probe(caller, kind, signed, call=call, env=env)

    return probe, call


def test_signer_props_are_what_the_signer_reports_not_the_api():
    probe, call = _probe(
        {"whoami": (200, {"ok": True, "body": {"region": "eu"}, "props": SHARED_PROPS})}
    )
    assert lab.signer_props("account-bench", probe=probe) == SHARED_PROPS
    method, url, headers, doc = call.requests[0]
    assert (method, url, doc) == ("POST", PROBE_URL, {"kind": "whoami"})
    assert headers["X-API-Key"] == PROBE_KEY


def test_signer_props_of_a_binding_without_props_are_empty():
    probe, _ = _probe({"whoami": (200, {"ok": True, "body": {}, "props": {}})})
    assert lab.signer_props("account-bench", probe=probe) == {}


def test_signer_props_with_the_signer_out_of_reach_is_a_lab_error():
    probe, _ = _probe({"whoami": (200, {"ok": False, "error": "SIGNER_UNAVAILABLE"})})
    with pytest.raises(proof.LabError, match="SIGNER_UNAVAILABLE"):
        lab.signer_props("account-bench", probe=probe)


@pytest.mark.parametrize("status", [401, 404, 500, 503])
def test_a_probe_that_is_not_answering_is_never_a_refusal(status):
    probe, _ = _probe({"raw-bytes": (status, {"ok": False, "error": "SIGNER_X"})})
    with pytest.raises(proof.LabError, match="answered HTTP %d" % status):
        lab.issue("account-bench", "raw-bytes", probe=probe, licences={})


@pytest.mark.parametrize("answer", [{}, {"error": "SIGNER_X"}, {"ok": "no"}])
def test_a_probe_answer_without_a_verdict_is_a_lab_error(answer):
    probe, _ = _probe({"licence": (200, answer)})
    with pytest.raises(proof.LabError, match="no verdict"):
        lab.issue("account-bench", "licence", probe=probe, licences={})


def test_a_refusal_without_a_code_is_a_lab_error():
    probe, _ = _probe({"wrong-host": (200, {"ok": False})})
    with pytest.raises(proof.LabError, match="no code"):
        lab.issue("account-bench", "wrong-host", probe=probe, licences={})


def test_a_scope_refusal_carries_the_signer_code():
    probe, _ = _probe({"suspended": (200, {"ok": False, "error": "SIGNER_SUSPENDED"})})
    got = lab.issue("account-bench", "suspended", probe=probe, licences={})
    assert got == proof.Answer(False, "SIGNER_SUSPENDED")


def test_issue_asks_only_for_the_kinds_the_proof_uses():
    probe, call = _probe({})
    with pytest.raises(proof.LabError, match="issues no"):
        lab.issue("account-bench", "whoami", probe=probe, licences={})
    assert call.requests == []
    assert set(lab.ISSUE_KINDS) == {"licence", "certificate", *proof.SCOPE_CODES}


def test_an_issued_licence_is_kept_and_verified_again_with_no_signer():
    licences: dict[str, dict[str, str]] = {}
    probe, call = _probe(
        {
            "licence": (200, {"ok": True, "body": {**SIGNED, "subscriptionId": "free:x"}}),
            "verify": (200, {"ok": True, "body": {"hardExpiresAt": "2999-01-01"}}),
        }
    )
    assert lab.issue("account-bench", "licence", probe=probe, licences=licences).ok
    assert licences == {"account-bench": SIGNED}
    assert lab.current_licence_works("account-bench", probe=probe, licences=licences)
    assert call.requests[-1][3] == {"kind": "verify", "signed": SIGNED}


def test_a_licence_the_server_no_longer_accepts_does_not_work():
    probe, _ = _probe({"verify": (200, {"ok": False, "error": "LICENCE_INVALID"})})
    assert not lab.current_licence_works(
        "account-bench", probe=probe, licences={"account-bench": SIGNED}
    )


def test_current_licence_with_none_issued_is_a_lab_error():
    probe, _ = _probe({})
    with pytest.raises(proof.LabError, match="no licence was issued"):
        lab.current_licence_works("account-bench", probe=probe, licences={})


def test_an_admitted_licence_without_its_signed_parts_is_a_lab_error():
    probe, _ = _probe({"licence": (200, {"ok": True, "body": {"payload": "x"}})})
    with pytest.raises(proof.LabError, match="no signed parts"):
        lab.issue("account-bench", "licence", probe=probe, licences={})


def test_the_certificate_id_rides_the_answer_body():
    probe, _ = _probe({"certificate": (200, {"ok": True, "body": {"id": "sub-1"}})})
    answer = lab.issue("account-bench", "certificate", probe=probe, licences={})
    assert answer.body == {"id": "sub-1"}


def test_the_probe_needs_the_server_api_key_and_names_the_enterprise_profile():
    with pytest.raises(proof.LabError, match=lab.SERVER_API_KEY_ENV) as caught:
        lab.signer_probe("account-bench", "whoami", call=FakeProbeCall({}), env={})
    assert "--profile enterprise" in str(caught.value)


def test_missing_cloudflare_credentials_name_the_enterprise_profile(monkeypatch):
    """The `enterprise` profile (.ci/config/secret-supply.json) binds the Cloudflare pair and the server API key the lab reads."""
    assert lab.PROFILE == "enterprise"
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    with pytest.raises(proof.LabError, match=r"--profile enterprise\)"):
        lab._credentials()


PROBE_COMPANIES = [
    {"id": "c00000000000000a1", "name": "acme", "state": "active"},
    {"id": "c00000000000000b2", "name": "gone", "state": "removed"},
]


def _company_probe(caller: str, call: FakeProbeCall, keys: list[str]) -> dict:
    def api_key(company: str) -> str:
        keys.append(company)
        return "company-key-%s" % company

    return lab.signer_probe(
        caller,
        "whoami",
        call=call,
        env={lab.SERVER_API_KEY_ENV: PROBE_KEY},
        companies=lambda _bench: PROBE_COMPANIES,
        api_key=api_key,
    )


def test_a_company_caller_is_asked_on_its_own_host_under_its_own_key():
    call = FakeProbeCall({"whoami": (200, {"ok": True, "body": {}, "props": {}})})
    keys: list[str] = []
    _company_probe("account-acme", call, keys)
    method, url, headers, doc = call.requests[0]
    assert method == "POST"
    assert url == "https://acme.%s%s" % (lab.PRODUCT_DOMAIN, lab.SIGNER_PROBE_PATH)
    assert headers["X-API-Key"] == "company-key-c00000000000000a1"
    assert keys == ["c00000000000000a1"]
    assert doc == {"kind": "whoami"}


@pytest.mark.parametrize("caller", ["account-ghost", "account-gone", "acme", "proxy-acme"])
def test_a_caller_that_is_neither_bench_nor_a_live_company_is_never_asked(caller):
    """Control: an unknown, removed or non-account Worker reaches no host and reads no key."""
    call = FakeProbeCall({})
    keys: list[str] = []
    with pytest.raises(proof.LabError, match="no signer probe to ask"):
        _company_probe(caller, call, keys)
    assert call.requests == []
    assert keys == []


def test_account_bench_never_reads_a_company_key():
    """Control: the shared caller keeps the shared key and origin."""
    call = FakeProbeCall({"whoami": (200, {"ok": True, "body": {}, "props": {}})})
    keys: list[str] = []
    _company_probe("account-bench", call, keys)
    assert call.requests[0][1] == PROBE_URL
    assert call.requests[0][2]["X-API-Key"] == PROBE_KEY
    assert keys == []


def test_the_stale_template_claim_is_gone_and_the_template_binds_the_signer():
    """The error text once said the company template binds no LICENSE_SIGNER; it does."""
    template = pathlib.Path(paths.repo_root()) / "workers" / "account" / "enterprise.template.toml"
    assert re.search(
        r'\[\[services\]\]\nbinding = "LICENSE_SIGNER"\nservice = "@@SIGNER@@"',
        template.read_text(),
    )
    assert "binds no LICENSE_SIGNER" not in pathlib.Path(lab.__file__).read_text()


RENEWED = {"payload": "p2", "signature": "s2", "publicKeyId": "k"}


def test_renew_issues_first_when_the_run_holds_no_licence_then_renews_it():
    licences: dict[str, dict[str, str]] = {}
    probe, call = _probe(
        {
            "licence": (200, {"ok": True, "body": SIGNED}),
            "renew": (200, {"ok": True, "body": RENEWED}),
        }
    )
    assert lab.renew("account-bench", probe=probe, licences=licences).ok
    assert [r[3]["kind"] for r in call.requests] == ["licence", "renew"]
    assert call.requests[1][3] == {"kind": "renew", "signed": SIGNED}
    assert licences == {"account-bench": RENEWED}


def test_renew_sends_the_held_licence_and_asks_for_no_new_one():
    licences = {"account-bench": SIGNED}
    probe, call = _probe({"renew": (200, {"ok": True, "body": RENEWED})})
    assert lab.renew("account-bench", probe=probe, licences=licences).ok
    assert [r[3] for r in call.requests] == [{"kind": "renew", "signed": SIGNED}]


def test_a_refused_renewal_carries_its_code_and_keeps_the_current_licence():
    licences = {"account-bench": SIGNED}
    probe, _ = _probe({"renew": (200, {"ok": False, "error": "SIGNER_UNAVAILABLE"})})
    got = lab.renew("account-bench", probe=probe, licences=licences)
    assert got == proof.Answer(False, "SIGNER_UNAVAILABLE")
    assert licences == {"account-bench": SIGNED}


def test_a_refused_first_issue_is_the_renewals_answer_and_no_renewal_is_asked():
    probe, call = _probe({"licence": (200, {"ok": False, "error": "SIGNER_UNAVAILABLE"})})
    got = lab.renew("account-bench", probe=probe, licences={})
    assert got == proof.Answer(False, "SIGNER_UNAVAILABLE")
    assert [r[3]["kind"] for r in call.requests] == ["licence"]


def test_the_company_scope_cases_mirror_the_probe_route():
    source = (
        pathlib.Path(paths.repo_root()) / "private/account/src/services/signer-probe.service.ts"
    ).read_text()
    block = source.split("SIGNER_PROBE_COMPANY_SCOPE_CASES = [", 1)[1].split("]", 1)[0]
    assert re.findall(r"'([a-z-]+)'", block) == list(proof.COMPANY_SCOPE_CODES)


def test_a_new_lab_forgets_the_licences_of_the_last(monkeypatch):
    monkeypatch.setitem(lab._LICENCES, "account-bench", SIGNED)
    lab.build(bench=True)
    assert lab._LICENCES == {}


def test_the_v1_methods_bind_to_this_module_not_the_signer_deploy_module():
    for method in ("signer_props", "issue", "renew", "current_licence_works"):
        assert lab.OWNERS[method] == "V1"
    assert lab.SEAMS["V1"].module == lab.__name__


ACCOUNT_CONFIGS = sorted(
    (pathlib.Path(paths.repo_root()) / "workers" / "account").glob("wrangler.*.toml")
)


def test_the_account_configs_are_found():
    """Control: the parametrized check below has every shared config to read."""
    assert {p.name for p in ACCOUNT_CONFIGS} >= {
        "wrangler.eu.toml",
        "wrangler.us.toml",
        "wrangler.asia.toml",
        "wrangler.bench.toml",
    }


@pytest.mark.parametrize("config", ACCOUNT_CONFIGS, ids=lambda p: p.name)
def test_every_account_config_binds_the_props_its_signer_requires(config):
    """The props each account Worker deploys with are the identity the lab expects of it, in the shape the signer parses."""
    doc = tomllib.loads(config.read_text(encoding="utf-8"))
    bound = [s for s in doc.get("services", []) if s.get("binding") == "LICENSE_SIGNER"]
    assert len(bound) == 1, "%s binds LICENSE_SIGNER %d times" % (config.name, len(bound))
    binding = bound[0]
    assert binding.get("entrypoint") == "LicenseSigner"
    # parseSignerCaller (private/account/src/services/license-signer.service.ts): a shared caller is exactly {tier, region}.
    props = binding.get("props")
    assert props == {"tier": "shared", "region": doc["vars"]["REGION"]}
    assert deploy_signer.expected_props(doc["name"], companies=lambda _bench: []) == props


# --- the live add's bws project -----------------------------------------------


def _drive_live_add(monkeypatch, project: str | None) -> dict[str, object]:
    seen: dict[str, object] = {}
    if project is None:
        monkeypatch.delenv(lab.BWS_PROJECT_ENV, raising=False)
    else:
        monkeypatch.setenv(lab.BWS_PROJECT_ENV, project)
    monkeypatch.setattr(lab.control_db, "ensure_all", lambda **_k: None)
    monkeypatch.setattr(lab.control_db, "transport", lambda: None)

    def fake_provision(pid, **_k):
        seen["project"] = pid
        return lambda _company: None

    def fake_actions(*, provision=None, **_k):
        seen["provision"] = provision
        return []

    monkeypatch.setattr(onboarding, "live_provision", fake_provision)
    monkeypatch.setattr(onboarding, "live_actions", fake_actions)
    monkeypatch.setattr(onboarding, "run", lambda *_a, **_k: onboarding.Outcome(0, "c1", ()))
    req = onboarding.Request(
        name="x",
        region="eu",
        owner="o@x.example",
        storage_gb=1,
        unlisted=True,
        lookup_domain="x.example",
        bench=True,
    )
    _lab()._live_add(req)
    return seen


def test_live_add_passes_the_env_bws_project_to_onboarding(monkeypatch):
    seen = _drive_live_add(monkeypatch, "proj-123")
    assert seen["project"] == "proj-123"
    assert callable(seen["provision"])


def test_live_add_without_the_bws_project_passes_no_provisioner(monkeypatch):
    assert _drive_live_add(monkeypatch, None)["provision"] is None


def test_live_add_with_an_empty_bws_project_passes_no_provisioner(monkeypatch):
    # Review e8770edd.1: an empty value is unset, never a project named "".
    assert _drive_live_add(monkeypatch, "")["provision"] is None
