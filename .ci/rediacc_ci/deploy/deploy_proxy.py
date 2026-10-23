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

K=5 LEDGER: `.ci/shadow/w7p6-deploy-proxy.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common
from rediacc_ci.version import resolve_version

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
        "(Worker rediacc-proxy-eu, route proxy.eu.rediacc.com), so only --region %s deploys. "
        "Another region needs its own wrangler config and a deploy that names it."
        % (region, DEFAULT_REGION)
    )


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


def dry_run_argv() -> list[str]:
    """`npx wrangler deploy --dry-run --outdir /tmp/rediacc-proxy-dry-run` (:54)."""
    return ["npx", "wrangler", "deploy", "--dry-run", "--outdir", DRY_RUN_OUTDIR]


def deploy_argv() -> list[str]:
    """`npx wrangler deploy` (:65). NO `--config`, unlike both siblings."""
    return ["npx", "wrangler", "deploy"]


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


def curl_argv(url: str) -> list[str]:
    """`curl -sS -o /dev/null -w '%{http_code}' --max-time 30 <url>`."""
    return ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "30", url]


def smoke_host(wrangler_toml: str) -> str:
    """The first `pattern = "..."` in wrangler.toml, as sed prints it (empty when none)."""
    for line in wrangler_toml.splitlines():
        match = ROUTE_PATTERN.fullmatch(line)
        if match:
            return match.group(1)
    return ""


def _http_code(url: str) -> str:
    """`$(curl ... || true)`: curl's stdout, whatever its status; stderr inherited."""
    return subprocess.run(curl_argv(url), stdout=subprocess.PIPE, text=True, check=False).stdout


def smoke(worker_dir: pathlib.Path) -> int:
    """The post-deploy smoke: /v1/health 200, then an unauthenticated /v1/server-info 401."""
    url = "https://" + smoke_host((worker_dir / "wrangler.toml").read_text(encoding="utf-8"))
    log.step("Smoke-testing %s..." % url)
    health = _http_code(url + "/v1/health")
    if health != "200":
        log.error("Smoke test failed: /v1/health answered %s, expected 200" % (health or "nothing"))
        return 1
    info = _http_code(url + "/v1/server-info")
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

    if region not in SUPPORTED_REGIONS:
        # Refused first, before the token check and before any build: it is an argument error, and a deploy of the wrong region's config is not one a caller asked for.
        log.error(region_refusal(region))
        return 1

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
        status = _run(dry_run_argv())
        if status != 0:
            return status  # `set -e`
        log.info("Dry run passed. Nothing was deployed.")
        return 0

    status = build_and_stage_renet(repo_root, worker_dir)
    if status != 0:
        return status

    log.step("Deploying the proxy worker and container image (region: %s)..." % region)
    status = _run(deploy_argv())
    if status != 0:
        return status  # `set -e`

    status = smoke(worker_dir)
    if status != 0:
        return status

    for line in CLOSING_LINES:
        log.info(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
