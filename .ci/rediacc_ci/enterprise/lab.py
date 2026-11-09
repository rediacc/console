"""The live `Lab` that `./run.sh enterprise proof <verb>` drives (agent/plans/PLAN-enterprise-isolation.md, the bench boxes V1-V11 and X1). `proof.load_lab` imports this module and calls `build(bench=...)`.

WHAT IS BOUND. The company half is real: `add` and `ensure_company` run box C1's resumable `onboarding.run` over the live steps, and a company's caller Worker, hosts and words come from its control row. `export`, `remove` and a ring placement run box C2's `lifecycle` verbs over the context `cli.lifecycle_context` builds.

WHAT IS A SEAM. Every other method belongs to a box whose code has not landed. `OWNERS` names that box per method, and `SEAMS` names the module the box will add. A call resolves the module when it is called, so a box that lands with a function of the method's name is bound without an edit here; until then the call raises `NotBuiltError("not built yet: <box> (...)")`. That is a `proof.LabError`, so the proof records it as a broken claim and exits 1 rather than claiming anything, and nothing live is touched first. The signer group (box S2) includes `account_workers` and `secret_names`: until the signers exist every account Worker holds the key by design, so reading the secret lists would only restate the known state.

The readers the proof needs that no writer box owns (routing, tokens, the proxy and executor, cost, the fleet renet, the GitHub run, what a removed company leaves) are named by the live box that first runs them, as the P1 correction in the plan says.
"""

from __future__ import annotations

import dataclasses
import importlib
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from rediacc_ci.enterprise import cli, control_db, names, onboarding, proof, registry
from rediacc_ci.well_known import PRODUCT_DOMAIN

if TYPE_CHECKING:
    import types

ADD_REGION = "eu"
PROOF_STORAGE_GB = 10
RING_REASON = "placed by enterprise proof"


class NotBuiltError(proof.LabError):
    """A lab method whose owning box has not landed."""


@dataclasses.dataclass(frozen=True)
class Seam:
    module: str | None
    what: str


SEAMS: dict[str, Seam] = {
    "S2": Seam("rediacc_ci.deploy.deploy_signer", "the regional signers and their binding"),
    "K2": Seam("rediacc_ci.release.rings_run", "the ring runner"),
    "C2": Seam("rediacc_ci.enterprise.lifecycle", "list, update, suspend, export and remove"),
    "A1": Seam(None, "the company bootstrap that sends the owner mail"),
    "V3": Seam(None, "the www lookup reader, bound by the first run of `proof add`"),
    "V4": Seam(None, "the routing reader, bound by the first run of `proof routing`"),
    "V6": Seam(None, "the token minter and presenter, bound by the first run of `proof replay`"),
    "V7": Seam(None, "the proxy and executor reader, bound by the first run of `proof proxy`"),
    "V8": Seam(None, "the cost reader, bound by the first run of `proof cost`"),
    "V9": Seam(None, "the fleet renet driver, bound by the first run of `proof renet`"),
    "V10": Seam(None, "the GitHub run reader, bound by the first run of `proof github`"),
    "V11": Seam(None, "the leftovers reader, bound by the first run of `proof remove`"),
}

_GROUPS: dict[str, tuple[str, ...]] = {
    "S2": (
        "account_workers", "signers", "secret_names", "callers", "signer_of", "signer_props",
        "expected_props", "issue", "certificate_audited", "current_licence_works", "renew",
        "stop_signer", "start_signer", "cut_region", "restore_region",
    ),
    "C1": ("ensure_company", "caller_of", "company_hosts", "company_words", "add"),
    "A1": ("captured_mail",),
    "V3": ("lookup",),
    "C2": ("export", "remove"),
    "V11": ("leftovers",),
    "V4": (
        "fetch", "expected_worker", "region_hosts", "specific_hosts", "cert_log_names",
        "turnstile_domains",
    ),
    "K2": ("target_version", "versions", "release"),
    "V6": ("mint", "present"),
    "V7": ("container_app", "durable_object", "console_command", "set_allowlist", "request_from"),
    "V8": ("deploy_records", "usage_rows", "image_rebuild_seconds", "read_limits"),
    "V9": (
        "fleet_machine", "renet_version", "released_renet", "run_verb", "executor_upload",
        "renew_with",
    ),
    "V10": ("dispatch_release", "run_surfaces"),
}  # fmt: skip
# Method -> the box that owns it.
OWNERS: dict[str, str] = {m: box for box, methods in _GROUPS.items() for m in methods}


def _import(name: str) -> types.ModuleType | None:
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name != name:
            raise
        return None


def _seam_module(box: str) -> types.ModuleType:
    seam = SEAMS[box]
    if seam.module is None:
        raise NotBuiltError("not built yet: %s (%s)" % (box, seam.what))
    module = _import(seam.module)
    if module is None:
        raise NotBuiltError("not built yet: %s (%s, %s)" % (box, seam.module, seam.what))
    return module


def _delegate(method: str) -> Callable[..., Any]:
    """The seam for one protocol method: its owner's module resolved at call time, refused by name while the box has not landed."""
    box = OWNERS[method]

    def call(*args: Any, **kwargs: Any) -> Any:
        module = _seam_module(box)
        fn = getattr(module, method, None)
        if not callable(fn):
            raise NotBuiltError(
                "not built yet: %s (%s has no %s)" % (box, SEAMS[box].module, method)
            )
        return fn(*args, **kwargs)

    call.__name__ = method
    call.__doc__ = "Box %s: %s." % (box, SEAMS[box].what)
    return call


Adder = Callable[..., onboarding.Outcome]
Finder = Callable[[str], dict | None]


class LiveLab:
    """The live world on bench (or production for `keys`)."""

    def __init__(
        self,
        *,
        bench: bool,
        adder: Adder | None = None,
        finder: Finder | None = None,
        resolver: Finder | None = None,
        lifecycle_ctx: Callable[..., Any] | None = None,
    ):
        self.bench = bench
        self._adder = adder or self._live_add
        self._finder = finder or self._live_find
        self._resolver = resolver or self._live_resolve
        self._lifecycle_ctx = lifecycle_ctx or cli.lifecycle_context

    def __getattr__(self, attr: str) -> Callable[..., Any]:
        """Every protocol method this class does not define is a seam bound to its owner's module (OWNERS)."""
        if attr in OWNERS:
            return _delegate(attr)
        raise AttributeError(attr)

    # -- production bindings -------------------------------------------------------

    def _registry(self) -> registry.Registry:
        return registry.Registry(control_db.transport(), bench=self.bench)

    def _live_add(self, req: onboarding.Request, stop_after: str = "") -> onboarding.Outcome:
        try:
            control_db.ensure_all(bench=req.bench)
        except control_db.ControlDbError as exc:
            return onboarding.Outcome(1, "", (), "refused: %s" % exc)
        return onboarding.run(
            req,
            query=control_db.transport(),
            actions=onboarding.live_actions(),
            stop_after=stop_after,
            out=lambda _line: None,
        )

    def _companies(self) -> list[dict]:
        try:
            return self._registry().companies()
        except registry.RegistryUnreachableError as exc:
            raise proof.LabError(str(exc)) from None

    def _live_find(self, name: str) -> dict | None:
        return next(
            (r for r in self._companies() if r["name"] == name and r.get("state") != "removed"),
            None,
        )

    def _live_resolve(self, company: str) -> dict | None:
        return next((r for r in self._companies() if r["id"] == company), None)

    def _row(self, company: str) -> dict:
        row = self._resolver(company)
        if row is None:
            raise proof.LabError("no company %s in the control databases" % company)
        return row

    def _lifecycle(self) -> types.ModuleType:
        return _seam_module("C2")

    def _context(self, lifecycle: types.ModuleType, *, github_actions: bool = False) -> Any:
        env = {"GITHUB_ACTIONS": "true"} if github_actions else {}
        return self._lifecycle_ctx(lifecycle, bench=self.bench, env=env)

    # -- companies (C1, C2) ------------------------------------------------------------

    def add(
        self, label: str, *, owner: str, unlisted: bool, lookup_domain: str, kill_after: str = ""
    ) -> proof.AddResult:
        req = onboarding.Request(
            name=label,
            region=ADD_REGION,
            owner=owner,
            storage_gb=PROOF_STORAGE_GB,
            unlisted=unlisted,
            lookup_domain=lookup_domain,
            bench=self.bench,
        )
        out = self._adder(req, stop_after=kill_after)
        return proof.AddResult(
            rc=out.rc, company=out.company_id, changed=tuple(out.changed), error=out.error
        )

    def ensure_company(self, label: str, region: str, *, ring: str | None = None) -> str:
        lifecycle = self._lifecycle() if ring is not None else None
        row = self._finder(label)
        if row is None or row.get("state") != "active":
            domain = "%s.example" % label
            req = onboarding.Request(
                name=label,
                region=region,
                owner="owner@%s" % domain,
                storage_gb=PROOF_STORAGE_GB,
                unlisted=True,
                lookup_domain=domain,
                bench=self.bench,
            )
            out = self._adder(req)
            if out.rc != 0:
                raise proof.LabError(out.error or "enterprise add exited %d" % out.rc)
            cid = out.company_id
        else:
            cid = str(row["id"])
        if lifecycle is not None:
            try:
                lifecycle.update(
                    self._context(lifecycle), label, ring=ring, ring_reason=RING_REASON
                )
            except lifecycle.LifecycleError as exc:
                raise proof.LabError(str(exc)) from None
        return cid

    def caller_of(self, company: str) -> str:
        return "account-%s" % self._row(company)["name"]

    def company_hosts(self, company: str) -> tuple[str, str]:
        return names.hosts(str(self._row(company)["name"]), PRODUCT_DOMAIN)

    def company_words(self, company: str) -> list[str]:
        name = str(self._row(company)["name"])
        return [name, *names.hosts(name, PRODUCT_DOMAIN)]

    def export(self, company: str) -> int:
        lifecycle = self._lifecycle()
        name = str(self._row(company)["name"])
        try:
            lifecycle.export(self._context(lifecycle), name)
        except lifecycle.LifecycleError:
            return 1
        return 0

    def remove(self, company: str, *, delete_data: bool, github_actions: bool) -> int:
        lifecycle = self._lifecycle()
        name = str(self._row(company)["name"])
        ctx = self._context(lifecycle, github_actions=github_actions)
        try:
            lifecycle.remove(ctx, name, delete_data=delete_data, confirm=name)
        except lifecycle.LifecycleError:
            return 1
        return 0


def build(*, bench: bool, **seams: Any) -> LiveLab:
    """The live lab `proof.load_lab` asks for. `seams` replaces the add, finder, resolver or lifecycle context (tests)."""
    return LiveLab(bench=bench, **seams)
