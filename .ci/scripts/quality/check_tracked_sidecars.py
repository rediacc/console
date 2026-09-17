#!/usr/bin/env python3
"""Entry point for the ported tracked-sidecars gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.tracked_sidecars`, which pytest
and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 2). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-tracked-sidecars --assert --k 5
    -> 15 row(s), 15 distinct clean tree(s), 3 distinct finding set(s)
    -> equivalence holds over 15 distinct trees

and driven again on this tree, both streams captured SEPARATELY: the twin and
this port exit 0 with byte-identical stdout and byte-identical stderr.

DRIVEN RED AS WELL. In a fixture repository holding a copy of `.ci` and the real
`.claude/hooks/stop/wl_store.py` (the gate's single source for the pattern
list), `.claude/hooks/stop/.epics` was force-added to the index. Both sides exit
1, name that one path, and print byte-identical stdout and stderr. The pattern
count in the clean line -- "21 pattern(s) derived from wl_store.py" -- is the
shape a reader can watch for: if it ever collapses, the list stopped parsing,
and this gate answers that with a refusal rather than a pass.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port
cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below),
and `python3 -m rediacc_ci.quality.tracked_sidecars` works but is the wrong
registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves
the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It is a SHORT header -- no
`emit:`, no `blocker:`, no `lane:` -- and that is the twin's shape, not an
omission. This gate IS emitted, so `gate:bind --write` owns its step in
`quality-static` and will rewrite that step's `run:` from the twin's path to
this file's path in the same pass. Adding a `lane:` here to be tidy would pin a
lane the header never claimed.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-tracked-sidecars.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5.

---- gate ----
step: Tracked runtime sidecars
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import tracked_sidecars

if __name__ == "__main__":
    raise SystemExit(tracked_sidecars.main(sys.argv[1:]))
