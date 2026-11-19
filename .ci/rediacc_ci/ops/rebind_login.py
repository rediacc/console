"""Run one rdc command with the authenticator code that moves a first-use token to this host's new IP.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.rebind_login -- <arguments for rdc.sh>

WHY. The account server binds a first-use API token to its first caller's address and answers any other with 403 TOKEN_IP_MISMATCH. On a terminal the CLI asks for the token creator's authenticator code; without one it reads that code from REDIACC_IP_REBIND_CODE (`packages/cli/src/services/account/token-ip-rebind.ts`). The token creator of the production configs (eu-remote, eu-edge) is the root account, whose seed is ROOT_TOTP_SEED, so an agent derives the code from the vault instead of asking the operator for it (operator 2026-11-17).

THE STEPS, in order:

  1. Re-execute under the `root-login` Bitwarden profile (`rediacc_ci.core.bws_env exec`), unless it is already bound.
  2. Refuse a seed that is unset, still the placeholder `PLACEHOLDER-operator-fills`, or not base32 (exit 2), before running anything.
  3. Derive the current six-digit code in memory (`rediacc_ci.ops.totp`), waiting for the next 30 s step when fewer than MIN_WINDOW_LEFT seconds remain.
  4. Run `./rdc.sh <argv>` with REDIACC_IP_REBIND_CODE in the child environment, and exit with its status.

SECRETS. The seed and the code stay in memory and in the child's environment: neither is put on argv, printed or logged. The CLI POSTs the code once, so a refused code is a named CLI failure and this tool does not retry. Exit 2 is a refusal before the child runs (usage, missing or bad seed); otherwise the child's status.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence

from rediacc_ci import log, paths
from rediacc_ci.ops import totp

PROFILE = "root-login"
SEED_ENV = "ROOT_TOTP_SEED"
CODE_ENV = "REDIACC_IP_REBIND_CODE"
PLACEHOLDER = "PLACEHOLDER-operator-fills"
MIN_WINDOW_LEFT = 5
USAGE = "usage: rebind_login -- <arguments for rdc.sh>"

Runner = Callable[[Sequence[str], Mapping[str, str]], int]


class RebindLoginError(RuntimeError):
    """A refusal before the child runs; the text never carries the seed or a code."""

    def __init__(self, message: str, rc: int = 2):
        super().__init__(message)
        self.rc = rc


def parse_args(argv: Sequence[str]) -> list[str]:
    """The rdc argv after `--`; RebindLoginError rc 2 when it is missing or empty."""
    args = list(argv)
    if not args or args[0] != "--" or len(args) < 2:
        raise RebindLoginError(USAGE)
    return args[1:]


def read_seed(env: Mapping[str, str]) -> str:
    """ROOT_TOTP_SEED, refused when unset, a placeholder or not base32."""
    seed = env.get(SEED_ENV) or ""
    if not seed or seed == PLACEHOLDER:
        raise RebindLoginError(
            "%s is unset or a placeholder in the %s profile" % (SEED_ENV, PROFILE)
        )
    try:
        totp.decode_seed(seed)
    except totp.TotpError as exc:
        raise RebindLoginError("%s: %s" % (SEED_ENV, exc)) from None
    return seed


def current_code(seed: str, now: Callable[[], float], sleep: Callable[[float], None]) -> str:
    """The code of the current step, or of the next one when this step ends within MIN_WINDOW_LEFT seconds."""
    left = totp.STEP - (now() % totp.STEP)
    if left < MIN_WINDOW_LEFT:
        sleep(left + 0.5)
    return totp.code(seed, at=now())


def child_command(rdc_argv: Sequence[str]) -> list[str]:
    return [str(paths.repo_root() / "rdc.sh"), *rdc_argv]


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    # stdin is closed so the CLI never sees a terminal and prompts: the code comes from the environment.
    return subprocess.run(
        list(argv), env=dict(env), stdin=subprocess.DEVNULL, check=False
    ).returncode


def _reexec_under_profile(argv: Sequence[str], run: Runner) -> int | None:
    """This entry point under the root-login profile; None when the profile is already bound."""
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
            "rediacc_ci.ops.rebind_login",
            *argv,
        ],
        env,
    )


def _clock() -> tuple[Callable[[], float], Callable[[float], None]]:
    """The wall clock and sleep `main` runs on; a test replaces this one seam."""
    return time.time, time.sleep


def main(argv: Sequence[str] | None = None, run: Runner = _subprocess_runner) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        return 0
    try:
        rdc_argv = parse_args(args)
        rebound = _reexec_under_profile(args, run)
        if rebound is not None:
            return rebound
        seed = read_seed(os.environ)
        now, sleep = _clock()
        code = current_code(seed, now, sleep)
    except RebindLoginError as exc:
        log.error(str(exc))
        return exc.rc
    command = child_command(rdc_argv)
    env = {k: v for k, v in os.environ.items() if k != SEED_ENV}
    env[CODE_ENV] = code
    log.step("Running %s with %s=<code> in its environment" % (" ".join(command), CODE_ENV))
    return run(command, env)


if __name__ == "__main__":
    sys.exit(main())
