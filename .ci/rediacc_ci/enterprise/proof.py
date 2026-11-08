"""`./run.sh enterprise proof <verb>`: the claims each live box of agent/plans/PLAN-enterprise-isolation.md must see hold (box P1).

ONE VERB PER LIVE BOX. `signer` (V1), `region-loss` (V2), `add` (V3), `routing` (V4), `release` (V5), `replay` (V6), `proxy` (V7), `cost` (V8), `renet` (V9), `github` (V10), `remove` (V11) and `keys` (X1). Each verb is a fixed list of claims over a `Lab`, the live world the proof drives. A claim that does not hold is printed `BROKEN` with what was seen, and the verb exits 1. A verb that records no claim at all also exits 1, because a proof that checked nothing is not a pass.

EVERY REFUSAL HAS A CONTROL. A claim that something is refused is paired with the same request admitted where it should be: a token refused by the other company's Worker is first accepted by its own, a scope case refused by a signer sits beside a legitimate licence that signer issues. Without the control, a dead signer or a wrong host would pass every refusal claim.

WHAT IS BROKEN IS PUT BACK. `signer` stops a signer, `region-loss` cuts a region and `proxy` sets an allowlist; each restores in a `finally`, and a restore that fails is itself a broken claim, so a run never leaves bench quietly degraded.

A LAB ERROR IS A BROKEN CLAIM, NOT A TRACEBACK. A lab raises `LabError` (or an OS, value, lookup or timeout error) when a live step fails; the verb records it as broken under the claim it was serving and still restores. Any other exception is a defect in the proof or the lab and propagates.

NAMES STAY OUT OF THE OUTPUT. Companies are printed by their opaque `c<hex>` id. `github` compares the run's logs and API answers against the fake company's name and hosts and, on a hit, prints the surface and the word's position in the list, never the word.

THE LAB. `Lab` is the protocol the verbs need. The live binding is `rediacc_ci.enterprise.lab.build(bench=...)`, built over the add, lifecycle, deploy and ring modules (boxes C1, C2, D1, K2, S2); until that module exists, `main` exits 2 and names it rather than claiming anything. The tests drive every verb through a recording fake.

EXIT CODES. 0 every claim holds; 1 a claim is broken or none was recorded; 2 the proof could not start (usage, a verb run off bench, no live lab).
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import pathlib
import re
import sys
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

SELF = "rediacc_ci.enterprise.proof"
LAB_MODULE = "rediacc_ci.enterprise.lab"
PRIVATE_KEY = "ACCOUNT_ED25519_PRIVATE_KEY"
# packages/shared/src/subscription/constants.ts LICENSE_RENEW_PATH; the one path the allowlist exempts.
LICENSE_RENEW_PATH = "/account/api/v1/licenses/renew"
OPAQUE_ID = re.compile(r"^c[0-9a-f]{6,}$")
HTTP_FORBIDDEN = 403

# The signer scope matrix of box S1: each is refused, beside a legitimate licence and certificate that are issued.
SCOPE_CASES: tuple[str, ...] = (
    "foreign-subscription",
    "wrong-host",
    "over-limit",
    "suspended",
    "raw-bytes",
    "shared-enterprise",
    "certificate-over-ceiling",
)
REPLAY_KINDS: tuple[str, ...] = ("session", "api-token", "config-token", "e2e-envelope")
GITHUB_SURFACES: tuple[str, ...] = ("logs", "jobs-api", "run-api", "step-summary")
RELEASE_RINGS: tuple[str, ...] = ("canary", "small", "medium", "large")
# The figures in the plan's *Limits*, which came through a summarizing tool; `cost` re-reads them.
PLAN_LIMITS: dict[str, int] = {"workers_scripts": 500, "routes_per_zone": 1000}
NOT_PROVEN_ON_BENCH: tuple[str, ...] = (
    "a real network partition between Cloudflare regions",
    "a D1 primary outage",
    "a failure of Cloudflare's control plane",
)
WORKFLOW_REMOVE = re.compile(r"enterprise\s+remove\b|enterprise\.lifecycle\b[^\n]*\bremove\b")
FREE_MAIL_DOMAIN = "gmail.com"


class LabError(RuntimeError):
    """A live step the lab could not complete."""


LAB_ERRORS: tuple[type[Exception], ...] = (LabError, OSError, ValueError, LookupError, TimeoutError)


@dataclasses.dataclass(frozen=True)
class Answer:
    """One request's outcome: `ok`, or refused with `error`."""

    ok: bool
    error: str = ""
    body: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass(frozen=True)
class Reply:
    """An HTTPS fetch of a host: status, the Worker that answered, and the names on the certificate served."""

    status: int
    worker: str
    cert_names: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class AddResult:
    rc: int
    company: str = ""
    changed: tuple[str, ...] = ()
    error: str = ""


@dataclasses.dataclass(frozen=True)
class ReleaseResult:
    rc: int
    stopped: str = ""
    error: str = ""


class Lab(Protocol):
    """The live world a proof drives. Company arguments are opaque ids; callers are Worker names."""

    # Workers, secrets and signers.
    def account_workers(self, *, bench: bool) -> list[str]: ...
    def signers(self, *, bench: bool) -> list[str]: ...
    def secret_names(self, worker: str) -> list[str]: ...
    def callers(self, *, bench: bool) -> list[str]: ...
    def signer_of(self, caller: str) -> str: ...
    def signer_props(self, caller: str) -> dict[str, str]: ...
    def expected_props(self, caller: str) -> dict[str, str]: ...
    def issue(self, caller: str, kind: str) -> Answer: ...
    def certificate_audited(self, signer: str, certificate_id: str) -> bool: ...
    def current_licence_works(self, caller: str) -> bool: ...
    def renew(self, caller: str) -> Answer: ...
    def stop_signer(self, signer: str) -> None: ...
    def start_signer(self, signer: str) -> None: ...
    def cut_region(self, region: str) -> None: ...
    def restore_region(self, region: str) -> None: ...

    # Companies.
    def ensure_company(self, label: str, region: str, *, ring: str | None = None) -> str: ...
    def caller_of(self, company: str) -> str: ...
    def company_hosts(self, company: str) -> tuple[str, str]: ...
    def company_words(self, company: str) -> list[str]: ...
    def add(
        self, label: str, *, owner: str, unlisted: bool, lookup_domain: str, kill_after: str = ""
    ) -> AddResult: ...
    def captured_mail(self, owner: str) -> list[str]: ...
    def lookup(self, domain: str) -> str | None: ...
    def export(self, company: str) -> int: ...
    def remove(self, company: str, *, delete_data: bool, github_actions: bool) -> int: ...
    def leftovers(self, company: str) -> list[str]: ...

    # Routing.
    def fetch(self, host: str) -> Reply: ...
    def expected_worker(self, host: str) -> str: ...
    def region_hosts(self, *, bench: bool) -> list[str]: ...
    def specific_hosts(self) -> list[str]: ...
    def cert_log_names(self) -> list[str]: ...
    def turnstile_domains(self) -> list[str]: ...

    # Releases.
    def target_version(self) -> str: ...
    def versions(self, targets: Sequence[str]) -> dict[str, str]: ...
    def release(
        self,
        *,
        skip_pauses: bool = False,
        order: str = "",
        plant_failure: str = "",
        resume: str = "",
    ) -> ReleaseResult: ...

    # Tokens, proxy and executor.
    def mint(self, company: str, kind: str) -> str: ...
    def present(self, company: str, kind: str, artifact: str) -> Answer: ...
    def container_app(self, company: str) -> str: ...
    def durable_object(self, company: str) -> str: ...
    def console_command(self, company: str) -> Answer: ...
    def set_allowlist(self, company: str, ips: Sequence[str]) -> None: ...
    def request_from(self, company: str, *, foreign: bool, method: str, path: str) -> int: ...

    # Cost.
    def deploy_records(self, *, bench: bool) -> list[dict[str, object]]: ...
    def usage_rows(self, *, bench: bool) -> list[dict[str, object]]: ...
    def image_rebuild_seconds(self) -> float: ...
    def read_limits(self) -> dict[str, int]: ...

    # Renet.
    def fleet_machine(self) -> str: ...
    def renet_version(self, machine: str) -> str: ...
    def released_renet(self) -> str: ...
    def run_verb(self, machine: str, *, mutating: bool) -> int: ...
    def executor_upload(self, machine: str) -> Answer: ...
    def renew_with(self, machine: str, *, renet: str, worker: str) -> Answer: ...

    # GitHub.
    def dispatch_release(self, company: str) -> str: ...
    def run_surfaces(self, run_id: str) -> dict[str, str]: ...


@dataclasses.dataclass(frozen=True)
class Outcome:
    claim: str
    ok: bool
    detail: str = ""


@dataclasses.dataclass
class Proof:
    """The claims one verb recorded, in order, and the notes it prints beside them."""

    outcomes: list[Outcome] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)

    def check(self, claim: str, *, ok: object, detail: str = "") -> bool:
        held = bool(ok)
        self.outcomes.append(Outcome(claim, held, "" if held else detail))
        return held

    def admitted(self, claim: str, answer: Answer) -> bool:
        return self.check(claim, ok=answer.ok, detail=f"refused: {answer.error or '(no error)'}")

    def refused(self, claim: str, answer: Answer, *, naming: str = "") -> bool:
        if answer.ok:
            return self.check(claim, ok=False, detail="admitted")
        if not answer.error.strip():
            return self.check(claim, ok=False, detail="refused with no error text")
        if naming and naming not in answer.error:
            return self.check(
                claim, ok=False, detail=f"error does not name {naming}: {answer.error}"
            )
        return self.check(claim, ok=True)

    def attempt(self, claim: str, action: Callable[[], object]) -> bool:
        """Run a lab step; a lab error is a broken claim under `claim`."""
        try:
            action()
        except LAB_ERRORS as exc:
            return self.check(claim, ok=False, detail=f"{type(exc).__name__}: {exc}")
        return self.check(claim, ok=True)

    @property
    def broken(self) -> list[Outcome]:
        return [o for o in self.outcomes if not o.ok]


# -- the verbs --------------------------------------------------------------------


def _no_key_on_account(lab: Lab, p: Proof, *, bench: bool) -> None:
    workers = lab.account_workers(bench=bench)
    p.check("account Workers are listed", ok=workers, detail="no account Worker found")
    for w in workers:
        names = lab.secret_names(w)
        p.check(f"{w} lists its secrets", ok=names, detail="empty secret list")
        p.check(f"{w} holds no {PRIVATE_KEY}", ok=PRIVATE_KEY not in names, detail="key present")
    signers = lab.signers(bench=bench)
    p.check("signers are listed", ok=signers, detail="no signer found")
    for s in signers:
        p.check(f"{s} holds {PRIVATE_KEY}", ok=PRIVATE_KEY in lab.secret_names(s), detail="absent")


def verb_signer(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V1: the binding across Workers, props honoured, scope refused, no key on any account Worker, certificates through the signer, a stopped signer named while a current licence works."""
    _no_key_on_account(lab, p, bench=bench)
    callers = lab.callers(bench=bench)
    if not p.check("signer callers are listed", ok=callers, detail="no caller found"):
        return
    for caller in callers:
        want, seen = lab.expected_props(caller), lab.signer_props(caller)
        p.check(f"{caller}: the signer sees its binding props", ok=seen == want, detail=f"{seen}")
        p.admitted(f"{caller}: a legitimate licence is issued", lab.issue(caller, "licence"))
        for case in SCOPE_CASES:
            p.refused(f"{caller}: {case} is refused", lab.issue(caller, case))
        cert = lab.issue(caller, "certificate")
        if p.admitted(f"{caller}: a legitimate certificate is issued", cert):
            cid = cert.body.get("id", "")
            audited = bool(cid) and lab.certificate_audited(lab.signer_of(caller), cid)
            p.check(f"{caller}: the certificate has an audit row", ok=audited, detail=f"id {cid!r}")

    caller = callers[0]
    signer = lab.signer_of(caller)
    if not p.attempt(f"{signer} stops", lambda: lab.stop_signer(signer)):
        p.attempt(f"{signer} restarts", lambda: lab.start_signer(signer))
        return
    try:
        p.refused(
            f"{caller}: a stopped signer is named", lab.issue(caller, "licence"), naming=signer
        )
        p.check(
            f"{caller}: the current licence works with the signer stopped",
            ok=lab.current_licence_works(caller),
            detail="current licence refused",
        )
    finally:
        p.attempt(f"{signer} restarts", lambda: lab.start_signer(signer))
    p.admitted(f"{caller}: issues again after the restart", lab.issue(caller, "licence"))


def verb_region_loss(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V2: with eu's signer and control database cut, the us company issues and renews, the eu company gets the named error and keeps its licence, and restoring eu renews it."""
    del bench
    eu = lab.caller_of(lab.ensure_company("proof-loss-eu", "eu"))
    us = lab.caller_of(lab.ensure_company("proof-loss-us", "us"))
    p.admitted("eu company renews before the cut", lab.renew(eu))
    if not p.attempt("eu signer and control are cut", lambda: lab.cut_region("eu")):
        p.attempt("eu is restored", lambda: lab.restore_region("eu"))
        return
    try:
        p.admitted("us company issues with eu cut", lab.issue(us, "licence"))
        p.admitted("us company renews with eu cut", lab.renew(us))
        p.refused("eu company gets the named error", lab.renew(eu), naming=lab.signer_of(eu))
        p.check(
            "eu company's current licence works with eu cut",
            ok=lab.current_licence_works(eu),
            detail="current licence refused",
        )
    finally:
        p.attempt("eu is restored", lambda: lab.restore_region("eu"))
    p.admitted("eu company renews after the restore", lab.renew(eu))
    p.notes.extend(f"not proven on bench: {n}" for n in NOT_PROVEN_ON_BENCH)


def verb_add(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V3: a killed add resumes, a rerun changes nothing, owner mail is captured, the lookup hits a listed company and misses an unlisted one, a free-mail domain is refused."""
    del bench
    cases = (
        ("proof-listed", "owner@proof-listed.example", False, "proof-listed.example"),
        ("proof-unlisted", "owner@proof-unlisted.example", True, "proof-unlisted.example"),
    )
    for label, owner, unlisted, domain in cases:
        killed = lab.add(
            label, owner=owner, unlisted=unlisted, lookup_domain=domain, kill_after="d1"
        )
        p.check(f"{label}: a killed add exits non-zero", ok=killed.rc != 0, detail="rc 0")
        resumed = lab.add(label, owner=owner, unlisted=unlisted, lookup_domain=domain)
        p.check(f"{label}: the add resumes", ok=resumed.rc == 0, detail=resumed.error)
        again = lab.add(label, owner=owner, unlisted=unlisted, lookup_domain=domain)
        p.check(
            f"{label}: a rerun changes nothing",
            ok=again.rc == 0 and not again.changed,
            detail=f"rc {again.rc}, changed {list(again.changed)}",
        )
        p.check(f"{label}: owner mail is captured", ok=lab.captured_mail(owner), detail="no mail")
        hit = lab.lookup(domain)
        if unlisted:
            p.check(f"{label}: the lookup misses", ok=hit is None, detail="lookup answered")
        else:
            host = lab.company_hosts(resumed.company)[0] if resumed.company else ""
            p.check(f"{label}: the lookup hits", ok=bool(host) and hit == host, detail=f"{hit!r}")
    free = lab.add(
        "proof-freemail",
        owner=f"owner@{FREE_MAIL_DOMAIN}",
        unlisted=False,
        lookup_domain=FREE_MAIL_DOMAIN,
    )
    p.check(
        "a free-mail lookup domain is refused",
        ok=free.rc != 0 and "free-mail" in free.error,
        detail=f"rc {free.rc}: {free.error}",
    )


def _covers(names: Iterable[str], host: str) -> bool:
    for name in names:
        if name == host:
            return True
        if name.startswith("*.") and host.count(".") == name.count(".") and host.endswith(name[1:]):
            return True
    return False


def verb_routing(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V4: the wildcard and routes reach each Worker, the certificate covers both company hosts, region hosts do not collide, specific records win, certificate logs lack company names, Turnstile covers the subdomains."""
    companies = [lab.ensure_company(label, "eu") for label in ("proof-route-a", "proof-route-b")]
    turnstile = lab.turnstile_domains()
    logged = {n.lower() for n in lab.cert_log_names()}
    company_workers: set[str] = set()
    for cid in companies:
        for host in lab.company_hosts(cid):
            reply = lab.fetch(host)
            want = lab.expected_worker(host)
            company_workers.add(reply.worker)
            p.check(
                f"{cid}: {_role(host)} reaches its Worker",
                ok=reply.worker == want,
                detail=f"answered by {reply.worker!r}",
            )
            p.check(
                f"{cid}: {_role(host)} certificate covers it",
                ok=_covers(reply.cert_names, host),
                detail=f"{list(reply.cert_names)}",
            )
            p.check(
                f"{cid}: {_role(host)} is absent from certificate logs",
                ok=host.lower() not in logged,
                detail="host in a logged certificate",
            )
            p.check(
                f"{cid}: Turnstile covers {_role(host)}",
                ok=any(host == d or host.endswith("." + d) for d in turnstile),
                detail="no Turnstile domain covers it",
            )
    for host in lab.region_hosts(bench=bench) + lab.specific_hosts():
        reply = lab.fetch(host)
        want = lab.expected_worker(host)
        p.check(
            f"{host} keeps its own Worker",
            ok=reply.worker == want,
            detail=f"answered by {reply.worker!r}",
        )
        p.check(
            f"{host} is not a company Worker",
            ok=reply.worker not in company_workers,
            detail="collides with a company Worker",
        )


def _role(host: str) -> str:
    return "proxy host" if host.split(".", 1)[0].endswith("-proxy") else "account host"


def verb_release(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V5: four companies across the rings; a planted failure stops and names one, the later ring and the fast tier are unchanged, `--skip-pauses` without `--order` is refused, and a resume finishes."""
    del bench
    ids = {
        ring: lab.ensure_company(f"proof-ring-{ring}", "eu", ring=ring) for ring in RELEASE_RINGS
    }
    targets = [*ids.values(), "fast"]
    target = lab.target_version()
    before = lab.versions(targets)

    bare = lab.release(skip_pauses=True)
    p.check("--skip-pauses without --order is refused", ok=bare.rc != 0, detail="rc 0")
    p.check(
        "the refused release changed nothing",
        ok=lab.versions(targets) == before,
        detail="versions moved",
    )

    planted = ids["medium"]
    run = lab.release(plant_failure=planted)
    p.check("a planted failure stops the release", ok=run.rc != 0, detail="rc 0")
    p.check(
        "the stop names the failed company",
        ok=run.stopped == planted,
        detail=f"named {run.stopped!r}",
    )
    after = lab.versions(targets)
    for ring in ("canary", "small"):
        p.check(
            f"{ring} took {target} before the stop",
            ok=after.get(ids[ring]) == target,
            detail=f"runs {after.get(ids[ring])!r}",
        )
    for key in (ids["large"], "fast"):
        p.check(
            f"{key} is unchanged by the stop",
            ok=after.get(key) == before.get(key),
            detail=f"{before.get(key)!r} -> {after.get(key)!r}",
        )

    resumed = lab.release(resume=planted)
    p.check("the resume finishes", ok=resumed.rc == 0, detail=resumed.error)
    final = lab.versions(list(ids.values()))
    p.check(
        f"every ring runs {target} after the resume",
        ok=all(final.get(c) == target for c in ids.values()),
        detail=f"{final}",
    )


def verb_replay(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V6: sessions, API tokens, config tokens and E2E envelopes from one company fail on the other, and work on their own."""
    del bench
    a = lab.ensure_company("proof-replay-a", "eu")
    b = lab.ensure_company("proof-replay-b", "eu")
    for kind in REPLAY_KINDS:
        art = lab.mint(a, kind)
        p.admitted(f"{kind}: accepted by its own company", lab.present(a, kind, art))
        p.refused(f"{kind}: refused by the other company", lab.present(b, kind, art))


def verb_proxy(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V7: a container app and Durable Object per company, one company's token refused by the other's proxy, a console command runs, the allowlist blocks a foreign IP while renewal passes."""
    del bench
    a = lab.ensure_company("proof-proxy-a", "eu")
    b = lab.ensure_company("proof-proxy-b", "eu")
    apps = (lab.container_app(a), lab.container_app(b))
    objs = (lab.durable_object(a), lab.durable_object(b))
    p.check(
        "each company has its own container app",
        ok=all(apps) and apps[0] != apps[1],
        detail=f"{apps}",
    )
    p.check(
        "each company has its own Durable Object",
        ok=all(objs) and objs[0] != objs[1],
        detail=f"{objs}",
    )
    tok = lab.mint(a, "proxy-token")
    p.admitted("a proxy token is accepted by its own proxy", lab.present(a, "proxy-token", tok))
    p.refused("a proxy token is refused by the other proxy", lab.present(b, "proxy-token", tok))
    p.admitted("a console command runs", lab.console_command(a))

    if not p.attempt("an allowlist is set", lambda: lab.set_allowlist(a, ["192.0.2.10"])):
        p.attempt("the allowlist is cleared", lambda: lab.set_allowlist(a, []))
        return
    try:
        cases = (
            ("a listed IP reaches GET /", False, "GET", "/", False),
            ("a foreign IP is blocked on GET /", True, "GET", "/", True),
            (
                "a foreign IP is blocked on POST to another path",
                True,
                "POST",
                "/account/api/v1/auth/login",
                True,
            ),
            (
                "a foreign IP is blocked on GET of the renew path",
                True,
                "GET",
                LICENSE_RENEW_PATH,
                True,
            ),
            ("a foreign IP still reaches POST renew", True, "POST", LICENSE_RENEW_PATH, False),
        )
        for claim, foreign, method, path, blocked in cases:
            status = lab.request_from(a, foreign=foreign, method=method, path=path)
            p.check(claim, ok=(status == HTTP_FORBIDDEN) == blocked, detail=f"status {status}")
    finally:
        p.attempt("the allowlist is cleared", lambda: lab.set_allowlist(a, []))


def verb_cost(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V8: per-company cost and time from the deploy records and the usage report, the image rebuild measured, and the Cloudflare limits re-read against the plan's figures."""
    records = lab.deploy_records(bench=bench)
    p.check("deploy records exist", ok=records, detail="no record")
    seconds: dict[str, float] = {}
    for r in records:
        cid, dur = str(r.get("company", "")), r.get("duration_s")
        ok = bool(OPAQUE_ID.match(cid)) and isinstance(dur, (int, float)) and dur > 0
        p.check(f"record {cid or '?'} has an opaque id and a duration", ok=ok, detail=f"{r}")
        if ok and isinstance(dur, (int, float)):
            seconds[cid] = seconds.get(cid, 0.0) + float(dur)
    usage = {str(u.get("company", "")) for u in lab.usage_rows(bench=bench)}
    for cid in sorted(seconds):
        p.check(f"{cid} appears in the usage report", ok=cid in usage, detail="no usage row")
        p.notes.append(f"{cid}: {seconds[cid]:.0f} s deploying")
    rebuild = lab.image_rebuild_seconds()
    p.check("the image rebuild is measured", ok=rebuild > 0, detail=f"{rebuild}")
    p.notes.append(f"image rebuild: {rebuild:.0f} s")
    limits = lab.read_limits()
    for key, want in PLAN_LIMITS.items():
        got = limits.get(key)
        p.check(
            f"Cloudflare {key} is still {want}",
            ok=got == want,
            detail=f"read {got!r}; the plan's Limits must change",
        )


def verb_renet(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V9: a mutating verb moves renet and a read-only one does not, an executor refuses to upload, and both directions of a spread release renew."""
    del bench
    m = lab.fleet_machine()
    released = lab.released_renet()
    before = lab.renet_version(m)
    p.check(
        "the machine starts behind the released renet",
        ok=before != released,
        detail=f"already on {released}",
    )
    p.check("a read-only verb runs", ok=lab.run_verb(m, mutating=False) == 0, detail="rc != 0")
    p.check("a read-only verb leaves renet", ok=lab.renet_version(m) == before, detail="moved")
    p.check("a mutating verb runs", ok=lab.run_verb(m, mutating=True) == 0, detail="rc != 0")
    now = lab.renet_version(m)
    p.check("a mutating verb moves renet", ok=now == released, detail=f"runs {now}")
    p.refused("an executor refuses to upload renet", lab.executor_upload(m))
    p.admitted(
        "the previous renet renews against the new Worker",
        lab.renew_with(m, renet="previous", worker="new"),
    )
    p.admitted(
        "the new renet renews against the previous Worker",
        lab.renew_with(m, renet="new", worker="previous"),
    )


def name_hits(surfaces: dict[str, str], words: Sequence[str]) -> list[str]:
    """`<surface>: word #<i>` for each word found in a surface, case-insensitively. Never the word itself."""
    out: list[str] = []
    for surface in sorted(surfaces):
        text = surfaces[surface].lower()
        out.extend(f"{surface}: word #{i}" for i, w in enumerate(words) if w and w.lower() in text)
    return out


def verb_github(lab: Lab, p: Proof, *, bench: bool) -> None:
    """V10: a release dispatched for a fake company by its opaque id leaves neither its name nor its hosts in the logs, the jobs API, the run API or the step summary."""
    del bench
    cid = lab.ensure_company("proof-github", "eu")
    p.check("the dispatch input is opaque", ok=OPAQUE_ID.match(cid), detail="not c<hex>")
    words = lab.company_words(cid)
    if not p.check("the company's name and hosts are known", ok=words, detail="no words"):
        return
    run_id = lab.dispatch_release(cid)
    surfaces = lab.run_surfaces(run_id)
    for s in GITHUB_SURFACES:
        p.check(f"surface {s} was read", ok=surfaces.get(s, "").strip(), detail="empty or missing")
    hits = name_hits(surfaces, words)
    p.check("no surface carries the name or a host", ok=not hits, detail="; ".join(hits))


def workflow_remove_calls(root: pathlib.Path) -> list[str]:
    """Each `<workflow>:<line>` under `.github/workflows` that calls `enterprise remove`."""
    out: list[str] = []
    for path in sorted((root / ".github" / "workflows").glob("*.y*ml")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if WORKFLOW_REMOVE.search(line):
                out.append(f"{path.name}:{n}")
    return out


def _repo_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[3]


def verb_remove(lab: Lab, p: Proof, *, bench: bool, root: pathlib.Path | None = None) -> None:
    """V11: remove refuses before an export and under GitHub Actions, removes an exported company with its data, and no workflow calls it."""
    del bench
    gone = lab.ensure_company("proof-remove", "eu")
    kept = lab.ensure_company("proof-remove-ci", "eu")
    p.check(
        "remove refuses before an export",
        ok=lab.remove(gone, delete_data=True, github_actions=False) != 0,
        detail="rc 0",
    )
    p.check(
        "the export completes", ok=lab.export(gone) == 0 and lab.export(kept) == 0, detail="rc != 0"
    )
    p.check(
        "remove refuses under GITHUB_ACTIONS",
        ok=lab.remove(kept, delete_data=True, github_actions=True) != 0,
        detail="rc 0",
    )
    p.check("the refused company is intact", ok=lab.leftovers(kept), detail="nothing left")
    p.check(
        "remove with data completes",
        ok=lab.remove(gone, delete_data=True, github_actions=False) == 0,
        detail="rc != 0",
    )
    left = lab.leftovers(gone)
    p.check("the removed company leaves nothing", ok=not left, detail=f"{left}")
    base = root or _repo_root()
    workflows = list((base / ".github" / "workflows").glob("*.y*ml"))
    p.check("workflows were scanned", ok=workflows, detail="no workflow file found")
    calls = workflow_remove_calls(base)
    p.check("no workflow calls enterprise remove", ok=not calls, detail=", ".join(calls))


def verb_keys(lab: Lab, p: Proof, *, bench: bool) -> None:
    """X1: no account Worker holds the private key, every signer does, and every region issues a licence."""
    _no_key_on_account(lab, p, bench=bench)
    callers = lab.callers(bench=bench)
    p.check("signer callers are listed", ok=callers, detail="no caller found")
    for caller in callers:
        p.admitted(f"{caller}: a licence is issued", lab.issue(caller, "licence"))


VERBS: dict[str, Callable[..., None]] = {
    "signer": verb_signer,
    "region-loss": verb_region_loss,
    "add": verb_add,
    "routing": verb_routing,
    "release": verb_release,
    "replay": verb_replay,
    "proxy": verb_proxy,
    "cost": verb_cost,
    "renet": verb_renet,
    "github": verb_github,
    "remove": verb_remove,
    "keys": verb_keys,
}
# Verbs that run against production; every other verb drives fake companies and runs on bench only.
PRODUCTION_VERBS: frozenset[str] = frozenset({"keys"})


def run_verb(verb: str, lab: Lab, *, bench: bool, out: Callable[[str], None] = print) -> int:
    """Run one verb and print its claims. 0 all hold, 1 any broken or none recorded."""
    p = Proof()
    try:
        VERBS[verb](lab, p, bench=bench)
    except LAB_ERRORS as exc:
        p.check(f"{verb} ran to the end", ok=False, detail=f"{type(exc).__name__}: {exc}")
    for o in p.outcomes:
        out(f"ok      {o.claim}" if o.ok else f"BROKEN  {o.claim}: {o.detail}")
    for note in p.notes:
        out(f"note    {note}")
    if not p.outcomes:
        out(f"proof {verb}: no claim was recorded")
        return 1
    broken = len(p.broken)
    out(f"proof {verb}: {len(p.outcomes)} claim(s), {broken} broken")
    return 1 if broken else 0


def load_lab(*, bench: bool) -> Lab | None:
    try:
        module = importlib.import_module(LAB_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != LAB_MODULE:
            raise
        return None
    lab: Lab = module.build(bench=bench)
    return lab


def parse(argv: Sequence[str]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        prog="./run.sh enterprise proof", description=__doc__.split("\n")[0]
    )
    ap.add_argument("verb", choices=sorted(VERBS))
    ap.add_argument("--bench", action="store_true", help="run against bench with fake companies")
    return ap.parse_args(list(argv))


def main(argv: Sequence[str], *, lab: Lab | None = None) -> int:
    try:
        args = parse(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    if args.verb not in PRODUCTION_VERBS and not args.bench:
        print(
            f"{SELF}: proof {args.verb} drives fake companies and runs on bench only: add --bench",
            file=sys.stderr,
        )
        return 2
    bound = lab if lab is not None else load_lab(bench=args.bench)
    if bound is None:
        print(
            f"{SELF}: no live lab: {LAB_MODULE} is not built yet; it binds the add, lifecycle, "
            "deploy and ring modules (boxes C1, C2, D1, K2, S2), and nothing was claimed",
            file=sys.stderr,
        )
        return 2
    return run_verb(args.verb, bound, bench=args.bench)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
