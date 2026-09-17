#!/usr/bin/env python3
"""Entry point for the ported drill-verdict-logic gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.drill_verdicts`, which pytest and
the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 5). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.drill_verdicts` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped. The twin carried exactly three fields -- `step`, `needs`, `selftest` -- and no `emit:`, no `blocker:`, no `id:`, no `kind:`, no `lane:`, no `run:`, no `why:`.

`needs: none` IS THE MEASURED ANSWER ON BOTH SIDES, not a default. `bind()`
unions the declared needs with `inferredNeeds(source)`; `inferredNeeds(twin)` is
`[]` (it drives bash only) and `inferredNeeds(this file)` is `[]` too, so both resolve to the empty set the declaration names.

DRIVEN, on this tree, both streams captured SEPARATELY:

    CI=true .ci/scripts/quality/check-drill-verdicts.sh  -> exit 0
    CI=true .ci/scripts/quality/check_drill_verdicts.py  -> exit 0
    stdout: byte-identical, EMPTY on both sides
    stderr: byte-identical, 370 bytes

The empty stdout is exactly why the streams are captured apart: this gate puts its whole verdict, five lines of it, on stderr. A merged comparison would have compared the log lines and a stdout-only comparison of merged output would have compared nothing.

DRIVEN RED AS WELL, which for this pair is the load-bearing half. Planted the 2026-08-05 defect itself into `scripts/drills/lib.sh`: the zero-assertion branch made to print `PASSED` where it must print `SKIPPED`. Both sides exit 1, both print an EMPTY stdout, and their stderr is byte-identical at 568 bytes -- the first of the four verdict assertions reds, the other three still
pass, so the gate is shown discriminating rather than collapsing. Reverted by its exact inverse and the file verified byte-identical to its pre-plant state, with the twin back at exit 0.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-drill-verdicts.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Drill verdict logic needs: none selftest: true ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import drill_verdicts

if __name__ == "__main__":
    raise SystemExit(drill_verdicts.main(sys.argv[1:]))
