#!/usr/bin/env python3
"""Entry point for the Bitwarden step-scope gate.

The logic and the controls live in `rediacc_ci.quality.bws_step_scope`; this file exists so the registry can invoke it BY PATH. The five rules, the names they cover (`.ci/config/bws-step-scoped.json`) and the one exposure they cannot reach are argued in that module's docstring.

---- gate ----
step: Bitwarden step-scoped secrets
needs: none
selftest: true
lane: quality-security
why: a production signing key fetched at job start through bws-secrets lands in
     GITHUB_ENV and is readable by every later step of the job. This keeps each
     listed key to a dedicated fetch, its consumer and an always() scrub.
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.quality import bws_step_scope

if __name__ == "__main__":
    raise SystemExit(bws_step_scope.main(sys.argv[1:]))
