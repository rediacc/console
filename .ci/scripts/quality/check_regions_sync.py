#!/usr/bin/env python3
"""Entry point for the ported regions-sync gate. The logic is in the package.

Contract section 5d: "a gate's ENTRY POINT lives in `.ci/scripts/quality/` ... even when all of its logic lives in the package and the entry point is three lines of import and dispatch", because `scripts/gate-bind.ts` enumerates its subjects with `git ls-files '.ci/scripts' 'scripts'` and a header anywhere else is INERT with nothing reporting the silence.

The sys.path hop is written by hand here and nowhere else. `rediacc_ci.paths` owns every other path question, but a script that wants the package has to put `.ci` on the path BEFORE it can import the module that would do it for it; see that module's `ensure_importable` docstring for the same bootstrap stated from the other end.

CUT OVER FROM BASH 2026-09-07 (W7 P4). The condition the previous version of this docstring was waiting for is met. Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-regions-sync --assert --k 5
    -> equivalence holds over 6 distinct trees

and driven again on this tree, both streams captured SEPARATELY, the twin and this port exit 0 with byte-identical stdout and byte-identical stderr. Driven RED as well, through the `REGIONS_ROOT_FILE` / `REGIONS_BAKED_FILE` seams with one extra key planted in the baked copy: both sides exit 1 and print the same 3,834 bytes, diff included.

`python3 -m rediacc_ci.quality.regions_sync` also works and is still the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`. The registered command is the bare path to this file.

THE `blocker:` BELOW NAMES A HARNESS THAT WAS RETARGETED IN THE SAME CHANGE. `.ci/scripts/test/gates/test-regions-sync.sh` sets its `SUT` to this file. That harness IS this gate's whole CI coverage -- no lane invokes it directly -- so had the registration moved here while the harness still drove the twin, CI would have stopped running the registered gate and the blocker below would
be false.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-regions-sync.sh` was retired by W7 P5. Registering this file was not a second gate for the same subject: what moved is which of the two the registry invokes.

---- gate ----
kind: test
test: .ci/scripts/test/gates/test-regions-sync.sh
blocker: BLOCKER: test-regions-sync.sh drives the REAL gate over the REAL regions.json and packages/shared/src/regions/data.json inside the gate-test battery (ci-quality.yml quality-security, "Quality-gate unit tests"), and its controls plant a divergence, an empty file and invalid JSON to prove all three refusals fire; the two files are held together by hand (no build step syncs them, despite what index.ts used to claim) and data.json is the ONLY region list users get because ${SITE_URL}/regions.json returns 404, so silent drift would ship to every install
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import regions_sync

if __name__ == "__main__":
    raise SystemExit(regions_sync.main(sys.argv[1:]))
