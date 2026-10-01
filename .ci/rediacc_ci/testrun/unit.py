"""Port of `.ci/scripts/test/run-unit.sh`: the four workspace unit suites, in order, stopping at the first failure.

Deliberate difference from the twin (Rule T), with a test that fails on the bash behaviour: an unknown argument was silently ignored (`case` with no default arm), so `--coverge` ran the suites WITHOUT coverage and exited 0. It is refused with exit 2.

KEPT, AND A FINDING: a failed `npm run test:coverage` only warns, as in the twin. The root package.json has no `test:coverage` script (`npm run test:coverage` answers "Missing script", measured 2026-10-01), so the `--coverage` step that ct-tests.yml passes has warned on every run and produced nothing. Making the step fatal would redden that job; the honest repair is to drop `--coverage` from the workflow call or to add the script, which is the lead's to apply.
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
COVERAGE = ("npm", "run", "test:coverage")
USAGE = "usage: run-unit.sh [--coverage]"


def _run(argv: tuple[str, ...]) -> int:
    try:
        return subprocess.run(argv, check=False).returncode
    except OSError as exc:
        log.error(f"{argv[0]}: {exc.strerror or exc}")
        return 127


def main(argv: list[str]) -> int:
    coverage = False
    for arg in argv:
        if arg == "--coverage":
            coverage = True
        else:
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
    if coverage:
        log.step("Generating coverage report...")
        if _run(COVERAGE) != 0:
            log.warn("Coverage generation failed")
    log.info("All unit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
