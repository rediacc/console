#!/usr/bin/env python3
"""Run `rediacc_ci.quality.cli_contract` by path, with the same argument check its own entry makes.

The gate is declared by the `---- gate ----` header in `.ci/rediacc_ci/quality/cli_contract.py` and registered from it
(`npm run gen:gates`), which runs the module directly; this file stays for callers that run it by path.
"""

import sys

import _cipath
from rediacc_ci.quality import cli_contract

if __name__ == "__main__":
    raise SystemExit(cli_contract.main(sys.argv[1:]))
