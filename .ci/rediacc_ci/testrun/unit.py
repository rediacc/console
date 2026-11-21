"""Port of `.ci/scripts/test/run-unit.sh`: the four workspace unit suites, in order, stopping at the first failure.

Deliberate difference from the twin (Rule T), with a test that fails on the bash behaviour: an unknown argument was silently ignored (`case` with no default arm), so `--coverge` ran the suites WITHOUT coverage and exited 0. It is refused with exit 2.

NO `--coverage`, a second deliberate difference. The twin's flag ran `npm run test:coverage`, a script no package.json defines ("Missing script", measured 2026-10-01), and only warned, so the one caller that passed it (ct-tests.yml) produced nothing on every run. The flag and its step are gone; the caller no longer passes it.

`--shard I/N`, a third difference (operator ruling #12755b25, "Shard into 2"): ct-tests.yml's Unit job runs as N legs, and each leg passes `--shard=I/N` through to every suite's vitest, which splits that suite's test files into N disjoint parts. Every file therefore runs in exactly one leg, the same coverage as the unsharded run. No flag runs everything, as before.
"""

import os
import re
import subprocess
import sys

from rediacc_ci import log, paths

SUITES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    (
        "@rediacc/shared",
        ("npm", "run", "test", "-w", "@rediacc/shared"),
        "@rediacc/shared tests failed",
    ),
    (
        "@rediacc/cli (unit)",
        ("npm", "run", "test:unit", "-w", "@rediacc/cli"),
        "@rediacc/cli unit tests failed",
    ),
    (
        "@rediacc/provisioning",
        ("npm", "run", "test", "-w", "@rediacc/provisioning"),
        "@rediacc/provisioning tests failed",
    ),
    (
        "@rediacc/e2e-tests (unit)",
        ("npm", "run", "test:unit", "-w", "@rediacc/e2e-tests"),
        "@rediacc/e2e-tests unit tests failed",
    ),
)
USAGE = "usage: PYTHONPATH=.ci python3 -m rediacc_ci.testrun.unit [--shard I/N]"
SHARD = re.compile(r"([1-9][0-9]*)/([1-9][0-9]*)")


def _run(argv: tuple[str, ...]) -> int:
    try:
        return subprocess.run(argv, check=False).returncode
    except OSError as exc:
        log.error(f"{argv[0]}: {exc.strerror or exc}")
        return 127


def _usage(message: str) -> int:
    log.error(message)
    print(USAGE, file=sys.stderr)
    return 2


def main(argv: list[str]) -> int:
    shard = ""
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg != "--shard":
            return _usage(f"Unknown option: {arg}")
        if shard or i + 1 >= len(argv):
            return _usage("--shard takes one I/N value, given once")
        m = SHARD.fullmatch(argv[i + 1])
        if m is None or int(m.group(1)) > int(m.group(2)):
            return _usage(f"--shard must be I/N with 1 <= I <= N, got {argv[i + 1]!r}")
        shard = argv[i + 1]
        i += 2
    os.chdir(paths.repo_root())
    log.step(f"Running unit tests{f' (shard {shard})' if shard else ''}...")
    # Every suite takes the same vitest --shard, so each test file runs in exactly one leg of N and the union of the legs is the unsharded run.
    extra = ("--", f"--shard={shard}") if shard else ()
    for name, command, failure in SUITES:
        log.step(f"Testing {name}...")
        if _run((*command, *extra)) != 0:
            log.error(failure)
            return 1
    log.info("All unit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
