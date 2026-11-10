"""The live `Lab` that `./run.sh enterprise proof <verb>` drives (agent/plans/PLAN-enterprise-isolation.md, the bench boxes V1-V11 and X1). `proof.load_lab` imports this module and calls `build(bench=...)`.

WHAT IS BOUND. The company half is real: `add` and `ensure_company` run box C1's resumable `onboarding.run` over the live steps, and a company's caller Worker, hosts and words come from its control row. `export`, `remove` and a ring placement run box C2's `lifecycle` verbs over the context `cli.lifecycle_context` builds.

WHAT IS A SEAM. Every other method belongs to a box whose code has not landed. `OWNERS` names that box per method, and `SEAMS` names the module the box will add. A call resolves the module when it is called, so a box that lands with a function of the method's name is bound without an edit here; until then the call raises `NotBuiltError("not built yet: <box> (...)")`. That is a `proof.LabError`, so the proof records it as a broken claim and exits 1 rather than claiming anything, and nothing live is touched first. The signer group (box S2) includes `account_workers` and `secret_names`: until the signers exist every account Worker holds the key by design, so reading the secret lists would only restate the known state.

The readers the proof needs that no writer box owns (the captured mail and the lookup, routing, tokens, the proxy and executor, cost, the fleet renet, the GitHub run, what a removed company leaves) are this module's own functions, one section per live box below `build`, each taking its live calls through the shared transports of the first section; their SEAMS name this module. A reader whose driver does not exist yet raises `not built yet: <box> (...)` from inside its section, the way S2's caller probe does. `release` is bound by `LiveLab` rather than by name, because the ring runner's own `release(args, world)` is its CLI entry: the lab calls `rings_run.lab_release`.
"""

from __future__ import annotations

import dataclasses
import datetime
import importlib
import json
import os
import pathlib
import re
import socket
import ssl
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from rediacc_ci import paths
from rediacc_ci.core import https, wrangler
from rediacc_ci.enterprise import (
    cli,
    control_db,
    lifecycle,
    lifecycle_adapters,
    names,
    onboarding,
    proof,
    registry,
    secrets,
)
from rediacc_ci.housekeeping import cf_leftovers
from rediacc_ci.ops import bench_access, cf_usage_report, enterprise_lookup
from rediacc_ci.ops import observability_volume as ov
from rediacc_ci.release import local
from rediacc_ci.well_known import CF_API_BASE, PRODUCT_DOMAIN

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
    "A1": Seam(__name__, "the owner mail a bench company captured"),
    "V3": Seam(__name__, "the www lookup entry reader"),
    "V4": Seam(__name__, "the routing, certificate and Turnstile reader"),
    "V6": Seam(__name__, "the token minter and presenter"),
    "V7": Seam(__name__, "the proxy and executor reader"),
    "V8": Seam(__name__, "the deploy record, usage and limits reader"),
    "V9": Seam(__name__, "the fleet renet driver"),
    "V10": Seam(__name__, "the GitHub dispatch and run reader"),
    "V11": Seam(__name__, "the leftovers reader"),
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
    "V7": (
        "container_app", "durable_object", "console_command", "egress_ips", "set_allowlist",
        "request_from",
    ),
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
        reset_sessions()
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
        # None lets the context inherit os.environ, as the CLI path does; the CI simulation sets only its variable.
        env = {"GITHUB_ACTIONS": "true"} if github_actions else None
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

    # -- releases (K2) ---------------------------------------------------------------

    def release(
        self,
        *,
        skip_pauses: bool = False,
        order: str = "",
        plant_failure: str = "",
        resume: str = "",
    ) -> proof.ReleaseResult:
        module = _seam_module("K2")
        fn = getattr(module, "lab_release", None)
        if not callable(fn):
            raise NotBuiltError("not built yet: K2 (%s has no lab_release)" % SEAMS["K2"].module)
        result: proof.ReleaseResult = fn(
            skip_pauses=skip_pauses, order=order, plant_failure=plant_failure, resume=resume
        )
        return result

    def export(self, company: str) -> int:
        lifecycle = self._lifecycle()
        name = str(self._row(company)["name"])
        try:
            lifecycle.export(self._context(lifecycle), name)
        except lifecycle.LifecycleError as exc:
            print("enterprise export: %s" % exc, file=sys.stderr)
            return 1
        return 0

    def remove(self, company: str, *, delete_data: bool, github_actions: bool) -> int:
        lifecycle = self._lifecycle()
        name = str(self._row(company)["name"])
        ctx = self._context(lifecycle, github_actions=github_actions)
        try:
            lifecycle.remove(ctx, name, delete_data=delete_data, confirm=name)
        except lifecycle.LifecycleError as exc:
            print("enterprise remove: %s" % exc, file=sys.stderr)
            return 1
        return 0


def build(*, bench: bool, **seams: Any) -> LiveLab:
    """The live lab `proof.load_lab` asks for. `seams` replaces the add, finder, resolver or lifecycle context (tests)."""
    return LiveLab(bench=bench, **seams)


# ---- the live readers the V boxes drive, bound through SEAMS by name ----------------


# ==== the transports every reader shares
#
# The transports the live lab readers share (agent/plans/PLAN-enterprise-isolation.md, the bench boxes V3-V11, read through `rediacc_ci.enterprise.lab`).
#
# Each reader below takes its live calls through keyword-only seams whose defaults are the transports in this section, the way `rediacc_ci.deploy.deploy_signer`'s lab group does: a test swaps the seam for a fake and no test reaches the network.
#
# EVERY FAILURE IS A `proof.LabError`. A Cloudflare read, a D1 query, a child process or a fetch that fails raises `LabError` naming what was asked, never a traceback, so `enterprise proof` records a broken claim and still restores what it changed. No value read from a secret is ever put into an error.
#
# THE FAKE-COMPANY VERBS RUN ON BENCH ONLY (`proof.PRODUCTION_VERBS`), so a reader that is handed only a company id reads the bench registry (`BENCH`).


BENCH = True
PROFILE = "deploy-workers"
CHILD_TIMEOUT_S = 1800
R2_JURISDICTION_HEADER = "cf-r2-jurisdiction"


@dataclasses.dataclass(frozen=True)
class Proc:
    rc: int
    stdout: str = ""
    stderr: str = ""


# (argv, cwd, extra env) -> Proc. Streams are captured, never echoed: they can carry a company name.
Runner = Callable[[Sequence[str], "pathlib.Path | None", "dict[str, str] | None"], Proc]
# (absolute API path, starting with `/`) -> the decoded `result`.
Api = Callable[[str], Any]
# (absolute API path) -> every `result` item of a paginated listing.
Listing = Callable[[str], list]
Companies = Callable[[bool], list[dict]]
Query = Callable[[str, str, Sequence[object]], list[dict]]
# (url) -> (status, body text). Fetches the public origin or a docs page; no credential.
Fetch = Callable[[str], tuple[int, str]]


def root() -> pathlib.Path:
    return pathlib.Path(paths.repo_root())


def run_process(
    argv: Sequence[str], cwd: pathlib.Path | None = None, env: dict[str, str] | None = None
) -> Proc:
    full = dict(os.environ)
    full.update(env or {})
    try:
        done = subprocess.run(
            list(argv),
            cwd=str(cwd or root()),
            env=full,
            capture_output=True,
            text=True,
            check=False,
            timeout=CHILD_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise proof.LabError("%s could not run: %s" % (argv[0], type(exc).__name__)) from None
    return Proc(done.returncode, done.stdout, done.stderr)


def _credentials() -> tuple[str, str]:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not token or not account:
        raise proof.LabError(
            "CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID are required (bws_env exec --profile %s)"
            % PROFILE
        )
    return token, account


def account_path(rest: str) -> str:
    """`/accounts/<id><rest>`, the account id read from the environment."""
    return "/accounts/%s%s" % (_credentials()[1], rest)


def cf_get(path: str) -> Any:
    token, _account = _credentials()
    try:
        return cf_leftovers.fetch(path, token).get("result")
    except cf_leftovers.CfError as exc:
        raise proof.LabError(str(exc)) from None


def cf_get_with(path: str, headers: dict[str, str]) -> Any:
    """`cf_get` with extra request headers (the R2 jurisdiction header): one GET, the decoded `result`."""
    token, _account = _credentials()
    sent = {"Authorization": "Bearer " + token, **headers}
    try:
        req = https.build_request(CF_API_BASE + path, headers=sent, method="GET")
        with https.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        exc.close()
        raise proof.LabError("GET %s: HTTP %d" % (path, exc.code)) from None
    except (OSError, ValueError) as exc:
        raise proof.LabError("GET %s: %s" % (path, type(exc).__name__)) from None
    if not isinstance(body, dict) or body.get("success") is not True:
        raise proof.LabError("GET %s: Cloudflare answered no success" % path)
    return body.get("result")


def r2_bucket_names(jurisdiction: str | None) -> set[str]:
    """Every R2 bucket name of the account in `jurisdiction` (None: the default one). Buckets in a jurisdiction are listed only under its header."""
    headers = {R2_JURISDICTION_HEADER: jurisdiction} if jurisdiction else {}
    result = cf_get_with(account_path("/r2/buckets?per_page=1000"), headers)
    rows = result.get("buckets") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise proof.LabError("the R2 bucket listing has no bucket list")
    return {str(r.get("name", "")) for r in rows if isinstance(r, dict)}


def region_jurisdiction(region: str, base: pathlib.Path | None = None) -> str | None:
    doc = json.loads(((base or root()) / "regions.json").read_text(encoding="utf-8"))
    for r in doc["regions"]:
        if r["id"] == region:
            return r.get("r2Jurisdiction") or None
    return None


def cf_list(path: str) -> list:
    token, _account = _credentials()
    try:
        return cf_leftovers.listing(path, token)
    except cf_leftovers.CfError as exc:
        raise proof.LabError(str(exc)) from None


def d1_query(database: str, sql: str, params: Sequence[object]) -> list[dict]:
    try:
        return control_db.query(database, sql, params, runner=control_db.run_wrangler)
    except control_db.ControlDbError as exc:
        raise proof.LabError(str(exc)) from None


def all_companies(bench: bool) -> list[dict]:
    """Every company row of the region control databases, removed ones included."""
    try:
        return registry.Registry(control_db.transport(), bench=bench).companies()
    except registry.RegistryUnreachableError as exc:
        raise proof.LabError(str(exc)) from None


def live_companies(bench: bool, *, companies: Companies = all_companies) -> list[dict]:
    return [r for r in companies(bench) if r.get("state") != "removed"]


def company_row(company: str, *, companies: Companies = all_companies) -> dict:
    """The bench control row of an opaque company id, removed or not."""
    for row in companies(BENCH):
        if str(row.get("id")) == company:
            return row
    raise proof.LabError("no company %s in the bench control databases" % company)


def http_get(url: str) -> tuple[int, str]:
    try:
        req = https.build_request(url, method="GET")
        with https.urlopen(req, timeout=60) as resp:
            return int(resp.status), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            return int(exc.code), exc.read().decode("utf-8", "replace")
        finally:
            exc.close()
    except OSError as exc:
        raise proof.LabError("GET %s: %s" % (url, type(exc).__name__)) from None


def edge_version(*, fetch: Fetch = http_get, base: pathlib.Path | None = None) -> str:
    """The version `cli/edge/latest.json` names over the public releases origin: what edge, and so the fast tier, runs."""
    origin = local.well_known(base or root()).get("WK_RELEASES_ORIGIN", "")
    if not origin:
        raise proof.LabError("well-known has no WK_RELEASES_ORIGIN")
    url = "%s/cli/edge/latest.json" % origin
    status, body = fetch(url)
    if status != 200:
        raise proof.LabError("GET %s answered %d" % (url, status))
    try:
        version = json.loads(body).get("version")
    except (ValueError, AttributeError):
        raise proof.LabError("%s is not a JSON object" % url) from None
    if not isinstance(version, str) or not version:
        raise proof.LabError("%s names no version" % url)
    return version


# ==== boxes A1 and V3: the captured owner mail and the lookup entry (`proof add`)
#
# The `enterprise proof add` readers (agent/plans/PLAN-enterprise-isolation.md, box V3): the owner mail a bench company captured (box A1's group) and the www lookup entry (box V3's group). SEAMS binds both by name.
#
# `captured_mail(owner)` reads `captured_emails` (private/account/src/services/email-capture.service.ts), the bench-only copy of every outgoing mail, in each live bench company's own D1 `account-<name>`: `enterprise add --bench` writes `ENVIRONMENT = "bench"` into the company config, so the invitation box A1 sends lands there. It answers the subjects of the mails sent to `owner`, never a body, because a body carries the invitation token.
#
# `lookup(domain)` reads the entry the lookup writer (`rediacc_ci.ops.enterprise_lookup.put`) stored: the KV key is the HMAC of the normalized domain under `ENTERPRISE_LOOKUP_PEPPER`, read with `wrangler kv key get --remote` from `workers/www`. It answers the host, or None for a miss, and None without a read for a malformed or free-mail domain, the same answers the www Worker gives (`workers/www/src/enterprise-lookup.ts`). The public route needs a Turnstile token the proof cannot solve, so the store the route reads is read instead.


CAPTURED_SQL = "SELECT subject FROM captured_emails WHERE recipient = ? ORDER BY created_at"
WWW_REL = ("workers", "www")
NOT_FOUND = "value not found"


def captured_mail(
    owner: str,
    *,
    companies: Companies = all_companies,
    query: Query = d1_query,
) -> list[str]:
    """The subjects of every captured mail sent to `owner`, across the live bench companies' databases."""
    rows = live_companies(BENCH, companies=companies)
    if not rows:
        raise proof.LabError("no live bench company to read captured mail from")
    subjects: list[str] = []
    for row in rows:
        found = query("account-%s" % row["name"], CAPTURED_SQL, [owner])
        subjects.extend(str(r.get("subject", "")) for r in found)
    return subjects


def _pepper() -> str:
    value = os.environ.get(enterprise_lookup.PEPPER_ENV, "")
    if not value:
        raise proof.LabError(
            "set %s (the www Worker's secret of the same name)" % enterprise_lookup.PEPPER_ENV
        )
    return value


def lookup(
    domain: str,
    *,
    run: Runner = run_process,
    namespace_id: str = enterprise_lookup.NAMESPACE_ID,
    pepper: str | None = None,
) -> str | None:
    try:
        d = enterprise_lookup.normalize_domain(domain)
        enterprise_lookup.refuse_free_mail(d)
    except enterprise_lookup.LookupRefusedError:
        return None
    key = enterprise_lookup.lookup_key(pepper if pepper is not None else _pepper(), d)
    argv = [*wrangler.ARGV, "kv", "key", "get", key, "--namespace-id", namespace_id, "--remote"]
    done = run(argv, root().joinpath(*WWW_REL), None)
    text = done.stdout.strip()
    if NOT_FOUND in (text + "\n" + done.stderr).lower():
        return None
    if done.rc != 0:
        raise proof.LabError("wrangler kv key get exited %d" % done.rc)
    return text or None


# ==== box V4: routing, certificates and Turnstile (`proof routing`)
#
# The `enterprise proof routing` readers (agent/plans/PLAN-enterprise-isolation.md, box V4). SEAMS binds them by name.
#
# WHO ANSWERED A HOST. No Worker names itself in a response, so `fetch(host)` takes the answer in two parts: a live HTTPS GET of `https://<host>/` gives the status and the certificate actually served (its subjectAltName DNS names, read from the TLS handshake), and the Worker is the one Cloudflare's live configuration sends the host to: a Workers Custom Domain naming the host exactly wins, then the most specific matching Worker Route of the product zone (an exact host before a `*.` wildcard, as Cloudflare orders them). A route with no script answers no Worker (`""`).
#
# WHO SHOULD ANSWER. `expected_worker(host)` is the intent, read from the repository, never from Cloudflare: a company host (`<name>.<domain>`, `<name>-proxy.<domain>`, per `names.hosts`) belongs to `account-<name>` / `proxy-<name>`, and every other host to the Worker whose tracked `workers/*/wrangler*.toml` declares it in `routes`. A host neither names is a `LabError`, so an unknown host is never compared against nothing.
#
# THE OTHER READS. `region_hosts(bench)` are the hosts the shared Workers declare (bench: `account-bench` and `proxy-bench`; production: each region's `workerName` and `proxyWorkerName` from regions.json). `specific_hosts()` are the other declared hosts under the product domain, the specific records that must win over the wildcard. `cert_log_names()` are the DNS names of every certificate Certificate Transparency logged under the product domain (crt.sh, queried by the domain only, never by a company name). `turnstile_domains()` are the domains of the one Turnstile widget the Workers share (`rediacc-console`, as `deploy.turnstile_drift` picks it).


WORKERS_REL = "workers"
# The proxy template renders a company config; its tokens are not TOML until rendered.
TEMPLATE = "wrangler.template.toml"
BENCH_WORKERS = ("account-bench", "proxy-bench")
TURNSTILE_WIDGET = "rediacc-console"
CRT_SH = "https://crt.sh/?q=%s&output=json"
TLS_TIMEOUT_S = 30

# host -> (status, certificate DNS names).
Probe = Callable[[str], tuple[int, tuple[str, ...]]]


def _tls_names(host: str) -> tuple[str, ...]:
    ctx = ssl.create_default_context()
    try:
        with (
            socket.create_connection((host, 443), timeout=TLS_TIMEOUT_S) as sock,
            ctx.wrap_socket(sock, server_hostname=host) as tls,
        ):
            cert = tls.getpeercert() or {}
    except (OSError, ssl.SSLError) as exc:
        raise proof.LabError("TLS to %s: %s" % (host, type(exc).__name__)) from None
    return tuple(str(v) for k, v in cert.get("subjectAltName", ()) if k == "DNS")


def live_probe(host: str) -> tuple[int, tuple[str, ...]]:
    cert = _tls_names(host)
    status, _body = http_get("https://%s/" % host)
    return status, cert


def _zone_id(api: Api) -> str:
    zones = api("/zones?name=%s" % urllib.parse.quote(PRODUCT_DOMAIN))
    if not isinstance(zones, list) or len(zones) != 1:
        raise proof.LabError("the zone %s was not found exactly once" % PRODUCT_DOMAIN)
    return str(zones[0]["id"])


def _pattern_host(pattern: str) -> str:
    return pattern.split("/", 1)[0].lower()


def _matches(pattern_host: str, host: str) -> bool:
    if pattern_host == host:
        return True
    if pattern_host.startswith("*."):
        return host.endswith(pattern_host[1:]) and host != pattern_host[2:]
    if pattern_host.startswith("*"):
        return host.endswith(pattern_host[1:])
    return False


def routed_worker(host: str, *, api: Api = cf_get, listing: Listing = cf_list) -> str:
    """The Worker Cloudflare's live configuration sends `host` to: a Custom Domain first, then the most specific route; `""` when none or a scriptless route matches."""
    host = host.lower()
    for d in listing(account_path("/workers/domains")):
        if isinstance(d, dict) and str(d.get("hostname", "")).lower() == host:
            return str(d.get("service", ""))
    routes = api("/zones/%s/workers/routes" % _zone_id(api)) or []
    hits = [
        r
        for r in routes
        if isinstance(r, dict) and _matches(_pattern_host(str(r.get("pattern", ""))), host)
    ]
    if not hits:
        return ""
    # An exact host, then the longest pattern: what Cloudflare treats as more specific.
    best = max(hits, key=lambda r: ("*" not in str(r["pattern"]), len(str(r["pattern"]))))
    return str(best.get("script") or "")


def fetch(
    host: str,
    *,
    probe: Probe = live_probe,
    worker_of: Callable[[str], str] = routed_worker,
) -> proof.Reply:
    status, cert = probe(host)
    return proof.Reply(status=status, worker=worker_of(host), cert_names=cert)


def declared_hosts(base: Any = None) -> dict[str, str]:
    """host -> Worker for every host a tracked `workers/*/wrangler*.toml` declares in `routes` (the template skipped, a config that does not parse a `LabError`)."""
    out: dict[str, str] = {}
    top = (base or root()) / WORKERS_REL
    for path in sorted(top.glob("*/wrangler*.toml")):
        if path.name == TEMPLATE:
            continue
        try:
            doc = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise proof.LabError(
                "%s cannot be read: %s" % (path.name, type(exc).__name__)
            ) from None
        name = str(doc.get("name", ""))
        if not name:
            continue
        for route in doc.get("routes", []) or []:
            pattern = route.get("pattern", "") if isinstance(route, dict) else str(route)
            host = _pattern_host(str(pattern))
            if host and "*" not in host:
                out[host] = name
    return out


def _company_worker(host: str, companies: list[dict]) -> str | None:
    for row in companies:
        account, proxy_host = names.hosts(str(row["name"]), PRODUCT_DOMAIN)
        if host == account:
            return "account-%s" % row["name"]
        if host == proxy_host:
            return "proxy-%s" % row["name"]
    return None


def expected_worker(
    host: str,
    *,
    companies: Companies = all_companies,
    declared: Callable[[], dict[str, str]] = declared_hosts,
) -> str:
    host = host.lower()
    known = declared()
    if host in known:
        return known[host]
    worker = _company_worker(host, live_companies(BENCH, companies=companies))
    if worker is None:
        raise proof.LabError("no tracked config or live company names the host %s" % host)
    return worker


def _shared_workers(bench: bool) -> set[str]:
    if bench:
        return set(BENCH_WORKERS)
    doc = json.loads((root() / "regions.json").read_text(encoding="utf-8"))
    return {str(r[k]) for r in doc["regions"] for k in ("workerName", "proxyWorkerName")}


def region_hosts(
    *, bench: bool, declared: Callable[[], dict[str, str]] = declared_hosts
) -> list[str]:
    shared = _shared_workers(bench)
    return sorted(h for h, w in declared().items() if w in shared)


def specific_hosts(*, declared: Callable[[], dict[str, str]] = declared_hosts) -> list[str]:
    shared = _shared_workers(True) | _shared_workers(False)
    return sorted(
        h
        for h, w in declared().items()
        if w not in shared and (h == PRODUCT_DOMAIN or h.endswith("." + PRODUCT_DOMAIN))
    )


def cert_log_names(*, fetch_url: Fetch = http_get) -> list[str]:
    url = CRT_SH % urllib.parse.quote("%." + PRODUCT_DOMAIN)
    status, body = fetch_url(url)
    if status != 200:
        raise proof.LabError("crt.sh answered %d" % status)
    try:
        rows = json.loads(body)
    except ValueError:
        raise proof.LabError("crt.sh answered no JSON") from None
    if not isinstance(rows, list) or not rows:
        raise proof.LabError("crt.sh logged no certificate for the product domain")
    found: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            found.update(n.strip().lower() for n in str(row.get("name_value", "")).splitlines())
    return sorted(n for n in found if n)


def turnstile_domains(*, listing: Listing = cf_list) -> list[str]:
    widgets = [
        w
        for w in listing(account_path("/challenges/widgets"))
        if isinstance(w, dict) and w.get("name") == TURNSTILE_WIDGET
    ]
    if len(widgets) != 1:
        raise proof.LabError(
            "%d Turnstile widgets are named %s, not 1" % (len(widgets), TURNSTILE_WIDGET)
        )
    return [str(d).lower() for d in widgets[0].get("domains") or []]


# ==== box V6: the token minter and presenter (`proof replay`, and the proxy token of `proof proxy`)
#
# The `enterprise proof replay` and `proof proxy` token readers (agent/plans/PLAN-enterprise-isolation.md, box V6's group, which V7's proxy token rides). SEAMS binds them by name.
#
# SIGNING IN AS A FAKE OWNER. `owner_session(company)` is the owner's first sign-in, the one company mode designs: the owner account is passwordless (private/account/src/services/enterprise-bootstrap.service.ts `ensureOwner`), and `POST /account/api/v1/subscriptions/enterprise/owner-mail` under the company's own `ACCOUNT_SERVER_API_KEY` mails it a magic link (`authService.sendCompanyOwnerMail`). That route carries no captcha, unlike the public `POST /auth/magic-link`. A bench company captures every mail in its own D1 (`captured_emails`, `kind = 'magic-link'`), so the link is read back from `account-<name>`, the one mail body the owner did not hold before the request (a set difference, so neither clock nor row order is read; two new bodies mean another sign-in raced this one and are a `LabError`), and `POST /account/api/v1/auth/magic-link/verify` answers the session as its `access_token` cookie. The owner has no TOTP; a verify answering `requiresTwoFactor` is a `LabError`. The owner address is read from the company D1 (`company_orgs` -> `organizations.owner_user_id` -> `users.email`) and the key from the enterprise bws project (`secrets.store_name(<id>, "ACCOUNT_SERVER_API_KEY")`, project id in `ENTERPRISE_PROOF_BWS_PROJECT`). The link's token is never put into an error.
#
# `mint(company, kind)`: a `session` is that cookie; an `api-token` (scope `license:read`) and a `proxy-token` (scope `proxy:exec`) are `POST /account/api/v1/api-tokens` under the session for the subscription the company's control row names (`scope.subscription_id`). A `config-token` needs the company's config store, whose setup takes a TOTP-verified, elevated session and client-wrapped CEK slots (`POST /configs/setup`), and an `e2e-envelope` needs a request sealed to the company's X25519 key (`POST /account/api/v1/tunnel`); neither driver is written, so both raise `LabError("not built yet: V6 ...")` naming what is missing, never an artifact.
#
# `present(company, kind, artifact)` sends one artifact to the company's own account host and maps the answer: 2xx is admitted, 401 or 403 is refused with the status, anything else is a `LabError` (a 5xx or a 404 says the probe is wrong, not that the artifact was refused). Each kind has one probe that changes nothing it reads: a `session` is the `access_token` cookie on `GET /account/api/v1/portal/me` (private/account/src/middleware/session.ts); an `api-token` is the bearer of `GET /account/api/v1/licenses/status` (scope `license:read`, private/account/src/routes/license.ts); a `proxy-token` is the bearer of `POST /account/api/v1/proxy/introspect` with `{"token": "self", "self": true}` (scope `proxy:exec`, private/account/src/routes/proxy.ts), the lookup the company's proxy makes through its own account Worker's `ExecutorIssuer`, over the same D1. The api-token middleware binds a first-use token to the presenting address, which is this machine for both companies, so a refusal by the other company is never an address mismatch. A `config-token` rotates on every use and an `e2e-envelope` has no presenter: both raise `LabError("not built yet: V6 ...")`.


ME_PATH = "/account/api/v1/portal/me"
STATUS_PATH = "/account/api/v1/licenses/status"
INTROSPECT_PATH = "/account/api/v1/proxy/introspect"
VERIFY_PATH = "/account/api/v1/auth/magic-link/verify"
TOKENS_PATH = "/account/api/v1/api-tokens"
REFUSED = (401, 403)
BWS_PROJECT_ENV = "ENTERPRISE_PROOF_BWS_PROJECT"
API_KEY_ENTRY = "ACCOUNT_SERVER_API_KEY"
MAIL_TRIES = 10
MAIL_POLL_S = 3.0
LABEL_PREFIX = "enterprise-proof"
# kind -> the scope its token carries.
TOKEN_SCOPES: dict[str, str] = {"api-token": "license:read", "proxy-token": "proxy:exec"}
OWNER_SQL = (
    "SELECT u.email AS email FROM company_orgs c JOIN organizations o ON o.id = c.org_id "
    "JOIN users u ON u.id = o.owner_user_id WHERE c.company_id = ?"
)
LINK_SQL = (
    "SELECT text_body FROM captured_emails WHERE recipient = ? AND kind = 'magic-link' "
    "ORDER BY created_at DESC"
)
SUBSCRIPTION_SQL = "SELECT subscription_id FROM scope WHERE company_id = ?"
MAGIC_TOKEN = re.compile(r"/account/magic-link/verify\?token=([^&\s\"'<>]+)")
ACCESS_COOKIE = re.compile(r"(?:^|[;,]\s*)access_token=([^;,\s]+)")


@dataclasses.dataclass(frozen=True)
class HttpAnswer:
    status: int
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes = b""

    def header_values(self, name: str) -> list[str]:
        return [v for k, v in self.headers if k.lower() == name.lower()]

    def json(self) -> dict:
        try:
            doc = json.loads(self.body or b"{}")
        except ValueError:
            return {}
        return doc if isinstance(doc, dict) else {}


# (url, headers) -> status.
Send = Callable[[str, dict[str, str]], int]
# (method, url, headers, body) -> the answer. A 4xx or 5xx is an answer; no answer at all is a LabError.
Call = Callable[[str, str, dict[str, str], "bytes | None"], HttpAnswer]
Minter = Callable[[str, str], str]
ApiKey = Callable[[str], str]


def _send(url: str, headers: dict[str, str]) -> int:
    try:
        req = https.build_request(url, headers=headers, method="GET")
        with https.urlopen(req, timeout=60) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        exc.close()
        return int(exc.code)
    except OSError as exc:
        raise proof.LabError(
            "GET %s: %s" % (urllib.parse.urlsplit(url).path, type(exc).__name__)
        ) from None


def http_call(method: str, url: str, headers: dict[str, str], body: bytes | None) -> HttpAnswer:
    """One HTTPS request through `core.https`; the path, never the host, names a failure."""
    path = urllib.parse.urlsplit(url).path
    try:
        req = https.build_request(url, data=body, headers=headers, method=method)
        with https.urlopen(req, timeout=60) as resp:
            return HttpAnswer(int(resp.status), tuple(resp.headers.items()), resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return HttpAnswer(int(exc.code), tuple(exc.headers.items()), exc.read())
        finally:
            exc.close()
    except OSError as exc:
        raise proof.LabError("%s %s: %s" % (method, path, type(exc).__name__)) from None


def _host(company: str, companies: Companies) -> str:
    return names.hosts(str(company_row(company, companies=companies)["name"]), PRODUCT_DOMAIN)[0]


def store_api_key(company: str, *, env: Mapping[str, str] | None = None) -> str:
    """The company's ACCOUNT_SERVER_API_KEY from the enterprise bws project `ENTERPRISE_PROOF_BWS_PROJECT` names."""
    environ = os.environ if env is None else env
    project = environ.get(BWS_PROJECT_ENV, "")
    if not project:
        raise proof.LabError("%s is not set (the enterprise bws project id)" % BWS_PROJECT_ENV)
    try:
        name = secrets.store_name(company, API_KEY_ENTRY)
        found = secrets.BwsStore.from_env(project).read([name])
    except secrets.SecretsError as exc:
        raise proof.LabError("company %s: %s" % (company, exc)) from None
    value = found.get(name, "")
    if not value:
        raise proof.LabError(
            "company %s: no %s in the enterprise project" % (company, API_KEY_ENTRY)
        )
    return value


def _one(rows: list[dict], key: str, what: str) -> str:
    values = [str(r.get(key) or "") for r in rows]
    if len(values) != 1 or not values[0]:
        raise proof.LabError("%s: %d answers, not 1" % (what, len(values)))
    return values[0]


def _links(rows: list[dict]) -> set[str]:
    """The distinct mail bodies of one owner's captured magic links."""
    return {str(r.get("text_body") or "") for r in rows if r.get("text_body")}


def owner_session(
    company: str,
    *,
    companies: Companies = all_companies,
    query: Query = d1_query,
    post: onboarding.AccountPost = onboarding.account_post,
    api_key: ApiKey = store_api_key,
    call: Call = http_call,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """The `access_token` of the company owner's magic-link sign-in."""
    row = company_row(company, companies=companies)
    name = str(row["name"])
    host = names.hosts(name, PRODUCT_DOMAIN)[0]
    database = "account-%s" % name
    owner = _one(
        query(database, OWNER_SQL, [company]), "email", "the owner of company %s" % company
    )
    before = _links(query(database, LINK_SQL, [owner]))
    url = "https://%s%sowner-mail" % (host, onboarding.SUBSCRIPTIONS_PATH)
    status, _payload = post(url, api_key(company), {"companyId": company, "ownerEmail": owner})
    if not 200 <= status < 300:
        raise proof.LabError("company %s: the owner-mail call answered HTTP %d" % (company, status))
    token = ""
    for attempt in range(MAIL_TRIES):
        # A link this request added is a body the owner did not hold before it; no clock or row order is read.
        fresh = sorted(_links(query(database, LINK_SQL, [owner])) - before)
        tokens = {m.group(1) for m in (MAGIC_TOKEN.search(t) for t in fresh) if m}
        if len(tokens) > 1:
            # Another sign-in captured a link in the same window: which one is this request's cannot be told.
            raise proof.LabError(
                "company %s: %d new magic links were captured for its owner, not 1; "
                "another sign-in raced this one" % (company, len(tokens))
            )
        if tokens:
            (token,) = tokens
            break
        if attempt + 1 < MAIL_TRIES:
            sleep(MAIL_POLL_S)
    if not token:
        raise proof.LabError("company %s: no magic link was captured for its owner" % company)
    answer = call(
        "POST",
        "https://%s%s" % (host, VERIFY_PATH),
        {"Content-Type": "application/json"},
        json.dumps({"token": token}).encode(),
    )
    if answer.status != 200:
        raise proof.LabError(
            "company %s: the magic-link verify answered HTTP %d" % (company, answer.status)
        )
    if answer.json().get("requiresTwoFactor"):
        raise proof.LabError("company %s: the owner sign-in asks for a second factor" % company)
    for cookie in answer.header_values("Set-Cookie"):
        got = ACCESS_COOKIE.search(cookie)
        if got:
            return got.group(1)
    raise proof.LabError("company %s: the magic-link verify set no access_token" % company)


def _subscription(company: str, *, companies: Companies, query: Query) -> str:
    row = company_row(company, companies=companies)
    database = registry.control_database(str(row.get("region", "")), BENCH)
    return _one(
        query(database, SUBSCRIPTION_SQL, [company]),
        "subscription_id",
        "the subscription of company %s" % company,
    )


# company -> its owner's session, for the length of one proof run: `LiveLab()` is a run, and empties it.
_SESSIONS: dict[str, str] = {}


def reset_sessions(sessions: dict[str, str] = _SESSIONS) -> None:
    sessions.clear()


def live_minter(
    company: str,
    kind: str,
    *,
    session: Callable[[str], str] | None = None,
    companies: Companies = all_companies,
    query: Query = d1_query,
    call: Call = http_call,
    sessions: dict[str, str] = _SESSIONS,
) -> str:
    """One token of `kind`, minted under the owner's session; the session is signed in once per company and shared by every kind (`sessions`)."""
    if kind == "config-token":
        raise proof.LabError(
            "not built yet: V6 (a config token of company %s needs its config store, whose setup takes a "
            "TOTP-verified elevated session and client-wrapped CEK slots; nothing was minted)"
            % company
        )
    if kind == "e2e-envelope":
        raise proof.LabError(
            "not built yet: V6 (an E2E envelope of company %s needs a request sealed to its X25519 key; "
            "nothing was minted)" % company
        )
    if kind != "session" and kind not in TOKEN_SCOPES:
        raise proof.LabError("no minter for a %s" % kind)
    if session is None:

        def session(c: str) -> str:
            if c not in sessions:
                sessions[c] = owner_session(c, companies=companies, query=query, call=call)
            return sessions[c]

    cookie = session(company)
    if kind == "session":
        return cookie
    body = {
        "subscriptionId": _subscription(company, companies=companies, query=query),
        "name": "%s-%s" % (LABEL_PREFIX, kind),
        "scopes": [TOKEN_SCOPES[kind]],
    }
    answer = call(
        "POST",
        "https://%s%s" % (_host(company, companies), TOKENS_PATH),
        {"Content-Type": "application/json", "Cookie": "access_token=%s" % cookie},
        json.dumps(body).encode(),
    )
    token = answer.json().get("token")
    if answer.status != 201 or not isinstance(token, str) or not token:
        raise proof.LabError(
            "company %s: creating a %s answered HTTP %d" % (company, kind, answer.status)
        )
    return token


def mint(company: str, kind: str, *, minter: Minter = live_minter) -> str:
    return minter(company, kind)


def _verdict(kind: str, status: int) -> proof.Answer:
    if 200 <= status < 300:
        return proof.Answer(True)
    if status in REFUSED:
        return proof.Answer(False, "HTTP %d" % status)
    raise proof.LabError("the %s probe answered HTTP %d" % (kind, status))


def present(
    company: str,
    kind: str,
    artifact: str,
    *,
    send: Send = _send,
    call: Call = http_call,
    companies: Companies = all_companies,
) -> proof.Answer:
    if kind not in ("session", "api-token", "proxy-token"):
        raise proof.LabError("not built yet: V6 (no probe presents a %s)" % kind)
    host = _host(company, companies)
    if kind == "session":
        return _verdict(
            kind, send("https://%s%s" % (host, ME_PATH), {"Cookie": "access_token=%s" % artifact})
        )
    bearer = {"Authorization": "Bearer %s" % artifact}
    if kind == "api-token":
        return _verdict(kind, send("https://%s%s" % (host, STATUS_PATH), bearer))
    answer = call(
        "POST",
        "https://%s%s" % (host, INTROSPECT_PATH),
        {**bearer, "Content-Type": "application/json"},
        json.dumps({"token": "self", "self": True}).encode(),
    )
    return _verdict(kind, answer.status)


# ==== box V7: the proxy and executor (`proof proxy`)
#
# The `enterprise proof proxy` readers (agent/plans/PLAN-enterprise-isolation.md, box V7). SEAMS binds them by name; the proxy token's `mint` and `present` are box V6's.
#
# `durable_object(company)` is the id of the `OrgExecutor` Durable Object namespace whose script is the company's `proxy-<name>` (`/workers/durable_objects/namespaces`). `container_app(company)` is the id of the Containers application backed by that namespace (`/containers/applications`, matched on `durable_objects.namespace_id`). Each answers an opaque id, never a name, and a company with none, or with more than one, is a `LabError`.
#
# THE ALLOWLIST FROM ONE VANTAGE POINT. This machine is the only place a request comes from, so the proof never asks for a request from another address: it lists this machine for the listed case and lists only `proof.FOREIGN_IP` (TEST-NET-1) for the foreign cases, which puts this machine off the list. `egress_ips()` is this machine's public address per family as Cloudflare sees it (`https://1.1.1.1/cdn-cgi/trace` and its IPv6 twin, through `ops.bench_access.detect_public_ips`), so whichever family a request to the company host takes, its address is on a list that names this machine.
#
# `set_allowlist(company, ips)` writes the control row's `scope.allow_ips` (box C2's `lifecycle.update`), regenerates the company's two configs with `ALLOW_IPS` (onboarding's `configs` step, against the company's existing `account-<name>` D1, never creating one), redeploys both Workers (onboarding's `deploy` step) and waits `ALLOWLIST_SETTLE_S` for the new version to serve. An empty list clears it. Any failure puts the previous `scope.allow_ips` back and deploys that list again, so the control row and the Workers agree; when either of those two repairs fails too, the error carries a note saying so. `request_from(company, method=, path=)` sends one request from this machine to the company's account host and answers the status; a 403 whose body is not the allowlist's own refusal (workers/proxy/src/ip-allowlist.ts) is a `LabError`, so a WAF or a token refusal never reads as the allowlist blocking.
#
# NOT BUILT HERE. `console_command` runs a machine command through the company's proxy, which needs the company's config store and an executor CEK grant; it raises `LabError("not built yet: V7 ...")` naming that, and `proof proxy` records it broken and still checks the allowlist.


EXECUTOR_CLASS = "OrgExecutor"
ALLOWLIST_STEPS = ("configs", "deploy")
BODY_START = 80
ALLOWLIST_SETTLE_S = 30.0
# workers/proxy/src/ip-allowlist.ts `allowlistRefusal`, the body of its 403.
ALLOWLIST_REFUSAL = "This address is not on the allowlist."


def _proxy_worker(company: str, companies: Companies) -> str:
    return "proxy-%s" % company_row(company, companies=companies)["name"]


def durable_object(
    company: str,
    *,
    listing: Listing = cf_list,
    companies: Companies = all_companies,
) -> str:
    script = _proxy_worker(company, companies)
    found = [
        str(n.get("id", ""))
        for n in listing(account_path("/workers/durable_objects/namespaces"))
        if isinstance(n, dict) and n.get("script") == script and n.get("class") == EXECUTOR_CLASS
    ]
    if len(found) != 1 or not found[0]:
        raise proof.LabError(
            "company %s has %d %s namespaces, not 1" % (company, len(found), EXECUTOR_CLASS)
        )
    return found[0]


def container_app(
    company: str,
    *,
    listing: Listing = cf_list,
    api: Api = cf_get,
    companies: Companies = all_companies,
) -> str:
    namespace = durable_object(company, listing=listing, companies=companies)
    apps = api(account_path("/containers/applications")) or []
    found = [
        str(a.get("id", ""))
        for a in apps
        if isinstance(a, dict) and (a.get("durable_objects") or {}).get("namespace_id") == namespace
    ]
    if len(found) != 1 or not found[0]:
        raise proof.LabError(
            "company %s has %d container applications, not 1" % (company, len(found))
        )
    return found[0]


def console_command(company: str) -> proof.Answer:
    raise proof.LabError(
        "not built yet: V7 (a console command for company %s runs a machine command through its proxy, "
        "which needs the company's config store and an executor CEK grant; nothing was run)"
        % company
    )


AllowUpdate = Callable[[str, Sequence[str]], None]
D1Ids = Callable[[], dict[str, str]]


def egress_ips(*, fetch: Callable[[str], str] | None = None) -> list[str]:
    try:
        return bench_access.detect_public_ips(fetch)
    except bench_access.AccessError as exc:
        raise proof.LabError(str(exc)) from None


def _update_scope(name: str, ips: Sequence[str]) -> None:
    try:
        lifecycle.update(cli.lifecycle_context(lifecycle, bench=BENCH), name, allow_ips=list(ips))
    except lifecycle.LifecycleError as exc:
        raise proof.LabError(str(exc)) from None


def _d1_ids() -> dict[str, str]:
    try:
        return control_db.database_ids(control_db.run_wrangler)
    except control_db.ControlDbError as exc:
        raise proof.LabError(str(exc)) from None


SCOPE_IPS_SQL = "SELECT allow_ips FROM scope WHERE company_id = ?"


def _scope_ips(rows: list[dict], company: str) -> list[str]:
    """The control row's `scope.allow_ips` (a JSON list, or NULL for none)."""
    if len(rows) != 1:
        raise proof.LabError("company %s has %d scope rows, not 1" % (company, len(rows)))
    raw = rows[0].get("allow_ips")
    if not raw:
        return []
    try:
        ips = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        ips = None
    if not isinstance(ips, list):
        raise proof.LabError("company %s: its scope.allow_ips is not a JSON list" % company)
    return [str(i) for i in ips]


def set_allowlist(
    company: str,
    ips: Sequence[str],
    *,
    companies: Companies = all_companies,
    query: Query = d1_query,
    update: AllowUpdate = _update_scope,
    d1_ids: D1Ids = _d1_ids,
    actions: dict[str, onboarding.Action] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    row = company_row(company, companies=companies)
    name, region = str(row["name"]), str(row.get("region", ""))
    database = "account-%s" % name
    uuid = d1_ids().get(database, "")
    if not uuid:
        raise proof.LabError("company %s has no account D1 to configure against" % company)
    previous = _scope_ips(
        query(registry.control_database(region, BENCH), SCOPE_IPS_SQL, [company]), company
    )

    def apply(wanted: Sequence[str]) -> None:
        # `configs` and `deploy` read the name, region, allowlist and bench flag only (onboarding.py `write_configs`,
        # `deploy_both`); `owner` and `storage_gb` feed the audit, subscription and lookup steps, which are not run here.
        req = onboarding.Request(
            name=name, region=region, owner="", storage_gb=0, allow_ips=tuple(wanted), bench=BENCH
        )
        ctx = onboarding.Context(
            plan=onboarding.plan_for(req, company),
            query=control_db.transport(),
            details={"d1": uuid},
            now=onboarding.utc_now(),
        )
        steps = actions if actions is not None else onboarding.live_actions()
        for step in ALLOWLIST_STEPS:
            try:
                steps[step](ctx)
            except onboarding.OnboardingError as exc:
                raise proof.LabError(str(exc)) from None

    update(name, ips)
    try:
        apply(ips)
        sleep(ALLOWLIST_SETTLE_S)
    except BaseException as exc:  # put the row back whatever failed, then re-raise it
        failures: list[str] = []
        try:
            update(name, previous)
        except ROLLBACK_FAILURES as back:
            failures.append(
                "putting scope.allow_ips of company %s back to %s failed: %s"
                % (company, previous, back)
            )
        else:
            # A step that already published a Worker with the new list left it serving that list, so the
            # previous one is deployed again: the row and the Workers agree again, or the error says they do not.
            try:
                apply(previous)
            except ROLLBACK_FAILURES as back:
                failures.append(
                    "redeploying the previous list %s for company %s failed (its Workers may still serve the "
                    "new list): %s" % (previous, company, back)
                )
        if failures:
            exc.add_note("; and ".join(failures))
        raise


def request_from(
    company: str,
    *,
    method: str,
    path: str,
    call: Call = http_call,
    companies: Companies = all_companies,
) -> int:
    body = b"{}" if method == "POST" else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    answer = call(method, "https://%s%s" % (_host(company, companies), path), headers, body)
    if answer.status == proof.HTTP_FORBIDDEN and answer.json().get("error") != ALLOWLIST_REFUSAL:
        start = " ".join(answer.body.decode("utf-8", "replace").split())[:BODY_START]
        raise proof.LabError(
            "%s %s answered a 403 that is not the allowlist's refusal (body starts: %r)"
            % (method, path, start)
        )
    return answer.status


# ==== box V8: deploy records, usage, the image rebuild and the limits (`proof cost`)
#
# The `enterprise proof cost` readers (agent/plans/PLAN-enterprise-isolation.md, box V8). SEAMS binds them by name.
#
# `deploy_records(bench)` reads every company deploy record from the region control databases: the `audit` rows of action `deploy-record` that `deploy_record after --sink control` writes, each carrying the whole record. A row becomes `{company, version, duration_s}`, the duration being the record's `recorded_at` less its `taken_at` (the `before` stamp the record keeps); a record missing either stamp has no duration, which the proof names as broken rather than guessing one.
#
# `usage_rows(bench)` reads the Workers dataset `cf_usage_report` reads (`workersInvocationsAdaptive` over the billing month, through `cf_usage_report.graphql`) and keeps each company Worker (`account-<name>`, `proxy-<name>`) as `{company, worker, requests, cpu_ms}`, the company given by its opaque id. A shared Worker has no row.
#
# `image_rebuild_seconds()` times a cold `docker build --no-cache` of the executor image (`workers/proxy/Dockerfile`, the image `console_executor --enable` ships), the question the plan's *Not verified* leaves open; a build that fails is a `LabError`, never a time.
#
# `read_limits()` re-reads the two figures *Limits* took from a summarizing tool, from Cloudflare's own Workers limits page (its markdown form): the last column of "Number of Workers" (Workers Paid; Free is the column before it) and of "Routes per zone" (the routes table has one Value column). A row that cannot be found, or whose last column holds no figure ("No limit" is how the page writes an unlimited Paid cell), is a `LabError`, so a page that moved never reads as a changed limit and a Paid cell is never read from the Free column.


RECORDS_SQL = "SELECT company_id, detail FROM audit WHERE action = ? ORDER BY id"
RECORD_ACTION = "deploy-record"
LIMITS_URL = "https://developers.cloudflare.com/workers/platform/limits/index.md"
# proof.PLAN_LIMITS key -> the row label on the limits page.
LIMIT_ROWS: dict[str, str] = {
    "workers_scripts": "Number of Workers",
    "routes_per_zone": "Routes per zone",
}
EXECUTOR_REL = ("workers", "proxy")
# A footnote mark beside a figure (`500[^1]`, `500<sup>1</sup>`) is not part of it.
MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
FOOTNOTE = re.compile(r"\[\^?[0-9]+\]|<sup>.*?</sup>")


def _at(text: object) -> datetime.datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def deploy_records(*, bench: bool, query: Query = d1_query) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for _region, database in sorted(registry.databases(bench).items()):
        for row in query(database, RECORDS_SQL, [RECORD_ACTION]):
            try:
                record = json.loads(row.get("detail") or "{}")
            except ValueError:
                record = {}
            start, end = _at(record.get("taken_at")), _at(record.get("recorded_at"))
            duration = (end - start).total_seconds() if start and end else None
            out.append(
                {
                    "company": str(row.get("company_id") or ""),
                    "version": str(record.get("version") or ""),
                    "duration_s": duration,
                }
            )
    return out


Workers = Callable[[], list[dict]]


def _workers_dataset() -> list[dict]:
    env = dict(os.environ)
    account = env.get("CLOUDFLARE_ACCOUNT_ID") or ov.DEFAULT_ACCOUNT_ID
    now = datetime.datetime.now(datetime.UTC)
    try:
        headers = ov.cf_headers(env)
        return cf_usage_report.graphql(ov.real_transport, headers, account, "workers", now)
    except (cf_usage_report.ReportError, ov.VolumeError) as exc:
        raise proof.LabError(str(exc)) from None


def usage_rows(
    *,
    bench: bool,
    workers: Workers = _workers_dataset,
    companies: Companies = all_companies,
) -> list[dict[str, object]]:
    by_worker: dict[str, str] = {}
    for row in live_companies(bench, companies=companies):
        for prefix in ("account-", "proxy-"):
            by_worker[prefix + str(row["name"])] = str(row["id"])
    rows: list[dict[str, object]] = []
    for group in workers():
        script = str((group.get("dimensions") or {}).get("scriptName") or "")
        if script not in by_worker:
            continue
        s = group.get("sum") or {}
        rows.append(
            {
                "company": by_worker[script],
                "worker": "account" if script.startswith("account-") else "proxy",
                "requests": float(s.get("requests") or 0),
                "cpu_ms": float(s.get("cpuTimeUs") or 0) / 1000.0,
            }
        )
    return rows


def image_rebuild_seconds(
    *,
    run: Runner = run_process,
    clock: Callable[[], float] = time.monotonic,
) -> float:
    tag = "rediacc-proof-executor:%s" % uuid.uuid4().hex[:12]
    argv: Sequence[str] = (
        "docker",
        "build",
        "--no-cache",
        "-q",
        "-t",
        tag,
        "-f",
        "Dockerfile",
        ".",
    )
    start = clock()
    done = run(argv, root().joinpath(*EXECUTOR_REL), None)
    took = clock() - start
    run(("docker", "image", "rm", "-f", tag), None, None)
    if done.rc != 0:
        raise proof.LabError("docker build of the executor image exited %d" % done.rc)
    return took


def _row_figure(text: str, label: str) -> int:
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        head = re.sub(r"[*_`]", "", MD_LINK.sub(r"\1", cells[0])).strip().lower()
        if len(cells) >= 2 and head == label.lower():
            # The last column only: Workers Paid in the plan table, Value in the single-column routes table. A Paid cell with no figure ("No limit") must never fall back to the Free column beside it.
            figure = re.sub(r"[^0-9]", "", FOOTNOTE.sub("", cells[-1]))
            if not figure:
                raise proof.LabError(
                    "the Workers limits page's %r row reads %r in its last column, not a figure"
                    % (label, cells[-1])
                )
            return int(figure)
    raise proof.LabError("the Workers limits page has no %r row with a figure" % label)


def read_limits(*, fetch: Fetch = http_get) -> dict[str, int]:
    status, text = fetch(LIMITS_URL)
    if status != 200:
        raise proof.LabError("GET %s answered %d" % (LIMITS_URL, status))
    return {key: _row_figure(text, label) for key, label in LIMIT_ROWS.items()}


# ==== box V9: renet on a fleet machine (`proof renet`)
#
# The `enterprise proof renet` readers and drivers (agent/plans/PLAN-enterprise-isolation.md, box V9). SEAMS binds them by name.
#
# A RELEASED CLI, NEVER `./rdc.sh`. A development build holds the machine's renet on every mutating verb (packages/cli/src/services/renet/renet-upload-decision.ts `renetHold`), so a checkout's CLI cannot show a mutating verb moving renet. Every call runs the released `rdc` that `ENTERPRISE_PROOF_RDC` names (the edge install), under the rdc config `ENTERPRISE_PROOF_CONFIG` (default `eu-bench`), with `REDIACC_NO_PROVISION` set to the empty string, overriding an inherited `1`. `renetHold` reads only `"1"` (hold) and `"0"` (lift the development default), so for a release build empty is the same as unset: no hold. It is not `0`, so a development build named by mistake keeps its hold, never moves renet, and breaks the `a mutating verb moves renet` claim instead of uploading a checkout's renet. The fleet VM is `ENTERPRISE_PROOF_MACHINE` and the repository the mutating verb runs on is `ENTERPRISE_PROOF_REPO` (a ref on that machine). An unset variable is a `LabError` naming it, before anything runs.
#
# THE VERBS. Read-only: `rdc machine status <machine>`. Mutating: `rdc repo up <repo>`, the ordinary verb a machine takes its new renet on. `renet_version` runs `renet version` on the machine through `rdc term connect <machine> -c`, and `released_renet` is the version edge runs (`cli/edge/latest.json`), which the released renet carries.
#
# THE EXECUTOR DRIVER. `executor_upload(machine)` sends the mutating verb through a company's proxy: `REDIACC_TOKEN=<proxy token> rdc --proxy https://<company>-proxy.<domain> repo up <repo>` (packages/cli/src/cli.ts `--proxy`), the proxy token minted by box V6 for the bench company `ENTERPRISE_PROOF_COMPANY` names. The executor serves the request (packages/cli/src/services/renet/renet-upload-decision.ts `inExecutor`), so it must leave the machine's renet as it was. The verb must succeed (a non-zero exit is a `LabError`, never a refusal: a verb that failed before reaching the machine proves nothing); the answer is refused, naming the version, when renet did not move, and admitted when it did. The company's executor resolves the repository from the company's config store, so the live run needs `ENTERPRISE_PROOF_REPO` in that store.
#
# THE SPREAD-RELEASE DRIVER. `renew_with(machine, renet=, worker=)` puts one renet on the machine, one version of the company's account Worker in front of it, and renews: `previous` renet is the one the released rdc `ENTERPRISE_PROOF_RDC_PREVIOUS` names uploads on `repo up`, `new` the one `ENTERPRISE_PROOF_RDC` uploads (checked against what edge runs). The Worker versions are the 100% versions of `wrangler deployments list --json --name account-<name>`, newest first (`new`, then the next distinct one, `previous`); `previous` is put in front with `wrangler rollback <id> --name account-<name> --yes`, and the newest is rolled back in again afterwards whatever happened. The renewal is `sudo renet license renew --force --output json` on the machine (private/renet/cmd/renet/license_renew.go): admitted when every result is `renewed`, refused naming the first other outcome and its code, and a `LabError` when nothing is installed or the lock was busy, so a renewal that never ran is never a refusal. The machine's repositories must carry licences of that company for the renewal to reach its Worker.


RDC_ENV = "ENTERPRISE_PROOF_RDC"
PREVIOUS_RDC_ENV = "ENTERPRISE_PROOF_RDC_PREVIOUS"
CONFIG_ENV = "ENTERPRISE_PROOF_CONFIG"
MACHINE_ENV = "ENTERPRISE_PROOF_MACHINE"
REPO_ENV = "ENTERPRISE_PROOF_REPO"
COMPANY_ENV = "ENTERPRISE_PROOF_COMPANY"
DEFAULT_CONFIG = "eu-bench"
HOLD_ENV = "REDIACC_NO_PROVISION"
PROXY_BEARER_ENV = "REDIACC_TOKEN"
VERSION_RE = re.compile(r"renet(?:\s+version)?\s+v?([0-9]+\.[0-9]+\.[0-9]+[0-9A-Za-z.+-]*)")
RENEW_COMMAND = "sudo renet license renew --force --output json"
RENEWED = "renewed"
ROLLBACK_MESSAGE = "enterprise proof renet: spread release"
SPREAD = ("previous", "new")

Env = Callable[[str], str]


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise proof.LabError(
            "%s is not set (see box V9's readers in rediacc_ci.enterprise.lab)" % name
        )
    return value


def _rdc(
    run: Runner,
    env: Env,
    *args: str,
    binary_env: str = RDC_ENV,
    extra: dict[str, str] | None = None,
) -> Proc:
    binary = env(binary_env)
    if binary.endswith("rdc.sh"):
        raise proof.LabError(
            "%s names the checkout's rdc.sh, which holds renet; name a released rdc" % binary_env
        )
    config = os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG
    # Empty, not removed and not "0": see the section header (renetHold reads only "1" and "0").
    return run((binary, "--config", config, *args), None, {HOLD_ENV: "", **(extra or {})})


def fleet_machine(*, env: Env = _env) -> str:
    return env(MACHINE_ENV)


def renet_version(machine: str, *, run: Runner = run_process, env: Env = _env) -> str:
    done = _rdc(run, env, "term", "connect", machine, "-c", "renet version")
    if done.rc != 0:
        raise proof.LabError("renet version on the fleet machine exited %d" % done.rc)
    found = VERSION_RE.search(done.stdout)
    if not found:
        raise proof.LabError("renet version printed no version")
    return found.group(1)


def released_renet(*, edge: Callable[[], str] = edge_version) -> str:
    return edge()


def run_verb(machine: str, *, mutating: bool, run: Runner = run_process, env: Env = _env) -> int:
    argv: Sequence[str] = (
        ("repo", "up", env(REPO_ENV)) if mutating else ("machine", "status", machine)
    )
    return _rdc(run, env, *argv).rc


Driver = Callable[[str], proof.Answer]
Versions = Callable[[str], str]


def live_executor_upload(
    machine: str,
    *,
    run: Runner = run_process,
    env: Env = _env,
    token: Callable[[str], str] | None = None,
    version: Versions | None = None,
    companies: Companies = all_companies,
) -> proof.Answer:
    company = env(COMPANY_ENV)
    proxy_host = names.hosts(
        str(company_row(company, companies=companies)["name"]), PRODUCT_DOMAIN
    )[1]
    read = version or (lambda m: renet_version(m, run=run, env=env))
    minted = (token or (lambda c: mint(c, "proxy-token")))(company)
    before = read(machine)
    done = _rdc(
        run,
        env,
        "--proxy",
        "https://%s" % proxy_host,
        "repo",
        "up",
        env(REPO_ENV),
        extra={PROXY_BEARER_ENV: minted},
    )
    if done.rc != 0:
        raise proof.LabError("the proxied repo up exited %d; nothing was proven" % done.rc)
    after = read(machine)
    if after == before:
        return proof.Answer(False, "the executor left renet at %s" % before)
    return proof.Answer(True)


def executor_upload(machine: str, *, driver: Driver | None = None) -> proof.Answer:
    return (driver or live_executor_upload)(machine)


def _json_value(text: str, open_ch: str) -> object:
    """The JSON value that opens with `open_ch` and runs to the end of `text` (a banner may come before it and carry brackets of its own); failing that, the longest complete one."""
    decoder = json.JSONDecoder()
    best: tuple[int, object] | None = None
    start = text.find(open_ch)
    while start >= 0:
        try:
            value, end = decoder.raw_decode(text, start)
        except ValueError:
            value, end = None, -1
        if end >= 0:
            if not text[end:].strip():
                return value
            if best is None or end - start > best[0]:
                best = (end - start, value)
            # A value nested inside this one is never the longest, so the scan resumes after it:
            # one pass over the text instead of a decode from every bracket (review e2231d81.3).
            start = text.find(open_ch, end)
            continue
        start = text.find(open_ch, start + 1)
    return best[1] if best else None


def worker_versions(worker: str, *, run: Runner = run_process) -> list[str]:
    """The 100% version of each deployment of `worker`, newest first, each version once."""
    done = run([*wrangler.ARGV, "deployments", "list", "--json", "--name", worker], None, None)
    if done.rc != 0:
        raise proof.LabError("wrangler deployments list exited %d" % done.rc)
    data = _json_value(done.stdout, "[")
    if not isinstance(data, list):
        raise proof.LabError("wrangler deployments list printed no JSON list")
    rows = sorted(
        (d for d in data if isinstance(d, dict)),
        key=lambda d: str(d.get("created_on", "")),
        reverse=True,
    )
    out: list[str] = []
    for row in rows:
        for v in row.get("versions") or []:
            vid = str(v.get("version_id") or "") if isinstance(v, dict) else ""
            if vid and v.get("percentage") in (100, 100.0) and vid not in out:
                out.append(vid)
    return out


def put_version(worker: str, version_id: str, *, run: Runner = run_process) -> None:
    argv = [
        *wrangler.ARGV, "rollback", version_id, "--message", ROLLBACK_MESSAGE, "--yes",
        "--name", worker,
    ]  # fmt: skip
    done = run(argv, None, None)
    if done.rc != 0:
        raise proof.LabError("wrangler rollback exited %d" % done.rc)


def renew_on(machine: str, *, run: Runner = run_process, env: Env = _env) -> proof.Answer:
    done = _rdc(run, env, "term", "connect", machine, "-c", RENEW_COMMAND)
    if done.rc != 0:
        raise proof.LabError("renet license renew on the fleet machine exited %d" % done.rc)
    doc = _json_value(done.stdout, "{")
    if not isinstance(doc, dict):
        raise proof.LabError("renet license renew printed no JSON object")
    if doc.get("lockBusy"):
        raise proof.LabError("another renewal held the lock; nothing was renewed")
    results = [r for r in doc.get("results") or [] if isinstance(r, dict)]
    if not results:
        raise proof.LabError("renet license renew found no installed licence")
    for r in results:
        if r.get("outcome") != RENEWED:
            code = str(r.get("code") or "")
            return proof.Answer(
                False, "%s%s" % (r.get("outcome"), " code=%s" % code if code else "")
            )
    return proof.Answer(True)


def live_spread_renew(
    machine: str,
    renet: str,
    worker: str,
    *,
    run: Runner = run_process,
    env: Env = _env,
    version: Versions | None = None,
    released: Callable[[], str] = released_renet,
    companies: Companies = all_companies,
) -> proof.Answer:
    if renet not in SPREAD or worker not in SPREAD:
        raise proof.LabError("a spread release is previous or new, not %s/%s" % (renet, worker))
    name = str(company_row(env(COMPANY_ENV), companies=companies)["name"])
    script = "account-%s" % name
    versions = worker_versions(script, run=run)
    if len(versions) < 2:
        raise proof.LabError("the company Worker has %d deployed version(s), not 2" % len(versions))
    newest, previous = versions[0], versions[1]
    binary_env = PREVIOUS_RDC_ENV if renet == "previous" else RDC_ENV
    placed = _rdc(run, env, "repo", "up", env(REPO_ENV), binary_env=binary_env)
    if placed.rc != 0:
        raise proof.LabError("repo up with the %s rdc exited %d" % (renet, placed.rc))
    runs = (version or (lambda m: renet_version(m, run=run, env=env)))(machine)
    current = released()
    if (runs == current) != (renet == "new"):
        raise proof.LabError(
            "the machine runs renet %s, not the %s one (edge runs %s)" % (runs, renet, current)
        )
    if worker == "new":
        return renew_on(machine, run=run, env=env)
    put_version(script, previous, run=run)
    try:
        answer = renew_on(machine, run=run, env=env)
    except BaseException as exc:
        try:
            put_version(script, newest, run=run)
        except ROLLBACK_FAILURES as back:  # not only LabError (review e2231d81.1)
            exc.add_note(_left_behind(script, newest, back))
        raise
    try:
        put_version(script, newest, run=run)
    except ROLLBACK_FAILURES as back:  # the same tuple as the failure path above
        raise proof.LabError(
            "the renewal answered ok=%s%s; %s"
            % (
                answer.ok,
                " (%s)" % answer.error if answer.error else "",
                _left_behind(script, newest, back),
            )
        ) from back
    return answer


# What a rollback can raise: the lab's own refusal, or the runner failing underneath it (a
# missing binary, a broken pipe, a subprocess timeout, an undecodable output, a runner that gives up).
ROLLBACK_FAILURES = (
    proof.LabError,
    OSError,
    subprocess.SubprocessError,
    ValueError,
    RuntimeError,
)


def _left_behind(script: str, version: str, back: BaseException) -> str:
    return "rolling Worker %s back to version %s failed (%s): restore it by hand" % (
        script,
        version,
        back,
    )


def renew_with(
    machine: str,
    *,
    renet: str,
    worker: str,
    driver: Callable[[str, str, str], proof.Answer] | None = None,
) -> proof.Answer:
    return (driver or live_spread_renew)(machine, renet, worker)


# ==== box V10: the GitHub dispatch and its run (`proof github`)
#
# The `enterprise proof github` readers (agent/plans/PLAN-enterprise-isolation.md, box V10): dispatch `cd-enterprise-release.yml` for a fake company and read back every surface of the run. SEAMS binds them by name.
#
# `dispatch_release(company)` refuses before any call unless the workflow file declares a `bench` input, which the release step turns into `--bench`: the fake companies live in the bench control databases, and a dispatch without it would read production, where the opaque id names nothing. It then runs `gh workflow run cd-enterprise-release.yml --ref <ref>` with `version` (what edge runs), the opaque `company` id, `bench=true` and `dry_run=false`, finds the `workflow_dispatch` run created after the dispatch, and waits for it to complete (at most `RUN_TIMEOUT_S`). The ref is the repository's default branch unless `ENTERPRISE_PROOF_REF` names another, because a dispatch needs the workflow file on the ref (*Not verified*).
#
# `run_surfaces(run_id)` reads the four surfaces `proof.GITHUB_SURFACES` names, as text: `logs` (`gh run view --log`), `jobs-api` (`/actions/runs/<id>/jobs`), `run-api` (`/actions/runs/<id>`) and `step-summary` (each job's check run `output.summary` and `output.text`, where GitHub serves `$GITHUB_STEP_SUMMARY`; the check run is the one the job's `check_run_url` names, never the job's own `id`). A read that fails is a `LabError`, so a surface is never compared as empty.


WORKFLOW = "cd-enterprise-release.yml"
WORKFLOW_REL = (".github", "workflows", WORKFLOW)
REF_ENV = "ENTERPRISE_PROOF_REF"
RUN_TIMEOUT_S = 2 * 60 * 60
POLL_S = 30
FIND_TRIES = 20


def _gh(run: Runner, *args: str) -> str:
    done = run(("gh", *args), None, None)
    if done.rc != 0:
        raise proof.LabError("gh %s exited %d" % (args[0] if args else "", done.rc))
    return done.stdout


def _json(text: str, what: str) -> object:
    try:
        return json.loads(text)
    except ValueError:
        raise proof.LabError("%s answered no JSON" % what) from None


def declares_bench_input(text: str) -> bool:
    """Whether the workflow's `workflow_dispatch.inputs` names `bench` (a plain scan: the inputs block is indented under `inputs:`)."""
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "inputs:":
            inside = True
            continue
        if inside:
            if line and not line.startswith(" " * 6) and stripped:
                inside = False
            elif line.startswith(" " * 6) and not line.startswith(" " * 7) and stripped == "bench:":
                return True
    return False


def _default_ref(run: Runner) -> str:
    doc = _json(_gh(run, "repo", "view", "--json", "defaultBranchRef"), "gh repo view")
    ref = (doc.get("defaultBranchRef") or {}).get("name") if isinstance(doc, dict) else None
    if not ref:
        raise proof.LabError("gh repo view named no default branch")
    return str(ref)


def dispatch_release(
    company: str,
    *,
    run: Runner = run_process,
    version: Callable[[], str] = edge_version,
    workflow_text: Callable[[], str] | None = None,
    now: Callable[[], datetime.datetime] = lambda: datetime.datetime.now(datetime.UTC),
    sleep: Callable[[float], None] = time.sleep,
    ref: str | None = None,
) -> str:
    if not proof.OPAQUE_ID.match(company):
        raise proof.LabError("the dispatch input must be an opaque c<hex> id")
    text = (workflow_text or (lambda: root().joinpath(*WORKFLOW_REL).read_text(encoding="utf-8")))()
    if not declares_bench_input(text):
        raise proof.LabError(
            "%s declares no bench input: a dispatch for a fake company would read production, so none was sent"
            % WORKFLOW
        )
    branch = ref or os.environ.get(REF_ENV) or _default_ref(run)
    started = now()
    _gh(
        run, "workflow", "run", WORKFLOW, "--ref", branch,
        "-f", "version=%s" % version(), "-f", "company=%s" % company,
        "-f", "bench=true", "-f", "dry_run=false",
    )  # fmt: skip
    run_id = ""
    for _ in range(FIND_TRIES):
        listed = _json(
            _gh(
                run, "run", "list", "--workflow", WORKFLOW, "--event", "workflow_dispatch",
                "--limit", "10", "--json", "databaseId,createdAt",
            ),
            "gh run list",
        )  # fmt: skip
        fresh = [
            r for r in listed if isinstance(r, dict)
            and (_at(r.get("createdAt")) or started) >= started - datetime.timedelta(seconds=5)
        ] if isinstance(listed, list) else []  # fmt: skip
        if fresh:
            run_id = str(min(fresh, key=lambda r: str(r.get("createdAt")))["databaseId"])
            break
        sleep(POLL_S / 3)
    if not run_id:
        raise proof.LabError("no %s run appeared after the dispatch" % WORKFLOW)
    waited = 0.0
    while True:
        doc = _json(_gh(run, "run", "view", run_id, "--json", "status"), "gh run view")
        if isinstance(doc, dict) and doc.get("status") == "completed":
            return run_id
        if waited >= RUN_TIMEOUT_S:
            raise proof.LabError("run %s did not complete in %d s" % (run_id, RUN_TIMEOUT_S))
        sleep(POLL_S)
        waited += POLL_S


CHECK_RUN_URL = re.compile(r"/check-runs/([0-9]+)$")


def _check_run_id(job: object) -> str:
    """The check run of an Actions job, from its `check_run_url`: the job's own `id` is a different number, and GET check-runs/<job id> reads another run or nothing."""
    url = str(job.get("check_run_url") or "") if isinstance(job, dict) else ""
    found = CHECK_RUN_URL.search(url)
    if not found:
        raise proof.LabError("a job of the run carries no check_run_url")
    return found.group(1)


def run_surfaces(run_id: str, *, run: Runner = run_process) -> dict[str, str]:
    if not run_id.isdigit():
        raise proof.LabError("%r is not a run id" % run_id)
    logs = _gh(run, "run", "view", run_id, "--log")
    jobs_text = _gh(run, "api", "repos/{owner}/{repo}/actions/runs/%s/jobs" % run_id)
    run_text = _gh(run, "api", "repos/{owner}/{repo}/actions/runs/%s" % run_id)
    jobs = _json(jobs_text, "the jobs API")
    summaries: list[str] = []
    for job in (jobs.get("jobs") or []) if isinstance(jobs, dict) else []:
        check = _json(
            _gh(run, "api", "repos/{owner}/{repo}/check-runs/%s" % _check_run_id(job)),
            "the check-runs API",
        )
        output = (check.get("output") or {}) if isinstance(check, dict) else {}
        summaries.extend(str(output.get(k) or "") for k in ("title", "summary", "text"))
    return {
        "logs": logs,
        "jobs-api": jobs_text,
        "run-api": run_text,
        "step-summary": "\n".join(s for s in summaries if s),
    }


# ==== box V11: what a removed company leaves (`proof remove`)
#
# The `enterprise proof remove` reader (agent/plans/PLAN-enterprise-isolation.md, box V11): what a company still holds on Cloudflare and in its control row. SEAMS binds it by name.
#
# `leftovers(company)` resolves the opaque id through the bench control databases (a removed row included) and lists, by KIND only, each piece `enterprise remove --delete-data` deletes that is still there: the account and proxy Workers (`account-<name>`, `proxy-<name>`), the D1 database `account-<name>`, the configs and backups buckets (listed under the region's R2 jurisdiction header, since a bucket in a jurisdiction is invisible to a plain listing), the bucket-scoped backup token (`enterprise-<id>-backups`, a user token), and a control row whose state is not `removed`. Kinds and never names, because the proof prints the list on a broken claim and a company's name is its Workers' and buckets' name. An empty list means nothing is left; a read that fails is a `LabError`, never an empty list.


def _names(rows: object, key: str) -> set[str]:
    return (
        {str(r.get(key, "")) for r in rows if isinstance(r, dict)}
        if isinstance(rows, list)
        else set()
    )


def leftovers(
    company: str,
    *,
    companies: Companies = all_companies,
    listing: Listing = cf_list,
    buckets: Callable[[str | None], set[str]] = r2_bucket_names,
) -> list[str]:
    row = company_row(company, companies=companies)
    name = str(row["name"])
    left: list[str] = []
    if row.get("state") != "removed":
        left.append("control row (state %s)" % row.get("state"))
    scripts = _names(listing(account_path("/workers/scripts")), "id")
    for kind, worker in (
        ("account Worker", "account-%s" % name),
        ("proxy Worker", "proxy-%s" % name),
    ):
        if worker in scripts:
            left.append(kind)
    d1 = "account-%s" % name
    found = listing(account_path("/d1/database?name=%s" % urllib.parse.quote(d1)))
    if d1 in _names(found, "name"):
        left.append("D1 database")
    held = buckets(region_jurisdiction(str(row.get("region", ""))))
    left.extend("%s bucket" % k for k in ("configs", "backups") if "%s-%s" % (k, name) in held)
    target = _target(row)
    tokens = _names(listing("/user/tokens"), "name")
    if lifecycle_adapters.backup_token_name(target) in tokens:
        left.append("backup token")
    return left


def _target(row: dict) -> lifecycle.Target:
    try:
        return lifecycle.Target(
            id=str(row["id"]),
            name=str(row["name"]),
            region=str(row.get("region", "")),
            state=str(row.get("state", "")),
            unlisted=bool(row.get("unlisted")),
        )
    except (KeyError, TypeError) as exc:
        raise proof.LabError("company %s: an unreadable control row" % row.get("id")) from exc
