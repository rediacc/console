"""`enterprise add`, resumable from the control database's `onboarding` table (agent/plans/PLAN-enterprise-isolation.md box C1, *Company lifecycle*).

THE STEPS, in order: `control-row` (the `companies` row in the company's own region), `d1` (create `account-<company>`), `configs` (the two gitignored tomls, which need the D1 id), `migrate` (the account schema through the company's own config), `buckets` (both buckets and the backup queue pair the template binds), `secrets` (box D2's provisioner), `deploy` (box D1's `--company` deploy of the proxy, then the account Worker), `bootstrap` (the org and an active ENTERPRISE subscription with limits: one POST to the company Worker under ACCOUNT_SERVER_API_KEY, a 200 rerun counting as success), `smoke` (both hosts answer), `lookup` (the www lookup entry through `ops.enterprise_lookup`, skipped and recorded for an unlisted company), `invite` (the owner invitation, sent by the company Worker through box A1) and `audit` (state `active` and one audit row). The Design lists `configs` after `buckets` and `secrets`; it runs straight after `d1` here because `migrate` reads the generated account config.

VALIDATION RUNS EVERY TIME, before any step: the name (`names.check`), the region of the environment, the owner address, the storage, the allowlist (`proxy_configs.allow_ips_refusal`) and, unless unlisted, the lookup domain against the free-mail list (`enterprise_lookup.refuse_free_mail`). Then every region's control database is read through the registry; an unreachable region refuses the add by name, and a name held in another region is refused.

RESUMABLE. A company already registered under the name is resumed under its own opaque id: each step recorded `done` is skipped, a `failed` step runs again, and the details recorded by earlier steps (the D1 id) reach the later ones. A rerun of a finished add runs nothing and reports nothing changed. `stop_after` ends the run after the named step with rc 1, which is how the proof's killed run is made.

BENCH. `--bench` selects `control-bench-<region>` (eu and us), the signer `signer-bench-<region>` and `ENVIRONMENT = "bench"` in the account config, so the bench mail capture applies.

NAMES STAY LOCAL. Progress lines and step errors carry the opaque id; a step error that quotes the label is masked by `console_executor.mask_label` before it is returned.

EVERY EXTERNAL CALL IS A SEAM. `run` takes the registry `Query` and one action per step; `live_actions` builds the production actions over injected runners, and a step whose owning box has not landed is a `not_built` action that refuses naming the box.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Any, NamedTuple

from rediacc_ci import paths
from rediacc_ci.core import https, wrangler
from rediacc_ci.deploy import console_executor
from rediacc_ci.deploy import proxy_configs as pc
from rediacc_ci.enterprise import configs, control_db, names, registry, secrets
from rediacc_ci.ops import enterprise_lookup
from rediacc_ci.well_known import PRODUCT_DOMAIN

if TYPE_CHECKING:
    import pathlib

STEPS: tuple[str, ...] = (
    "control-row",
    "d1",
    "configs",
    "migrate",
    "buckets",
    "secrets",
    "deploy",
    "bootstrap",
    "smoke",
    "lookup",
    "invite",
    "audit",
)
ACTOR = "enterprise add"
BENCH_ENVIRONMENT = "bench"
OWNER_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HTTP_SERVER_ERROR = 500
CF_ACCOUNT_ID = "fa51e4a18d553c30e1633288e9733d04"  # ops.cf_auth.DEFAULT_ACCOUNT_ID
MAX_DETAIL = 500


class OnboardingError(RuntimeError):
    """A refusal or a failed step; the message names the opaque id, never the label."""


class NotBuiltError(OnboardingError):
    """A step whose owning box has not landed."""


# What a step may raise and still be recorded as failed. Anything else is a defect and propagates.
STEP_ERRORS: tuple[type[Exception], ...] = (
    OnboardingError,
    registry.RegistryUnreachableError,
    control_db.ControlDbError,
    secrets.SecretsError,
    configs.ConfigError,
    enterprise_lookup.LookupRefusedError,
    console_executor.RefusedError,
    OSError,
    subprocess.SubprocessError,
)


@dataclasses.dataclass(frozen=True)
class Request:
    name: str
    region: str
    owner: str
    storage_gb: int
    allow_ips: tuple[str, ...] = ()
    unlisted: bool = False
    lookup_domain: str = ""
    bench: bool = False

    @property
    def lookup(self) -> str:
        """The lookup domain, defaulting to the owner's mail domain, lowercased without a trailing dot."""
        raw = self.lookup_domain or self.owner.rpartition("@")[2]
        return raw.strip().lower().removesuffix(".")


@dataclasses.dataclass(frozen=True)
class Plan:
    request: Request
    company_id: str
    database: str
    signer: str
    environment: str
    hosts: tuple[str, str]

    @property
    def name(self) -> str:
        return self.request.name

    @property
    def region(self) -> str:
        return self.request.region


@dataclasses.dataclass
class Context:
    plan: Plan
    query: registry.Query
    details: dict[str, str]
    now: str


Action = Callable[[Context], str]


class Outcome(NamedTuple):
    rc: int
    company_id: str
    changed: tuple[str, ...]
    error: str = ""


def utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan_for(req: Request, company_id: str) -> Plan:
    region = req.region
    return Plan(
        request=req,
        company_id=company_id,
        database=registry.control_database(region, req.bench),
        signer=("signer-bench-%s" if req.bench else "signer-%s") % region,
        environment=BENCH_ENVIRONMENT if req.bench else pc.COMPANY_ENVIRONMENT,
        hosts=names.hosts(req.name, PRODUCT_DOMAIN),
    )


def check_request(req: Request) -> None:
    """Raise OnboardingError naming the first rule the request breaks."""
    try:
        names.check(req.name)
    except names.CompanyNameError as exc:
        raise OnboardingError(str(exc)) from None
    regions = list(registry.databases(req.bench))
    if req.region not in regions:
        raise OnboardingError(
            "--region %s is not a region of %s (%s)"
            % (req.region, "bench" if req.bench else "production", ", ".join(regions))
        )
    if not OWNER_RE.fullmatch(req.owner or ""):
        raise OnboardingError("--owner %r is not a mail address" % (req.owner,))
    if (
        isinstance(req.storage_gb, bool)
        or not isinstance(req.storage_gb, int)
        or req.storage_gb < 1
    ):
        raise OnboardingError("--storage-gb must be a positive whole number of GB")
    if req.allow_ips:
        reason = pc.allow_ips_refusal(",".join(req.allow_ips))
        if reason:
            raise OnboardingError("--allow-ip refused: %s" % reason)
    if not req.unlisted:
        try:
            enterprise_lookup.refuse_free_mail(enterprise_lookup.normalize_domain(req.lookup))
        except enterprise_lookup.LookupRefusedError as exc:
            raise OnboardingError(str(exc)) from None


# --- the ledger ------------------------------------------------------------------


class Ledger:
    """The `onboarding` rows of one control database."""

    def __init__(self, query: registry.Query, database: str):
        self.query = query
        self.database = database

    def steps(self, company_id: str) -> dict[str, tuple[str, str]]:
        rows = self.query(
            self.database,
            "SELECT step, status, detail FROM onboarding WHERE company_id = ?",
            [company_id],
        )
        return {str(r["step"]): (str(r["status"]), str(r.get("detail") or "")) for r in rows}

    def mark(self, company_id: str, step: str, status: str, detail: str, now: str) -> None:
        self.query(
            self.database,
            "INSERT INTO onboarding (company_id, step, status, detail, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(company_id, step) DO UPDATE SET status = excluded.status, "
            "detail = excluded.detail, updated_at = excluded.updated_at",
            [company_id, step, status, detail, now],
        )


def write_control_row(ctx: Context) -> str:
    plan = ctx.plan
    ctx.query(
        plan.database,
        "INSERT INTO companies (id, name, region, state, unlisted, created_at, updated_at) "
        "VALUES (?, ?, ?, 'onboarding', ?, ?, ?) ON CONFLICT(id) DO NOTHING",
        [plan.company_id, plan.name, plan.region, int(plan.request.unlisted), ctx.now, ctx.now],
    )
    return ""


def write_audit(ctx: Context) -> str:
    plan = ctx.plan
    ctx.query(
        plan.database,
        "UPDATE companies SET state = 'active', updated_at = ? WHERE id = ?",
        [ctx.now, plan.company_id],
    )
    detail = json.dumps(
        {
            "region": plan.region,
            "bench": plan.request.bench,
            "unlisted": plan.request.unlisted,
            "storage_gb": plan.request.storage_gb,
            "signer": plan.signer,
        },
        sort_keys=True,
    )
    ctx.query(
        plan.database,
        "INSERT INTO audit (at, company_id, actor, action, detail) VALUES (?, ?, ?, 'add', ?)",
        [ctx.now, plan.company_id, ACTOR, detail],
    )
    return ""


def not_built(box: str, what: str) -> Action:
    """An action for a step whose owning box has not landed: it refuses naming the box."""

    def refuse(ctx: Context) -> str:
        del ctx
        raise NotBuiltError("not built yet: %s (%s)" % (box, what))

    return refuse


# --- the run ---------------------------------------------------------------------


def run(
    req: Request,
    *,
    query: registry.Query,
    actions: Mapping[str, Action],
    new_id: Callable[[], str] = secrets.new_company_id,
    now: Callable[[], str] = utc_now,
    stop_after: str = "",
    out: Callable[[str], None] = print,
) -> Outcome:
    """Validate, find or mint the company id, and run every step not yet done."""
    try:
        check_request(req)
        row = registry.Registry(query, bench=req.bench).find(req.name)
    except (OnboardingError, registry.RegistryUnreachableError) as exc:
        return Outcome(1, "", (), "refused: %s" % exc)
    if row is not None and row.get("region") != req.region:
        return Outcome(
            1,
            "",
            (),
            "refused: the name is already registered in %s (company %s)"
            % (row.get("region"), row.get("id")),
        )
    cid = str(row["id"]) if row is not None else new_id()
    plan = plan_for(req, cid)
    ledger = Ledger(query, plan.database)

    def masked(text: str) -> str:
        return console_executor.mask_label(text, req.name, cid)

    try:
        recorded = ledger.steps(cid) if row is not None else {}
    except STEP_ERRORS as exc:
        error = "company %s: the onboarding table cannot be read: %s" % (cid, exc)
        return Outcome(1, cid, (), masked(error))
    done = {s for s, (status, _d) in recorded.items() if status == "done"}
    details = {s: d for s, (status, d) in recorded.items() if status == "done"}
    changed: list[str] = []
    for step in STEPS:
        if step in done:
            continue
        stamp = now()
        ctx = Context(plan=plan, query=query, details=details, now=stamp)
        try:
            detail = "unlisted" if step == "lookup" and req.unlisted else actions[step](ctx) or ""
            ledger.mark(cid, step, "done", detail, stamp)
        except STEP_ERRORS as exc:
            error = masked("company %s: step %s failed: %s" % (cid, step, exc))
            if "control-row" in done:
                try:
                    ledger.mark(cid, step, "failed", error[:MAX_DETAIL], stamp)
                except STEP_ERRORS as mark_exc:
                    error += "; recording the failure also failed (%s)" % type(mark_exc).__name__
            return Outcome(1, cid, tuple(changed), error)
        done.add(step)
        details[step] = detail
        changed.append(step)
        out("company %s: %s done" % (cid, step))
        if step == stop_after:
            stopped = "company %s: stopped after %s as asked" % (cid, step)
            return Outcome(1, cid, tuple(changed), stopped)
    if changed:
        out("company %s: onboarded, %d step(s) run" % (cid, len(changed)))
    else:
        out("company %s: already onboarded, nothing changed" % cid)
    return Outcome(0, cid, tuple(changed))


# --- the live steps ----------------------------------------------------------------


class Proc(NamedTuple):
    returncode: int
    stdout: str
    stderr: str


def run_captured(argv: list[str], *, cwd: pathlib.Path | str | None = None) -> Proc:
    """The production runner for wrangler steps: both streams captured, never echoed (they can name the company)."""
    if cwd is None:
        with tempfile.TemporaryDirectory(prefix="enterprise-add-") as tmp:
            proc = subprocess.run(argv, cwd=tmp, capture_output=True, text=True, check=False)
    else:
        proc = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, check=False)
    return Proc(proc.returncode, proc.stdout, proc.stderr)


def run_module(module: str, argv: list[str]) -> int:
    """A deploy module in a child, with this package on the path; its streams are inherited because the deploy modules mask the label themselves."""
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return subprocess.call(
        [sys.executable, "-m", module, *argv], cwd=str(paths.repo_root()), env=env
    )


def http_status(url: str) -> int:
    """The status of an HTTPS GET through `core.https`, 0 when nothing answered."""
    try:
        with https.urlopen(https.build_request(url, method="GET"), timeout=20) as reply:
            return int(reply.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except OSError:
        return 0


ACCOUNT_KEY_ENV = "ACCOUNT_SERVER_API_KEY"
SUBSCRIPTIONS_PATH = "/account/api/v1/subscriptions/enterprise/"
HTTP_OK = 200
HTTP_CREATED = 201
AccountPost = Callable[[str, str, dict], tuple[int, dict]]


def account_post(url: str, api_key: str, body: dict) -> tuple[int, dict]:
    """(status, JSON body) of an authenticated POST to the company's account Worker through `core.https`; (0, {}) when nothing answered."""
    request = https.build_request(
        url,
        data=json.dumps(body).encode(),
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with https.urlopen(request, timeout=60) as reply:
            return int(reply.status), _json_body(reply.read())
    except urllib.error.HTTPError as exc:
        return int(exc.code), _json_body(exc.read())
    except OSError:
        return 0, {}


def _json_body(raw: bytes) -> dict:
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def region_entry(region: str, root: pathlib.Path | None = None) -> dict:
    data = json.loads(((root or paths.repo_root()) / "regions.json").read_text(encoding="utf-8"))
    for entry in data["regions"]:
        if str(entry["id"]) == region:
            return dict(entry)
    raise OnboardingError("no region %r in regions.json" % region)


def _exists(done: Any) -> bool:
    text = ("%s %s" % (done.stdout or "", done.stderr or "")).lower()
    return "already exists" in text or "already owned" in text


def live_actions(
    *,
    runner: Callable[..., Any] | None = None,
    control_runner: control_db.Runner | None = None,
    out_root: pathlib.Path | None = None,
    root: pathlib.Path | None = None,
    deploy: Callable[[str, list[str]], int] | None = None,
    fetch: Callable[[str], int] | None = None,
    provision: Callable[[secrets.Company], Any] | None = None,
    lookup_put: Callable[[str, str, str], int] | None = None,
    lookup_namespace: str = enterprise_lookup.NAMESPACE_ID,
    post: AccountPost | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Action]:
    """The production action of every step, each external call through the seam its argument names."""
    run_cmd = runner or run_captured
    control = control_runner or control_db.run_wrangler
    deploy_run = deploy or run_module
    get = fetch or http_status
    put = lookup_put or enterprise_lookup.put
    send = post or account_post

    def account_call(ctx: Context, route: str, body: dict) -> tuple[int, dict]:
        """One authenticated call to the company's account host. The key is read here, so a step that never runs needs none."""
        plan = ctx.plan
        key = (os.environ if env is None else env).get(ACCOUNT_KEY_ENV, "")
        if not key:
            raise OnboardingError(
                "company %s: the %s step needs %s" % (plan.company_id, route, ACCOUNT_KEY_ENV)
            )
        url = "https://%s%s%s" % (plan.hosts[0], SUBSCRIPTIONS_PATH, route)
        status, payload = send(url, key, {"companyId": plan.company_id, **body})
        if status == 0:
            raise OnboardingError(
                "company %s: the %s call got no answer" % (plan.company_id, route)
            )
        if status not in (HTTP_OK, HTTP_CREATED):
            code = str(payload.get("code") or "")
            raise OnboardingError(
                "company %s: the %s call was refused with HTTP %d%s"
                % (plan.company_id, route, status, " (%s)" % code if code else "")
            )
        return status, payload

    def bootstrap(ctx: Context) -> str:
        status, _payload = account_call(
            ctx,
            "bootstrap",
            {"ownerEmail": ctx.plan.request.owner, "storageGb": ctx.plan.request.storage_gb},
        )
        return "created" if status == HTTP_CREATED else "already bootstrapped"

    def invite(ctx: Context) -> str:
        account_call(ctx, "owner-mail", {"ownerEmail": ctx.plan.request.owner})
        return ""

    def base() -> pathlib.Path:
        return out_root if out_root is not None else paths.repo_root()

    def files(plan: Plan) -> tuple[pathlib.Path, pathlib.Path]:
        leaf = "enterprise.%s.toml" % plan.name
        return (
            base().joinpath(*pc.PROXY_REL) / leaf,
            base().joinpath(*pc.ACCOUNT_REL) / leaf,
        )

    def d1(ctx: Context) -> str:
        uuid, _created = control_db.ensure_database(
            "account-%s" % ctx.plan.name, ctx.plan.region, runner=control
        )
        return uuid

    def write_configs(ctx: Context) -> str:
        plan = ctx.plan
        uuid = ctx.details.get("d1", "")
        if not uuid:
            raise OnboardingError("company %s: the d1 step left no database id" % plan.company_id)
        configs.write(
            plan.name, plan.region, uuid, allow_ips=plan.request.allow_ips, out_root=out_root
        )
        if plan.environment == pc.COMPANY_ENVIRONMENT:
            return ""
        account = files(plan)[1]
        text = account.read_text(encoding="utf-8")
        line = 'ENVIRONMENT = "%s"' % pc.COMPANY_ENVIRONMENT
        if text.count(line) != 1:
            raise OnboardingError(
                "company %s: the account config has no single ENVIRONMENT line" % plan.company_id
            )
        text = text.replace(line, 'ENVIRONMENT = "%s"' % plan.environment)
        reasons = configs.account_refusals(plan.name, plan.region, text)
        if reasons:
            raise OnboardingError("company %s: %s" % (plan.company_id, "; ".join(reasons)))
        account.write_text(text, encoding="utf-8")
        return ""

    def migrate(ctx: Context) -> str:
        plan = ctx.plan
        argv = [
            *wrangler.ARGV, "d1", "migrations", "apply", "account-%s" % plan.name,
            "--remote", "--config", "enterprise.%s.toml" % plan.name,
        ]  # fmt: skip
        done = run_cmd(argv, cwd=base().joinpath(*pc.ACCOUNT_REL))
        if done.returncode != 0:
            raise OnboardingError(
                "company %s: the account migrations exited %d" % (plan.company_id, done.returncode)
            )
        return ""

    def buckets(ctx: Context) -> str:
        plan = ctx.plan
        jurisdiction = region_entry(plan.region).get("r2Jurisdiction")
        flag = ["--jurisdiction", str(jurisdiction)] if jurisdiction else []
        work = (
            ("configs bucket", ["r2", "bucket", "create", "configs-%s" % plan.name, *flag]),
            ("backups bucket", ["r2", "bucket", "create", "backups-%s" % plan.name, *flag]),
            ("backup queue", ["queues", "create", "backup-replicate-%s" % plan.name]),
            ("dead-letter queue", ["queues", "create", "backup-replicate-%s-dlq" % plan.name]),
        )
        for what, args in work:
            done = run_cmd([*wrangler.ARGV, *args], cwd=None)
            if done.returncode != 0 and not _exists(done):
                raise OnboardingError(
                    "company %s: creating the %s failed (wrangler exited %d)"
                    % (plan.company_id, what, done.returncode)
                )
        return ""

    def provision_secrets(ctx: Context) -> str:
        plan = ctx.plan
        if provision is None:
            raise OnboardingError(
                "company %s: the secrets step needs --bws-project (the enterprise bws project)"
                % plan.company_id
            )
        company = secrets.Company(
            id=plan.company_id,
            name=plan.name,
            region=plan.region,
            cf_account_id=CF_ACCOUNT_ID,
            r2_jurisdiction=region_entry(plan.region).get("r2Jurisdiction"),
        )
        report = provision(company)
        return "%d created, %d reused, %d pushed" % (
            len(report.created),
            len(report.reused),
            len(report.pushed),
        )

    def deploy_both(ctx: Context) -> str:
        plan = ctx.plan
        proxy_path, account_path = files(plan)
        tree = root if root is not None else paths.repo_root()

        def target(**config: pathlib.Path) -> console_executor.CompanyTarget:
            return console_executor.company_target(
                tree,
                name=plan.name,
                company_id=plan.company_id,
                region=plan.region,
                domain=PRODUCT_DOMAIN,
                bench=plan.request.bench,
                **config,
            )

        for module, company in (
            ("rediacc_ci.deploy.deploy_proxy", target(proxy_config=proxy_path)),
            ("rediacc_ci.deploy.deploy_account", target(account_config=account_path)),
        ):
            rc = deploy_run(module, console_executor.company_argv(company))
            if rc != 0:
                raise OnboardingError(
                    "company %s: %s exited %d" % (plan.company_id, module.rsplit(".", 1)[1], rc)
                )
        return ""

    def smoke(ctx: Context) -> str:
        plan = ctx.plan
        bad = []
        for role, host in zip(("account host", "proxy host"), plan.hosts, strict=True):
            status = get("https://%s/" % host)
            if not status or status >= HTTP_SERVER_ERROR:
                bad.append("the %s answered %s" % (role, status or "nothing"))
        if bad:
            raise OnboardingError("company %s: %s" % (plan.company_id, "; ".join(bad)))
        return ""

    def lookup(ctx: Context) -> str:
        plan = ctx.plan
        try:
            rc = put(plan.request.lookup, plan.hosts[0], lookup_namespace)
        except enterprise_lookup.LookupRefusedError as exc:
            raise OnboardingError("company %s: %s" % (plan.company_id, exc)) from None
        if rc != 0:
            raise OnboardingError("company %s: the lookup writer exited %d" % (plan.company_id, rc))
        return ""

    return {
        "control-row": write_control_row,
        "d1": d1,
        "configs": write_configs,
        "migrate": migrate,
        "buckets": buckets,
        "secrets": provision_secrets,
        "deploy": deploy_both,
        "bootstrap": bootstrap,
        "smoke": smoke,
        "lookup": lookup,
        "invite": invite,
        "audit": write_audit,
    }


class Minters:
    """D2's `Minter` from its two production halves: the IAM minter mints the SES user, the Cloudflare minter the bucket token."""

    def __init__(self, cloudflare: secrets.CloudflareMinter, iam: secrets.IamMinter):
        self.cloudflare = cloudflare
        self.iam = iam

    def ses_user(self, user_name: str) -> tuple[str, str]:
        return self.iam.ses_user(user_name)

    def r2_bucket_token(self, token_name: str, resource: str) -> tuple[str, str]:
        return self.cloudflare.r2_bucket_token(token_name, resource)


def live_provision(
    project_id: str, env: Mapping[str, str] | None = None
) -> Callable[[secrets.Company], Any]:
    """Box D2's provisioner over its production adapters: the enterprise bws project, a Cloudflare management token (`CF_MANAGEMENT_TOKEN`), the AWS CLI, and the shared values of the company's region from the environment."""
    environ = dict(os.environ if env is None else env)

    def provision(company: secrets.Company) -> Any:
        token = environ.get("CF_MANAGEMENT_TOKEN", "")
        if not token:
            raise OnboardingError(
                "company %s: the secrets step needs CF_MANAGEMENT_TOKEN to mint the backup token"
                % company.id
            )
        entry = region_entry(company.region)
        from_domain = environ.get("AWS_SES_FROM", "").rpartition("@")[2].strip("> ")
        if not from_domain:
            raise OnboardingError("company %s: the secrets step needs AWS_SES_FROM" % company.id)

        def aws(argv: list[str]) -> tuple[int, str]:
            proc = secrets.awscli.run(argv, capture_output=True, text=True)
            return proc.returncode, proc.stdout

        minter = Minters(
            secrets.CloudflareMinter.from_headers(["-H", "Authorization: Bearer %s" % token]),
            secrets.IamMinter(aws=aws, ses_region=str(entry["sesRegion"]), from_domain=from_domain),
        )
        return secrets.provision(
            company,
            secrets.shared_from_env(environ, str(entry["secretSuffix"])),
            store=secrets.BwsStore.from_env(project_id, environ),
            minter=minter,
            push=secrets.wrangler_push,
        )

    return provision
