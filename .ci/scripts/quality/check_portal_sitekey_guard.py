#!/usr/bin/env python3
"""Entry point for the portal Turnstile site-key guard gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.portal_sitekey_guard`, which the gate's own `--selftest` exercises.

---- gate ----
step: Portal site-key guard
needs: none
lane: quality-static
selftest: true
why: every production login failed on 2026-09-24 because the deployed portal was built
     with an empty Turnstile site key, and no check read the deploy workflows for it
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import portal_sitekey_guard

if __name__ == "__main__":
    raise SystemExit(portal_sitekey_guard.main(sys.argv[1:]))
