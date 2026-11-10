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
from collections.abc import Callable, Sequence
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
)
from rediacc_ci.housekeeping import cf_leftovers
from rediacc_ci.ops import cf_usage_report, enterprise_lookup
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
# `present(company, kind, artifact)` sends one artifact to the company's own host and maps the answer: 2xx is admitted, 401 or 403 is refused with the status, anything else is a `LabError` (a 5xx or a 404 says the probe is wrong, not that the artifact was refused). Each kind has one READ-ONLY probe, so presenting never changes what it presents: a `session` is the `access_token` cookie on `GET /account/api/v1/portal/me` (private/account/src/middleware/session.ts). The other kinds have no read-only probe on the account Worker: the config token's routes rotate the token they accept (`X-Config-Token`, private/account/src/routes/configs.ts), the API token's are writes, and the E2E envelope and the proxy token are presented through the proxy. Their presenters raise `LabError("not built yet: V6 ...")` naming the missing probe.
#
# `mint(company, kind)` needs a signed-in user of a fake company. The owner has no password and no TOTP the proof holds, and no sign-in driver is written here (the candidate is the magic link `POST /account/api/v1/auth/magic-link` sends, read back from the company's captured mail through `captured_mail`, with the captcha that route carries unverified on a bench company), so no minter exists: the default raises `LabError("not built yet: V6 ...")`, never an artifact, and `proof replay` and the token half of `proof proxy` stop there by name.


ME_PATH = "/account/api/v1/portal/me"
REFUSED = (401, 403)

# (url, headers) -> status.
Send = Callable[[str, dict[str, str]], int]
Minter = Callable[[str, str], str]


def _send(url: str, headers: dict[str, str]) -> int:
    try:
        req = https.build_request(url, headers=headers, method="GET")
        with https.urlopen(req, timeout=60) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        exc.close()
        return int(exc.code)
    except OSError as exc:
        raise proof.LabError("GET %s: %s" % (ME_PATH, type(exc).__name__)) from None


def _host(company: str, companies: Companies) -> str:
    return names.hosts(str(company_row(company, companies=companies)["name"]), PRODUCT_DOMAIN)[0]


def _no_minter(company: str, kind: str) -> str:
    raise proof.LabError(
        "not built yet: V6 (no minter for a %s of company %s: the fake owner holds no credential "
        "the proof can sign in with, and nothing was minted)" % (kind, company)
    )


def mint(company: str, kind: str, *, minter: Minter = _no_minter) -> str:
    return minter(company, kind)


def present(
    company: str,
    kind: str,
    artifact: str,
    *,
    send: Send = _send,
    companies: Companies = all_companies,
) -> proof.Answer:
    if kind != "session":
        raise proof.LabError("not built yet: V6 (no read-only probe presents a %s)" % kind)
    url = "https://%s%s" % (_host(company, companies), ME_PATH)
    status = send(url, {"Cookie": "access_token=%s" % artifact})
    if 200 <= status < 300:
        return proof.Answer(True)
    if status in REFUSED:
        return proof.Answer(False, "HTTP %d" % status)
    raise proof.LabError("the session probe answered HTTP %d" % status)


# ==== box V7: the proxy and executor (`proof proxy`)
#
# The `enterprise proof proxy` readers (agent/plans/PLAN-enterprise-isolation.md, box V7). SEAMS binds them by name; the proxy token's `mint` and `present` are box V6's.
#
# `durable_object(company)` is the id of the `OrgExecutor` Durable Object namespace whose script is the company's `proxy-<name>` (`/workers/durable_objects/namespaces`). `container_app(company)` is the id of the Containers application backed by that namespace (`/containers/applications`, matched on `durable_objects.namespace_id`). Each answers an opaque id, never a name, and a company with none, or with more than one, is a `LabError`.
#
# NOT BUILT HERE. `console_command` needs a minted proxy token (box V6). `set_allowlist` and `request_from` need a redeploy of one company with a changed `ALLOW_IPS` and a request from an address on the list and one off it; this host is one vantage point, and the proof asks for the listed case from `192.0.2.10` (TEST-NET-1), an address no request can come from. Each raises `LabError("not built yet: V7 ...")` naming that, so no allowlist claim can pass on a request that was never sent.


EXECUTOR_CLASS = "OrgExecutor"


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
        "not built yet: V7 (a console command for company %s needs V6's minted proxy token; nothing was run)"
        % company
    )


def set_allowlist(company: str, ips: Sequence[str]) -> None:
    raise proof.LabError(
        "not built yet: V7 (no allowlist driver: %d address(es) for company %s need a redeploy of its "
        "Workers, and nothing was changed)" % (len(ips), company)
    )


def request_from(company: str, *, foreign: bool, method: str, path: str) -> int:
    where = "an address off the list" if foreign else "an address on the list"
    raise proof.LabError(
        "not built yet: V7 (no vantage point sends %s %s to company %s from %s)"
        % (method, path, company, where)
    )


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
# `read_limits()` re-reads the two figures *Limits* took from a summarizing tool, from Cloudflare's own Workers limits page (its markdown form): the Workers Paid column of "Number of Workers" and of "Routes per zone". A row that cannot be found is a `LabError`, so a page that moved never reads as a changed limit.


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
            figures = [re.sub(r"[^0-9]", "", FOOTNOTE.sub("", c)) for c in cells[1:]]
            figures = [f for f in figures if f]
            if figures:
                return int(figures[-1])
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
# A RELEASED CLI, NEVER `./rdc.sh`. A development build holds the machine's renet on every mutating verb (packages/cli/src/services/renet/renet-upload-decision.ts `renetHold`), so a checkout's CLI cannot show a mutating verb moving renet. Every call runs the released `rdc` that `ENTERPRISE_PROOF_RDC` names (the edge install), under the rdc config `ENTERPRISE_PROOF_CONFIG` (default `eu-bench`), with `REDIACC_NO_PROVISION` removed from its environment. The fleet VM is `ENTERPRISE_PROOF_MACHINE` and the repository the mutating verb runs on is `ENTERPRISE_PROOF_REPO` (a ref on that machine). An unset variable is a `LabError` naming it, before anything runs.
#
# THE VERBS. Read-only: `rdc machine status <machine>`. Mutating: `rdc repo up <repo>`, the ordinary verb a machine takes its new renet on. `renet_version` runs `renet version` on the machine through `rdc term connect <machine> -c`, and `released_renet` is the version edge runs (`cli/edge/latest.json`), which the released renet carries.
#
# NOT BUILT HERE. `executor_upload` needs a mutating verb sent through a company's proxy with a minted proxy token (box V6's minter), and `renew_with` needs the previous and the new Worker deployed side by side for one company; neither driver exists, so both raise `LabError("not built yet: V9 ...")` through their seam, never an answer, so a refusal claim cannot pass on a missing driver.


RDC_ENV = "ENTERPRISE_PROOF_RDC"
CONFIG_ENV = "ENTERPRISE_PROOF_CONFIG"
MACHINE_ENV = "ENTERPRISE_PROOF_MACHINE"
REPO_ENV = "ENTERPRISE_PROOF_REPO"
DEFAULT_CONFIG = "eu-bench"
HOLD_ENV = "REDIACC_NO_PROVISION"
VERSION_RE = re.compile(r"renet(?:\s+version)?\s+v?([0-9]+\.[0-9]+\.[0-9]+[0-9A-Za-z.+-]*)")

Env = Callable[[str], str]


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    if not value:
        raise proof.LabError(
            "%s is not set (see box V9's readers in rediacc_ci.enterprise.lab)" % name
        )
    return value


def _rdc(run: Runner, env: Env, *args: str) -> Proc:
    binary = env(RDC_ENV)
    if binary.endswith("rdc.sh"):
        raise proof.LabError(
            "%s names the checkout's rdc.sh, which holds renet; name a released rdc" % RDC_ENV
        )
    config = os.environ.get(CONFIG_ENV) or DEFAULT_CONFIG
    # An empty value lifts the hold the same way an unset one does (renetHold reads only "1" and "0").
    return run((binary, "--config", config, *args), None, {HOLD_ENV: ""})


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


def _not_built(what: str) -> proof.Answer:
    raise proof.LabError("not built yet: V9 (%s; nothing was run)" % what)


Driver = Callable[[str], proof.Answer]


def executor_upload(machine: str, *, driver: Driver | None = None) -> proof.Answer:
    if driver is None:
        return _not_built(
            "no executor driver: a mutating verb through a company proxy needs V6's minted proxy token"
        )
    return driver(machine)


def renew_with(
    machine: str,
    *,
    renet: str,
    worker: str,
    driver: Callable[[str, str, str], proof.Answer] | None = None,
) -> proof.Answer:
    if driver is None:
        return _not_built(
            "no spread-release driver: renewing %s renet against the %s Worker needs both Worker versions deployed"
            % (renet, worker)
        )
    return driver(machine, renet, worker)


# ==== box V10: the GitHub dispatch and its run (`proof github`)
#
# The `enterprise proof github` readers (agent/plans/PLAN-enterprise-isolation.md, box V10): dispatch `cd-enterprise-release.yml` for a fake company and read back every surface of the run. SEAMS binds them by name.
#
# `dispatch_release(company)` refuses before any call unless the workflow file declares a `bench` input: the fake companies live in the bench control databases, and a dispatch without it reads production, where the opaque id names nothing. It then runs `gh workflow run cd-enterprise-release.yml --ref <ref>` with `version` (what edge runs), the opaque `company` id, `bench=true` and `dry_run=false`, finds the `workflow_dispatch` run created after the dispatch, and waits for it to complete (at most `RUN_TIMEOUT_S`). The ref is the repository's default branch unless `ENTERPRISE_PROOF_REF` names another, because a dispatch needs the workflow file on the ref (*Not verified*).
#
# `run_surfaces(run_id)` reads the four surfaces `proof.GITHUB_SURFACES` names, as text: `logs` (`gh run view --log`), `jobs-api` (`/actions/runs/<id>/jobs`), `run-api` (`/actions/runs/<id>`) and `step-summary` (each job's check run `output.summary` and `output.text`, where GitHub serves `$GITHUB_STEP_SUMMARY`). A read that fails is a `LabError`, so a surface is never compared as empty.


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

    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


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
            _gh(run, "api", "repos/{owner}/{repo}/check-runs/%s" % job.get("id")),
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
