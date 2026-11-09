"""enterprise.lab: the live Lab the proof verbs drive, its seams for the boxes not built yet, and its binding of `enterprise add`. Fakes only."""

from __future__ import annotations

import sys
import types

import pytest

from rediacc_ci.enterprise import lab, onboarding, proof


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
