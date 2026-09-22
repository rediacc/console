#!/usr/bin/env python3
"""Entry point for the ported autopilot/breakpoint alignment gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.autopilot_breakpoint_alignment`.

CUT OVER FROM BASH 2026-09-07 (W7 P4). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-apbp --assert --k 5
    -> equivalence holds over 7 distinct trees

and driven again on this tree, both streams captured SEPARATELY, the twin and this port exit 0 with byte-identical stdout and byte-identical stderr. Driven RED as well, through the `AUTOPILOT_BP_ALIGN_*` seams against a copy of autopilot.yml whose `send-email` default was flipped to false: both sides exit 1 and print the same drift line.

THE FIRST PLANT DID NOT FIRE, and the reason was the control, not the gate. It rewrote the first `default:` after `send-email:`, which is the one INSIDE the description string ("ON by default: on a public repo..."), not the field. This gate deliberately does not compare descriptions, so staying green was correct. Recorded because a control that cannot fire reads exactly like a gate
that cannot fail.

`id:` IS AN OVERRIDE AND MUST STAY. `derivedId` turns this filename into `check:ci-autopilot-breakpoint-alignment`; the registered id is `check:ci-autopilot-bp-align`, so without the line below the header would re-derive a gate that does not exist.

WHY AN ENTRY POINT AT ALL. A port cannot be run by path (`from rediacc_ci ...` fails with `.ci` off `sys.path`, which the insert below fixes), and the `-m` form that does work is unreadable to `check:ci-parity`'s tokenizer, which resolves its leaves to `[python3]`. `check_npmrc.py` records both measurements.

THE `blocker:` BELOW NAMES A HARNESS THAT WAS RETARGETED IN THE SAME CHANGE. `.ci/rediacc_ci/tests/gates/test_gate_autopilot_breakpoint_alignment.py` (the pytest port of the retired `test-autopilot-breakpoint-alignment.sh`, W7 P5) sets its `GATE` to this file. That harness IS this gate's whole CI coverage -- no lane invokes it directly -- so had the registration moved here while
the harness still drove the twin, CI would have stopped running the registered gate and the blocker below would be false.

INVARIANT 5 IS DISCHARGED, TWICE. W7 P5 retired the bash GATE twin; the shadow ledger under `.ci/shadow/` is the licence record. The bash TEST twin (`test-autopilot-breakpoint-alignment.sh`) was retired in the same wave, once its pytest port reached the same verdict on the same tree, case for case.

---- gate ----
kind: test
test: .ci/rediacc_ci/tests/gates/test_gate_autopilot_breakpoint_alignment.py
blocker: BLOCKER: test_gate_autopilot_breakpoint_alignment.py:52 runs the gate seam-free against the real .ci/breakpoint/workflow/breakpoint.yml and .github/workflows/autopilot.yml, and check:ci-pytest (ci-quality.yml quality-security, "Python package tests") executes that real comparison every CI run; the mutated-copy cases around it prove both fire directions
id: check:ci-autopilot-bp-align
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import autopilot_breakpoint_alignment

if __name__ == "__main__":
    raise SystemExit(autopilot_breakpoint_alignment.main(sys.argv[1:]))
