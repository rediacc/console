#!/usr/bin/env python3
"""Run `rediacc_ci.quality.cli_contract` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/cli_contract.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import cli_contract

if __name__ == "__main__":
    _gate_args.parse("check_cli_contract.py", sys.argv[1:], switches=("--selftest", "--no-build"))
    raise SystemExit(cli_contract.main(sys.argv[1:]))
