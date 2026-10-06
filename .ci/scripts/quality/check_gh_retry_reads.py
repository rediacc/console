#!/usr/bin/env python3
"""Entry point for check:ci-gh-retry-reads; the logic lives in `rediacc_ci.quality.gh_retry_reads`.

Every non-test GitHub READ made through `gh` under `.ci/rediacc_ci` and `.ci/scripts` must go through `rediacc_ci.core.gh_retry` (or a `ghx` helper with `attempts>=2`, or a spawn inside `retry_transient`), so a one-shot read that fails CI or releases the wrong build on a single 5xx cannot come back (agent/plans/PLAN-gh-retry.md box G9).

---- gate ----
step: GitHub reads retry transient faults
needs: none
lane: quality-static
selftest: true
why: one HTTP 502 failed CI Complete on PR #597 (run 37507913738), and an audit found
     20 modules reading GitHub through a one-shot `gh` spawn, three of which released
     the wrong build, bump or label set on a single 5xx instead of failing
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import gh_retry_reads

if __name__ == "__main__":
    raise SystemExit(gh_retry_reads.main(sys.argv[1:]))
