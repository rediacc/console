"""Headless read smoke of one region's account Worker: sign in with a probe account, read the remote config store, and compare its content hash with the baseline taken before a database move.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.region_smoke --region eu|us|asia|bench [--record-baseline] [--baseline PATH]

WHY (agent/plans/PLAN-d1-eu-jurisdiction.md, Design 7). A relocated D1 is only proven by a real client reading what a real client wrote: `region_smoke --region eu --record-baseline` runs before the fence and stores the sha256 of the probe account's config content; the same command after the repoint reads it back through the new database and must print the same digest. `verify_edge_endpoints`, `portal_health` and `region_consistency_live` prove the Worker is up and the names agree; none of them reads user data.

THE STEPS, in order:

  1. Re-execute under the `region-smoke-<region>` Bitwarden profile (`rediacc_ci.core.bws_env exec`), unless it is already bound. The profile binds REDIACC_SMOKE_EMAIL, REDIACC_SMOKE_PASSWORD, REDIACC_SMOKE_MASTER_PASSWORD and, when the probe account has TOTP on, REDIACC_SMOKE_TOTP_SEED. Only `region-smoke-bench` is declared (.ci/config/secret-supply.json; it aliases the bench-login entries, the bench probe being the bench account); a region whose profile is not declared is a rc-2 refusal naming the missing profile, because a production probe account is a vault entry that must exist first.
  2. Refuse a missing value or the placeholder `PLACEHOLDER-operator-fills`, naming the store entry, before anything runs.
  3. Create the probe config `region-smoke-<region>` (`config init`; "already exists" is fine), then `subscription login --server <origin>` with REDIACC_LOGIN_EMAIL, REDIACC_LOGIN_PASSWORD and, with a seed, REDIACC_LOGIN_TOTP in the child environment.
  4. `config remote enable --master-password --api-url <origin>` with REDIACC_STORE_MASTER_PASSWORD (the first enable seeds the store from the local config; a later one is "already linked and this device can open it"), then `config remote refresh`: the read of the store through the region's Worker and D1.
  5. `config show` as JSON, canonicalised (sorted keys, no whitespace) and hashed with sha256.
  6. `--record-baseline` writes the digest to `.ci/state/region-smoke/<region>.json`; otherwise the digest must equal the stored one.

UNPROVEN UNTIL THE FIRST LIVE RUN. The CLI has no `config pull` verb (the plan's wording); `config remote refresh` is its read of the store, and `config show` its content. The first `--record-baseline` run (box P2, and B6 on bench) is what proves steps 3 to 5 against a real region; a refusal there names the step that failed.

SECRETS. Every value travels by name in a child's environment: never on argv, never printed. `RDC_DEV`, `REDIACC_CONFIG`, `REDIACC_TOKEN` and `REDIACC_ACCOUNT_SERVER` are dropped from each child so an inherited selection cannot redirect the run.

Exit 0 smoke passed (or baseline recorded), 1 a step failed, 2 a refusal before any step (usage, missing value, no baseline), 3 the digest differs from the baseline.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from rediacc_ci import log, paths
from rediacc_ci.ops import totp
from rediacc_ci.well_known import BENCH_ORIGIN

PROFILE_PREFIX = "region-smoke-"
SUPPLY_REL = (".ci", "config", "secret-supply.json")
BENCH = "bench"
PLACEHOLDER = "PLACEHOLDER-operator-fills"
MIN_WINDOW_LEFT = 5

EMAIL_ENV = "REDIACC_SMOKE_EMAIL"
PW_ENV = "REDIACC_SMOKE_PASSWORD"
MASTER_PW_ENV = "REDIACC_SMOKE_MASTER_PASSWORD"
TOTP_SEED_ENV = "REDIACC_SMOKE_TOTP_SEED"
REQUIRED_NAMES = (EMAIL_ENV, PW_ENV, MASTER_PW_ENV)

# The names the CLI reads (packages/cli/src/services/account/subscription-password-auth.ts, packages/cli/src/commands/config-remote-master-password.ts).
LOGIN_EMAIL_ENV = "REDIACC_LOGIN_EMAIL"
LOGIN_PW_ENV = "REDIACC_LOGIN_PASSWORD"
LOGIN_TOTP_ENV = "REDIACC_LOGIN_TOTP"
CLI_STORE_MASTER_PW_ENV = "REDIACC_STORE_MASTER_PASSWORD"
CHILD_SECRET_NAMES = (
    EMAIL_ENV,
    PW_ENV,
    MASTER_PW_ENV,
    TOTP_SEED_ENV,
    LOGIN_EMAIL_ENV,
    LOGIN_PW_ENV,
    LOGIN_TOTP_ENV,
    CLI_STORE_MASTER_PW_ENV,
)
SCRUBBED_SELECTORS = ("RDC_DEV", "REDIACC_CONFIG", "REDIACC_TOKEN", "REDIACC_ACCOUNT_SERVER")
ALREADY_EXISTS = "already exists"
BASELINE_DIR = (".ci", "state", "region-smoke")
USAGE = (
    "Usage: PYTHONPATH=.ci python3 -m rediacc_ci.ops.region_smoke "
    "--region <id>|bench [--record-baseline] [--baseline PATH]"
)

Runner = Callable[[Sequence[str], Mapping[str, str]], int]
Capture = Callable[[Sequence[str], Mapping[str, str]], tuple[int, str]]


class SmokeError(RuntimeError):
    """A refusal or a failed step; `rc` is the exit status. The message never carries a secret."""

    def __init__(self, message: str, rc: int = 1):
        super().__init__(message)
        self.rc = rc


def profile_for(region: str) -> str:
    return PROFILE_PREFIX + region


def declared_profiles(root: pathlib.Path | None = None) -> set[str]:
    """The consumer profiles .ci/config/secret-supply.json declares."""
    path = (root or paths.repo_root()).joinpath(*SUPPLY_REL)
    with open(path, encoding="utf-8") as fh:
        return set(json.load(fh).get("consumers", {}))


def region_ids(root: pathlib.Path | None = None) -> list[str]:
    path = (root or paths.repo_root()) / "regions.json"
    with open(path, encoding="utf-8") as fh:
        return [str(r["id"]) for r in json.load(fh)["regions"]]


def origin(region: str, root: pathlib.Path | None = None) -> str:
    """The account server a region's probe signs in to: the bench origin, or `https://<regions.json domain>`."""
    if region == BENCH:
        return BENCH_ORIGIN
    path = (root or paths.repo_root()) / "regions.json"
    with open(path, encoding="utf-8") as fh:
        for row in json.load(fh)["regions"]:
            if str(row["id"]) == region:
                return "https://%s" % row["domain"]
    raise SmokeError("no region %r in regions.json" % region, rc=2)


def parse_args(argv: Sequence[str]) -> tuple[str, bool, pathlib.Path | None]:
    """(region, record_baseline, baseline override). Any other argument is a rc-2 refusal."""
    region = ""
    record = False
    baseline: pathlib.Path | None = None
    args = list(argv)
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--region" and i + 1 < len(args):
            region = args[i + 1]
            i += 2
        elif arg == "--baseline" and i + 1 < len(args):
            baseline = pathlib.Path(args[i + 1])
            i += 2
        elif arg == "--record-baseline":
            record = True
            i += 1
        else:
            raise SmokeError("unknown argument %r\n%s" % (arg, USAGE), rc=2)
    if not region:
        raise SmokeError("--region is required\n%s" % USAGE, rc=2)
    if region != BENCH and region not in region_ids():
        raise SmokeError(
            "unknown region %r (regions.json has %s, plus bench)"
            % (region, ", ".join(region_ids())),
            rc=2,
        )
    return region, record, baseline


def read_values(env: Mapping[str, str]) -> dict[str, str]:
    """The probe values. A missing one or the placeholder is a rc-2 refusal; the TOTP seed is optional and decoded when present."""
    values: dict[str, str] = {}
    for name in (*REQUIRED_NAMES, TOTP_SEED_ENV):
        value = (env.get(name) or "").strip()
        if not value and name == TOTP_SEED_ENV:
            continue
        if not value:
            raise SmokeError(
                "%s is not set: run under `bws_env exec --profile region-smoke-<region>` "
                "(region_smoke does)" % name,
                rc=2,
            )
        if value == PLACEHOLDER:
            raise SmokeError("%s still holds the placeholder %r" % (name, PLACEHOLDER), rc=2)
        values[name] = value
    if TOTP_SEED_ENV in values:
        try:
            totp.decode_seed(values[TOTP_SEED_ENV])
        except totp.TotpError as exc:
            raise SmokeError("%s: %s" % (TOTP_SEED_ENV, exc), rc=2) from None
    return values


def base_env(env: Mapping[str, str]) -> dict[str, str]:
    """The inherited environment without any probe secret or config or server selector."""
    child = {k: v for k, v in env.items() if k not in CHILD_SECRET_NAMES}
    for name in SCRUBBED_SELECTORS:
        child.pop(name, None)
    return child


def config_name(region: str) -> str:
    return "region-smoke-%s" % region


def _rdc(config: str, *args: str) -> list[str]:
    return [str(paths.repo_root() / "rdc.sh"), "--config", config, *args]


def canonical_digest(document: object) -> str:
    """sha256 of the canonical JSON (sorted keys, no whitespace) of DOCUMENT."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def content_digest(out: str) -> str:
    """The digest of the JSON document `config show` printed; anything else is a failed step."""
    try:
        document = json.loads(out)
    except ValueError:
        raise SmokeError("config show did not print a JSON document: %r" % out[:200]) from None
    return canonical_digest(document)


def baseline_path(region: str, root: pathlib.Path | None = None) -> pathlib.Path:
    return (root or paths.repo_root()).joinpath(*BASELINE_DIR) / ("%s.json" % region)


def write_baseline(path: pathlib.Path, region: str, digest: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "region": region,
        "sha256": digest,
        "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def read_baseline(path: pathlib.Path, region: str) -> str:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        digest = str(record["sha256"])
    except (OSError, ValueError, KeyError, TypeError):
        raise SmokeError(
            "no readable baseline at %s: run `region_smoke --region %s --record-baseline` "
            "before the move" % (path, region),
            rc=2,
        ) from None
    if str(record.get("region")) != region:
        raise SmokeError(
            "%s records region %r, not %r" % (path, record.get("region"), region), rc=2
        )
    return digest


def fresh_code(
    seed: str,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """The current TOTP code, from the next window when the current one is about to close."""
    left = totp.STEP - (now() % totp.STEP)
    if left < MIN_WINDOW_LEFT:
        sleep(left + 0.5)
    return totp.code(seed, at=now())


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    return subprocess.run(
        list(argv), env=dict(env), cwd=str(paths.repo_root()), check=False
    ).returncode


def _subprocess_capture(argv: Sequence[str], env: Mapping[str, str]) -> tuple[int, str]:
    proc = subprocess.run(
        list(argv),
        env=dict(env),
        cwd=str(paths.repo_root()),
        stdout=subprocess.PIPE,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout or ""


def smoke(
    region: str,
    values: Mapping[str, str],
    env: Mapping[str, str],
    run: Runner,
    capture: Capture,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Steps 3 to 5; the content digest. A failed step is a SmokeError naming it."""
    server = origin(region)
    config = config_name(region)
    clean = base_env(env)

    log.step("Creating the probe config %s" % config)
    init_rc, init_out = capture(_rdc(config, "config", "init", config), dict(clean))
    if init_rc != 0 and ALREADY_EXISTS not in init_out:
        raise SmokeError("config init %s failed (exit %d)" % (config, init_rc))

    login_env = dict(clean)
    login_env[LOGIN_EMAIL_ENV] = values[EMAIL_ENV]
    login_env[LOGIN_PW_ENV] = values[PW_ENV]
    if TOTP_SEED_ENV in values:
        login_env[LOGIN_TOTP_ENV] = fresh_code(values[TOTP_SEED_ENV], now, sleep)
    log.step("Logging %s in to %s" % (config, server))
    rc = run(_rdc(config, "subscription", "login", "--server", server), login_env)
    if rc != 0:
        raise SmokeError("subscription login to %s failed (exit %d)" % (server, rc))

    enable_env = dict(clean)
    enable_env[CLI_STORE_MASTER_PW_ENV] = values[MASTER_PW_ENV]
    log.step("Linking the remote config store (config remote enable)")
    rc, out = capture(
        _rdc(
            config,
            "-o",
            "json",
            "config",
            "remote",
            "enable",
            "--master-password",
            "--api-url",
            server,
        ),
        enable_env,
    )
    if rc != 0 and "this device can open it" not in out:
        raise SmokeError("config remote enable failed (exit %d)" % rc)

    log.step("Reading the store through %s (config remote refresh)" % server)
    rc = run(_rdc(config, "config", "remote", "refresh"), dict(clean))
    if rc != 0:
        raise SmokeError("config remote refresh failed (exit %d)" % rc)

    log.step("Hashing the probe config content (config show)")
    rc, out = capture(_rdc(config, "-o", "json", "config", "show"), dict(clean))
    if rc != 0:
        raise SmokeError("config show failed (exit %d)" % rc)
    return content_digest(out)


def _reexec_under_profile(region: str, argv: Sequence[str], run: Runner) -> int | None:
    """This entry point under the region's smoke profile; None when the profile is already bound."""
    profile = profile_for(region)
    if profile in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(","):
        return None
    env = dict(os.environ)
    ci = str(paths.repo_root() / ".ci")
    env["PYTHONPATH"] = ci + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return run(
        [
            sys.executable,
            "-m",
            "rediacc_ci.core.bws_env",
            "exec",
            "--profile",
            profile,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.region_smoke",
            *argv,
        ],
        env,
    )


def main(
    argv: Sequence[str] | None = None,
    run: Runner = _subprocess_runner,
    capture: Capture = _subprocess_capture,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        region, record, override = parse_args(args)
        # Refusals that need no credential come first, so a wrong region never reads one.
        target = override or baseline_path(region)
        if not record:
            expected = read_baseline(target, region)
        if profile_for(region) not in declared_profiles():
            raise SmokeError(
                "no profile %s in .ci/config/secret-supply.json: %s needs a probe account in the "
                "vault and that profile before it can be smoked" % (profile_for(region), region),
                rc=2,
            )
        rebound = _reexec_under_profile(region, args, run)
        if rebound is not None:
            return rebound
        values = read_values(os.environ)
        digest = smoke(region, values, dict(os.environ), run, capture)
    except SmokeError as exc:
        log.error(str(exc))
        return exc.rc
    if record:
        write_baseline(target, region, digest)
        log.success("%s baseline recorded: sha256 %s -> %s" % (region, digest, target))
        return 0
    if digest != expected:
        log.error(
            "%s content differs from the baseline: sha256 %s now, %s recorded in %s"
            % (region, digest, expected, target)
        )
        return 3
    log.success("%s smoke passed: sha256 %s equals the baseline" % (region, digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
