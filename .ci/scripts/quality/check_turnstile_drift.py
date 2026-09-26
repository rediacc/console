#!/usr/bin/env python3
"""Entry point for the Turnstile widget drift gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.deploy.turnstile_drift`. CI's quality lane runs the CONTROLS only (`--selftest`: a fake Cloudflare, no network, no credential). The LIVE comparison needs production credentials, so it runs as the deploy preflight in `.github/workflows/cd-deploy-account.yml`, before any account Worker deploy or secret push.

---- gate ----
step: Turnstile widget drift
run: .ci/scripts/quality/check_turnstile_drift.py --selftest
selftest: true
needs: none
lane: quality-static
why: on 2026-09-24 Bitwarden's Turnstile secret had silently stopped matching the live
     rediacc-console widget, a routine secret push deployed it, and every login failed
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.deploy import turnstile_drift

if __name__ == "__main__":
    raise SystemExit(turnstile_drift.main(sys.argv[1:]))
