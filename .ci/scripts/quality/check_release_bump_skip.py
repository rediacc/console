#!/usr/bin/env python3
"""Entry point for the ported release-bump-skip gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.release_bump_skip`.

No `---- gate ----` header: the bash twin remains the registered gate until the
differential ledger says the port kept its verdict.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from rediacc_ci.quality import release_bump_skip

if __name__ == "__main__":
    raise SystemExit(release_bump_skip.main(sys.argv[1:]))
