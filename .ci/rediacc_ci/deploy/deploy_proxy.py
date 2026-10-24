#!/usr/bin/env python3
"""Port of the retired `.ci/scripts/deploy/deploy-proxy.sh`; its answers are frozen in `.ci/rediacc_ci/tests/goldens/twins/deploy.deploy-proxy.jsonl`.

Builds the CLI bundle the executor container image ships, then deploys the proxy Worker and that container image to Cloudflare. MANUAL ONLY: the twin's header says why in four lines, and the reason is not caution about the tooling -- the executor is the component that holds customers' config keys in memory and the only thing allowed to open SSH to their machines, so a human stays
in the loop until it has run in front of real traffic. CI drives the `--dry-run` path.

IT IS THE ODD ONE OUT OF THE THREE DEPLOY SCRIPTS, in four ways that all matter to a caller:

  * IT BUILDS FIRST, AND THE BUILD IS TWO `npm run build --workspace` RUNS FROM
    THE REPO ROOT (:46-48), before it has looked at the worker directory at all.
  * IT NEVER CHECKS THAT `workers/proxy` EXISTS. There is no `-f`/`-d` guard
    like the other two have; `cd "$WORKER_DIR"` (:50) simply fails, AFTER the
    full CLI build has run. See `THE_BUILD_RUNS_BEFORE_THE_DIRECTORY_IS_CHECKED`.
  * IT DEMANDS ONLY THE TOKEN. `CLOUDFLARE_ACCOUNT_ID` is named as required in
    the twin's own header (:22) and is never checked anywhere in the file. See
    `THE_ACCOUNT_ID_IS_DOCUMENTED_AND_UNCHECKED`.
  * IT PASSES NO `--config` TO WRANGLER. The other two name their config file;
    this one relies on wrangler's own discovery from cwd.

NOTHING HERE REACHES CLOUDFLARE, AND NOTHING BUILDS, IN A TEST. `npm` and `npx` are the only external tools, so the differential (`.ci/rediacc_ci/tests/test_deploy_deploy_proxy.py`) puts RECORDING FAKES for both on a scratch PATH and points both sides at a fixture repo root; the fake `npm` is what stops the real `@rediacc/shared` and `@rediacc/cli` builds from running.
`.ci/shadow/w7p5a-status.json` records this path as blocked only for the "one real run" clause and says in as many words that the mocked parity ledger is separate, achievable work. This is that piece.

TWO DIVERGENCES IN TEXT NOBODY PARSES, both bash's own diagnostics:

  1. `: "${CLOUDFLARE_API_TOKEN:?...}"` (:38) prints the SCRIPT PATH AS INVOKED
     and a bash LINE NUMBER before the message:

         .ci/scripts/deploy/deploy-proxy.sh: line 29: CLOUDFLARE_API_TOKEN: CLOUDFLARE_API_TOKEN is required (use a scoped token, never the global API key)

     Note the doubled name, exactly as in `set-www-worker-secrets.sh`: the
     twin's own message begins with the variable name, so bash says it twice.
     `MISSING_AUTH_MSG` carries the `VAR: message` half, same stream, same exit 1.
  2. A failed `cd` (:50) is bash's message with the same path-and-line prefix.
     `CD_FAILED` carries the `cd: <dir>: No such file or directory` half, same
     stream, same exit 1.

`:?` IS AN UNSET-OR-EMPTY TEST, so `CLOUDFLARE_API_TOKEN=` refuses exactly as an
absent one does. Driven, and pinned in the differential.

A REAL DEPLOY ALSO BUILDS RENET AND SMOKE-TESTS (2026-09-24, PLAN-cloudflare-proxy.md B2 and missing test 10). The image runs the CLI outside a SEA, which executes the renet on PATH and uploads that same binary to a machine whose renet differs, so the deploy builds a release renet at the current version (`rediacc_ci.version.resolve_version --current` in process, then `python3 -m rediacc_ci.build.build_renet --version V` as a child, so its working directory changes stay out of this process) and stages it in `workers/proxy/renet/`. That is why a real deploy refuses before any build without `ACCOUNT_ED25519_PUBLIC_KEY`: a renet built without it cannot verify a licence. After `wrangler deploy` both twins GET `/v1/health` (must be 200) and an unauthenticated `/v1/server-info` (must be 401) through `curl`, at the host `wrangler.toml`'s route names. A dry run does none of this, because `wrangler deploy --dry-run` never builds the image.

A BENCH TARGET, AND THE BENCH-ONLY GATE IN FRONT OF IT (operator order 2026-10-24, so PLAN-cloudflare-proxy Phase 2 runs on bench without the operator). `--target bench` deploys `workers/proxy/wrangler.bench.toml` with `--config`, smokes the route that file names, and runs under the `deploy-proxy-bench` Bitwarden profile (`.ci/config/secret-supply.json`), re-executing itself under it when the profile is not already bound, so the image's renet verifies with the DEV public key bench signs with. Before the profile, the token or any build, `bench_refusals` reads that file and refuses (exit 1) unless the name is exactly `rediacc-proxy-bench`, the only route `proxy.bench.rediacc.com`, `ACCOUNT_URL` exactly `https://bench.rediacc.com`, and every `[[services]]` entry a bench Worker with `ACCOUNT` bound to `rediacc-account-bench`; a name or route naming eu, another region or production refuses by name, and an `[env.*]` table refuses because it could rename the Worker. That is the shape the account server gives `EMAIL_CAPTURE_D1`: a bench-only switch refused off bench. `--target eu` (the default) is untouched, byte for byte.

K=5 LEDGER: `.ci/shadow/w7p6-deploy-proxy.observations.jsonl`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.parse

from rediacc_ci import log
from rediacc_ci.core import common, https
from rediacc_ci.version import resolve_version
from rediacc_ci.well_known import BENCH_ORIGIN, PROXY_BENCH_HOST

# This module's own dotted name, the prefix of every diagnostic it prints (the same name `python3 -m` runs it by). A literal, because `__name__` is `__main__` under `-m`.
SELF = "rediacc_ci.deploy.deploy_proxy"

# The `${CLOUDFLARE_API_TOKEN:?...}` stand-in named in the docstring. The twin's
# message already begins with the variable name, so this reads it twice; kept, because that is the text.
MISSING_AUTH_MSG = (
    "CLOUDFLARE_API_TOKEN: CLOUDFLARE_API_TOKEN is required "
    "(use a scoped token, never the global API key)"
)

# `$REPO_ROOT/workers/proxy` (:34).
WORKER_SUBDIR = ("workers", "proxy")

# `REGION="${ARG_REGION:-eu}"` (:35). The region for the proxy lives in `workers/proxy/wrangler.toml` (Worker `rediacc-proxy-eu`, route `proxy.eu.rediacc.com`), never in a flag, so the only region this script can deploy is the one that file names. The twin read `--region`, printed it in one log line and passed it to no argv, so `--region us` got a message saying `us` and a deploy of the eu config. That defect is REPAIRED here, not reproduced (PLAN-cloudflare-proxy.md, the `--region` box): any other value is refused before any build, and the differential reads the twin's frozen answer to show what it did instead.
DEFAULT_REGION = "eu"
SUPPORTED_REGIONS = (DEFAULT_REGION,)


def region_refusal(region: str) -> str:
    """The refusal for a region this script cannot deploy, naming the file that fixes the region and the way forward."""
    return (
        "--region %s is not supported: the proxy's region is fixed by workers/proxy/wrangler.toml "
        "(Worker rediacc-proxy-eu, whose route that file names), so only --region %s deploys. "
        "Another region needs its own wrangler config and a deploy that names it."
        % (region, DEFAULT_REGION)
    )


# `--target`: which Worker config deploys. `eu` is `wrangler.toml` and the twin's whole behaviour; `bench` is `wrangler.bench.toml`, admitted only through `bench_refusals`.
DEFAULT_TARGET = "eu"
BENCH_TARGET = "bench"
SUPPORTED_TARGETS = (DEFAULT_TARGET, BENCH_TARGET)
EU_CONFIG = "wrangler.toml"
BENCH_CONFIG = "wrangler.bench.toml"
BENCH_CONFIG_REL = "workers/proxy/" + BENCH_CONFIG

# What the bench config must name, exactly (workers/account/wrangler.bench.toml is the account Worker it reaches).
BENCH_NAME = "rediacc-proxy-bench"
BENCH_ROUTE = PROXY_BENCH_HOST
BENCH_ACCOUNT_URL = BENCH_ORIGIN
BENCH_ACCOUNT_BINDING = "ACCOUNT"
BENCH_ACCOUNT_SERVICE = "rediacc-account-bench"
# Tokens of a name or route (split on `.`, `-`, `_`) that mean "not bench": the regions and the production words.
NOT_BENCH_TOKENS = ("eu", "us", "asia", "prod", "production", "stable", "edge")
NAME_TOKEN_SPLIT = re.compile(r"[.\-_]")

# The Bitwarden profile a bench deploy runs under: the Workers token, the account id, and the DEV public key bench signs with, renamed to the name the renet build reads.
BENCH_PROFILE = "deploy-proxy-bench"
PROFILES_ENV = "REDIACC_BWS_PROFILES"


def target_refusal(target: str) -> str:
    return "--target %s is not supported: only %s deploys." % (
        target,
        " or ".join(SUPPORTED_TARGETS),
    )


def _routes(config: dict) -> list[str]:
    """Every route pattern a wrangler config names, through `routes` or `route`, string or table form."""
    raw = config.get("routes")
    entries = list(raw) if isinstance(raw, list) else []
    if "route" in config:
        entries.append(config["route"])
    return [str(e.get("pattern", "")) if isinstance(e, dict) else str(e) for e in entries]


def _not_bench_tokens(value: str) -> list[str]:
    return [t for t in NAME_TOKEN_SPLIT.split(value.lower()) if t in NOT_BENCH_TOKENS]


def bench_refusals(text: str) -> list[str]:
    """Why a bench deploy of this `wrangler.bench.toml` text must not run; empty when it may."""
    try:
        config = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return ["%s does not parse as TOML: %s" % (BENCH_CONFIG_REL, exc)]
    out: list[str] = []
    name = config.get("name")
    if name != BENCH_NAME:
        out.append("name is %r, not %r" % (name, BENCH_NAME))
    routes = _routes(config)
    if routes != [BENCH_ROUTE]:
        out.append("routes are %r, not exactly [%r]" % (routes, BENCH_ROUTE))
    for label, value in [("name", str(name or ""))] + [("route", r) for r in routes]:
        hits = _not_bench_tokens(value)
        if hits:
            out.append("%s %r names %s, which is not bench" % (label, value, "/".join(hits)))
    account_url = (config.get("vars") or {}).get("ACCOUNT_URL")
    if account_url != BENCH_ACCOUNT_URL:
        out.append("vars.ACCOUNT_URL is %r, not %r" % (account_url, BENCH_ACCOUNT_URL))
    services = config.get("services") or []
    account = [
        s for s in services if isinstance(s, dict) and s.get("binding") == BENCH_ACCOUNT_BINDING
    ]
    if [s.get("service") for s in account] != [BENCH_ACCOUNT_SERVICE]:
        out.append(
            "the %s service binding is %r, not exactly one binding to %r"
            % (BENCH_ACCOUNT_BINDING, [s.get("service") for s in account], BENCH_ACCOUNT_SERVICE)
        )
    for entry in services:
        service = str(entry.get("service", "")) if isinstance(entry, dict) else str(entry)
        if not service.endswith("-" + BENCH_TARGET):
            out.append("[[services]] binds %r, which is not a bench Worker" % service)
    if "env" in config:
        out.append(
            "an [env.*] table can rename the Worker or its routes; a bench config carries none"
        )
    return out


def bench_gate(worker_dir: pathlib.Path) -> int:
    """The bench-only gate: 0 when `wrangler.bench.toml` names bench and nothing else, else 1 with every reason."""
    path = worker_dir / BENCH_CONFIG
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        reasons = ["%s cannot be read: %s" % (BENCH_CONFIG_REL, exc.strerror or exc)]
    else:
        reasons = bench_refusals(text)
    for reason in reasons:
        log.error("--target bench refused: %s" % reason)
    return 1 if reasons else 0


def reexec_argv(argv: list[str]) -> list[str]:
    """This same run under the deploy-proxy-bench profile."""
    return [
        sys.executable,
        "-m",
        "rediacc_ci.core.bws_env",
        "exec",
        "--profile",
        BENCH_PROFILE,
        "--",
        sys.executable,
        "-m",
        SELF,
        *argv,
    ]


def profile_bound() -> bool:
    return BENCH_PROFILE in (os.environ.get(PROFILES_ENV) or "").split(",")


# `DRY_RUN="${ARG_DRY_RUN:-false}"` (:36) and the one value that branches (:52).
# The comparison is against the literal `true`, which is also what a bare `--dry-run` with no value produces through `parse_args`. Anything else -- `1`, `yes`, `True` -- IS A REAL DEPLOY.
TRUE = "true"
DEFAULT_DRY_RUN = "false"

# `--outdir /tmp/rediacc-proxy-dry-run` (:54). A FIXED path in /tmp, not a mktemp: two concurrent dry runs write the same directory, and so does anything
# else that picks the name. Reproduced as the literal it is.
DRY_RUN_OUTDIR = "/tmp/rediacc-proxy-dry-run"

# The two workspace builds (:47-48), in order.
WORKSPACES = ("@rediacc/shared", "@rediacc/cli")

# The three closing lines (:81-83), byte for byte including the two-space indent on the middle one. They go through `log_info`, so each gets the green check glyph -- including the one that is a command to copy, which is why they are quoted here whole rather than assembled.
CLOSING_LINES = (
    "Deployed. The executor still needs its own account token:",
    "  npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml",
    "That token must carry the proxy:exec and audit:write scopes and belong to the Rediacc org.",
)

# The bench deploy's closing lines: the same three, naming the bench config and a bench org.
BENCH_CLOSING_LINES = (
    CLOSING_LINES[0],
    "  npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.bench.toml",
    "That token must carry the proxy:exec and audit:write scopes and belong to a %s org."
    % BENCH_ORIGIN.removeprefix("https://"),
)

# The real-deploy refusal when renet could not be built with the licence key.
MISSING_KEY = (
    "ACCOUNT_ED25519_PUBLIC_KEY is required: the image's renet is uploaded to machines, "
    "and without the key it cannot verify a licence"
)

# The directory holding the `rediacc_ci` package (`.ci`).
PACKAGE_PARENT = str(pathlib.Path(__file__).resolve().parents[2])

# The renet the image ships: built into private/bin by `rediacc_ci.build.build_renet`, staged here for the Dockerfile.
RENET_BINARY = "renet-linux-amd64"
RENET_BUILT = ("private", "bin", RENET_BINARY)
RENET_STAGE = "renet"

# `sed -n 's/.*pattern = "\([^"]*\)".*/\1/p' wrangler.toml | head -n 1`: the first route pattern.
ROUTE_PATTERN = re.compile(r'.*pattern = "([^"]*)".*')

SMOKE_PASSED = "Smoke test passed: /v1/health 200, unauthenticated /v1/server-info 401."

# THE TWO DEFECTS NAMED IN THE DOCSTRING, as constants so the differential can assert them by name rather than restating the sentences. Both driven against the real twin on 2026-09-13 in a fixture tree; both reproduced, not repaired, because repairing a twin is a cutover decision and this file is not it.
#
# 1. THE BUILD RUNS BEFORE THE DIRECTORY IS CHECKED. With `workers/proxy` absent, both `npm run build` calls complete and only then does the run die on `cd`. Measured in the fixture: two recorded npm calls, then `line 36: cd: .../workers/proxy: No such file or directory`, exit 1. 2. THE ACCOUNT ID IS DOCUMENTED AND UNCHECKED. The header lists `CLOUDFLARE_ACCOUNT_ID` under
# "Requires:" and no line reads it. A deploy
#      with the token set and the account id absent gets all the way to wrangler
# before anything notices, after the build.
THE_BUILD_RUNS_BEFORE_THE_DIRECTORY_IS_CHECKED = True
THE_ACCOUNT_ID_IS_DOCUMENTED_AND_UNCHECKED = True


def build_argv(workspace: str) -> list[str]:
    """`npm run build --workspace <name>` (:47-48)."""
    return ["npm", "run", "build", "--workspace", workspace]


def dry_run_argv(config: str | None = None) -> list[str]:
    """`npx wrangler deploy --dry-run --outdir /tmp/rediacc-proxy-dry-run` (:54), plus `--config` for bench."""
    argv = ["npx", "wrangler", "deploy", "--dry-run", "--outdir", DRY_RUN_OUTDIR]
    return [*argv, "--config", config] if config else argv


def deploy_argv(config: str | None = None) -> list[str]:
    """`npx wrangler deploy` (:65). NO `--config` for eu, unlike both siblings; bench names its file."""
    argv = ["npx", "wrangler", "deploy"]
    return [*argv, "--config", config] if config else argv


def build_renet_argv(repo_root: pathlib.Path, version: str) -> list[str]:
    """`python3 -m rediacc_ci.build.build_renet --version "$VERSION"`, the module that replaced `build-renet.sh`."""
    del repo_root
    return [sys.executable, "-m", "rediacc_ci.build.build_renet", "--version", version]


def package_env() -> dict[str, str]:
    """The environment for a `python3 -m rediacc_ci...` child: this checkout's `.ci` first on `PYTHONPATH`, as an ABSOLUTE path, because the run has already changed directory and a relative entry would no longer resolve."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = PACKAGE_PARENT + (os.pathsep + existing if existing else "")
    return env


def curl_argv(url: str, pin: str | None = None) -> list[str]:
    """`curl -sS -o /dev/null -w '%{http_code}' --max-time 30 <url>`, with `--resolve host:443:<pin>` ahead of the URL when a DoH answer pins the address."""
    argv = ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "30"]
    if pin:
        argv += ["--resolve", "%s:443:%s" % (urllib.parse.urlsplit(url).hostname, pin)]
    return [*argv, url]


# A brand-new custom domain is often NXDOMAIN on the local resolver for a while: the zone's negative TTL is up to 1800 s, and the first lookup before the record existed is cached. Only a curl "could not resolve host" (exit 6) is retried, for RESOLVE_WINDOW_S seconds; after that the address is read over DNS-over-HTTPS and pinned with `--resolve`. Both are set by the environment so a test (or an operator) can shorten or disable them; an empty `REDIACC_SMOKE_DOH_URL` disables the DoH step.
CURL_RESOLVE_RC = 6
RESOLVE_WINDOW_ENV = "REDIACC_SMOKE_RESOLVE_WINDOW_S"
RESOLVE_INTERVAL_S = 5.0
DEFAULT_RESOLVE_WINDOW_S = "90"
DOH_URL_ENV = "REDIACC_SMOKE_DOH_URL"
DEFAULT_DOH_URL = "https://1.1.1.1/dns-query"
DOH_A_RECORD = 1
DOH_TIMEOUT_S = 10.0


def _resolve_window() -> float:
    try:
        return max(0.0, float(os.environ.get(RESOLVE_WINDOW_ENV, DEFAULT_RESOLVE_WINDOW_S)))
    except ValueError:
        return float(DEFAULT_RESOLVE_WINDOW_S)


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


def _doh_lookup(host: str) -> str | None:
    """The first A record Cloudflare's DoH JSON API holds for `host`, or None (disabled, unreachable, no answer)."""
    base = os.environ.get(DOH_URL_ENV, DEFAULT_DOH_URL)
    if not base:
        return None
    url = "%s?%s" % (base, urllib.parse.urlencode({"name": host, "type": "A"}))
    try:
        request = https.build_request(url, headers={"Accept": "application/dns-json"})
        with https.urlopen(request, timeout=DOH_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    for answer in body.get("Answer") or [] if isinstance(body, dict) else []:
        if isinstance(answer, dict) and answer.get("type") == DOH_A_RECORD and answer.get("data"):
            return str(answer["data"])
    return None


def smoke_host(wrangler_toml: str) -> str:
    """The first `pattern = "..."` in wrangler.toml, as sed prints it (empty when none)."""
    for line in wrangler_toml.splitlines():
        match = ROUTE_PATTERN.fullmatch(line)
        if match:
            return match.group(1)
    return ""


def _curl(url: str, pin: str | None = None) -> tuple[str, int]:
    """`$(curl ... || true)`: curl's stdout and exit status; stderr inherited."""
    proc = subprocess.run(curl_argv(url, pin), stdout=subprocess.PIPE, text=True, check=False)
    return proc.stdout, proc.returncode


class _Fetcher:
    """Issues the smoke's requests. A resolution failure is retried for the window, then answered by a DoH pin shared by every later request; any other outcome (a code, or another curl failure) returns at once."""

    def __init__(self, host: str) -> None:
        self.host = host
        self.pin: str | None = None

    def code(self, url: str) -> str:
        deadline = time.monotonic() + _resolve_window()
        while True:
            out, rc = _curl(url, self.pin)
            if rc != CURL_RESOLVE_RC:
                return out
            if self.pin is None and time.monotonic() >= deadline:
                address = _doh_lookup(self.host)
                if not address:
                    if os.environ.get(DOH_URL_ENV, DEFAULT_DOH_URL):
                        log.error(
                            "%s does not resolve locally (retried %gs) and DNS-over-HTTPS has no answer for it either; the DNS record may not exist yet"
                            % (self.host, _resolve_window())
                        )
                    return out
                log.info(
                    "%s does not resolve locally; DNS-over-HTTPS answers %s, pinning it"
                    % (self.host, address)
                )
                self.pin = address
                return _curl(url, self.pin)[0]
            if self.pin is not None:
                return out
            _sleep(RESOLVE_INTERVAL_S)


def smoke(worker_dir: pathlib.Path, config: str = EU_CONFIG) -> int:
    """The post-deploy smoke: /v1/health 200, then an unauthenticated /v1/server-info 401."""
    host = smoke_host((worker_dir / config).read_text(encoding="utf-8"))
    url = "https://" + host
    log.step("Smoke-testing %s..." % url)
    fetch = _Fetcher(host)
    health = fetch.code(url + "/v1/health")
    if health != "200":
        log.error("Smoke test failed: /v1/health answered %s, expected 200" % (health or "nothing"))
        return 1
    info = fetch.code(url + "/v1/server-info")
    if info != "401":
        log.error(
            "Smoke test failed: an unauthenticated /v1/server-info answered %s, expected 401"
            % (info or "nothing")
        )
        return 1
    log.info(SMOKE_PASSED)
    return 0


def build_and_stage_renet(repo_root: pathlib.Path, worker_dir: pathlib.Path) -> int:
    """Resolve the release version, build renet at it, and stage linux-amd64 for the image."""
    log.step("Building the renet the container image ships...")
    status, out, err = resolve_version.run(["--current"])
    if status != 0:
        sys.stderr.write(err)
        sys.stderr.flush()
        return status  # `set -e` on the assignment
    version = out.rstrip("\n")
    status = _run(build_renet_argv(repo_root, version), env=package_env())
    if status != 0:
        return status  # `set -e`
    built = repo_root.joinpath(*RENET_BUILT)
    try:
        staged = worker_dir / RENET_STAGE / RENET_BINARY
        shutil.copyfile(built, staged)
        # EXECUTABLE BY CONSTRUCTION, a deliberate difference from the twin (2026-09-24, #a2a8491c): `copyfile` drops the mode, and the twin's `cp` onto an existing file keeps THAT file's mode, so a stale non-executable stage survived either way and the Dockerfile's `test -x` guard refused the image on the first Phase 2 deploy.
        staged.chmod(0o755)
    except OSError as exc:
        print("cp: cannot stat '%s': %s" % (built, exc.strerror or ""), file=sys.stderr, flush=True)
        return 1
    return 0


def cd_failed(worker_dir: pathlib.Path, reason: str) -> str:
    """Bash's own `cd` diagnostic (:50), minus its path-and-line prefix.

    The REASON comes from the operating system rather than from a literal, because bash's does too: a `workers/proxy` that is a regular file reads "Not a directory", one without `+x` on a parent reads "Permission denied", and only an absent one reads "No such file or directory". `os.strerror` produces the same three strings from the same three errnos.
    """
    return "cd: %s: %s" % (worker_dir, reason)


def _run(argv: list[str], *, env: dict[str, str] | None = None) -> int:
    """One child with BOTH streams inherited, as the twin leaves them."""
    return subprocess.run(argv, check=False, env=env).returncode


def main(argv: list[str]) -> int:
    try:
        args = common.parse_args(argv)
    except common.RefusalError as exc:
        print("%s: %s" % (SELF, exc.lines[0]), file=sys.stderr, flush=True)
        return exc.code

    repo_root = common.repo_root()
    worker_dir = repo_root.joinpath(*WORKER_SUBDIR)
    region = args.get("ARG_REGION") or DEFAULT_REGION
    dry_run = args.get("ARG_DRY_RUN") or DEFAULT_DRY_RUN
    target = args.get("ARG_TARGET") or DEFAULT_TARGET
    bench = target == BENCH_TARGET
    config = BENCH_CONFIG if bench else None

    if region not in SUPPORTED_REGIONS:
        # Refused first, before the token check and before any build: it is an argument error, and a deploy of the wrong region's config is not one a caller asked for.
        log.error(region_refusal(region))
        return 1

    if target not in SUPPORTED_TARGETS:
        log.error(target_refusal(target))
        return 1

    if bench:
        # The bench-only gate: before the profile, the token and any build, so a config that reaches eu or production never gets credentials.
        if bench_gate(worker_dir) != 0:
            return 1
        if not profile_bound():
            return _run(reexec_argv(argv), env=package_env())

    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        # THE DIVERGENCE: bash prefixes this with `<script>: line 29: `.
        print(MISSING_AUTH_MSG, file=sys.stderr, flush=True)
        return 1

    if dry_run != TRUE and not os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY"):
        log.error(MISSING_KEY)
        return 1

    log.step("Building the CLI bundle the container image ships...")
    os.chdir(repo_root)
    for workspace in WORKSPACES:
        status = _run(build_argv(workspace))
        if status != 0:
            return status  # `set -e`

    try:
        os.chdir(worker_dir)
    except OSError as exc:
        # THE DIVERGENCE, and the defect: this is reached only after the build.
        print(cd_failed(worker_dir, exc.strerror or ""), file=sys.stderr, flush=True)
        return 1

    if dry_run == TRUE:
        log.step("Dry run: type-checking and compiling the worker without deploying...")
        status = _run(dry_run_argv(config))
        if status != 0:
            return status  # `set -e`
        log.info("Dry run passed. Nothing was deployed.")
        return 0

    status = build_and_stage_renet(repo_root, worker_dir)
    if status != 0:
        return status

    if bench:
        log.step("Deploying the bench proxy worker and container image (config: %s)..." % config)
    else:
        log.step("Deploying the proxy worker and container image (region: %s)..." % region)
    status = _run(deploy_argv(config))
    if status != 0:
        return status  # `set -e`

    status = smoke(worker_dir, config or EU_CONFIG)
    if status != 0:
        return status

    for line in BENCH_CLOSING_LINES if bench else CLOSING_LINES:
        log.info(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
