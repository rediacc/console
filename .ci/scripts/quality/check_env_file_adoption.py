#!/usr/bin/env python3
"""Entry point for the env-file adoption gate.

The logic lives in `rediacc_ci.quality.env_file_adoption`; this file exists so the registry can invoke it BY PATH, for the parity-tokenizer reason recorded in `gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring.

---- gate ----
step: Env file adoption
needs: none
lane: quality-static
selftest: true
why: `set -a; source <envfile>` both EXECUTES the file and lets it overwrite the
     shell, and the files it is used on hold ACCOUNT_ED25519_PRIVATE_KEY and
     ACCOUNT_JWT_SECRET. Three call sites adopted env_file_load instead; this
     sweeps for the pattern coming back, RUNS each adopted site's own invocation
     against a planted override to prove the shell still wins, and drives a real
     `set -a; source` on the same fixture demanding the opposite answer so the
     second check cannot pass against a helper that reads nothing
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import env_file_adoption

if __name__ == "__main__":
    raise SystemExit(env_file_adoption.main(sys.argv[1:]))
