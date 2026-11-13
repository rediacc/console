"""The S2 lab method group of `rediacc_ci.deploy.deploy_signer`: bound by name from `rediacc_ci.enterprise.lab`, signatures from the `Lab` protocol, behaviour over fake transports."""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest

from rediacc_ci.deploy import deploy_signer as ds
from rediacc_ci.enterprise import lab, proof
from rediacc_ci.ops import bench_production

KEYS = {
    "CLOUDFLARE_API_TOKEN": "t",
    "ACCOUNT_ED25519_PRIVATE_KEY": "k",
    "ACCOUNT_ED25519_PUBLIC_KEY": "p",
}


@pytest.fixture(autouse=True)
def _nothing_declared(monkeypatch):
    """The live `.ci/config/bench-production.json` decides nothing here; a test that needs a declaration passes one."""
    monkeypatch.setattr(bench_production, "load", lambda *_a: [])


DECLARED = [
    bench_production.Protected(
        "11111111-2222-4333-8444-555555555555", "hostinger", "production backups"
    )
]


def _protocol_signature(name: str) -> inspect.Signature:
    return inspect.signature(getattr(proof.Lab, name))


def test_every_method_of_the_s2_group_exists_and_matches_the_protocol():
    group = lab._GROUPS["S2"]
    assert lab.SEAMS["S2"].module == ds.SELF
    for name in group:
        fn = getattr(ds, name, None)
        assert callable(fn), "deploy_signer has no %s" % name
        want = [p for p in _protocol_signature(name).parameters.values() if p.name != "self"]
        have = list(inspect.signature(fn).parameters.values())
        for w, h in zip(want, have[: len(want)], strict=True):
            assert (w.name, w.kind) == (h.name, h.kind), name
        for extra in have[len(want) :]:
            assert extra.kind is inspect.Parameter.KEYWORD_ONLY, "%s.%s" % (name, extra.name)
            assert extra.default is not inspect.Parameter.empty, "%s.%s" % (name, extra.name)


def test_the_group_list_and_the_protocol_signer_section_agree():
    source = inspect.getsource(proof.Lab)
    section = source.split("# Workers, secrets and signers.")[1].split("# Companies.")[0]
    declared = [
        line.split("def ")[1].split("(")[0] for line in section.splitlines() if "def " in line
    ]
    assert declared == list(lab._GROUPS["S2"])


class FakeRun:
    def __init__(self, stdout: str = "[]", rc: int = 0):
        self.calls: list[list[str]] = []
        self.stdins: list[str | None] = []
        self.stdout, self.rc = stdout, rc

    def __call__(self, argv, _cwd, stdin):
        self.calls.append(list(argv))
        self.stdins.append(stdin)
        return ds.Result(self.rc, self.stdout, "")


@pytest.fixture(autouse=True)
def _wrangler_present(monkeypatch):
    monkeypatch.setattr(ds.wrangler, "require", lambda _cwd, _env=None: list(ds.wrangler.ARGV))


def companies(_bench: bool) -> list[dict]:
    return [{"id": "c0123456789abcdef", "name": "acme", "region": "us", "state": "active"}]


def test_account_workers_bench_lists_account_bench_then_the_companies():
    assert ds.account_workers(bench=True, companies=companies) == ["account-bench", "account-acme"]


def test_account_workers_production_lists_each_region():
    got = ds.account_workers(bench=False, companies=lambda _b: [])
    assert got[0].startswith("account-")
    assert "account-bench" not in got
    assert len(got) == len(ds.load_region_ids(ds._root()))


def test_signers_bench_and_production():
    assert ds.signers(bench=True) == ["signer-bench-eu", "signer-bench-us"]
    assert all(s.startswith("signer-") and "bench" not in s for s in ds.signers(bench=False))


def test_secret_names_runs_wrangler_secret_list_by_name():
    run = FakeRun(json.dumps([{"name": "B", "type": "secret_text"}, {"name": "A"}]))
    assert ds.secret_names("account-bench", run=run) == ["A", "B"]
    assert run.calls[0][-6:] == ["secret", "list", "--format", "json", "--name", "account-bench"]


def test_secret_names_failure_is_a_lab_error_not_an_empty_list():
    with pytest.raises(proof.LabError):
        ds.secret_names("account-bench", run=FakeRun(rc=1))
    with pytest.raises(proof.LabError):
        ds.secret_names("account-bench", run=FakeRun("not json"))


def settings(props: dict | None = None, service: str = "signer-bench-eu"):
    binding: dict[str, Any] = {"type": "service", "name": "LICENSE_SIGNER", "service": service}
    if props is not None:
        binding["props"] = props
    other = {"type": "d1", "name": "DB"}

    def api(path: str):
        assert path == "/workers/scripts/account-bench/settings"
        return {"bindings": [other, binding]}

    return api


def test_signer_of_and_props_read_the_license_signer_binding():
    props = {"tier": "shared", "region": "eu"}
    assert ds.signer_of("account-bench", api=settings(props)) == "signer-bench-eu"
    assert ds.signer_props("account-bench", api=settings(props)) == props


def test_props_absent_on_the_binding_read_as_empty_and_a_missing_binding_is_an_error():
    assert ds.signer_props("account-bench", api=settings()) == {}
    with pytest.raises(proof.LabError):
        ds.signer_of("account-bench", api=lambda _p: {"bindings": []})


def test_expected_props_shared_and_company():
    assert ds.expected_props("account-bench", companies=companies) == {
        "tier": "shared",
        "region": ds._account_region("wrangler.bench.toml"),
    }
    region = ds.load_region_ids(ds._root())[0]
    assert ds.expected_props("account-" + region, companies=companies) == {
        "tier": "shared",
        "region": region,
    }
    assert ds.expected_props("account-acme", companies=companies) == {
        "tier": "enterprise",
        "companyId": "c0123456789abcdef",
        "region": "us",
    }
    with pytest.raises(proof.LabError):
        ds.expected_props("account-nobody", companies=companies)


def test_issue_without_a_probe_refuses_by_name_and_never_answers():
    with pytest.raises(proof.LabError, match="not built yet: S4"):
        ds.issue("account-bench", "licence")


def test_issue_renew_and_current_go_through_the_probe():
    seen: list[tuple[str, str, str]] = []

    def probe(caller: str, action: str, kind: str) -> proof.Answer:
        seen.append((caller, action, kind))
        return proof.Answer(ok=action != "renew", error="" if action != "renew" else "SIGNER_X")

    assert ds.issue("account-bench", "over-limit", probe=probe).ok
    assert not ds.renew("account-bench", probe=probe).ok
    assert ds.current_licence_works("account-bench", probe=probe)
    assert seen == [
        ("account-bench", "issue", "over-limit"),
        ("account-bench", "renew", "licence"),
        ("account-bench", "current", "licence"),
    ]


COMPANIES = [
    {"id": "c00000000000000aa", "name": "probe500", "region": "eu", "state": "active"},
    {"id": "c00000000000000bb", "name": "proof-loss-eu", "region": "eu", "state": "active"},
]


def _companies(_bench: bool) -> list[dict]:
    return COMPANIES


def _scoped_to(*pairs: tuple[str, str]):
    def scoped(_bench: bool) -> set[tuple[str, str]]:
        return set(pairs)

    return scoped


def test_callers_ask_only_companies_with_a_scope_row_and_name_the_rest():
    """account-probe500 had no scope row, and every claim for it failed with SIGNER_UNKNOWN_COMPANY (2026-11-13)."""
    scoped = _scoped_to(("eu", "c00000000000000bb"))
    assert ds.callers(bench=True, companies=_companies, scoped=scoped) == [
        "account-bench",
        "account-proof-loss-eu",
    ]
    assert ds.unscoped_callers(bench=True, companies=_companies, scoped=scoped) == [
        "account-probe500"
    ]
    # A scope row in another region's control database is not the company's: the signer joins within one database.
    elsewhere = _scoped_to(("us", "c00000000000000aa"), ("eu", "c00000000000000bb"))
    assert ds.unscoped_callers(bench=True, companies=_companies, scoped=elsewhere) == [
        "account-probe500"
    ]
    # control: every company scoped, none named; account_workers still lists all of them for the key check
    every = _scoped_to(*(("eu", r["id"]) for r in COMPANIES))
    assert ds.unscoped_callers(bench=True, companies=_companies, scoped=every) == []
    assert ds.account_workers(bench=True, companies=_companies) == [
        "account-bench",
        "account-probe500",
        "account-proof-loss-eu",
    ]


def test_no_company_reads_no_scope():
    def scoped(_bench):
        raise AssertionError("scope read with no company")

    assert ds.callers(bench=True, companies=lambda _b: [], scoped=scoped) == ["account-bench"]


def test_default_scoped_reads_every_control_database(monkeypatch):
    def read_all(_self, sql, _params=None):
        assert sql == ds.SCOPED_SQL
        return {"eu": [{"company_id": "c1"}], "us": [{"company_id": "c2"}]}

    monkeypatch.setattr(ds.control_db, "transport", lambda: None)
    monkeypatch.setattr(ds.registry.Registry, "read_all", read_all)
    assert ds.default_scoped(True) == {("eu", "c1"), ("us", "c2")}


SECRET_DELETE = ["secret", "delete", "ACCOUNT_ED25519_PRIVATE_KEY", "--name", "signer-bench-eu"]


def test_stop_signer_deletes_the_private_key_secret_not_the_worker():
    """Deleting the Worker detached account-bench's LICENSE_SIGNER binding on 2026-11-12; the stop deletes the key."""
    run = FakeRun(json.dumps([{"name": "ACCOUNT_ED25519_PUBLIC_KEY"}]))
    ds.stop_signer("signer-bench-eu", run=run, env=KEYS)
    assert run.calls[0][len(ds.wrangler.ARGV) :] == SECRET_DELETE
    assert run.stdins[0] == "y\n"
    assert "--force" not in run.calls[0]
    assert run.calls[0][len(ds.wrangler.ARGV) : len(ds.wrangler.ARGV) + 2] != ["delete", "--name"]
    # The secret list is read back by name after the delete.
    assert run.calls[1][-6:] == ["secret", "list", "--format", "json", "--name", "signer-bench-eu"]
    assert len(run.calls) == 2
    with pytest.raises(proof.LabError):
        ds.stop_signer("account-bench", run=run, env=KEYS)
    assert len(run.calls) == 2


@pytest.mark.parametrize("signer", ["signer-bench-eu", "signer-bench-us"])
def test_stop_and_cut_refuse_while_bench_carries_production_data(signer):
    run = FakeRun(json.dumps([{"name": "ACCOUNT_ED25519_PUBLIC_KEY"}]))
    with pytest.raises(proof.LabError, match=r"bench carries production data.*hostinger"):
        ds.stop_signer(signer, run=run, env=KEYS, protected=lambda: DECLARED)
    with pytest.raises(proof.LabError, match="is not stopped or cut"):
        ds.cut_region(signer.rsplit("-", 1)[1], run=run, env=KEYS, protected=lambda: DECLARED)
    assert run.calls == []
    assert "hostinger" in ds.stop_refusal(signer, protected=lambda: DECLARED)
    # control: with nothing declared the stop deletes the key
    assert ds.stop_refusal(signer, protected=list) == ""
    ds.stop_signer(signer, run=run, env=KEYS, protected=list)
    assert run.calls[0][len(ds.wrangler.ARGV) : len(ds.wrangler.ARGV) + 3] == [
        "secret",
        "delete",
        "ACCOUNT_ED25519_PRIVATE_KEY",
    ]


def test_an_unreadable_declaration_refuses_the_stop(monkeypatch):
    def unreadable(*_a):
        raise bench_production.ProductionRefusalError("cannot read; the guard fails closed")

    monkeypatch.setattr(bench_production, "load", unreadable)
    run = FakeRun()
    assert "fails closed" in ds.stop_refusal("signer-bench-eu")
    with pytest.raises(proof.LabError, match="fails closed"):
        ds.cut_region("eu", run=run, env=KEYS)
    assert run.calls == []


def test_stop_refusal_reads_the_declaration_by_default(monkeypatch):
    monkeypatch.setattr(bench_production, "load", lambda *_a: DECLARED)
    assert "production backups" in ds.stop_refusal("signer-bench-eu")


def test_stop_signer_refuses_a_signer_that_still_lists_its_private_key():
    run = FakeRun(json.dumps([{"name": "ACCOUNT_ED25519_PRIVATE_KEY"}]))
    with pytest.raises(
        proof.LabError, match="signer-bench-eu still holds ACCOUNT_ED25519_PRIVATE_KEY"
    ):
        ds.stop_signer("signer-bench-eu", run=run, env=KEYS)


def test_stop_signer_refuses_before_the_delete_when_the_restart_key_is_unbound():
    run = FakeRun()
    with pytest.raises(proof.LabError, match="ACCOUNT_ED25519_PRIVATE_KEY"):
        ds.stop_signer("signer-bench-eu", run=run, env={"ACCOUNT_ED25519_PUBLIC_KEY": "p"})
    with pytest.raises(proof.LabError, match="not stopped"):
        ds.cut_region("eu", run=run, env={})
    without_token = {k: v for k, v in KEYS.items() if k != "CLOUDFLARE_API_TOKEN"}
    with pytest.raises(proof.LabError, match="CLOUDFLARE_API_TOKEN"):
        ds.stop_signer("signer-bench-eu", run=run, env=without_token)
    assert run.calls == []


@pytest.mark.parametrize("name", ["signer-eu", "signer-us", "signer-asia", "account-eu", "nope"])
def test_stop_and_start_refuse_every_non_bench_signer(name):
    run = FakeRun()
    with pytest.raises(proof.LabError, match="bench signer"):
        ds.stop_signer(name, run=run)
    with pytest.raises(proof.LabError, match="bench signer"):
        ds.start_signer(name, run=run)
    assert run.calls == []


def test_start_signer_redeploys_a_bench_signer_and_translates_refusals(monkeypatch):
    seen: list[str] = []

    def fake_deploy(_root, key, **_kw):
        seen.append(key)

    monkeypatch.setattr(ds, "deploy", fake_deploy)
    ds.start_signer("signer-bench-us", run=FakeRun(), env={})
    assert seen == ["bench-us"]

    def refuse(*_a, **_k):
        raise ds.RefusedError("no key", "second line")

    monkeypatch.setattr(ds, "deploy", refuse)
    with pytest.raises(proof.LabError, match="no key; second line"):
        ds.start_signer("signer-bench-eu", run=FakeRun(), env={})

    def missing(*_a, **_k):
        raise ds.wrangler.WranglerNotInstalledError("wrangler absent")

    monkeypatch.setattr(ds, "deploy", missing)
    with pytest.raises(proof.LabError):
        ds.start_signer("signer-bench-eu", run=FakeRun(), env={})


def test_restore_region_redeploys_the_bench_signer_and_refuses_other_regions(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(ds, "deploy", lambda _r, key, **_k: seen.append(key))
    ds.restore_region("eu", run=FakeRun(), env={})
    assert seen == ["bench-eu"]
    with pytest.raises(proof.LabError):
        ds.restore_region("asia", run=FakeRun(), env={})


def test_certificate_audited_matches_the_id_literally_without_a_like_pattern(monkeypatch):
    """D1 refuses a LIKE pattern over 50 bytes, which `proof signer --bench` hit on 2026-11-12."""
    seen: dict = {}

    def query(_database, sql, params, **_kw):
        seen.update(sql=sql, params=params)
        return [{"n": 0}]

    monkeypatch.setattr(ds.control_db, "query", query)
    ds.certificate_audited("signer-eu", "a%b_c")
    assert "LIKE" not in seen["sql"].upper()
    assert "instr(detail, ?)" in seen["sql"]
    assert seen["params"][1] == '"subscriptionId":"a%b_c"'
    ds.certificate_audited("signer-eu", "Sub-AbC")
    # The needle keeps the id's case: instr is an exact, case-sensitive match.
    assert seen["params"][1] == '"subscriptionId":"Sub-AbC"'


def test_cut_region_stops_the_bench_signer_and_refuses_other_regions():
    run = FakeRun()
    ds.cut_region("eu", run=run, env=KEYS)
    assert run.calls[0][len(ds.wrangler.ARGV) :] == SECRET_DELETE
    with pytest.raises(proof.LabError):
        ds.cut_region("asia", run=run, env=KEYS)


def test_a_failed_secret_delete_is_a_lab_error_and_reads_nothing_back():
    run = FakeRun(rc=1)
    with pytest.raises(proof.LabError, match="secret delete ACCOUNT_ED25519_PRIVATE_KEY"):
        ds.stop_signer("signer-bench-us", run=run, env=KEYS)
    assert len(run.calls) == 1


def test_certificate_audited_queries_the_signer_regions_control_database(monkeypatch):
    seen: dict = {}

    def query(database, _sql, params, **_kw):
        seen.update(database=database, params=params)
        return [{"n": 1}]

    monkeypatch.setattr(ds.control_db, "query", query)
    assert ds.certificate_audited("signer-bench-eu", "sub-1")
    assert seen["database"] == "control-bench-eu"
    assert seen["params"][0] == "delegation_cert.signed"
    assert '"subscriptionId":"sub-1"' in seen["params"][1]
    monkeypatch.setattr(ds.control_db, "query", lambda *_a, **_k: [{"n": 0}])
    assert not ds.certificate_audited("signer-eu", "sub-1")
    with pytest.raises(proof.LabError):
        ds.certificate_audited("account-eu", "sub-1")


def test_the_live_lab_binds_the_group_now():
    live = lab.build(bench=True)
    assert live.signers(bench=True) == ["signer-bench-eu", "signer-bench-us"]
