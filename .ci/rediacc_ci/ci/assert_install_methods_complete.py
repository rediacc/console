#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/assert-install-methods-complete.sh` (56 lines).

Aggregates the six per-platform install-method jobs into one verdict and renders the platform table into the job summary. Every platform is HARD-required here -- `skipped` is not accepted, unlike the soft tier in `assert-ci-complete.sh` -- because an install method that silently stops being tested is the failure this gate exists to prevent. The twin's header owns that reasoning.

LIVE CALLER, not repointed: `.github/workflows/ct-install-methods.yml:257` `run: .ci/scripts/ci/assert-install-methods-complete.sh`. The bash twin stays the registered gate; this module is its verified-equivalent alternative and the cutover is a separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-assert-install-methods-complete.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-install-methods-complete --assert --k 5`).

-----------------------------------------------------------------------------
THE SUMMARY FILE IS OPENED ONCE, NOT ONCE PER LINE
-----------------------------------------------------------------------------
The twin appends with a separate `>>"$SUMMARY"` redirect per line group. Every one of those is `O_APPEND` on the same path, so the resulting bytes are identical to a single append-mode handle held for the run, and the differential compares the file's contents rather than trusting that claim.

The one observable difference is the FAILURE mode. An unwritable `$SUMMARY` kills the twin at its first redirect with a bare shell diagnostic (`assert-install-methods-complete.sh: line 37: /nope/x/y: No such file or directory`, exit 1) before any platform is judged. This port refuses in the same place with the same exit code and the same two facts -- the path and the OS error --
through `log.error` instead of a bash line number, which is the same rewording convention the earlier ports in this workstream use.

-----------------------------------------------------------------------------
`${!var:-<unset>}` AND `${VERSION:-<unset>}` TREAT EMPTY AS UNSET
-----------------------------------------------------------------------------
`:-`, not `-`, so an env var set to the empty string (what a workflow expression yielding nothing produces) renders as `<unset>` in the table and fails the platform, rather than printing a blank cell that reads as fine.
"""

from __future__ import annotations

import os
import sys

from rediacc_ci import log

UNSET = "<unset>"

# Where the twin writes when Actions has given it nowhere: `/dev/null`, so the table is discarded rather than mixed into stdout. Reproduced exactly, because a port that fell back to stdout would put table rows into a stream callers read as data.
DEFAULT_SUMMARY = "/dev/null"

# label|env-var-suffix, in the twin's order. The order is load-bearing: it is the order of the rows in the rendered job-summary table.
PLATFORMS = (
    ("Linux x64 (Binary, Docker, APT, DNF, APK, Pacman, Quick, Linuxbrew)", "LINUX_X64"),
    ("Linux arm64 (Binary, Docker, Quick)", "LINUX_ARM64"),
    ("macOS ARM64 (Binary, Homebrew)", "MACOS_ARM64"),
    ("macOS x64 (Binary, Homebrew)", "MACOS_X64"),
    ("Windows x64 (Binary)", "WINDOWS_X64"),
    ("Windows arm64 (Binary)", "WINDOWS_ARM64"),
)


def main(argv: list[str]) -> int:
    del argv
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "") or DEFAULT_SUMMARY

    try:
        handle = open(summary_path, "a", encoding="utf-8")  # noqa: SIM115
    except OSError as exc:
        # The twin dies here too, under `set -e`, before judging any platform.
        log.error("%s: %s" % (summary_path, exc.strerror))
        return 1

    failed = False
    with handle:
        handle.write("## Install Method Test Results\n")
        handle.write("\n")
        handle.write("| Platform | Result |\n")
        handle.write("|----------|--------|\n")

        for label, suffix in PLATFORMS:
            value = os.environ.get("RESULT_%s" % suffix, "") or UNSET
            handle.write("| %s | %s |\n" % (label, value))
            if value != "success":
                failed = True
        handle.write("\n")

        if failed:
            handle.write("**Status:** Some installation method tests failed\n")
        else:
            version = os.environ.get("VERSION", "") or UNSET
            handle.write(
                "**Status:** All installation method tests passed for version %s\n" % version
            )

    if failed:
        log.error("Some installation method tests failed")
        return 1

    log.info(
        "All installation method tests passed for version %s"
        % (os.environ.get("VERSION", "") or UNSET)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
