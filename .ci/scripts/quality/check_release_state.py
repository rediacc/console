#!/usr/bin/env python3
"""Entry point for the ported release-state bijection gate.

The logic lives in `rediacc_ci.quality.release_state`; this file exists so the registry can invoke the port BY PATH, which is the only invocation form `check-ci-parity`'s tokenizer can read. `python3 -m rediacc_ci.quality.release_state` works and is still wrong here: parity resolves the leaves of a `-m` command to `[python3]` and the gate fails. `gate-header.ts`'s `derivedRun`
records that trap.

The three-line hop below is what makes the path invocation work at all. Nothing follows it but the import it exists for: a gate run by path has no `.ci` on `sys.path`, so `from rediacc_ci.quality import release_state` dies without it, and any stdlib import placed after it fragments the block into a ruff I001.

NO `---- gate ----` HEADER, and that is deliberate rather than an omission. `check-release-state.sh` carries none either: this pair is hand-registered in `package.json` and `.github/workflows/ci.yml`, and `check:ci-parity` is what holds the two ends together. Writing a header here would hand the step to `gate:bind`, which is a different change from moving which file the step runs.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-release-state.sh` was the twin this port is proven against, and W7 P5 retired it; the shadow ledger under `.ci/shadow/` is the licence record.

THE LEDGER CONDITION IS MET. Driven 2026-09-08:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-release-state --assert --k 5
    -> equivalence holds over 5 distinct trees
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import release_state

if __name__ == "__main__":
    raise SystemExit(release_state.main(sys.argv[1:]))
