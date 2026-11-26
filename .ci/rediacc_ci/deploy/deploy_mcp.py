#!/usr/bin/env python3
"""Deploy the remote MCP Worker of one region and prove the deployed Worker answers.

    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_mcp --target stable|bench --region eu|us|asia [--record PATH] [--smoke-only] [--dry-run]
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_mcp --target stable|bench --region R --rollback VERSION_ID [--record PATH]
    PYTHONPATH=.ci python3 -m rediacc_ci.deploy.deploy_mcp [--check]        # render workers/mcp/wrangler.<target>.toml, or refuse drift

agent/plans/PLAN-rmcp-remote-worker.md Design 1, 10 and 12, box RW-D2. The shape is `deploy_proxy`'s: a dry run that reads no secret, one record per deploy, and a rollback command in that record.

THE CONFIGS. `workers/mcp/wrangler.template.toml` and `regions.json` generate one file per target: `wrangler.<region>.toml` for the stable Worker of each region and `wrangler.bench-<region>.toml` for each bench. The names come from regions.json (`mcpWorkerName`, the region's `workerName` and `proxyWorkerName`, and the bench object's own names), so no name is spelled in this module. The rendered files are committed; `--check` refuses a hand edit, and `config_refusals` runs on the file before any credential is read.

THE REGION BOUNDARY (Design 12). A config must bind only its own region: the `GRANTS` service is the region's account Worker (`GrantResolver`), the `EXECUTOR` service is the region's proxy Worker (`McpExecutor`), the Analytics Engine dataset is `mcp_<region>` (`mcp_bench_<region>` on a bench, whose account may be the production account), and the route, `REGION`, `MCP_HOST`, `ACCOUNT_URL` and telemetry destinations name the region. A config naming another region's token in any non-comment line is refused, so a us file carrying an eu binding never reaches a credential.

THE BINDINGS THE OAUTH PROVIDER READS. `OAUTH_KV` is a `[[kv_namespaces]]` entry with no id: wrangler provisions the namespace on the first deploy and reuses it, so no namespace id is committed. `AUTH_REQUEST_KEY` (signs the `authRequest` handles) and `CONFIRM_KEY` (seals confirmation state) are Worker secrets. This module generates a random value for each name the Worker does not already list and pushes it as the JSON document on `wrangler secret bulk` stdin; a name already present is never overwritten, because a new value would invalidate every sealed handle in flight. No value is put in argv, printed, recorded or kept after the push. The names are in SECRET_NAMES and the Worker's `Env`, and a dry run reads and generates none.

THE VERSION ID. The `Current Version ID:` line of `wrangler deploy` is captured, and `wrangler deployments list --json` must name that id at 100%, or the run fails. The newest deployment before the deploy gives the rollback target.

THE SMOKE. `/.well-known/oauth-authorization-server` must answer 200 with `issuer` equal to `https://<host>` (the OAuth provider is up, which needs `OAUTH_KV` and `AUTH_REQUEST_KEY`), and a `POST /g/smoke-check` without a credential must answer 401. Both are polled for READY_TIMEOUT_S. The smoke holds no grant, so a pass says nothing about a tool call. `--smoke-only` skips the deploy.

THE RECORD. `--record PATH` writes JSON: target, region, worker, config, version id, previous version id, secret names (never values), smoke rc and the rollback command. A rollback is `wrangler rollback <previous> --config <file> --yes`, or null on a first deploy. The Worker's one Durable Object migration (v1) is a creation, so a rollback never meets a forward-only class change.

A ROLLBACK (`--rollback <version-id>`) runs wrangler's rollback against the target's config, cross-checks the deployments list, smokes, and writes the record with `rolled_back: true`.

A DRY RUN (`--dry-run`) runs the refusals and `wrangler deploy --dry-run`, which bundles the Worker and needs no credential.

Credentials: a run with no `CLOUDFLARE_API_TOKEN` re-executes itself under `bws_env exec --profile deploy-proxy-bench-eu` (bench) or `deploy-proxy` (stable), the profiles `deploy_proxy` uses; CD supplies the token from its own bws step. This module never reads a Bitwarden value itself.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import secrets as secrets_module
import subprocess
import sys
import time
import tomllib
import typing
import urllib.error
from datetime import UTC, datetime

from rediacc_ci import log, paths
from rediacc_ci.core import https, wrangler

SELF = "rediacc_ci.deploy.deploy_mcp"
MCP_REL = ("workers", "mcp")
TEMPLATE = "wrangler.template.toml"
REGIONS_REL = "regions.json"

STABLE_TARGET = "stable"
BENCH_TARGET = "bench"
SUPPORTED_TARGETS = (STABLE_TARGET, BENCH_TARGET)

# Worker secrets this module provisions, generated when absent. INTERNAL_REVOKE_TOKEN is the account's to hand over (it must match the account Worker's own secret) and is not generated here.
SECRET_NAMES = ("AUTH_REQUEST_KEY", "CONFIRM_KEY")
SECRET_BYTES = 32

GRANTS_BINDING = ("GRANTS", "GrantResolver")
EXECUTOR_BINDING = ("EXECUTOR", "McpExecutor")
KV_BINDING = "OAUTH_KV"
RATE_BINDING = ("RATE", "GrantRateObject")
METRICS_BINDING = "MCP_METRICS"
MAIN = "src/index.ts"

# Tokens of a non-comment config line that name a channel, besides the region ids.
CHANNEL_TOKENS = frozenset({"bench"})
TOKEN_SPLIT = re.compile(r"[^A-Za-z0-9]+")
PLACEHOLDER_RE = re.compile(r"@@[A-Z_]+@@")

HEADER = "Rendered from wrangler.template.toml for one target and region; edit the template and render again, never this file alone."

VERSION_ID_RE = re.compile(r"Current Version ID:\s*([0-9A-Za-z][0-9A-Za-z-]*)")
WORKER_VERSION_RE = re.compile(
    r"\A[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z", re.IGNORECASE
)
NO_WORKER_RE = re.compile(r"\[code: 10007\]|does not exist on your account|script_not_found")

BENCH_PROFILE = "deploy-proxy-bench-eu"
STABLE_PROFILE = "deploy-proxy"
PROFILES_ENV = "REDIACC_BWS_PROFILES"

READY_TIMEOUT_S = 120
READY_POLL_S = 5
SMOKE_PATH_OAUTH = "/.well-known/oauth-authorization-server"
SMOKE_PATH_GRANT = "/g/smoke-check"
DRY_RUN_OUTDIR = "/tmp/rediacc-mcp-dry-run"
REDACTED = "[redacted]"


class RefusedError(Exception):
    """A run that must stop with exit 1. Its lines never carry a secret value."""

    def __init__(self, *lines: str) -> None:
        super().__init__(lines[0] if lines else "")
        self.lines = lines


@dataclasses.dataclass(frozen=True)
class Target:
    """What one MCP config must name, exactly."""

    key: str
    config: str
    name: str
    region: str
    bench: bool
    host: str
    environment: str
    account_url: str
    account_service: str
    proxy_service: str
    dataset: str
    otlp: str

    @property
    def own_tokens(self) -> frozenset[str]:
        return frozenset({self.region, "bench"} if self.bench else {self.region})


@dataclasses.dataclass(frozen=True)
class Result:
    rc: int
    stdout: str
    stderr: str


# (argv, cwd, stdin, env) -> Result. The tests swap it for a recording fake.
Runner = typing.Callable[[list[str], pathlib.Path, "str | None", "dict[str, str]"], Result]
# (url, method) -> (status, body). The tests swap it for a table.
Fetcher = typing.Callable[[str, str], "tuple[int, str]"]


def run_process(
    argv: list[str], cwd: pathlib.Path, stdin: str | None, env: dict[str, str]
) -> Result:
    proc = subprocess.run(
        argv, cwd=cwd, env=env, input=stdin, capture_output=True, text=True, check=False
    )
    return Result(proc.returncode, proc.stdout, proc.stderr)


def fetch_url(url: str, method: str) -> tuple[int, str]:
    """One HTTPS request; an HTTP error status is an answer, a transport failure is status 0."""
    request = https.build_request(url, method=method, data=b"{}" if method == "POST" else None)
    try:
        with https.urlopen(request, timeout=15) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return 0, ""


# ---- targets and configs --------------------------------------------------------


def load_regions(root: pathlib.Path) -> list[dict]:
    data = json.loads((root / REGIONS_REL).read_text(encoding="utf-8"))
    rows = data.get("regions") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise RefusedError("%s: %s has no `regions` list" % (SELF, REGIONS_REL))
    return rows


def _need(row: dict, key: str, where: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise RefusedError("%s: %s names no %s" % (SELF, where, key))
    return value


def targets(regions: list[dict]) -> dict[str, Target]:
    """Every MCP target, keyed by its config suffix: `eu`, `us`, `asia` and `bench-<r>` for each region with a bench object."""
    out: dict[str, Target] = {}
    for row in regions:
        rid = str(row["id"])
        where = "%s region %s" % (REGIONS_REL, rid)
        domain = _need(row, "domain", where)
        out[rid] = Target(
            key=rid,
            config="wrangler.%s.toml" % rid,
            name=_need(row, "mcpWorkerName", where),
            region=rid,
            bench=False,
            host="mcp." + domain,
            environment="edge",
            account_url="https://" + domain,
            account_service=_need(row, "workerName", where),
            proxy_service=_need(row, "proxyWorkerName", where),
            dataset="mcp_" + rid,
            otlp="otlp-" + rid,
        )
        bench = row.get("bench")
        if isinstance(bench, dict):
            bwhere = where + " bench"
            bhost = _need(bench, "host", bwhere)
            key = "bench-" + rid
            out[key] = Target(
                key=key,
                config="wrangler.%s.toml" % key,
                name=_need(bench, "mcpWorkerName", bwhere),
                region=rid,
                bench=True,
                host="mcp." + bhost,
                environment="bench",
                account_url="https://" + bhost,
                account_service=_need(bench, "workerName", bwhere),
                proxy_service=_need(bench, "proxyWorkerName", bwhere),
                dataset="mcp_bench_" + rid,
                otlp="otlp-" + _need(bench, "otlp", bwhere),
            )
    return out


def pick(all_targets: dict[str, Target], target: str, region: str) -> Target:
    if target not in SUPPORTED_TARGETS:
        raise RefusedError("--target %s is not one of %s" % (target, ", ".join(SUPPORTED_TARGETS)))
    key = region if target == STABLE_TARGET else "bench-" + region
    if key not in all_targets:
        raise RefusedError(
            "--target %s --region %s names no config (the configs are %s)"
            % (target, region, ", ".join(sorted(all_targets)))
        )
    return all_targets[key]


def render(template: str, target: Target) -> str:
    """The config text of one target; a placeholder left unfilled is an error."""
    values = {
        "HEADER": HEADER,
        "NAME": target.name,
        "HOST": target.host,
        "REGION": target.region,
        "ENVIRONMENT": target.environment,
        "ACCOUNT_URL": target.account_url,
        "ACCOUNT_SERVICE": target.account_service,
        "PROXY_SERVICE": target.proxy_service,
        "DATASET": target.dataset,
        "OTLP": target.otlp,
    }
    text = template
    for key, value in values.items():
        text = text.replace("@@%s@@" % key, value)
    left = sorted(set(PLACEHOLDER_RE.findall(text)))
    if left:
        raise RefusedError("%s leaves %s unfilled" % (TEMPLATE, ", ".join(left)))
    return text


def _services(doc: dict) -> dict[str, tuple[str, str]]:
    return {
        str(s.get("binding")): (str(s.get("service")), str(s.get("entrypoint")))
        for s in doc.get("services", [])
        if isinstance(s, dict)
    }


def config_refusals(text: str, target: Target, all_regions: frozenset[str]) -> list[str]:
    """Every reason `text` is not exactly the config of `target`; empty when it holds."""
    try:
        doc = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return ["does not parse as TOML: %s" % exc]
    out: list[str] = []

    def expect(label: str, got: object, want: object) -> None:
        if got != want:
            out.append("%s is %r, not %r" % (label, got, want))

    expect("name", doc.get("name"), target.name)
    expect("main", doc.get("main"), MAIN)
    routes = doc.get("routes", [])
    expect(
        "routes", [r.get("pattern") if isinstance(r, dict) else r for r in routes], [target.host]
    )
    if not all(isinstance(r, dict) and r.get("custom_domain") is True for r in routes):
        out.append("every route must be a custom_domain route")
    variables = doc.get("vars", {})
    expect("vars.REGION", variables.get("REGION"), target.region)
    expect("vars.ENVIRONMENT", variables.get("ENVIRONMENT"), target.environment)
    expect("vars.MCP_HOST", variables.get("MCP_HOST"), target.host)
    expect("vars.ACCOUNT_URL", variables.get("ACCOUNT_URL"), target.account_url)
    expect(
        "services",
        _services(doc),
        {
            GRANTS_BINDING[0]: (target.account_service, GRANTS_BINDING[1]),
            EXECUTOR_BINDING[0]: (target.proxy_service, EXECUTOR_BINDING[1]),
        },
    )
    kv = doc.get("kv_namespaces", [])
    expect("kv_namespaces bindings", [k.get("binding") for k in kv], [KV_BINDING])
    if any(k.get("id") for k in kv):
        out.append("kv_namespaces must carry no id: wrangler provisions the namespace")
    expect(
        "analytics_engine_datasets",
        [(d.get("binding"), d.get("dataset")) for d in doc.get("analytics_engine_datasets", [])],
        [(METRICS_BINDING, target.dataset)],
    )
    expect(
        "durable_objects.bindings",
        [
            (b.get("name"), b.get("class_name"))
            for b in doc.get("durable_objects", {}).get("bindings", [])
        ],
        [RATE_BINDING],
    )
    observability = doc.get("observability", {})
    expect(
        "observability destinations",
        (
            observability.get("logs", {}).get("destinations"),
            observability.get("traces", {}).get("destinations"),
        ),
        ([target.otlp + "-logs"], [target.otlp + "-traces"]),
    )
    if observability.get("logs", {}).get("invocation_logs") is not False:
        out.append("observability.logs.invocation_logs must be false")
    if "env" in doc:
        out.append("an [env.*] table is refused: one config is one target")
    left = sorted(set(PLACEHOLDER_RE.findall(text)))
    if left:
        out.append("leaves %s unfilled" % ", ".join(left))

    foreign = (all_regions | CHANNEL_TOKENS) - target.own_tokens
    for number, line in enumerate(text.splitlines(), 1):
        code = line.split("#", 1)[0]
        if any(name in code for name in SECRET_NAMES):
            out.append("line %d names a Worker secret; secrets are never written here" % number)
        hits = sorted(foreign & {t.lower() for t in TOKEN_SPLIT.split(code) if t})
        if hits:
            out.append(
                "line %d names %s, which is not this target's region (%s)"
                % (number, ", ".join(hits), target.key)
            )
    return out


def generate(root: pathlib.Path) -> dict[str, str]:
    template = (root.joinpath(*MCP_REL) / TEMPLATE).read_text(encoding="utf-8")
    return {t.config: render(template, t) for t in targets(load_regions(root)).values()}


def check(root: pathlib.Path) -> list[str]:
    """Every refusal over the committed configs; empty when they hold."""
    regions = load_regions(root)
    all_targets = targets(regions)
    all_regions = frozenset(str(r["id"]).lower() for r in regions)
    rendered = generate(root)
    mcp_dir = root.joinpath(*MCP_REL)
    rel = "/".join(MCP_REL)
    known = {TEMPLATE} | set(rendered)
    out = [
        "%s/%s is no known MCP target" % (rel, p.name)
        for p in sorted(mcp_dir.glob("wrangler*.toml"))
        if p.name not in known
    ]
    for target in all_targets.values():
        path = mcp_dir / target.config
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            out.append("%s/%s cannot be read: %s" % (rel, target.config, exc.strerror or exc))
            continue
        if text != rendered[target.config]:
            out.append(
                "%s/%s is stale: run `PYTHONPATH=.ci python3 -m %s`" % (rel, target.config, SELF)
            )
        out.extend(
            "%s/%s: %s" % (rel, target.config, r)
            for r in config_refusals(text, target, all_regions)
        )
    return out


def write(root: pathlib.Path) -> list[str]:
    mcp_dir = root.joinpath(*MCP_REL)
    written = []
    for name, text in generate(root).items():
        path = mcp_dir / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
            written.append(name)
    return written


# ---- wrangler -------------------------------------------------------------------


def deploy_argv(config: str, *, dry_run: bool) -> list[str]:
    argv = [*wrangler.ARGV, "deploy", "--config", config]
    if dry_run:
        argv += ["--dry-run", "--outdir", DRY_RUN_OUTDIR]
    return argv


def deployments_argv(config: str) -> list[str]:
    return [*wrangler.ARGV, "deployments", "list", "--json", "--config", config]


def secret_bulk_argv(config: str) -> list[str]:
    return [*wrangler.ARGV, "secret", "bulk", "--config", config]


def secret_list_argv(config: str) -> list[str]:
    return [*wrangler.ARGV, "secret", "list", "--format", "json", "--config", config]


def rollback_argv(config: str, version: str, message: str) -> list[str]:
    return [*wrangler.ARGV, "rollback", version, "--message", message, "--yes", "--config", config]


def rollback_command(config_rel: str, version: str) -> str:
    return "npx --no-install wrangler rollback %s --config %s --yes" % (version, config_rel)


class DeploymentsUnreadableError(Exception):
    """The deployments list failed or printed something that is not a list, which is not a first deploy."""


def deployments(run: Runner, cwd: pathlib.Path, env: dict[str, str], config: str) -> list[dict]:
    """The deployments list; empty for a Worker that does not exist yet."""
    res = run(deployments_argv(config), cwd, None, env)
    if res.rc != 0:
        if NO_WORKER_RE.search(res.stdout + res.stderr):
            return []
        raise DeploymentsUnreadableError
    try:
        rows = json.loads(res.stdout)
    except json.JSONDecodeError:
        raise DeploymentsUnreadableError from None
    if not isinstance(rows, list) or not all(isinstance(d, dict) for d in rows):
        raise DeploymentsUnreadableError
    return rows


def live_version(rows: list[dict]) -> str | None:
    """The version id the newest deployment serves at 100%, or None."""
    if not rows:
        return None
    newest = max(rows, key=lambda d: str(d.get("created_on", "")))
    versions = newest.get("versions", [])
    if not isinstance(versions, list):
        raise DeploymentsUnreadableError
    for v in versions:
        if isinstance(v, dict) and v.get("percentage") == 100:
            return str(v.get("version_id")).lower()
    return None


class Redactor:
    """Replaces every secret value in text before it is printed or raised."""

    def __init__(self, values: typing.Iterable[str]) -> None:
        self.values = sorted({v for v in values if v}, key=len, reverse=True)

    def __call__(self, text: str) -> str:
        for v in self.values:
            text = text.replace(v, REDACTED)
        return text


# ---- the smoke ------------------------------------------------------------------


def smoke_once(target: Target, fetch: Fetcher) -> str | None:
    """None when both smoke requests answer as expected, else why not."""
    base = "https://" + target.host
    status, body = fetch(base + SMOKE_PATH_OAUTH, "GET")
    if status != 200:
        return "GET %s answered %d, not 200" % (SMOKE_PATH_OAUTH, status)
    try:
        issuer = json.loads(body).get("issuer")
    except (json.JSONDecodeError, AttributeError):
        return "GET %s printed no JSON object" % SMOKE_PATH_OAUTH
    if issuer != base:
        return "the OAuth issuer is %r, not %r" % (issuer, base)
    status, _ = fetch(base + SMOKE_PATH_GRANT, "POST")
    if status != 401:
        return "POST %s without a credential answered %d, not 401" % (SMOKE_PATH_GRANT, status)
    return None


def smoke(
    target: Target,
    fetch: Fetcher,
    say: typing.Callable[[str], None],
    *,
    sleep: typing.Callable[[float], None] = time.sleep,
    timeout_s: float = READY_TIMEOUT_S,
) -> int:
    """Poll the smoke for `timeout_s`; 0 on a pass, 1 otherwise."""
    waited = 0.0
    while True:
        why = smoke_once(target, fetch)
        if why is None:
            say(
                "Smoke test passed on %s: OAuth metadata names its own issuer, an anonymous call is 401."
                % target.host
            )
            return 0
        if waited >= timeout_s:
            say("Smoke test failed on %s: %s" % (target.host, why))
            return 1
        sleep(READY_POLL_S)
        waited += READY_POLL_S


# ---- the run --------------------------------------------------------------------


def ensure_secrets(
    run: Runner,
    cwd: pathlib.Path,
    env: dict[str, str],
    config: str,
    say: typing.Callable[[str], None],
    *,
    token: typing.Callable[[], str] = lambda: secrets_module.token_urlsafe(SECRET_BYTES),
) -> list[str]:
    """Push a fresh random value for each SECRET_NAMES entry the Worker does not list, and return the names the Worker then lists. Values travel on stdin only."""
    res = run(secret_list_argv(config), cwd, None, env)
    if res.rc != 0:
        raise RefusedError("%s: wrangler secret list failed (rc %d)" % (SELF, res.rc))
    try:
        present = {str(s.get("name")) for s in json.loads(res.stdout)}
    except (json.JSONDecodeError, AttributeError, TypeError):
        raise RefusedError("%s: wrangler secret list printed no JSON list" % SELF) from None
    missing = [n for n in SECRET_NAMES if n not in present]
    if missing:
        document = {n: token() for n in missing}
        redact = Redactor(document.values())
        pushed = run(secret_bulk_argv(config), cwd, json.dumps(document), env)
        say(redact(pushed.stdout))
        say(redact(pushed.stderr))
        if pushed.rc != 0:
            raise RefusedError("%s: wrangler secret bulk failed (rc %d)" % (SELF, pushed.rc))
        say("Pushed secrets %s." % ", ".join(missing))
    return sorted(present | set(missing))


def write_record(path: pathlib.Path | None, result: dict[str, typing.Any]) -> None:
    if path is not None:
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


def _stamp(now: typing.Callable[[], datetime]) -> str:
    return now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _rollback(
    run: Runner,
    target: Target,
    version: str,
    base: dict[str, typing.Any],
    *,
    env: dict[str, str],
    mcp_dir: pathlib.Path,
    fetch: Fetcher,
    say: typing.Callable[[str], None],
    sleep: typing.Callable[[float], None],
    record: pathlib.Path | None,
    now: typing.Callable[[], datetime],
) -> dict[str, typing.Any]:
    res = run(rollback_argv(target.config, version, SELF + " --rollback"), mcp_dir, None, env)
    say(res.stdout)
    say(res.stderr)
    failure = None if res.rc == 0 else "wrangler rollback failed (rc %d)" % res.rc
    live = None
    if failure is None:
        try:
            live = live_version(deployments(run, mcp_dir, env, target.config))
        except DeploymentsUnreadableError:
            live = None
        if live != version:
            failure = "the deployments list names %r at 100%%, not %s" % (live, version)
    rc = smoke(target, fetch, say, sleep=sleep) if failure is None else None
    result = {
        **base,
        "rolled_back": True,
        "requested_version_id": version,
        "version_id": live,
        "smoke_rc": rc,
        "failure": failure,
        "at": _stamp(now),
    }
    write_record(record, result)
    if failure is not None or rc != 0:
        raise RefusedError(
            "%s: rollback of %s to %s failed: %s" % (SELF, target.name, version, failure or "smoke")
        )
    say("Rolled %s back to %s." % (target.name, version))
    return result


def run_deploy(
    root: pathlib.Path,
    target_name: str,
    region: str,
    *,
    env: dict[str, str],
    run: Runner,
    fetch: Fetcher,
    dry_run: bool = False,
    smoke_only: bool = False,
    rollback: str | None = None,
    record: pathlib.Path | None = None,
    out: typing.TextIO = sys.stdout,
    sleep: typing.Callable[[float], None] = time.sleep,
    now: typing.Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, typing.Any]:
    if rollback is not None:
        if dry_run or smoke_only:
            raise RefusedError("--rollback cannot be combined with --dry-run or --smoke-only")
        if not WORKER_VERSION_RE.match(rollback):
            raise RefusedError(
                "--rollback needs a full version UUID, as `wrangler deployments list` prints"
            )
        rollback = rollback.lower()
    if dry_run and smoke_only:
        raise RefusedError("--dry-run and --smoke-only are exclusive")
    regions = load_regions(root)
    target = pick(targets(regions), target_name, region)
    all_regions = frozenset(str(r["id"]).lower() for r in regions)
    mcp_dir = root.joinpath(*MCP_REL)
    config_rel = "/".join(MCP_REL) + "/" + target.config
    text = (mcp_dir / target.config).read_text(encoding="utf-8")
    reasons = config_refusals(text, target, all_regions)
    if text != render((mcp_dir / TEMPLATE).read_text(encoding="utf-8"), target):
        reasons.append("is stale: run `PYTHONPATH=.ci python3 -m %s`" % SELF)
    if reasons:
        raise RefusedError(*("%s refused: %s" % (config_rel, r) for r in reasons))

    def say(line: str) -> None:
        if line:
            out.write(line if line.endswith("\n") else line + "\n")

    base: dict[str, typing.Any] = {
        "target": target_name,
        "region": region,
        "worker": target.name,
        "config": config_rel,
    }

    if dry_run:
        res = run(deploy_argv(target.config, dry_run=True), mcp_dir, None, env)
        say(res.stdout)
        say(res.stderr)
        if res.rc != 0:
            raise RefusedError("%s: wrangler deploy --dry-run failed (rc %d)" % (SELF, res.rc))
        say("Dry run passed: %s bundles with %s." % (target.name, config_rel))
        return {**base, "dry_run": True}

    if not env.get("CLOUDFLARE_API_TOKEN"):
        raise RefusedError(
            "%s: CLOUDFLARE_API_TOKEN is required (bind with bws_env exec --profile %s)"
            % (SELF, BENCH_PROFILE if target_name == BENCH_TARGET else STABLE_PROFILE)
        )

    if rollback is not None:
        return _rollback(
            run,
            target,
            rollback,
            base,
            env=env,
            mcp_dir=mcp_dir,
            fetch=fetch,
            say=say,
            sleep=sleep,
            record=record,
            now=now,
        )

    try:
        before = live_version(deployments(run, mcp_dir, env, target.config))
        previous_known = True
    except DeploymentsUnreadableError:
        before, previous_known = None, False

    if smoke_only:
        rc = smoke(target, fetch, say, sleep=sleep)
        result = {**base, "version_id": before, "smoke_rc": rc, "smoke_only": True}
        write_record(record, result)
        if rc != 0:
            raise RefusedError("%s: the smoke failed on %s" % (SELF, target.host))
        return result

    res = run(deploy_argv(target.config, dry_run=False), mcp_dir, None, env)
    say(res.stdout)
    say(res.stderr)
    if res.rc != 0:
        raise RefusedError("%s: wrangler deploy failed (rc %d)" % (SELF, res.rc))
    found = VERSION_ID_RE.findall(res.stdout + res.stderr)
    if not found:
        raise RefusedError("%s: wrangler deploy printed no Current Version ID" % SELF)
    version = found[-1].lower()
    try:
        serving = live_version(deployments(run, mcp_dir, env, target.config))
    except DeploymentsUnreadableError:
        serving = None
    if serving != version:
        raise RefusedError(
            "%s: wrangler printed version %s but the deployments list names %r at 100%%"
            % (SELF, version, serving)
        )

    rollback_line = rollback_command(config_rel, before) if before else None
    result = {
        **base,
        "version_id": version,
        "previous_version_id": before,
        "previous_known": previous_known,
        "secret_names": [],
        "smoke_rc": None,
        "rollback": rollback_line,
        "at": _stamp(now),
    }
    # The version is live from here, so the record and the way back exist before the secrets and the smoke.
    write_record(record, result)
    say("Deployed %s version %s." % (target.name, version))
    if rollback_line:
        say("Rollback: %s" % rollback_line)
    elif previous_known:
        say("Rollback: none (first deploy)")
    else:
        say("Rollback: unknown (the deployments list could not be read before this deploy)")

    result["secret_names"] = ensure_secrets(run, mcp_dir, env, target.config, say)
    result["smoke_rc"] = smoke(target, fetch, say, sleep=sleep)
    write_record(record, result)
    if result["smoke_rc"] != 0:
        raise RefusedError("%s: the smoke failed on %s version %s" % (SELF, target.host, version))
    return result


def reexec_argv(target: str, argv: list[str]) -> list[str] | None:
    """This same run under its bws profile, or None when a Cloudflare token or the profile is already bound."""
    profile = BENCH_PROFILE if target == BENCH_TARGET else STABLE_PROFILE
    bound = [b.strip() for b in os.environ.get(PROFILES_ENV, "").split(",") if b.strip()]
    if os.environ.get("CLOUDFLARE_API_TOKEN") or profile in bound:
        return None
    return [
        sys.executable,
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        profile,
        "--",
        sys.executable,
        "-m",
        SELF,
        *argv,
    ]


def main(argv: list[str] | None = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog=SELF, description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=SUPPORTED_TARGETS)
    parser.add_argument("--region")
    parser.add_argument("--record", type=pathlib.Path)
    parser.add_argument("--smoke-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback", metavar="VERSION_ID")
    parser.add_argument(
        "--check", action="store_true", help="refuse drift and bad shapes; write nothing"
    )
    parser.add_argument("--root", type=pathlib.Path, default=None, help="repository root (tests)")
    args = parser.parse_args(args_in)
    root = args.root or paths.repo_root()
    try:
        if args.target is None:
            if args.check:
                reasons = check(root)
                for reason in reasons:
                    log.error("%s: %s" % (SELF, reason))
                if reasons:
                    return 1
                print("%s: %d MCP configs hold" % (SELF, len(targets(load_regions(root)))))
                return 0
            written = write(root)
            print(
                "%s: wrote %s" % (SELF, ", ".join(written) if written else "nothing (up to date)")
            )
            return 0
        if args.region is None:
            raise RefusedError("--target needs --region")
        again = None if args.dry_run else reexec_argv(args.target, args_in)
        if again is not None:
            env = {
                **os.environ,
                PROFILES_ENV: BENCH_PROFILE if args.target == BENCH_TARGET else STABLE_PROFILE,
            }
            return subprocess.run(again, env=env, check=False).returncode
        run_deploy(
            root,
            args.target,
            args.region,
            env=dict(os.environ),
            run=lambda argv_, cwd, stdin, env: run_process(
                wrangler.resolve(argv_, cwd, env), cwd, stdin, env
            ),
            fetch=fetch_url,
            dry_run=args.dry_run,
            smoke_only=args.smoke_only,
            rollback=args.rollback,
            record=args.record,
        )
    except RefusedError as exc:
        for line in exc.lines or (str(exc),):
            log.error(line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
