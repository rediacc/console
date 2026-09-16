#!/usr/bin/env python3
"""Entry point for the ported create-manifest docker script. Logic is in the package.

THIS ENTRY POINT IS DELIBERATELY HEADERLESS, matching its bash twin: neither
`.ci/scripts/docker/create-manifest.sh` nor this is a CI quality gate; both are
direct workflow `run:` targets. See `.ci/rediacc_ci/docker/__init__.py`'s
docstring for why nothing in this package carries a `---- gate ----` header, and
why no `package.json` / `scripts/ci-runner/manifest.ts` / `gates.lock.json`
registration follows from a module living there.

NOT YET THE LIVE TARGET. `.github/workflows/ci-build-docker.yml` still names the
bash twin at its three call sites (the renet, rdc and web image jobs). Flipping
them is Stage 2 of `agent/PLAN-w7p4w-docker-cutover.md`; this file is Stage 0,
the plumbing that makes that flip a one-word edit.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.docker import create_manifest as port

if __name__ == "__main__":
    raise SystemExit(port.main(sys.argv[1:]))
