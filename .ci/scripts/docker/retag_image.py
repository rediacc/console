#!/usr/bin/env python3
"""Entry point for the ported retag-image docker script. Logic is in the package.

THIS ENTRY POINT IS DELIBERATELY HEADERLESS, as its retired bash twin was: neither was a CI quality gate; both are direct workflow `run:` targets. See `.ci/rediacc_ci/docker/__init__.py`'s docstring for why nothing in this package carries a `---- gate ----` header, and why no `package.json` / `scripts/ci-runner/manifest.ts` / `gates.lock.json`
registration follows from a module living there.

THE LIVE TARGET. `.github/workflows/cd-stage.yml` and `.github/workflows/cd-v2.yml` name this path at three call sites each; the flips were Stages 3 and 4 of `agent/PLAN-w7p4w-docker-cutover.md` and this file was Stage 0, the plumbing that made them one-word edits. The bash twin is retired and its recorded results are in `.ci/rediacc_ci/tests/goldens/retag-image/`.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.docker import retag_image as port

if __name__ == "__main__":
    raise SystemExit(port.main(sys.argv[1:]))
