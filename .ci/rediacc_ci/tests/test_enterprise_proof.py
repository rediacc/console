"""`rediacc_ci.enterprise.proof` (agent/plans/PLAN-enterprise-isolation.md box P1): each verb passes against a healthy recording fake, exits non-zero on each broken claim, and puts back what it broke."""

from __future__ import annotations

import dataclasses
import pathlib
from typing import TYPE_CHECKING, cast

import pytest

from rediacc_ci.enterprise import proof
from rediacc_ci.enterprise.proof import AddResult, Answer, LabError, ReleaseResult, Reply

if TYPE_CHECKING:
    from collections.abc import Sequence

DOMAIN = "bench.example"
OK = Answer(ok=True)


def refused(error: str = "refused by scope") -> Answer:
    return Answer(ok=False, error=error)


@dataclasses.dataclass
class FakeLab:
    """A healthy bench, recording every call. Each test breaks one thing."""

    calls: list[str] = dataclasses.field(default_factory=list)
    companies: dict[str, tuple[str, str | None]] = dataclasses.field(default_factory=dict)
    secrets: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    props_override: dict[str, dict[str, str]] = dataclasses.field(default_factory=dict)
    admit_cases: set[str] = dataclasses.field(default_factory=set)
    stopped: set[str] = dataclasses.field(default_factory=set)
    cut: set[str] = dataclasses.field(default_factory=set)
    licence_survives: bool = True
    raise_on: str = ""
    stopped_error_names_signer: bool = True
    # add
    added: dict[str, str] = dataclasses.field(default_factory=dict)
    rerun_changes: tuple[str, ...] = ()
    unlisted_hits: bool = False
    free_mail_admitted: bool = False
    # routing
    wrong_worker: str = ""
    logged_host: str = ""
    turnstile: list[str] = dataclasses.field(default_factory=lambda: [DOMAIN])
    # release
    version: dict[str, str] = dataclasses.field(default_factory=dict)
    skip_without_order_admitted: bool = False
    stop_names: str = ""
    fast_moves_on_stop: bool = False
    # replay / proxy
    cross_accepts: str = ""
    shared_container: bool = False
    allowlist: list[str] = dataclasses.field(default_factory=list)
    renew_blocked_by_allowlist: bool = False
    # cost
    limits: dict[str, int] = dataclasses.field(default_factory=lambda: dict(proof.PLAN_LIMITS))
    usage_missing: bool = False
    # renet
    renet: str = "1.0.0"
    read_only_moves: bool = False
    upload_admitted: bool = False
    # github
    leak_surface: str = ""
    empty_surface: str = ""
    # remove
    exported: set[str] = dataclasses.field(default_factory=set)
    removed: set[str] = dataclasses.field(default_factory=set)
    removes_under_gha: bool = False
    leaves_d1: bool = False

    def _rec(self, name: str) -> None:
        self.calls.append(name)
        if self.raise_on == name:
            msg = f"{name} failed"
            raise LabError(msg)

    # -- workers and signers
    def account_workers(self, *, bench: bool) -> list[str]:
        self._rec("account_workers")
        base = ["account-bench"] if bench else ["account-eu", "account-us", "account-asia"]
        return base + [f"account-{c}" for c in self.companies]

    def signers(self, *, bench: bool) -> list[str]:
        self._rec("signers")
        return (
            ["signer-bench-eu", "signer-bench-us"]
            if bench
            else ["signer-eu", "signer-us", "signer-asia"]
        )

    def secret_names(self, worker: str) -> list[str]:
        self._rec("secret_names")
        if worker in self.secrets:
            return self.secrets[worker]
        if worker.startswith("signer-"):
            return [proof.PRIVATE_KEY, "ACCOUNT_ED25519_PUBLIC_KEY"]
        return ["ACCOUNT_ED25519_PUBLIC_KEY", "ACCOUNT_JWT_SECRET"]

    def callers(self, *, bench: bool) -> list[str]:
        self._rec("callers")
        return ["account-bench", "account-cabc123"] if bench else ["account-eu", "account-us"]

    def signer_of(self, caller: str) -> str:
        return (
            "signer-bench-eu" if caller.endswith(("bench", "cabc123", "eu")) else "signer-bench-us"
        )

    def signer_props(self, caller: str) -> dict[str, str]:
        self._rec("signer_props")
        return self.props_override.get(caller, self.expected_props(caller))

    def expected_props(self, caller: str) -> dict[str, str]:
        return {"tier": "enterprise" if caller.endswith("cabc123") else "shared", "caller": caller}

    def issue(self, caller: str, kind: str) -> Answer:
        self._rec(f"issue:{kind}")
        signer = self.signer_of(caller)
        if signer in self.stopped or ("eu" in signer and "eu" in self.cut and "us" not in signer):
            name = signer if self.stopped_error_names_signer else "upstream"
            return refused(f"{name} is unreachable")
        if kind in proof.SCOPE_CASES:
            return OK if kind in self.admit_cases else refused(f"{kind} refused")
        if kind == "certificate":
            return Answer(ok=True, body={"id": "cert-1"})
        return OK

    def certificate_audited(self, signer: str, certificate_id: str) -> bool:
        self._rec("certificate_audited")
        return bool(signer) and certificate_id == "cert-1"

    def current_licence_works(self, caller: str) -> bool:
        del caller
        self._rec("current_licence_works")
        return self.licence_survives

    def renew(self, caller: str) -> Answer:
        self._rec("renew")
        return self.issue(caller, "licence")

    def stop_signer(self, signer: str) -> None:
        self._rec("stop_signer")
        self.stopped.add(signer)

    def start_signer(self, signer: str) -> None:
        self._rec("start_signer")
        self.stopped.discard(signer)

    def cut_region(self, region: str) -> None:
        self._rec("cut_region")
        self.cut.add(region)

    def restore_region(self, region: str) -> None:
        self._rec("restore_region")
        self.cut.discard(region)

    # -- companies
    def ensure_company(self, label: str, region: str, *, ring: str | None = None) -> str:
        self._rec("ensure_company")
        cid = "c" + format(abs(hash(label)) % (16**8), "08x")
        self.companies[cid] = (label, ring)
        self.version.setdefault(cid, "0.9.0")
        self.version.setdefault("fast", "0.9.1")
        del region
        return cid

    def caller_of(self, company: str) -> str:
        return f"account-{company}-{'us' if 'us' in self.companies[company][0] else 'eu'}"

    def company_hosts(self, company: str) -> tuple[str, str]:
        label = self.companies[company][0] if company in self.companies else company
        return (f"{label}.{DOMAIN}", f"{label}-proxy.{DOMAIN}")

    def company_words(self, company: str) -> list[str]:
        return [self.companies[company][0], *self.company_hosts(company)]

    def add(
        self, label: str, *, owner: str, unlisted: bool, lookup_domain: str, kill_after: str = ""
    ) -> AddResult:
        self._rec(f"add:{kill_after or 'run'}")
        del owner, unlisted
        if lookup_domain == proof.FREE_MAIL_DOMAIN and not self.free_mail_admitted:
            return AddResult(rc=2, error="free-mail domain refused")
        if kill_after:
            return AddResult(rc=137, error="killed")
        cid = self.ensure_company(label, "eu")
        changed = self.rerun_changes if label in self.added else ("control", "d1", "buckets")
        self.added[label] = cid
        return AddResult(rc=0, company=cid, changed=changed)

    def captured_mail(self, owner: str) -> list[str]:
        return [f"invitation to {owner}"]

    def lookup(self, domain: str) -> str | None:
        label = domain.removesuffix(".example")
        if label == "proof-unlisted" and not self.unlisted_hits:
            return None
        return f"{label}.{DOMAIN}"

    def export(self, company: str) -> int:
        self._rec("export")
        self.exported.add(company)
        return 0

    def remove(self, company: str, *, delete_data: bool, github_actions: bool) -> int:
        self._rec(f"remove:gha={github_actions}")
        del delete_data
        if company not in self.exported or (github_actions and not self.removes_under_gha):
            return 2
        self.removed.add(company)
        return 0

    def leftovers(self, company: str) -> list[str]:
        if company in self.removed:
            return ["d1"] if self.leaves_d1 else []
        return ["control", "d1", "buckets"]

    # -- routing
    def fetch(self, host: str) -> Reply:
        self._rec("fetch")
        worker = self.expected_worker(host)
        if self.wrong_worker and host.startswith(self.wrong_worker):
            worker = "account-bench"
        return Reply(200, worker, (f"*.{DOMAIN}", DOMAIN))

    def expected_worker(self, host: str) -> str:
        label = host.split(".", 1)[0]
        if label.endswith("-proxy"):
            return f"proxy-{label.removesuffix('-proxy')}"
        return f"account-{label}"

    def region_hosts(self, *, bench: bool) -> list[str]:
        return [f"bench.{DOMAIN}"] if bench else [f"eu.{DOMAIN}"]

    def specific_hosts(self) -> list[str]:
        return [f"www.{DOMAIN}"]

    def cert_log_names(self) -> list[str]:
        return [f"*.{DOMAIN}", DOMAIN] + ([self.logged_host] if self.logged_host else [])

    def turnstile_domains(self) -> list[str]:
        return self.turnstile

    # -- releases
    def target_version(self) -> str:
        return "0.9.1"

    def versions(self, targets: Sequence[str]) -> dict[str, str]:
        return {t: self.version.get(t, "") for t in targets}

    def _ring_ids(self) -> dict[str, str]:
        return {ring: cid for cid, (_, ring) in self.companies.items() if ring}

    def release(
        self,
        *,
        skip_pauses: bool = False,
        order: str = "",
        plant_failure: str = "",
        resume: str = "",
    ) -> ReleaseResult:
        self._rec("release")
        if skip_pauses and not order and not self.skip_without_order_admitted:
            return ReleaseResult(rc=2, error="--skip-pauses needs --order")
        ids = self._ring_ids()
        if plant_failure:
            for ring in proof.RELEASE_RINGS:
                if ids[ring] == plant_failure:
                    break
                self.version[ids[ring]] = "0.9.1"
            if self.fast_moves_on_stop:
                self.version["fast"] = "0.9.2"
            return ReleaseResult(rc=1, stopped=self.stop_names or plant_failure)
        for cid in ids.values():
            self.version[cid] = "0.9.1"
        del resume
        return ReleaseResult(rc=0)

    # -- tokens, proxy, executor
    def mint(self, company: str, kind: str) -> str:
        return f"{kind}@{company}"

    def present(self, company: str, kind: str, artifact: str) -> Answer:
        self._rec(f"present:{kind}")
        if artifact.endswith(company) or kind == self.cross_accepts:
            return OK
        return refused("unknown token")

    def container_app(self, company: str) -> str:
        return "app-shared" if self.shared_container else f"app-{company}"

    def durable_object(self, company: str) -> str:
        return f"do-{company}"

    def console_command(self, company: str) -> Answer:
        del company
        return OK

    def set_allowlist(self, company: str, ips: Sequence[str]) -> None:
        del company
        self._rec(f"set_allowlist:{len(ips)}")
        self.allowlist = list(ips)

    def request_from(self, company: str, *, foreign: bool, method: str, path: str) -> int:
        del company
        self._rec("request_from")
        exempt = method == "POST" and path == proof.LICENSE_RENEW_PATH
        if self.allowlist and foreign and (self.renew_blocked_by_allowlist or not exempt):
            return 403
        return 200

    # -- cost
    def deploy_records(self, *, bench: bool) -> list[dict[str, object]]:
        del bench
        return [{"company": cid, "duration_s": 42.0} for cid in ["c0123abcd", *self.companies]]

    def usage_rows(self, *, bench: bool) -> list[dict[str, object]]:
        del bench
        return (
            []
            if self.usage_missing
            else [{"company": cid} for cid in ["c0123abcd", *self.companies]]
        )

    def image_rebuild_seconds(self) -> float:
        return 310.0

    def read_limits(self) -> dict[str, int]:
        return self.limits

    # -- renet
    def fleet_machine(self) -> str:
        return "vm1"

    def renet_version(self, machine: str) -> str:
        del machine
        return self.renet

    def released_renet(self) -> str:
        return "1.1.0"

    def run_verb(self, machine: str, *, mutating: bool) -> int:
        del machine
        self._rec(f"run_verb:{mutating}")
        if mutating or self.read_only_moves:
            self.renet = "1.1.0"
        return 0

    def executor_upload(self, machine: str) -> Answer:
        del machine
        return OK if self.upload_admitted else refused("executor may not upload renet")

    def renew_with(self, machine: str, *, renet: str, worker: str) -> Answer:
        del machine, renet, worker
        return OK

    # -- github
    def dispatch_release(self, company: str) -> str:
        del company
        self._rec("dispatch_release")
        return "run-1"

    def run_surfaces(self, run_id: str) -> dict[str, str]:
        del run_id
        out = {s: f"{s}: release *** finished" for s in proof.GITHUB_SURFACES}
        if self.leak_surface:
            label = next(label for label, _ in self.companies.values())
            out[self.leak_surface] += f" deploying {label.upper()}.{DOMAIN}"
        if self.empty_surface:
            out[self.empty_surface] = ""
        return out


def run(verb: str, lab: FakeLab, *, bench: bool = True) -> tuple[int, list[str]]:
    lines: list[str] = []
    rc = proof.run_verb(verb, cast("proof.Lab", lab), bench=bench, out=lines.append)
    return rc, lines


def broken(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("BROKEN")]


# -- every verb holds on a healthy fake ------------------------------------------


@pytest.mark.parametrize("verb", sorted(proof.VERBS))
def test_every_verb_passes_on_a_healthy_lab(verb: str) -> None:
    rc, lines = run(verb, FakeLab(), bench=verb not in proof.PRODUCTION_VERBS)
    assert broken(lines) == []
    assert rc == 0, lines
    assert lines[-1].startswith(f"proof {verb}: ")


def test_the_verbs_are_the_twelve_live_boxes() -> None:
    assert set(proof.VERBS) == {
        "signer",
        "region-loss",
        "add",
        "routing",
        "release",
        "replay",
        "proxy",
        "cost",
        "renet",
        "github",
        "remove",
        "keys",
    }


# -- each broken claim exits non-zero --------------------------------------------


def _key_on_account() -> FakeLab:
    lab = FakeLab()
    lab.secrets["account-bench"] = [proof.PRIVATE_KEY, "ACCOUNT_JWT_SECRET"]
    return lab


BREAKS: list[tuple[str, FakeLab, str]] = [
    ("signer", _key_on_account(), f"account-bench holds no {proof.PRIVATE_KEY}"),
    (
        "signer",
        FakeLab(secrets={"signer-bench-us": ["X"]}),
        f"signer-bench-us holds {proof.PRIVATE_KEY}",
    ),
    ("signer", FakeLab(props_override={"account-bench": {"tier": "enterprise"}}), "binding props"),
    ("signer", FakeLab(admit_cases={"raw-bytes"}), "raw-bytes is refused"),
    ("signer", FakeLab(admit_cases={"shared-enterprise"}), "shared-enterprise is refused"),
    ("signer", FakeLab(admit_cases={"certificate-over-ceiling"}), "certificate-over-ceiling"),
    ("signer", FakeLab(licence_survives=False), "current licence works"),
    ("signer", FakeLab(stopped_error_names_signer=False), "a stopped signer is named"),
    ("region-loss", FakeLab(licence_survives=False), "current licence works with eu cut"),
    ("add", FakeLab(rerun_changes=("d1",)), "a rerun changes nothing"),
    ("add", FakeLab(unlisted_hits=True), "unlisted company: the lookup misses"),
    ("add", FakeLab(free_mail_admitted=True), "free-mail lookup domain is refused"),
    ("routing", FakeLab(wrong_worker="proof-route-a-proxy"), "proxy host reaches its Worker"),
    ("routing", FakeLab(logged_host=f"proof-route-b.{DOMAIN}"), "absent from certificate logs"),
    ("routing", FakeLab(turnstile=["other.example"]), "Turnstile covers"),
    ("release", FakeLab(skip_without_order_admitted=True), "--skip-pauses without --order"),
    ("release", FakeLab(stop_names="cdeadbeef"), "the stop names the failed company"),
    ("release", FakeLab(fast_moves_on_stop=True), "fast is unchanged by the stop"),
    ("replay", FakeLab(cross_accepts="config-token"), "config-token: refused by the other"),
    ("proxy", FakeLab(cross_accepts="proxy-token"), "refused by the other proxy"),
    ("proxy", FakeLab(shared_container=True), "own container app"),
    ("proxy", FakeLab(renew_blocked_by_allowlist=True), "still reaches POST renew"),
    ("cost", FakeLab(limits={"workers_scripts": 100, "routes_per_zone": 1000}), "workers_scripts"),
    ("cost", FakeLab(usage_missing=True), "appears in the usage report"),
    ("renet", FakeLab(read_only_moves=True), "a read-only verb leaves renet"),
    ("renet", FakeLab(upload_admitted=True), "executor refuses to upload"),
    ("renet", FakeLab(renet="1.1.0"), "starts behind the released renet"),
    ("github", FakeLab(leak_surface="jobs-api"), "no surface carries the name"),
    ("github", FakeLab(empty_surface="step-summary"), "surface step-summary was read"),
    ("remove", FakeLab(removes_under_gha=True), "remove refuses under GITHUB_ACTIONS"),
    ("remove", FakeLab(leaves_d1=True), "the removed company leaves nothing"),
    ("keys", _key_on_account(), "holds no"),
]


@pytest.mark.parametrize(("verb", "lab", "claim"), BREAKS, ids=[f"{v}:{c}" for v, _, c in BREAKS])
def test_a_broken_claim_exits_non_zero_and_is_named(verb: str, lab: FakeLab, claim: str) -> None:
    if verb == "keys":
        lab.secrets["account-eu"] = [proof.PRIVATE_KEY]
    rc, lines = run(verb, lab, bench=verb not in proof.PRODUCTION_VERBS)
    assert rc == 1
    assert any(claim in line for line in broken(lines)), broken(lines)


def test_every_verb_has_at_least_one_break_case() -> None:
    assert {v for v, _, _ in BREAKS} == set(proof.VERBS)


# -- what is broken is put back --------------------------------------------------


def test_signer_restarts_the_stopped_signer_even_when_the_lab_fails_mid_proof() -> None:
    lab = FakeLab(raise_on="current_licence_works")
    rc, lines = run("signer", lab)
    assert rc == 1
    assert lab.calls.index("stop_signer") < lab.calls.index("start_signer")
    assert lab.stopped == set()
    assert any("ran to the end" in line for line in broken(lines))


def test_region_loss_restores_eu_when_a_claim_raises() -> None:
    lab = FakeLab(raise_on="current_licence_works")
    rc, _ = run("region-loss", lab)
    assert rc == 1
    assert "restore_region" in lab.calls
    assert lab.cut == set()


def test_region_loss_records_what_bench_cannot_prove() -> None:
    _, lines = run("region-loss", FakeLab())
    notes = [line for line in lines if line.startswith("note")]
    assert len(notes) == len(proof.NOT_PROVEN_ON_BENCH)


def test_proxy_clears_the_allowlist_after_the_proof() -> None:
    lab = FakeLab(renew_blocked_by_allowlist=True)
    run("proxy", lab)
    assert lab.calls[-1] == "set_allowlist:0"
    assert lab.allowlist == []


def test_a_failed_restore_is_a_broken_claim() -> None:
    lab = FakeLab(raise_on="start_signer")
    rc, lines = run("signer", lab)
    assert rc == 1
    assert any("restarts" in line for line in broken(lines))


def test_a_failed_stop_restores_and_claims_nothing_about_the_stopped_state() -> None:
    lab = FakeLab(raise_on="stop_signer")
    rc, lines = run("signer", lab)
    assert rc == 1
    assert "start_signer" in lab.calls
    assert not any("stopped signer is named" in line for line in lines)


# -- refusals need their controls ------------------------------------------------


def test_replay_presents_each_artifact_to_its_own_company_first() -> None:
    lab = FakeLab()
    run("replay", lab)
    presents = [c for c in lab.calls if c.startswith("present:")]
    assert presents == [f"present:{k}" for k in proof.REPLAY_KINDS for _ in (0, 1)]


def test_refused_without_error_text_is_broken() -> None:
    p = proof.Proof()
    assert not p.refused("x", Answer(ok=False, error="  "))
    assert not p.refused("y", OK)
    assert p.refused("z", Answer(ok=False, error="signer-eu down"), naming="signer-eu")


def test_a_verb_that_records_nothing_is_not_a_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    def silent(lab: proof.Lab, p: proof.Proof, *, bench: bool) -> None:
        del lab, p, bench

    monkeypatch.setitem(proof.VERBS, "signer", silent)
    rc, lines = run("signer", FakeLab())
    assert rc == 1
    assert lines == ["proof signer: no claim was recorded"]


# -- names stay out of the output ------------------------------------------------


def test_github_names_the_surface_and_position_never_the_word() -> None:
    lab = FakeLab(leak_surface="logs")
    rc, lines = run("github", lab)
    assert rc == 1
    text = "\n".join(lines).lower()
    assert "logs: word #" in text
    assert "proof-github" not in text
    assert DOMAIN not in text


def test_name_hits_is_case_insensitive() -> None:
    hits = proof.name_hits({"a": "x ACME y", "b": "clean"}, ["acme", "", "none"])
    assert hits == ["a: word #0"]


# -- the workflow scan is real ---------------------------------------------------


def test_workflow_scan_finds_a_remove_call(tmp_path: pathlib.Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "a.yml").write_text(
        "steps:\n  - run: ./run.sh enterprise remove cabc\n", encoding="utf-8"
    )
    (wf / "b.yaml").write_text("steps:\n  - run: ./run.sh enterprise release\n", encoding="utf-8")
    assert proof.workflow_remove_calls(tmp_path) == ["workflows/a.yml:2"]


def test_no_workflow_in_this_tree_calls_enterprise_remove() -> None:
    root = pathlib.Path(__file__).resolve().parents[3]
    assert list((root / ".github" / "workflows").glob("*.yml"))
    assert proof.workflow_remove_calls(root) == []


def test_remove_fails_when_no_workflow_is_found(tmp_path: pathlib.Path) -> None:
    p = proof.Proof()
    proof.verb_remove(cast("proof.Lab", FakeLab()), p, bench=True, root=tmp_path)
    assert any(o.claim == "workflows were scanned" and not o.ok for o in p.outcomes)


# -- main ------------------------------------------------------------------------


def test_main_refuses_a_bench_verb_off_bench(capsys: pytest.CaptureFixture[str]) -> None:
    assert proof.main(["signer"], lab=cast("proof.Lab", FakeLab())) == 2
    assert "bench only" in capsys.readouterr().err


def test_main_runs_keys_against_production() -> None:
    lab = FakeLab()
    assert proof.main(["keys"], lab=cast("proof.Lab", lab)) == 0
    assert "account_workers" in lab.calls


def test_main_runs_a_bench_verb_with_bench() -> None:
    assert proof.main(["replay", "--bench"], lab=cast("proof.Lab", FakeLab())) == 0


def test_main_names_the_missing_lab(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(proof, "LAB_MODULE", "rediacc_ci.enterprise.no_such_lab_for_test")
    assert proof.main(["signer", "--bench"]) == 2
    err = capsys.readouterr().err
    assert "no live lab" in err
    assert "nothing was claimed" in err


def test_main_usage_errors_exit_two() -> None:
    assert proof.main(["no-such-verb"]) == 2
    assert proof.main([]) == 2


# -- review 5b19ed43: names, startup, scans, side effects -------------------------

REAL_NAME = "Acme Holdings"
REAL_HOST = "acme-holdings.customer.example"


@dataclasses.dataclass
class RealNamedRecords(FakeLab):
    def deploy_records(self, *, bench: bool) -> list[dict[str, object]]:
        del bench
        return [{"company": REAL_NAME, "duration_s": 5.0, "host": REAL_HOST}]


@dataclasses.dataclass
class LeakyAdd(FakeLab):
    def add(
        self, label: str, *, owner: str, unlisted: bool, lookup_domain: str, kill_after: str = ""
    ) -> AddResult:
        res = super().add(
            label,
            owner=owner,
            unlisted=unlisted,
            lookup_domain=lookup_domain,
            kill_after=kill_after,
        )
        if res.rc:
            return dataclasses.replace(res, error=f"{label} at {label}.{DOMAIN} failed")
        return res

    def lookup(self, domain: str) -> str | None:
        return f"{domain}.elsewhere.example"


@dataclasses.dataclass
class FailingExport(FakeLab):
    exported_for: list[str] = dataclasses.field(default_factory=list)

    def export(self, company: str) -> int:
        self.exported_for.append(company)
        return 1


@dataclasses.dataclass
class KeptExportFails(FakeLab):
    def export(self, company: str) -> int:
        super().export(company)
        return 1 if self.companies[company][0].endswith("-ci") else 0


def test_cost_masks_a_company_that_is_not_an_opaque_id() -> None:
    rc, lines = run("cost", RealNamedRecords())
    text = "\n".join(lines)
    assert rc == 1
    assert any("record #0" in line for line in broken(lines)), broken(lines)
    assert REAL_NAME.lower() not in text.lower()
    assert REAL_HOST not in text


def test_add_keeps_labels_hosts_and_domains_out_of_the_output() -> None:
    rc, lines = run("add", LeakyAdd(unlisted_hits=True))
    text = "\n".join(lines).lower()
    assert rc == 1
    assert broken(lines)
    for word in ("proof-listed", "proof-unlisted", "proof-freemail", "elsewhere.example"):
        assert word not in text, word


def test_add_prints_no_label_on_a_healthy_run() -> None:
    rc, lines = run("add", FakeLab())
    assert rc == 0
    assert "proof-" not in "\n".join(lines)


def test_main_exits_two_when_the_live_lab_fails_to_build(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Broken:
        @staticmethod
        def build(*, bench: bool) -> None:
            del bench
            msg = "no bench credentials"
            raise LabError(msg)

    monkeypatch.setattr(proof.importlib, "import_module", lambda _name: Broken)
    assert proof.main(["signer", "--bench"]) == 2
    err = capsys.readouterr().err
    assert "could not start" in err
    assert "no bench credentials" in err


def test_workflow_scan_joins_backslash_continuations(tmp_path: pathlib.Path) -> None:
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "a.yml").write_text(
        "steps:\n  - run: ./run.sh enterprise \\\n      remove cabc\n  - run: echo hi\n",
        encoding="utf-8",
    )
    assert proof.workflow_remove_calls(tmp_path) == ["workflows/a.yml:2"]


def test_workflow_scan_reads_composite_actions(tmp_path: pathlib.Path) -> None:
    act = tmp_path / ".github" / "actions" / "tidy"
    act.mkdir(parents=True)
    (act / "action.yml").write_text(
        "runs:\n  steps:\n    - run: ./run.sh enterprise remove c1\n", encoding="utf-8"
    )
    (tmp_path / ".github" / "workflows").mkdir()
    assert proof.workflow_remove_calls(tmp_path) == ["actions/tidy/action.yml:3"]
    p = proof.Proof()
    proof.verb_remove(cast("proof.Lab", FakeLab()), p, bench=True, root=tmp_path)
    assert any(o.claim == "no workflow calls enterprise remove" and not o.ok for o in p.outcomes)


def test_remove_reports_which_export_failed() -> None:
    _, lines = run("remove", KeptExportFails())
    assert any("export failed for ['kept company']" in line for line in broken(lines)), lines


def test_remove_calls_both_exports_even_when_the_first_fails() -> None:
    lab = FailingExport()
    _, lines = run("remove", lab)
    assert len(lab.exported_for) == 2
    assert any("removed company" in line and "kept company" in line for line in broken(lines))


def test_keys_mints_no_licence_in_production() -> None:
    lab = FakeLab()
    rc, lines = run("keys", lab, bench=False)
    assert rc == 0
    assert "issue:licence" not in lab.calls
    assert any(line.startswith("skipped") and "bench-only" in line for line in lines)
    assert "skipped" in lines[-1]


def test_keys_issues_licences_on_bench() -> None:
    lab = FakeLab()
    rc, lines = run("keys", lab, bench=True)
    assert rc == 0
    assert "issue:licence" in lab.calls
    assert not any(line.startswith("skipped") for line in lines)


def test_a_run_of_only_skipped_claims_does_not_exit_zero() -> None:
    def only_skips(lab: object, p: proof.Proof, *, bench: bool) -> None:
        del lab, bench
        p.skip("a: licence", "bench-only")

    proof.VERBS["only-skips-for-test"] = only_skips
    try:
        lines: list[str] = []
        lab = cast("proof.Lab", FakeLab())
        rc = proof.run_verb("only-skips-for-test", lab, bench=False, out=lines.append)
    finally:
        del proof.VERBS["only-skips-for-test"]
    assert rc == 1
    assert "1 skipped" in lines[-2]
    assert "no claim held" in lines[-1]


def test_a_production_keys_run_counts_its_held_claims_apart_from_skips() -> None:
    p = proof.Proof()
    proof.verb_keys(cast("proof.Lab", FakeLab()), p, bench=False)
    assert p.held
    licence = [o for o in p.outcomes if "licence is issued" in o.claim]
    assert licence, "the licence claims were not recorded at all"
    assert all(o.skipped for o in licence)
    assert not any(o.skipped for o in p.held)


def test_remove_fails_when_only_composite_actions_exist(tmp_path: pathlib.Path) -> None:
    act = tmp_path / ".github" / "actions" / "tidy"
    act.mkdir(parents=True)
    (act / "action.yml").write_text("runs:\n  steps:\n    - run: echo hi\n", encoding="utf-8")
    p = proof.Proof()
    proof.verb_remove(cast("proof.Lab", FakeLab()), p, bench=True, root=tmp_path)
    assert any(o.claim == "workflows were scanned" and not o.ok for o in p.outcomes)


def test_a_composite_action_named_workflows_keeps_its_path(tmp_path: pathlib.Path) -> None:
    act = tmp_path / ".github" / "actions" / "workflows"
    act.mkdir(parents=True)
    (act / "action.yml").write_text(
        "runs:\n  steps:\n    - run: ./run.sh enterprise remove c1\n", encoding="utf-8"
    )
    assert proof.workflow_remove_calls(tmp_path) == ["actions/workflows/action.yml:3"]
