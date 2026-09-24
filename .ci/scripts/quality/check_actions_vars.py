#!/usr/bin/env python3
"""Entry point for the GitHub Actions variables gate.

The logic lives in `rediacc_ci.quality.actions_vars`; this file exists so the registry can invoke it BY PATH, the same split `check_secret_supply.py` uses and documents. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: GitHub Actions variables
needs: none
lane: quality-security
selftest: true
why: every vars.NAME a workflow reads must be declared in .ci/config/actions-vars.json
     and every declaration must still be read, so no workflow depends on a GitHub
     variable without the file saying why. Only the FIRST line of this field
     survives the parser. The secrets arm allows the bootstrap token named in
     secret-supply.json and the runner-minted GITHUB_TOKEN, nothing else.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import actions_vars

if __name__ == "__main__":
    raise SystemExit(actions_vars.main(sys.argv[1:]))
