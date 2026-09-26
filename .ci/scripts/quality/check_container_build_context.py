#!/usr/bin/env python3
"""Entry point for the container build-context gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.container_build_context`, which the gate's own `--selftest` exercises.

---- gate ----
step: Container build context
needs: none
lane: quality-static
selftest: true
why: workers/proxy's container could never build (its Dockerfile copies packages/* from
     the repo root while wrangler built from workers/proxy), and no CI path builds it
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import container_build_context

if __name__ == "__main__":
    raise SystemExit(container_build_context.main(sys.argv[1:]))
