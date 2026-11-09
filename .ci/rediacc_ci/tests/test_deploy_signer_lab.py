"""The S2 lab method group of `rediacc_ci.deploy.deploy_signer`: bound by name from `rediacc_ci.enterprise.lab`, signatures from the `Lab` protocol, behaviour over fake transports."""

from __future__ import annotations

import inspect
import json
from typing import Any

import pytest

from rediacc_ci.deploy import deploy_signer as ds
from rediacc_ci.enterprise import lab, proof


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
        self.stdout, self.rc = stdout, rc

    def __call__(self, argv, _cwd, _stdin):
        self.calls.append(list(argv))
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


def test_stop_signer_deletes_only_a_known_signer():
    run = FakeRun()
    ds.stop_signer("signer-bench-eu", run=run)
    assert run.calls[0][-4:] == ["delete", "--name", "signer-bench-eu", "--force"]
    with pytest.raises(proof.LabError):
        ds.stop_signer("account-bench", run=run)
    assert len(run.calls) == 1


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


def test_certificate_audited_escapes_like_wildcards_in_the_id(monkeypatch):
    seen: dict = {}

    def query(_database, sql, params, **_kw):
        seen.update(sql=sql, params=params)
        return [{"n": 0}]

    monkeypatch.setattr(ds.control_db, "query", query)
    ds.certificate_audited("signer-eu", "a%b_c")
    assert "ESCAPE '\\'" in seen["sql"]
    assert "a\\%b\\_c" in seen["params"][1]


def test_cut_region_stops_the_bench_signer_and_refuses_other_regions():
    run = FakeRun()
    ds.cut_region("eu", run=run)
    assert run.calls[0][-2:] == ["signer-bench-eu", "--force"]
    with pytest.raises(proof.LabError):
        ds.cut_region("asia", run=run)


def test_a_failed_delete_is_a_lab_error():
    with pytest.raises(proof.LabError):
        ds.stop_signer("signer-bench-us", run=FakeRun(rc=1))


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
