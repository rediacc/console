#!/usr/bin/env python3
"""Entry point for the CLI proxy-safe output gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.cli_proxy_safe_output`, which the gate's own `--selftest` exercises.

---- gate ----
step: CLI proxy-safe output
needs: none
lane: quality-static
selftest: true
why: a CLI command that wrote to process.stdout or set process.exitCode directly returned
     empty output and exit 0 through the executor proxy (repo cat, 2026-09-24)
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import cli_proxy_safe_output

if __name__ == "__main__":
    raise SystemExit(cli_proxy_safe_output.main(sys.argv[1:]))
