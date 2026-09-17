#!/usr/bin/env python3
"""Entry point for the ported rubric-calibration gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.rubric_calibration`.

CUT OVER FROM BASH 2026-09-07 (W7 P4). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-rubric --assert --k 5
    -> equivalence holds over 7 distinct trees

and driven again on this tree, both streams captured SEPARATELY, the twin and this port exit 0 with byte-identical stdout and byte-identical stderr. The RED direction was driven too: handed a copy of `.ci/config/rubric-calibration.json`
with every recorded hash zeroed, both sides exit 1 and name the same four
rubrics in the same order, byte for byte.

WHY AN ENTRY POINT AT ALL. A port cannot be run by path (`from rediacc_ci ...` fails with `.ci` off `sys.path`, which the insert below fixes), and the `-m` form that does work is unreadable to `check:ci-parity`'s tokenizer, which resolves its leaves to `[python3]`. `check_npmrc.py` records both measurements.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-rubric-calibration.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5.

---- gate ---- step: Rubric calibration
     # The EXISTING step name. Renaming a step is a separate change from
     # moving which file the step invokes.
needs: none lane: quality-code ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import rubric_calibration

if __name__ == "__main__":
    raise SystemExit(rubric_calibration.main(sys.argv[1:]))
