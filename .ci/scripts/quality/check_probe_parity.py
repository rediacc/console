#!/usr/bin/env python3
"""Entry point for the ported capability-probe-parity gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.probe_parity`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 2). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-probe-parity --assert --k 5
    -> 6 row(s), 6 distinct clean tree(s), 6 distinct finding set(s)
    -> equivalence holds over 6 distinct trees

and driven again on this tree, both streams captured SEPARATELY: the twin and this port exit 0 with byte-identical stdout (EMPTY, both of them) and byte-identical stderr (286 bytes). THE EMPTY STDOUT IS THE POINT OF CAPTURING THEM SEPARATELY: this gate writes its whole verdict, pass line included, to stderr, so a comparison that merged the streams would have compared the same bytes
twice and a comparison that only read stdout would have compared nothing.

DRIVEN RED AS WELL. In a fixture root holding a copy of `.ci` and copies of the two real subjects, one call to a verb the preflight never exercises was planted in the consumer:

    execFileSync('keyctl', ['link', '@u', '@s'])

Both sides exit 1, print "The keyring preflight does NOT exercise: link", and their stdout and stderr are byte-identical.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.probe_parity` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It is a SHORT header -- no `emit:`, no `blocker:`, no `lane:` -- which is the twin's shape, not an omission. This gate IS emitted, so `gate:bind --write` owns its step in `quality-static` and rewrites that step's `run:` from the twin's path to this file's path in the same pass.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-probe-parity.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5.

---- gate ---- step: Capability-probe parity needs: none selftest: true ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import probe_parity

if __name__ == "__main__":
    raise SystemExit(probe_parity.main(sys.argv[1:]))
