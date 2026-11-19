#!/usr/bin/env python3
"""Run an apt-backed command with bounded retries, a per-attempt timeout and a mirror fallback.

WHY. PR #605 run 44442526107 failed three jobs on a stalled Ubuntu mirror, not on code: `playwright install-deps chromium` timed out once at 120 s and the lane died, with no second attempt. One attempt against one mirror makes any mirror blip a red job.

WHAT. `run_with_retry` runs the command up to `attempts` times, each cut at `timeout` seconds, with `backoff * attempt` seconds between. When an earlier attempt STALLED (timed out) and the next one is the final one, `fallback` runs first (on a hosted runner it re-points apt at archive.ubuntu.com through `rediacc_ci.infra.apt_mirror`). A final failure is never absorbed: the exit code is non-zero and the last error is named. Nothing here is a `continue-on-error`.

CLI: `python3 -m rediacc_ci.infra.apt_retry [--attempts N] [--timeout S] [--backoff S] -- <command...>`.
"""

import argparse
import dataclasses
import subprocess
import sys
import time
import typing

DEFAULT_ATTEMPTS = 3
DEFAULT_TIMEOUT_S = 120
DEFAULT_BACKOFF_S = 5


class AptRetryError(RuntimeError):
    """Every attempt failed; the message names the last error."""


@dataclasses.dataclass
class Outcome:
    attempts: int
    fell_back: bool


def system_fallback() -> None:
    """Re-point apt at the global archive as root; a no-op off GitHub-hosted runners (apt_mirror decides)."""
    subprocess.run(
        [
            "sudo",
            "--preserve-env=GITHUB_ACTIONS,RUNNER_ENVIRONMENT",
            "env",
            "PYTHONPATH=.ci",
            sys.executable,
            "-m",
            "rediacc_ci.infra.apt_mirror",
        ],
        check=False,
    )


def run_with_retry(
    cmd: list[str],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    timeout: float = DEFAULT_TIMEOUT_S,
    backoff: float = DEFAULT_BACKOFF_S,
    runner: typing.Callable[..., typing.Any] = subprocess.run,
    sleep: typing.Callable[[float], None] = time.sleep,
    fallback: typing.Callable[[], None] = system_fallback,
    **run_kw: typing.Any,
) -> Outcome:
    """Run `cmd` until it exits 0; raise AptRetryError naming the last error after `attempts` failures."""
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    stalled = False
    fell_back = False
    last = ""
    for n in range(1, attempts + 1):
        if n == attempts and n > 1 and stalled and not fell_back:
            print(
                f"apt-retry: a mirror stalled; falling back before attempt {n}/{attempts}",
                flush=True,
            )
            fallback()
            fell_back = True
        try:
            done = runner(cmd, check=False, timeout=timeout, **run_kw)
        except subprocess.TimeoutExpired:
            stalled = True
            last = f"timed out after {timeout:g}s (apt mirror stall?)"
        else:
            if done.returncode == 0:
                return Outcome(n, fell_back)
            last = f"exited {done.returncode}"
        print(f"apt-retry: attempt {n}/{attempts} of `{' '.join(cmd)}` {last}", flush=True)
        if n < attempts:
            sleep(backoff * n)
    raise AptRetryError(f"`{' '.join(cmd)}` failed in all {attempts} attempts; last error: {last}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--backoff", type=float, default=DEFAULT_BACKOFF_S)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    args = ap.parse_args(argv)
    cmd = args.cmd[1:] if args.cmd[:1] == ["--"] else args.cmd
    if not cmd:
        print(
            "apt-retry: no command given; usage: apt_retry [opts] -- <command...>", file=sys.stderr
        )
        return 2
    try:
        out = run_with_retry(
            cmd, attempts=args.attempts, timeout=args.timeout, backoff=args.backoff
        )
    except AptRetryError as exc:
        print(f"apt-retry: FAILED: {exc}", file=sys.stderr)
        return 1
    print(
        f"apt-retry: ok after {out.attempts} attempt(s)"
        + (" (mirror fallback used)" if out.fell_back else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
