#!/usr/bin/env python3
"""Entry point for the ported cleanup-staging docker script. Logic is in the package.

THIS ENTRY POINT IS DELIBERATELY HEADERLESS, matching its bash twin: neither
`.ci/scripts/docker/cleanup-staging.sh` nor this is a CI quality gate; both are
release-script forwarders. See `.ci/rediacc_ci/docker/__init__.py`'s docstring
for why nothing in this package carries a `---- gate ----` header, and why no
`package.json` / `scripts/ci-runner/manifest.ts` / `gates.lock.json`
registration follows from a module living there.

NOT YET THE LIVE TARGET, AND ITS FLIP IS NOT A ONE-WORD EDIT. No workflow
reaches this script at all; its single caller is
`.ci/scripts/release/cleanup-channel-docker-tags.sh:66`. Renaming that call site
to name this file makes `check:ci-staging-tag-guard` -- a live, currently-green
gate that greps for `cleanup-staging\\.sh` in `*.sh` and `*.yml` only -- find
ZERO executing call sites and take its anti-vacuity refusal. So Stage 5 of
`agent/PLAN-w7p4w-docker-cutover.md` widens that gate and its Python twin
`.ci/rediacc_ci/quality/staging_tag_guard.py` in the SAME commit as the flip.
This file is Stage 0 and changes nothing about which script executes.

THE MUTATION THIS ONE PERFORMS IS THE ONLY IRREVERSIBLE ONE OF THE THREE: a
`gh api --method DELETE` of a GHCR package version. A deleted package version
cannot be restored, which is why the plan treats ever feeding
`cleanup-channel-docker-tags.sh` a real `staging-*` CHANNEL as a separate
decision from this cutover.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.docker import cleanup_staging as port

if __name__ == "__main__":
    raise SystemExit(port.main(sys.argv[1:]))
