#!/usr/bin/env python3
"""Entry point for the account-env-retired gate.

The logic lives in `rediacc_ci.quality.account_env_retired`; this file exists so the registry can invoke it BY PATH, the same split `check_actions_vars.py` uses. The `---- gate ----` header is HERE and not on the module, because `gate-bind` reads the file package.json names.

---- gate ----
step: Account env files retired
needs: submodules
selftest: true
why: private/account/.env is retired in favour of Bitwarden profiles, so no tracked file
     may start reading or recommending it again, the dotenv table only shrinks, and the
     bootstrap token path must stay outside the repository.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import account_env_retired

if __name__ == "__main__":
    raise SystemExit(account_env_retired.main(sys.argv[1:]))
