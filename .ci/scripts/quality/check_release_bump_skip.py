#!/usr/bin/env python3
"""Entry point for the ported release-bump-skip gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.release_bump_skip`.

CUT OVER FROM BASH 2026-09-07 (W7 P4), measured with `npx tsx scripts/lib/shadow-gate.ts --pair w7p2-rbs --assert --k 5` (equivalence over 7 distinct trees, byte-identical streams on this tree, and byte-identical RED through the `RELEASE_DECIDE_SCRIPT` seam).

THE SUBJECT MOVED 2026-10-07. The gate drove `.ci/scripts/ci/dispatch-release.sh` until initialize cut over to the retried Python decider (056fe87b6); it now drives `python3 -m rediacc_ci.ci.dispatch_release --decide-only`, the module `rediacc_ci.ci.initialize.DISPATCH_RELEASE_MODULE` names, so it judges the decider CI runs rather than a frozen twin.

`test:` NAMES `test_gate_dispatch_release.py`, WHICH RUNS THIS GATE IN CI. Until 2026-10-07 it named this file, and no workflow step, pytest shard or battery member ran it, so the registry claimed CI coverage nothing delivered. `test_release_bump_skip_gate_holds_on_the_live_decider` in that file runs this entry point and its `--selftest` in the quality-pytest lane.

WHY AN ENTRY POINT AT ALL. A port cannot be run by path (`from rediacc_ci ...` fails with `.ci` off `sys.path`, which the insert below fixes), and the `-m` form that does work is unreadable to `check:ci-parity`'s tokenizer, which resolves its leaves to `[python3]`. `check_npmrc.py` records both measurements.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-release-bump-skip.sh` was the differential twin, and W7 P5 retired it.

---- gate ----
kind: test
test: .ci/rediacc_ci/tests/gates/test_gate_dispatch_release.py
blocker: BLOCKER: test_gate_dispatch_release.py runs this gate and its selftest in the quality-pytest lane; the gate drives the release decider initialize runs (python3 -m rediacc_ci.ci.dispatch_release --decide-only, the module named by initialize.DISPATCH_RELEASE_MODULE) with a shimmed gh through all five paths; it exists because a bump-none merge and a broken decision both produce "no release" and only the emitted signal distinguishes them, which no release gate could see
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import release_bump_skip

if __name__ == "__main__":
    raise SystemExit(release_bump_skip.main(sys.argv[1:]))
