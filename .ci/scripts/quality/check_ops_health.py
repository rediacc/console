#!/usr/bin/env python3
"""Entry point for the off-box ops-health gate (agent/plans/PLAN-health-checks-local.md L4, D-gate). Logic is in `rediacc_ci.ops.ops_health.gate_main`.

Reads the ops-health Worker's `GET /v1/status` with the bearer OPS_HEALTH_READ_TOKEN and fails on a red verdict (exit 1) or on a `last_cron_at` older than the stale limit of .ci/config/ops-health.json (exit 1: the alerter itself has stopped). A status that cannot be read, or whose verdict is `unknown`, is exit 2. It asks a host outside the repository, so it is one of `UPSTREAM_GATES` (.ci/rediacc_ci/security/ci_workflow_invariants.py): hard on every cadence, held only by the `no-external-quality` label, and named by its job's announcer.

---- gate ----
step: Off-box ops health
needs: none
lane: quality-go
when: inputs.external_quality != 'skip'
env-OPS_HEALTH_READ_TOKEN: ${{ env.BWS_OPS_HEALTH_READ_TOKEN }}
---- end gate ----
"""

import sys

import _cipath
from rediacc_ci.ops import ops_health

if __name__ == "__main__":
    if sys.argv[1:] in (["-h"], ["--help"]):
        print(__doc__)
        raise SystemExit(0)
    raise SystemExit(ops_health.gate_main())
