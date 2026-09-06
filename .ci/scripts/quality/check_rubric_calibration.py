#!/usr/bin/env python3
"""Entry point for the ported rubric-calibration gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.rubric_calibration`.

The bash twin `.ci/scripts/quality/check-rubric-calibration.sh` carries the
`---- gate ----` header and remains the registered gate. This file carries none
until the differential ledger says the port kept its verdict.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci.quality import rubric_calibration

if __name__ == "__main__":
    raise SystemExit(rubric_calibration.main(sys.argv[1:]))
