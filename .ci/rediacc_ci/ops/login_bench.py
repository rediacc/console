"""Headless login of the eu-bench config into https://bench.rediacc.com with the operator's own bench account.

    npm run login:bench
    PYTHONPATH=.ci python3 -m rediacc_ci.ops.login_bench [--server URL] [--config NAME]

BENCH ONLY (operator order 2026-10-27). The run refuses, with a named error and exit 2, any server other than https://bench.rediacc.com and any rdc config other than eu-bench, before it reads a credential. Edge and stable keep human login; no profile binds an account for them.

THE STEPS, in order:

  1. Re-execute under the `bench-login` Bitwarden profile (`rediacc_ci.core.bws_env exec`), unless it is already bound. The profile binds REDIACC_BENCH_EMAIL, REDIACC_BENCH_PASSWORD, REDIACC_BENCH_TOTP_SEED and REDIACC_BENCH_MASTER_PASSWORD.
  2. Refuse a value that is unset or still the placeholder `PLACEHOLDER-operator-fills`, naming its Bitwarden entry, before anything else runs.
  3. Refresh the bench IP allowlist (`rediacc_ci.ops.bench_access add-current`, which binds its own `bench-access` profile). The four bench values are removed from that child's environment.
  4. Compute the six-digit TOTP code in memory (`rediacc_ci.ops.totp`), waiting for the next 30 s window when fewer than `MIN_WINDOW_LEFT` seconds remain, then run `./rdc.sh --config eu-bench subscription login --server https://bench.rediacc.com` with REDIACC_LOGIN_EMAIL, REDIACC_LOGIN_PASSWORD and REDIACC_LOGIN_TOTP in the child environment.
  5. Run `./rdc.sh --config eu-bench config remote enable --master-password --config-id <CONFIG_ID> --api-url https://bench.rediacc.com` with REDIACC_STORE_MASTER_PASSWORD in the child environment, unless `config remote status` already reports the config connected to CONFIG_ID on bench: enable refuses a linked config ("nothing to enable", exit 2, measured 2026-10-27 on the first live run), so a second run skips the step instead of failing on it.
  6. Print `./rdc.sh --config eu-bench config remote status`.

SECRETS. Every value travels by name in a child's environment: never on argv, never printed, never logged. Each `rdc` child gets only the values its own step needs, and `RDC_DEV`, `REDIACC_CONFIG`, `REDIACC_TOKEN` and `REDIACC_ACCOUNT_SERVER` are dropped from it, so an inherited dev selection cannot redirect the login to another server or config. A failed step exits 1 naming the step.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence

from rediacc_ci import log, paths
from rediacc_ci.ops import totp
from rediacc_ci.well_known import BENCH_ORIGIN

PROFILE = "bench-login"
SERVER = BENCH_ORIGIN
CONFIG = "eu-bench"
CONFIG_ID = "1880812c-2086-4daa-a620-8f84aa3b6e7c"
PLACEHOLDER = "PLACEHOLDER-operator-fills"
MIN_WINDOW_LEFT = 5

EMAIL_ENV = "REDIACC_BENCH_EMAIL"
PW_ENV = "REDIACC_BENCH_PASSWORD"
TOTP_SEED_ENV = "REDIACC_BENCH_TOTP_SEED"
MASTER_PW_ENV = "REDIACC_BENCH_MASTER_PASSWORD"
SOURCE_NAMES = (EMAIL_ENV, PW_ENV, TOTP_SEED_ENV, MASTER_PW_ENV)

# The names the CLI reads (packages/cli/src/services/account/subscription-password-auth.ts, packages/cli/src/commands/config-remote-master-password.ts).
LOGIN_EMAIL_ENV = "REDIACC_LOGIN_EMAIL"
LOGIN_PW_ENV = "REDIACC_LOGIN_PASSWORD"
LOGIN_TOTP_ENV = "REDIACC_LOGIN_TOTP"
CLI_STORE_MASTER_PW_ENV = "REDIACC_STORE_MASTER_PASSWORD"
CHILD_SECRET_NAMES = (
    *SOURCE_NAMES,
    LOGIN_EMAIL_ENV,
    LOGIN_PW_ENV,
    LOGIN_TOTP_ENV,
    CLI_STORE_MASTER_PW_ENV,
)
# Inherited selections that would point `./rdc.sh` somewhere other than eu-bench on bench.
SCRUBBED_SELECTORS = ("RDC_DEV", "REDIACC_CONFIG", "REDIACC_TOKEN", "REDIACC_ACCOUNT_SERVER")

USAGE = "usage: login_bench [--server %s] [--config %s]" % (SERVER, CONFIG)

Runner = Callable[[Sequence[str], Mapping[str, str]], int]
Capture = Callable[[Sequence[str], Mapping[str, str]], tuple[int, str]]


class LoginError(RuntimeError):
    """A refusal or a failed step; `rc` is the exit status. The message never carries a secret."""

    def __init__(self, message: str, rc: int = 1):
        super().__init__(message)
        self.rc = rc


def _bws_entry(name: str) -> str:
    """`NAME (<uuid>)` from the vault map, for a refusal that names the entry to fill."""
    try:
        secrets = json.loads(
            paths.from_root(".ci", "config", "bws-secret-map.json").read_text(encoding="utf-8")
        )["secrets"]
        return "%s (%s)" % (name, secrets[name]["id"])
    except (OSError, ValueError, KeyError):
        return name


def parse_args(argv: Sequence[str]) -> tuple[str, str]:
    """(server, config). Anything but bench and eu-bench is a LoginError with rc 2."""
    server, config = SERVER, CONFIG
    rest = list(argv)
    while rest:
        arg = rest.pop(0)
        if arg in ("--server", "--config") and rest:
            value = rest.pop(0)
        elif arg.startswith(("--server=", "--config=")):
            arg, value = arg.split("=", 1)
        else:
            raise LoginError("%s (unexpected argument %r)" % (USAGE, arg), rc=2)
        if arg == "--server":
            server = value
        else:
            config = value
    if server.rstrip("/") != SERVER:
        raise LoginError(
            "login:bench refuses server %r: it logs in to %s only; edge and stable keep human login"
            % (server, SERVER),
            rc=2,
        )
    if config != CONFIG:
        raise LoginError(
            "login:bench refuses config %r: it writes the %s config only" % (config, CONFIG), rc=2
        )
    return SERVER, CONFIG


def read_values(env: Mapping[str, str]) -> dict[str, str]:
    """The four bench values; a missing one or the placeholder is a LoginError (rc 2) naming the Bitwarden entry."""
    values: dict[str, str] = {}
    for name in SOURCE_NAMES:
        value = env.get(name) or ""
        if not value.strip():
            raise LoginError(
                "%s is not set: run under `bws_env exec --profile %s` (npm run login:bench does)"
                % (_bws_entry(name), PROFILE),
                rc=2,
            )
        if value.strip() == PLACEHOLDER:
            raise LoginError(
                "%s still holds the placeholder %r: the operator fills that Bitwarden entry first"
                % (_bws_entry(name), PLACEHOLDER),
                rc=2,
            )
        values[name] = value.strip()
    try:
        totp.decode_seed(values[TOTP_SEED_ENV])
    except totp.TotpError as exc:
        raise LoginError("%s: %s" % (_bws_entry(TOTP_SEED_ENV), exc), rc=2) from None
    return values


def base_env(env: Mapping[str, str]) -> dict[str, str]:
    """The inherited environment with every bench secret and every config or server selector removed."""
    child = {k: v for k, v in env.items() if k not in CHILD_SECRET_NAMES}
    for name in SCRUBBED_SELECTORS:
        child.pop(name, None)
    return child


def fresh_code(
    seed: str, now: Callable[[], float] = time.time, sleep: Callable[[float], None] = time.sleep
) -> str:
    """The current TOTP code, taken from the next window when the current one is about to close."""
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


def already_linked(status_rc: int, status_out: str, server: str) -> bool:
    """True when `config remote status` reports this config connected to CONFIG_ID on `server`: `config remote enable` then refuses with "nothing to enable", so the step is skipped."""
    if status_rc != 0:
        return False
    try:
        data = json.loads(status_out).get("data") or {}
    except (ValueError, AttributeError):
        return False
    return (
        data.get("status") == "connected"
        and data.get("configId") == CONFIG_ID
        and str(data.get("apiUrl") or "").rstrip("/") == server
    )


def _rdc(config: str, *args: str) -> list[str]:
    return [str(paths.repo_root() / "rdc.sh"), "--config", config, *args]


def _step(run: Runner, label: str, argv: Sequence[str], env: Mapping[str, str]) -> None:
    log.step(label)
    rc = run(argv, env)
    if rc != 0:
        raise LoginError("%s failed (exit %d)" % (label, rc), rc=1)


def login(
    argv: Sequence[str],
    env: Mapping[str, str],
    run: Runner = _subprocess_runner,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    capture: Capture = _subprocess_capture,
) -> None:
    """Steps 2-6 of the module docstring, with the profile already bound. Raises LoginError."""
    server, config = parse_args(argv)
    values = read_values(env)
    clean = base_env(env)

    ci = str(paths.repo_root() / ".ci")
    access_env = dict(clean)
    access_env["PYTHONPATH"] = ci + (
        os.pathsep + access_env["PYTHONPATH"] if access_env.get("PYTHONPATH") else ""
    )
    _step(
        run,
        "Refreshing the bench IP allowlist (bench_access add-current)",
        [sys.executable, "-m", "rediacc_ci.ops.bench_access", "add-current"],
        access_env,
    )

    login_env = dict(clean)
    login_env[LOGIN_EMAIL_ENV] = values[EMAIL_ENV]
    login_env[LOGIN_PW_ENV] = values[PW_ENV]
    login_env[LOGIN_TOTP_ENV] = fresh_code(values[TOTP_SEED_ENV], now, sleep)
    _step(
        run,
        "Logging %s in to %s (subscription login)" % (config, server),
        _rdc(config, "subscription", "login", "--server", server),
        login_env,
    )

    status_rc, status_out = capture(_rdc(config, "config", "remote", "status"), dict(clean))
    if already_linked(status_rc, status_out, server):
        log.info(
            "%s is already linked to config %s on %s; config remote enable skipped"
            % (config, CONFIG_ID, server)
        )
    else:
        enable_env = dict(clean)
        enable_env[CLI_STORE_MASTER_PW_ENV] = values[MASTER_PW_ENV]
        _step(
            run,
            "Enabling the remote config store (config remote enable)",
            _rdc(
                config,
                "config",
                "remote",
                "enable",
                "--master-password",
                "--config-id",
                CONFIG_ID,
                "--api-url",
                server,
            ),
            enable_env,
        )

    _step(
        run,
        "Remote config store status",
        _rdc(config, "config", "remote", "status"),
        dict(clean),
    )
    log.success("%s is logged in to %s" % (config, server))


def _reexec_under_profile(argv: Sequence[str], run: Runner) -> int | None:
    """This entry point under the bench-login profile; None when the profile is already bound."""
    if PROFILE in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(","):
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
            PROFILE,
            "--",
            sys.executable,
            "-m",
            "rediacc_ci.ops.login_bench",
            *argv,
        ],
        env,
    )


def main(argv: Sequence[str] | None = None, run: Runner = _subprocess_runner) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        # The bench-only refusal runs before the profile is entered, so a wrong target never reads a credential.
        parse_args(args)
        rebound = _reexec_under_profile(args, run)
        if rebound is not None:
            return rebound
        login(args, os.environ, run)
    except LoginError as exc:
        log.error(str(exc))
        return exc.rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
