"""enterprise.lab: the live Lab the proof verbs drive, its seams for the boxes not built yet, and its binding of `enterprise add`. Fakes only."""

from __future__ import annotations

import datetime
import functools
import json
import socket
import subprocess
import sys
import types

import pytest

from rediacc_ci.core import https
from rediacc_ci.enterprise import lab, onboarding, proof
from rediacc_ci.ops import enterprise_lookup
from rediacc_ci.well_known import PRODUCT_DOMAIN


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test in this file reaches a child process, an HTTPS request or a TLS socket: the live readers take fakes."""

    def boom(*_a, **_k):
        raise AssertionError("a test reached a live call")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(https, "urlopen", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
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
        ("issue", ("account-bench", "licence"), {}, "S2"),
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
    kv = Kv({_key_add("acme.example"): "acme.rediacc.cloud"})
    assert lab.lookup("ACME.example.", run=kv, pepper="pep") == "acme.rediacc.cloud"
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

    with pytest.raises(proof.LabError, match="exited 1"):
        lab.lookup("acme.example", run=broken, pepper="pep")


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
    widgets = [
        {"name": "rediacc-console", "domains": ["rediacc.cloud", "Bench.rediacc.cloud"]},
        {"name": "other", "domains": ["example.org"]},
    ]
    got = lab.turnstile_domains(listing=lambda _p: widgets)
    assert got == ["rediacc.cloud", "bench.rediacc.cloud"]


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
    assert proof.run_verb("routing", built, bench=True, out=lines.append) == 0, lines


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
    assert proof.run_verb("routing", built, bench=True, out=lines.append) == 1
    assert any(line.startswith("BROKEN") and "status." in line for line in lines)


def test_the_cloudflare_credentials_are_required(monkeypatch):
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN")
    with pytest.raises(proof.LabError, match="CLOUDFLARE_API_TOKEN"):
        lab.account_path("/x")


# --- proxy ---------------------------------------------------------------
# The token readers (box V6) and the proxy readers (box V7): the session presenter, the executor readers, and the drivers that are not built refusing by name. Fakes only.


ROWS_PROXY = [
    {"id": "c0000000a", "name": "proof-a", "state": "active"},
    {"id": "c0000000b", "name": "proof-b", "state": "active"},
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


@pytest.mark.parametrize("kind", ["api-token", "config-token", "e2e-envelope", "proxy-token"])
def test_kinds_without_a_read_only_probe_are_not_built(kind):
    with pytest.raises(proof.LabError, match="not built yet: V6"):
        lab.present("c0000000a", kind, "x", send=Server({}), companies=companies_proxy)


def test_mint_without_a_minter_is_not_built_and_a_minter_is_used():
    with pytest.raises(proof.LabError, match="not built yet: V6"):
        lab.mint("c0000000a", "session")
    assert lab.mint("c0000000a", "session", minter=lambda c, k: "%s:%s" % (c, k)) == (
        "c0000000a:session"
    )


def test_the_replay_proof_stops_at_the_minter_by_name():
    class Lab:
        def ensure_company(self, label, region, *, ring=None):
            del region, ring
            return {"proof-replay-a": "c0000000a", "proof-replay-b": "c0000000b"}[label]

        mint = staticmethod(lab.mint)
        present = staticmethod(lab.present)

    lines: list[str] = []
    assert proof.run_verb("replay", Lab(), bench=True, out=lines.append) == 1
    assert any("not built yet: V6" in line for line in lines)


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


@pytest.mark.parametrize(
    ("call", "args", "kwargs"),
    [
        (lab.console_command, ("c0000000a",), {}),
        (lab.set_allowlist, ("c0000000a", ["192.0.2.10"]), {}),
        (
            lab.request_from,
            ("c0000000a",),
            {"foreign": True, "method": "GET", "path": "/"},
        ),
    ],
)
def test_the_unbuilt_proxy_drivers_refuse_by_name(call, args, kwargs):
    with pytest.raises(proof.LabError, match="not built yet: V7"):
        call(*args, **kwargs)


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
    assert proof.run_verb("cost", Lab(), bench=True, out=lines.append) == 1
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
    shared = [g for g in GROUPS_COST if g["dimensions"]["scriptName"] == "account-eu"]
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


def test_the_unbuilt_drivers_refuse_by_name_and_a_driver_is_used():
    with pytest.raises(proof.LabError, match="not built yet: V9"):
        lab.executor_upload("vm-1")
    with pytest.raises(proof.LabError, match="not built yet: V9"):
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
    with pytest.raises(proof.LabError, match="no .* run appeared"):
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


def test_run_surfaces_reads_logs_both_apis_and_each_job_summary():
    def gh(argv, cwd, env):
        del cwd, env
        args = list(argv[1:])
        if args[:2] == ["run", "view"]:
            return lab.Proc(0, "log line\n")
        if args[1].endswith("/jobs"):
            return lab.Proc(0, json.dumps({"jobs": [{"id": 5}, {"id": 6}]}))
        if "/check-runs/" in args[1]:
            job = args[1].rsplit("/", 1)[1]
            return lab.Proc(
                0, json.dumps({"output": {"title": None, "summary": "sum %s" % job, "text": ""}})
            )
        return lab.Proc(0, json.dumps({"id": 77, "name": "Enterprise release"}))

    got = lab.run_surfaces("77", run=gh)
    assert set(got) == set(proof.GITHUB_SURFACES)
    assert got["logs"] == "log line\n"
    assert got["step-summary"] == "sum 5\nsum 6"
    assert '"id": 77' in got["run-api"]


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
    assert proof.run_verb("github", Lab(), bench=True, out=lines.append) == 1
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


def rows_left(state):
    return lambda _b: [
        {"id": "c00000001", "name": "proof-remove", "region": "eu", "state": state, "unlisted": 1}
    ]


def test_a_kept_company_lists_every_piece_by_kind():
    acct = Account(present=True)
    got = lab.leftovers(
        "c00000001", companies=rows_left("active"), listing=acct.listing, buckets=acct.buckets
    )
    assert got == [
        "control row (state active)",
        "account Worker",
        "proxy Worker",
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
    assert (
        lab.leftovers(
            "c00000001", companies=rows_left("removed"), listing=acct.listing, buckets=acct.buckets
        )
        == []
    )


def test_a_similar_database_name_is_not_this_companys():
    def listing(path):
        if path.startswith("/accounts/acct/d1/database?name="):
            return [{"name": "account-proof-remove-ci"}]
        return []

    got = lab.leftovers(
        "c00000001", companies=rows_left("removed"), listing=listing, buckets=lambda _j: set()
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
