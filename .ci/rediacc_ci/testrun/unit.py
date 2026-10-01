"""Port of `.ci/scripts/test/run-unit.sh`: the four workspace unit suites, in order, stopping at the first failure.

Deliberate difference from the twin (Rule T), with a test that fails on the bash behaviour: an unknown argument was silently ignored (`case` with no default arm), so `--coverge` ran the suites WITHOUT coverage and exited 0. It is refused with exit 2.

NO `--coverage`, a second deliberate difference. The twin's flag ran `npm run test:coverage`, a script no package.json defines ("Missing script", measured 2026-10-01), and only warned, so the one caller that passed it (ct-tests.yml) produced nothing on every run. The flag and its step are gone; the caller no longer passes it.
"""

import os
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
USAGE = "usage: python3 -m rediacc_ci.testrun.unit"


def _run(argv: tuple[str, ...]) -> int:
    try:
        return subprocess.run(argv, check=False).returncode
    except OSError as exc:
        log.error(f"{argv[0]}: {exc.strerror or exc}")
        return 127


def main(argv: list[str]) -> int:
    for arg in argv:
        log.error(f"Unknown option: {arg}")
        print(USAGE, file=sys.stderr)
        return 2
    os.chdir(paths.repo_root())
    log.step("Running unit tests...")
    for name, command, failure in SUITES:
        log.step(f"Testing {name}...")
        if _run(command) != 0:
            log.error(failure)
            return 1
    log.info("All unit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
