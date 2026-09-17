#!/usr/bin/env python3
"""Entry point for the ported retag-image docker script. Logic is in the package.

THIS ENTRY POINT IS DELIBERATELY HEADERLESS, matching its bash twin: neither
`.ci/scripts/docker/retag-image.sh` nor this is a CI quality gate; both are
direct workflow `run:` targets. See `.ci/rediacc_ci/docker/__init__.py`'s
docstring for why nothing in this package carries a `---- gate ----` header, and
why no `package.json` / `scripts/ci-runner/manifest.ts` / `gates.lock.json`
registration follows from a module living there.

NOT YET THE LIVE TARGET. `.github/workflows/cd-stage.yml` and
`.github/workflows/cd-v2.yml` still name the bash twin at three call sites each.
Flipping them is Stages 3 and 4 of `agent/PLAN-w7p4w-docker-cutover.md`, in that
order, because cd-v2's promotion touches `:stable` and `--push-latest`; this
file is Stage 0, the plumbing that makes those flips one-word edits.
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.docker import retag_image as port

if __name__ == "__main__":
    raise SystemExit(port.main(sys.argv[1:]))
