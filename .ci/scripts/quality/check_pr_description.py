#!/usr/bin/env python3
"""Entry point for the ported PR description gate.

The logic lives in `rediacc_ci.quality.pr_description`; this file exists so the registry can invoke the port BY PATH. `python3 -m rediacc_ci.quality.pr_description` also works and is still wrong here: `check-ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`, so the gate fails parity. `gate-header.ts`'s `derivedRun` records that trap for every `.py`.

The three-line hop below is what makes a path invocation work at all: nothing puts `.ci` on `sys.path` for a gate run by path, so the import beneath it would die. Nothing follows the hop but that import, because a stdlib import placed after it fragments the block into a ruff I001.

NO `---- gate ----` HEADER, deliberately. `.ci/scripts/quality/check-pr-description.sh` carried none either: this pair is hand-registered in `.github/workflows/ci-quality.yml` and excused from the local gate set by `.ci/policy/.ci-parity-exempt`, and `check:ci-parity` is what holds those two ends together. Writing a header here would hand the step to `gate:bind`, which is a
different change from moving which file the step runs.

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-pr-description.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-pr-description.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch A2 retired it, and the cases that ran it were retired with it.

THE LEDGER CONDITION IS MET. Driven 2026-09-08:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-pr-description --assert --k 5
    -> equivalence holds over 6 distinct trees
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import pr_description

if __name__ == "__main__":
    raise SystemExit(pr_description.main(sys.argv[1:]))
