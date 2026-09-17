#!/usr/bin/env python3
"""Entry point for the ported autopilot/breakpoint alignment gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.autopilot_breakpoint_alignment`.

CUT OVER FROM BASH 2026-09-07 (W7 P4). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-apbp --assert --k 5
    -> equivalence holds over 7 distinct trees

and driven again on this tree, both streams captured SEPARATELY, the twin and
this port exit 0 with byte-identical stdout and byte-identical stderr. Driven
RED as well, through the `AUTOPILOT_BP_ALIGN_*` seams against a copy of
autopilot.yml whose `send-email` default was flipped to false: both sides exit 1
and print the same drift line.

THE FIRST PLANT DID NOT FIRE, and the reason was the control, not the gate. It
rewrote the first `default:` after `send-email:`, which is the one INSIDE the
description string ("ON by default: on a public repo..."), not the field. This
gate deliberately does not compare descriptions, so staying green was correct.
Recorded because a control that cannot fire reads exactly like a gate that
cannot fail.

`id:` IS AN OVERRIDE AND MUST STAY. `derivedId` turns this filename into
`check:ci-autopilot-breakpoint-alignment`; the registered id is
`check:ci-autopilot-bp-align`, so without the line below the header would
re-derive a gate that does not exist.

WHY AN ENTRY POINT AT ALL. A port cannot be run by path (`from rediacc_ci ...`
fails with `.ci` off `sys.path`, which the insert below fixes), and the `-m`
form that does work is unreadable to `check:ci-parity`'s tokenizer, which
resolves its leaves to `[python3]`. `check_npmrc.py` records both measurements.

THE `blocker:` BELOW NAMES A HARNESS THAT MUST BE RETARGETED IN THE SAME CHANGE.
`.ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh:32` hard-codes
`GATE=...check-autopilot-breakpoint-alignment.sh`. That harness IS this gate's
whole CI coverage -- no lane invokes it directly -- so if the registration moves
here while the harness still drives the twin, CI stops running the registered
gate and the blocker below becomes false. The harness line is part of this
cutover's patch set, not a follow-up.

INVARIANT 5 IS INTACT: the twin is NOT deleted here; deletion is W7 P5.

---- gate ----
kind: test
test: .ci/scripts/test/gates/test-autopilot-breakpoint-alignment.sh
blocker: BLOCKER: test-autopilot-breakpoint-alignment.sh:59 runs the gate seam-free against the real .ci/breakpoint/workflow/breakpoint.yml and .github/workflows/autopilot.yml inside run-all.sh (ci-quality.yml quality-security, "Quality-gate unit tests"), so the real comparison executes every CI run; the mutated-copy cases around it prove both fire directions
id: check:ci-autopilot-bp-align
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import autopilot_breakpoint_alignment

if __name__ == "__main__":
    raise SystemExit(autopilot_breakpoint_alignment.main(sys.argv[1:]))
