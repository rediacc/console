#!/usr/bin/env python3
"""Entry point for the W7P5-a real-run blocklist gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.w7p5a_real_run_blockers`, which
pytest and the port's own `--selftest` import directly.

---- gate ---- step: W7P5-a real-run blocklist needs: none lane: quality-static selftest: true why: the 39 real-run-blocked W7P5-a paths had BLOCKER reasons that validated
     but lived only in a status file nothing in CI reads
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import w7p5a_real_run_blockers

if __name__ == "__main__":
    raise SystemExit(w7p5a_real_run_blockers.main(sys.argv[1:]))
