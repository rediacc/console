"""Deploy the off-box ops-health Worker (workers/ops-health) with the `ops` repo's target file (agent/plans/PLAN-health-checks-local.md W4, D-runner, E4).

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.deploy_ops_health \\
        --targets-ref <repo>@<machine> --config <rdc config> --targets-path <file in the repo> [--write]

All three arguments are required and have no default in code: the repo, its machine and the config name the operator's own infrastructure, which this public tree does not carry (ruling A).

WHAT A RUN DOES, in order:
  1. Reads the target file out of the live repo from this machine: `rdc --config <config> term connect <ref> -c 'cat -- <path>'`, falling back to `rdc repo sync download <ref> --remote-file <path>`. REDIACC_NO_PROVISION=1 is forced in the child, so a read never installs renet or restarts daemons as a side effect (F5). The Worker cannot read the file itself: backups are encrypted chunks and the repo key never leaves the machine (F20).
  2. Validates it against the schema of D-record (the same rules as workers/ops-health/src/targets.ts). An invalid file exits 2 before anything is deployed.
  3. Computes what is deployed now from the Worker's own `/v1/status` (bearer OPS_HEALTH_READ_TOKEN): `targets_sha`, and the `deploy` block that carries the code sha and the salted secret digests a previous run set as vars. A host that does not resolve or connect, or a 404, means a first deploy; any other answer (a 401, a 5xx, a body that is not the status JSON) or a read that dies mid-body stops the run with the deployed state unknown.
  4. Plans the change set: the code (a sha over the Worker source, its wrangler.toml and lockfile, .ci/config/ops-health.json and regions.json), the OPS_HEALTH_TARGETS_SHA var, and each secret whose salted digest differs. An unchanged input plans zero changes and runs nothing.
  5. Dry run (the default) prints the plan. `--write` puts the changed secrets in ONE `wrangler secret bulk` call over stdin, then runs `wrangler deploy` with the three vars (which also applies the Durable Object migration in wrangler.toml). A first deploy runs `wrangler deploy` first, because a secret needs an existing Worker, and deploys once more after the secrets so the digests var is written only once the secrets are in.

EXIT CODES: 0 done (or a dry run printed its plan); 1 a read, a status or a deploy step failed; 2 the target file is invalid or an argument is bad; 3 a required secret is absent from the environment (the caller's setup, not a bad file).

SECRETS NEVER TRAVEL AS ARGUMENTS OR IN OUTPUT. The values come from the environment (`bws_env exec --profile ops-health`) and reach wrangler as a JSON document on stdin. A digest is HMAC-SHA256 keyed with OPS_HEALTH_INGEST_TOKEN and truncated to 16 hex characters, so the var reveals nothing a reader of the dashboard could invert.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import tempfile
import tomllib
import urllib.error
from collections.abc import Callable, Mapping, Sequence

from rediacc_ci import paths
from rediacc_ci.core import https, wrangler
from rediacc_ci.ops import cf_auth

SELF = "rediacc_ci.ops.deploy_ops_health"

WORKER_DIR = ("workers", "ops-health")

# The secrets the Worker reads, in the order they are put. OPS_HEALTH_TARGETS comes from the target file, the rest from the environment.
REQUIRED_SECRETS = (
    "OPS_ALERT_EMAILS",
    "AWS_SES_ACCESS_KEY_ID_EU",
    "AWS_SES_SECRET_ACCESS_KEY_EU",
    "AWS_SES_REGION_EU",
    "OPS_HEALTH_READ_TOKEN",
    "OPS_HEALTH_INGEST_TOKEN",
)
OPTIONAL_SECRETS = ("SPAMHAUS_DQS_KEY",)
TARGETS_NAME = "OPS_HEALTH_TARGETS"

VAR_TARGETS_SHA = "OPS_HEALTH_TARGETS_SHA"
VAR_CODE_SHA = "OPS_HEALTH_CODE_SHA"
VAR_DIGESTS = "OPS_HEALTH_SECRET_DIGESTS"

# The inputs of the deployed bundle, repo-relative. Tests are excluded: they are not in the bundle.
CODE_INPUTS = (
    "workers/ops-health/src",
    "workers/ops-health/wrangler.toml",
    "workers/ops-health/package-lock.json",
    ".ci/config/ops-health.json",
    "regions.json",
)

# The schema of D-record, mirrored from workers/ops-health/src/targets.ts.
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,63}$")
HOST_RE = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
RESERVED_IDS = ("targets", "mailer")
RESERVED_PREFIX = "health:"

EXIT_INVALID = 2
EXIT_FAILED = 1
# The Global API Key names `cf_auth.wrangler_env(scrub_global_key=True)` removes; the caller's copies are never put back.
SCRUBBED_ENV = frozenset({"CF_GLOBAL_API_KEY", "CF_API_KEY", "CF_EMAIL"})
# A secret absent from the environment is the caller's setup, not a bad target file.
EXIT_NO_SECRETS = 3


class TargetsInvalidError(ValueError):
    """The target file breaks the schema; the message names the first problem."""


class ReadFailedError(RuntimeError):
    """Neither rdc path could read the target file."""


class StatusUnreadableError(RuntimeError):
    """`/v1/status` answered, but not with a readable state: a refused token or a server error is never a first deploy."""


def _is_ipv4(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def validate_targets(text: str) -> int:
    """The number of probes the file declares (dnsbl zones included), or TargetsInvalidError."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TargetsInvalidError("not valid JSON: %s" % exc.msg) from None
    if not isinstance(doc, dict):
        raise TargetsInvalidError("the document is not an object")
    if doc.get("version") != 1 or isinstance(doc.get("version"), bool):
        raise TargetsInvalidError("version must be 1")
    probes = doc.get("probes")
    if not isinstance(probes, list):
        raise TargetsInvalidError("probes must be an array")
    ids: list[str] = []
    for index, probe in enumerate(probes):
        where = "probes[%d]" % index
        if not isinstance(probe, dict):
            raise TargetsInvalidError("%s is not an object" % where)
        pid, kind, host = probe.get("id"), probe.get("kind"), probe.get("host")
        if not isinstance(pid, str) or not ID_RE.match(pid):
            raise TargetsInvalidError("%s.id must match %s" % (where, ID_RE.pattern))
        if not isinstance(kind, str) or not kind:
            raise TargetsInvalidError("%s.kind must be a non-empty string" % where)
        if not isinstance(host, str) or not HOST_RE.match(host):
            raise TargetsInvalidError("%s.host must be a host name" % where)
        port = probe.get("port")
        if port is not None and (
            isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535
        ):
            raise TargetsInvalidError("%s.port must be an integer 1..65535" % where)
        path = probe.get("path")
        if path is not None and (not isinstance(path, str) or not path.startswith("/")):
            raise TargetsInvalidError("%s.path must start with /" % where)
        expect = probe.get("expect")
        if expect is not None and (not isinstance(expect, str) or not expect):
            raise TargetsInvalidError("%s.expect must be a non-empty string" % where)
        ids.append(pid)
    dnsbl = doc.get("dnsbl")
    if dnsbl is not None:
        if not isinstance(dnsbl, dict):
            raise TargetsInvalidError("dnsbl must be an object")
        ip, zones = dnsbl.get("ip"), dnsbl.get("zones")
        if not _is_ipv4(ip):
            raise TargetsInvalidError("dnsbl.ip must be an IPv4 address")
        if not isinstance(zones, list) or any(
            not isinstance(z, str) or not HOST_RE.match(z) for z in zones
        ):
            raise TargetsInvalidError("dnsbl.zones must be an array of zone names")
        ids.extend("dnsbl:%s" % z.lower() for z in zones)
    seen: set[str] = set()
    for pid in ids:
        if pid in seen:
            raise TargetsInvalidError("duplicate probe id %s" % pid)
        if pid in RESERVED_IDS or pid.startswith(RESERVED_PREFIX):
            raise TargetsInvalidError("probe id %s is reserved" % pid)
        seen.add(pid)
    return len(ids)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def code_sha(root: pathlib.Path) -> str:
    """One sha over every bundled input, path and bytes, in sorted order."""
    digest = hashlib.sha256()
    files: list[pathlib.Path] = []
    for rel in CODE_INPUTS:
        target = root / rel
        if target.is_dir():
            files.extend(p for p in target.rglob("*") if p.is_file() and "__tests__" not in p.parts)
        elif target.is_file():
            files.append(target)
    for path in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def secret_digest(name: str, value: str, salt: str) -> str:
    return hmac.new(salt.encode(), ("%s\0%s" % (name, value)).encode(), hashlib.sha256).hexdigest()[
        :16
    ]


def encode_digests(digests: Mapping[str, str]) -> str:
    """The var form the Worker parses back (`NAME=hex,NAME=hex`, sorted): no quote or colon, so it survives `--var NAME:value`."""
    return ",".join("%s=%s" % (k, digests[k]) for k in sorted(digests))


@dataclasses.dataclass
class Deployed:
    """What `/v1/status` says is deployed now."""

    targets_sha: str | None
    code_sha: str | None
    digests: dict[str, str]


@dataclasses.dataclass
class Plan:
    first_deploy: bool
    code_changed: bool
    targets_changed: bool
    secrets: dict[str, str]  # name -> value, only the changed ones
    vars: dict[str, str]

    def changes(self) -> list[str]:
        out: list[str] = []
        if self.first_deploy:
            out.append("worker:create")
        if self.code_changed:
            out.append("code")
        out.extend("secret:%s" % name for name in self.secrets)
        if self.targets_changed:
            out.append("var:%s" % VAR_TARGETS_SHA)
        return out


def make_plan(
    *, targets_text: str, env: Mapping[str, str], code: str, deployed: Deployed | None
) -> Plan:
    values: dict[str, str] = {TARGETS_NAME: targets_text}
    for name in REQUIRED_SECRETS:
        values[name] = env[name]
    for name in OPTIONAL_SECRETS:
        if env.get(name):
            values[name] = env[name]
    salt = env["OPS_HEALTH_INGEST_TOKEN"]
    digests = {name: secret_digest(name, value, salt) for name, value in values.items()}
    targets_sha = sha256_hex(targets_text.encode())
    vars_ = {VAR_TARGETS_SHA: targets_sha, VAR_CODE_SHA: code, VAR_DIGESTS: encode_digests(digests)}
    if deployed is None:
        return Plan(True, True, True, dict(values), vars_)
    changed = {n: v for n, v in values.items() if deployed.digests.get(n) != digests[n]}
    return Plan(
        first_deploy=False,
        code_changed=deployed.code_sha != code,
        targets_changed=deployed.targets_sha != targets_sha,
        secrets=changed,
        vars=vars_,
    )


Runner = Callable[..., subprocess.CompletedProcess]


def _run(argv: Sequence[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), check=False, **kwargs)


def rdc_env(base: Mapping[str, str]) -> dict[str, str]:
    """The rdc child's environment: REDIACC_NO_PROVISION=1 forced, never inherited (F5)."""
    env = dict(base)
    env["REDIACC_NO_PROVISION"] = "1"
    return env


def _is_json(text: str) -> bool:
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def read_targets(
    root: pathlib.Path,
    ref: str,
    config: str,
    path: str,
    run: Runner = _run,
    base_env: Mapping[str, str] | None = None,
) -> str:
    """The target file's text, read through `rdc term connect`, falling back to `rdc repo sync download`."""
    rdc = str(root / "rdc.sh")
    env = rdc_env(os.environ if base_env is None else base_env)
    first = run(
        [
            rdc,
            "--config",
            config,
            "term",
            "connect",
            ref,
            "-c",
            "cat -- '%s'" % path.replace("'", "'\\''"),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    # Only a clean JSON answer counts: a login banner or a motd on stdout falls through to the file transfer.
    if first.returncode == 0 and _is_json(first.stdout):
        return first.stdout
    with tempfile.TemporaryDirectory(prefix="ops-health-targets-") as scratch:
        second = run(
            [
                rdc,
                "--config",
                config,
                "repo",
                "sync",
                "download",
                ref,
                "--local",
                scratch,
                "--remote-file",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        landed = pathlib.Path(scratch) / pathlib.PurePosixPath(path).name
        if second.returncode == 0 and landed.is_file():
            return landed.read_text(encoding="utf-8")
    raise ReadFailedError(
        "could not read %s from %s: term connect exited %d (%s); sync download exited %d (%s)"
        % (
            path,
            ref,
            first.returncode,
            first.stderr.strip()[-300:],
            second.returncode,
            second.stderr.strip()[-300:],
        )
    )


def status_url(root: pathlib.Path) -> str:
    """`https://<custom domain>/v1/status`, from the route in workers/ops-health/wrangler.toml."""
    doc = tomllib.loads((root.joinpath(*WORKER_DIR) / "wrangler.toml").read_text(encoding="utf-8"))
    for route in doc.get("routes", []):
        if isinstance(route, dict) and route.get("custom_domain"):
            return "https://%s/v1/status" % route["pattern"]
    raise RuntimeError("workers/ops-health/wrangler.toml has no custom_domain route")


def fetch_deployed(url: str, token: str) -> Deployed | None:
    """The deployed state from `/v1/status`; None only when no Worker answers there (a first deploy).

    A first deploy is a host that does not resolve or refuses the connection, or a 404; a connect or send timeout is neither, so it raises too (a Worker behind a slow path is not a missing one). Any other HTTP status (a 401 from a rotated read token, a 5xx), a stall or malformed reply after the connection is made, or an unreadable body raises StatusUnreadableError: reading it as a first deploy would re-put every secret and run the create deploy over a Worker that exists.
    """
    request = https.build_request(url, headers={"Authorization": "Bearer %s" % token})
    try:
        response = https.urlopen(request, timeout=20)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise StatusUnreadableError("%s answered HTTP %d" % (url, exc.code)) from exc
    except urllib.error.URLError as exc:
        # urllib wraps every OSError of h.request() in URLError, and that call also SENDS the request once connected, so a reset or a broken pipe arrives here too. Only a host that does not resolve or refuses the connection is "no Worker answers"; any other reason is a Worker that may exist.
        if isinstance(exc.reason, (socket.gaierror, ConnectionRefusedError)):
            return None
        if isinstance(exc.reason, TimeoutError):
            raise StatusUnreadableError(
                "%s timed out while connecting or sending: %s" % (url, exc)
            ) from exc
        raise StatusUnreadableError("%s failed after the request began: %s" % (url, exc)) from exc
    except (TimeoutError, OSError, http.client.HTTPException) as exc:
        # urllib lets these escape only once the connection is made (a stall waiting for headers, a reset, a malformed reply): a Worker that exists and answers badly, never a first deploy.
        raise StatusUnreadableError("%s answered badly: %s" % (url, exc)) from exc
    # The connection is made: a stall or a reset from here on is a Worker that answers and then fails, never a first deploy.
    with response:
        try:
            raw = response.read()
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            raise StatusUnreadableError(
                "%s dropped the connection while answering: %s" % (url, exc)
            ) from exc
    try:
        body = json.loads(raw)
    except ValueError as exc:
        # JSONDecodeError, and the UnicodeDecodeError a body of invalid UTF-8 raises first.
        raise StatusUnreadableError("%s answered a body that is not JSON" % url) from exc
    if not isinstance(body, dict):
        raise StatusUnreadableError("%s answered JSON that is not an object" % url)
    deploy = body.get("deploy")
    if deploy is None:
        deploy = {}
    digests = deploy.get("secret_digests") if isinstance(deploy, dict) else None
    if not isinstance(deploy, dict) or not (digests is None or isinstance(digests, dict)):
        raise StatusUnreadableError("%s answered a deploy block that is not an object" % url)
    return Deployed(
        targets_sha=body.get("targets_sha"),
        code_sha=deploy.get("code_sha"),
        digests=dict(digests or {}),
    )


def deploy_argv(vars_: Mapping[str, str]) -> list[str]:
    argv = [*wrangler.ARGV, "deploy"]
    for name in (VAR_TARGETS_SHA, VAR_CODE_SHA, VAR_DIGESTS):
        argv += ["--var", "%s:%s" % (name, vars_[name])]
    return argv


def secret_bulk_argv() -> list[str]:
    return [*wrangler.ARGV, "secret", "bulk"]


def execute(
    plan: Plan, worker_dir: pathlib.Path, env: Mapping[str, str], run: Runner = _run
) -> int:
    """Runs the plan with wrangler; 0 on success, the first failing step's status otherwise."""

    def deploy(vars_: Mapping[str, str]) -> int:
        print("%s: wrangler deploy (applies the Durable Object migration)" % SELF)
        return run(deploy_argv(vars_), cwd=str(worker_dir), env=dict(env)).returncode

    if plan.first_deploy:
        status = deploy({**plan.vars, VAR_DIGESTS: ""})
        if status:
            return status
    if plan.secrets:
        print("%s: wrangler secret bulk (%s)" % (SELF, ", ".join(sorted(plan.secrets))))
        status = run(
            secret_bulk_argv(),
            cwd=str(worker_dir),
            env=dict(env),
            input=json.dumps(plan.secrets),
            text=True,
        ).returncode
        if status:
            return status
    return deploy(plan.vars)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python3 -m %s" % SELF, description=__doc__.splitlines()[0]
    )
    parser.add_argument("--targets-ref", required=True, help="the `ops` repo ref, <repo>@<machine>")
    parser.add_argument("--config", required=True, help="the rdc config that reaches the machine")
    parser.add_argument(
        "--targets-path", required=True, help="the target file, relative to the repo root"
    )
    parser.add_argument(
        "--write", action="store_true", help="deploy; without it the run only prints the plan"
    )
    return parser.parse_args(list(argv))


@dataclasses.dataclass
class Seams:
    """Everything a test replaces: the subprocess runner, the status read and the Cloudflare credential."""

    run: Runner = _run
    fetch_deployed: Callable[[str, str], Deployed | None] = fetch_deployed
    wrangler_env: (
        Callable[[Mapping[str, str]], tuple[dict[str, str], Callable[[], None]]] | None
    ) = None


def _cloudflare_env(base: Mapping[str, str]) -> tuple[dict[str, str], Callable[[], None]]:

    auth = cf_auth.resolve(cf_auth.DEFAULT_ACCOUNT_ID)
    try:
        if auth.created:
            cf_auth.await_propagation(auth)
        env = cf_auth.wrangler_env(auth, cf_auth.DEFAULT_ACCOUNT_ID, scrub_global_key=True)
    except BaseException:
        # The credential this run used is destroyed on a failure before the caller holds its cleanup, exactly as on the normal path (`self_destruct` deletes the token in use, minted by this run or supplied to it).
        cf_auth.self_destruct(auth)
        raise
    for name, value in base.items():
        if name not in SCRUBBED_ENV:
            env.setdefault(name, value)
    return env, lambda: cf_auth.self_destruct(auth)


def main(
    argv: Sequence[str], seams: Seams | None = None, environ: Mapping[str, str] | None = None
) -> int:
    seams = seams or Seams()
    env = dict(os.environ if environ is None else environ)
    args = parse_args(argv)
    root = paths.repo_root()
    worker_dir = root.joinpath(*WORKER_DIR)

    try:
        text = read_targets(root, args.targets_ref, args.config, args.targets_path, seams.run, env)
    except ReadFailedError as exc:
        print("%s: %s" % (SELF, exc), file=sys.stderr)
        return EXIT_FAILED
    try:
        count = validate_targets(text)
    except TargetsInvalidError as exc:
        print(
            "%s: the target file %s is invalid: %s; nothing was deployed"
            % (SELF, args.targets_path, exc),
            file=sys.stderr,
        )
        return EXIT_INVALID
    missing = [name for name in REQUIRED_SECRETS if not env.get(name)]
    if missing:
        print(
            "%s: missing %s; run under `PYTHONPATH=.ci python3 -m rediacc_ci.core.bws_env exec --profile ops-health --`"
            % (SELF, ", ".join(missing)),
            file=sys.stderr,
        )
        return EXIT_NO_SECRETS

    try:
        deployed = seams.fetch_deployed(status_url(root), env["OPS_HEALTH_READ_TOKEN"])
    except StatusUnreadableError as exc:
        print(
            "%s: %s; the deployed state is unknown, so nothing was deployed (check OPS_HEALTH_READ_TOKEN against the Worker)"
            % (SELF, exc),
            file=sys.stderr,
        )
        return EXIT_FAILED
    plan = make_plan(targets_text=text, env=env, code=code_sha(root), deployed=deployed)
    changes = plan.changes()
    print(
        "%s: target file %s from %s: %d probe(s), sha256 %s"
        % (SELF, args.targets_path, args.targets_ref, count, plan.vars[VAR_TARGETS_SHA])
    )
    if not changes:
        print("%s: 0 changes; the deployed Worker matches" % SELF)
        return 0
    print("%s: %d change(s): %s" % (SELF, len(changes), ", ".join(changes)))
    if not args.write:
        print("%s: dry run; re-run with --write to deploy" % SELF)
        return 0

    make_env = seams.wrangler_env or _cloudflare_env
    child_env, cleanup = make_env(env)
    try:
        status = execute(plan, worker_dir, child_env, seams.run)
    finally:
        cleanup()
    if status:
        print(
            "%s: a wrangler step exited %d; the digests var was not written, so a re-run retries"
            % (SELF, status),
            file=sys.stderr,
        )
        return EXIT_FAILED
    print("%s: deployed (%s)" % (SELF, ", ".join(changes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
