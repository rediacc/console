#!/usr/bin/env python3
"""Entry point for the ported release-state bijection gate.

The logic lives in `rediacc_ci.quality.release_state`; this file exists so the registry can invoke the port BY PATH, which is the only invocation form `check-ci-parity`'s tokenizer can read. `python3 -m rediacc_ci.quality.release_state` works and is still wrong here: parity resolves the leaves of a `-m` command to `[python3]` and the gate fails. `gate-header.ts`'s `derivedRun`
records that trap.

The three-line hop below is what makes the path invocation work at all. Nothing follows it but the import it exists for: a gate run by path has no `.ci` on `sys.path`, so `from rediacc_ci.quality import release_state` dies without it, and any stdlib import placed after it fragments the block into a ruff I001.

NO `---- gate ----` HEADER, and that is deliberate rather than an omission. `check-release-state.sh` carries none either: this pair is hand-registered in `package.json` and `.github/workflows/ci.yml`, and `check:ci-parity` is what holds the two ends together. Writing a header here would hand the step to `gate:bind`, which is a different change from moving which file the step runs.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-release-state.sh` was the twin this port is proven against, and W7 P5 retired it. The licence was a shadow ledger (equivalence over 5 distinct trees, 2026-09-08), deleted with its gate in commit:936280cd35, so that record is in history only.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import release_state

if __name__ == "__main__":
    _gate_args.parse("check_release_state.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(release_state.main(sys.argv[1:]))
