#!/usr/bin/env python3
"""Entry point for the ported regions-sync gate. The logic is in the package.

Contract section 5d: "a gate's ENTRY POINT lives in `.ci/scripts/quality/` ...
even when all of its logic lives in the package and the entry point is three
lines of import and dispatch", because `scripts/gate-bind.ts` enumerates its
subjects with `git ls-files '.ci/scripts' 'scripts'` and a header anywhere else
is INERT with nothing reporting the silence.

The sys.path hop is written by hand here and nowhere else. `rediacc_ci.paths`
owns every other path question, but a script that wants the package has to put
`.ci` on the path BEFORE it can import the module that would do it for it; see
that module's `ensure_importable` docstring for the same bootstrap stated from
the other end.

NO `---- gate ----` HEADER YET, deliberately. The bash twin
`.ci/scripts/quality/check-regions-sync.sh` is still the registered gate and is
still what CI runs. Registering this file as a second gate for the same subject
would double the CI cost and, worse, would make a disagreement between the two
implementations read as two independent failures rather than as the one port
defect it is. The header lands when the differential ledger says the port kept
the verdict; the exact registry text is in the W7 P2 registry proposal.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci.quality import regions_sync

if __name__ == "__main__":
    raise SystemExit(regions_sync.main(sys.argv[1:]))
