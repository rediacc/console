#!/usr/bin/env python3
"""Print the current authenticator code that moves a bench config's API token to this host's new IP.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.rebind_code <config>     # eu-bench, us-bench, asia-bench or bench
    .ci/rediacc_ci/ops/rebind_code.py <config>                        # the same, as one executable path

WHY. The account server binds a first-use API token to its first caller's address and answers any other with 403 TOKEN_IP_MISMATCH; the CLI moves the token with the token creator's authenticator code (`packages/cli/src/services/account/token-ip-rebind.ts`). The creator of a bench config's token is the bench root that `npm run login:bench` signs in as, and its seed is the bench's `BENCH_ROOT_TOTP_SEED_<REGION>` vault entry, so bench needs no human for the move (operator 2026-11-24). `rdc.sh` exports `REDIACC_IP_REBIND_CODE_COMMAND=$ROOT_DIR/.ci/rediacc_ci/ops/rebind_code.py` (an absolute path) for a bench config (the CLI spawns that one path with no shell, so this file is executable and puts its own `.ci` on sys.path), and the CLI runs this program only when the server actually refuses the token for its address, then replays the refused request: the original command continues.

THE STEPS, in order:

  1. Map the config to its bench region (`login_bench.REGION_CONFIGS`, and `bench` to eu); any other config is refused with exit 2 before a vault read.
  2. Re-execute under that bench's login profile (`bench-login-<region>`, `rediacc_ci.core.bws_env exec`), unless it is bound; another bench's login profile bound is refused with exit 2.
  3. Refuse a seed that is unset, the placeholder or not base32, naming its vault entry (exit 2).
  4. Derive the code in memory (`rediacc_ci.ops.totp`), waiting for the next 30 s step when fewer than `login_bench.MIN_WINDOW_LEFT` seconds remain, and print it on stdout.

SECRETS. Stdout carries the six digits and nothing else, for the CLI that reads it through a pipe; the seed is never printed, logged or put on argv, and every refusal goes to stderr. Exit 0 printed a code, 2 is a refusal; otherwise the profile re-execution's status.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence

# THE HOP, WRITTEN BY HAND EXACTLY ONCE. Run by path, this file cannot import the package that would put
# `.ci` on sys.path until `.ci` is on sys.path. Under `-m` the entry is already there and a second copy is harmless.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci import log, paths
from rediacc_ci.ops import bench_preflight, login_bench, totp

SEED_ENV = login_bench.TOTP_SEED_ENV
PLACEHOLDER = login_bench.PLACEHOLDER
PROFILE_ROLE = login_bench.PROFILE_ROLE
# `./rdc.sh --config bench <cmd>` is the eu bench (login_bench.BENCH_CONFIGS).
CONFIG_REGIONS = {
    **{config: region for region, config in login_bench.REGION_CONFIGS.items()},
    "bench": login_bench.DEFAULT_REGION,
}
USAGE = "usage: rebind_code <%s>" % "|".join(CONFIG_REGIONS)

Runner = Callable[[Sequence[str], Mapping[str, str]], int]


class RebindCodeError(RuntimeError):
    """A refusal before any code is printed; the text never carries the seed or a code."""

    def __init__(self, message: str, rc: int = 2):
        super().__init__(message)
        self.rc = rc


def region_for(args: Sequence[str]) -> str:
    """The bench region of the one config argument; RebindCodeError rc 2 for anything else."""
    if len(args) != 1 or args[0] not in CONFIG_REGIONS:
        raise RebindCodeError(
            "rebind_code: no vault seed is mapped for %s; %s"
            % (" ".join(map(repr, args)) or "no config", USAGE)
        )
    return CONFIG_REGIONS[args[0]]


def read_seed(env: Mapping[str, str], region: str) -> str:
    """BENCH_ROOT_TOTP_SEED of REGION's bench, refused when unset, the placeholder or not base32."""
    seed = (env.get(SEED_ENV) or "").strip()
    entry = login_bench.seed_entry(region)
    if not seed or seed == PLACEHOLDER:
        raise RebindCodeError(
            "rebind_code: %s is unset or the placeholder in the %s profile"
            % (entry, bench_preflight.profile_for(PROFILE_ROLE, region))
        )
    try:
        totp.decode_seed(seed)
    except totp.TotpError as exc:
        raise RebindCodeError("rebind_code: %s: %s" % (entry, exc)) from None
    return seed


def _reexec_under_profile(args: Sequence[str], region: str, run: Runner) -> int | None:
    """This entry point under REGION's login profile; None when that profile is already bound."""
    bound = [p for p in (os.environ.get("REDIACC_BWS_PROFILES") or "").split(",") if p]
    profile = bench_preflight.profile_for(PROFILE_ROLE, region)
    foreign = bench_preflight.foreign_profiles(PROFILE_ROLE, region, bound)
    if foreign:
        raise RebindCodeError(
            "rebind_code: refuses to run under %s: that profile binds another bench's seed and "
            "bws_env exec never overwrites a name already set" % ", ".join(foreign)
        )
    if profile in bound:
        return None
    env = {k: v for k, v in os.environ.items() if k != SEED_ENV}
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
            "rediacc_ci.ops.rebind_code",
            *args,
        ],
        env,
    )


def _subprocess_runner(argv: Sequence[str], env: Mapping[str, str]) -> int:
    # stdin closed and stdout inherited: the child's one line of digits is this program's stdout.
    return subprocess.run(
        list(argv), env=dict(env), stdin=subprocess.DEVNULL, check=False
    ).returncode


def _clock() -> tuple[Callable[[], float], Callable[[float], None]]:
    """The wall clock and sleep `main` runs on; a test replaces this one seam."""
    return time.time, time.sleep


def main(argv: Sequence[str] | None = None, run: Runner = _subprocess_runner) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print((__doc__ or "").strip(), file=sys.stderr)
        return 0
    try:
        region = region_for(args)
        rebound = _reexec_under_profile(args, region, run)
        if rebound is not None:
            return rebound
        seed = read_seed(os.environ, region)
    except RebindCodeError as exc:
        log.error(str(exc))
        return exc.rc
    now, sleep = _clock()
    sys.stdout.write(login_bench.fresh_code(seed, now, sleep) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
