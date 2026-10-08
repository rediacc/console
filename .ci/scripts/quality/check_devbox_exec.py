#!/usr/bin/env python3
"""Entry point for the devbox exec-invocation gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.devbox_exec`, which pytest and the port's own `--selftest` import directly. A path invocation puts nothing on `sys.path`, hence the `_cipath` hop below.

The subject is `.ci/rediacc_ci/core/devbox.py`, the Python port of the retired `.ci/lib/devbox.sh`.

---- gate ----
step: Devbox exec invocation
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import devbox_exec

if __name__ == "__main__":
    raise SystemExit(devbox_exec.main(sys.argv[1:]))
