#!/usr/bin/env python3
"""Entry point for the control-plant proof gate.

The logic lives in `rediacc_ci.quality.plant_proofs`; this file exists so the
registry can invoke it BY PATH, for the parity-tokenizer reason recorded in
`gate-header.ts`'s `derivedRun` and in `_cipath`'s docstring. The
`---- gate ----` header is HERE and not on the module, because `gate-bind` reads
the file package.json names.

---- gate ----
step: Control plant proofs
needs: none
lane: quality-static
selftest: true
why: a control proves a gate can fail by feeding it a MUTATED fixture, and a
     mutation whose needle has gone changes nothing -- so the control scans the
     clean text, asserts the opposite verdict about identical input, and passes
     for free. Python already refuses this via `rediacc_ci.controls.plant`
     (check:ci-python-control-plants) and bash GATE SCRIPTS via
     check:ci-control-vacuity; this closes the other two thirds, every tracked
     .sh and every tracked .ts, and REFUSES if the Python delegate stops being
     registered rather than leaving that third silently unscanned
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import plant_proofs

if __name__ == "__main__":
    raise SystemExit(plant_proofs.main(sys.argv[1:]))
