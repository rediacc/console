#!/usr/bin/env python3
"""Entry point for the ported commit identity gate.

The logic lives in `rediacc_ci.quality.commit_identity`; this file exists so the registry can invoke the port BY PATH. `python3 -m rediacc_ci.quality.commit_identity` also works and is still wrong here: `check-ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`, so the gate fails parity. `gate-header.ts`'s `derivedRun` records that trap for every `.py`.

The three-line hop below is what makes a path invocation work at all: nothing puts `.ci` on `sys.path` for a gate run by path, so the import beneath it would die. Nothing follows the hop but that import, because a stdlib import placed after it fragments the block into a ruff I001.

NO `---- gate ----` HEADER, deliberately. `.ci/scripts/quality/check-commit-identity.sh` carries none either: this pair is hand-registered in `.github/workflows/ci-quality.yml` and excused from the local gate set by `.ci/policy/.ci-parity-exempt`, and `check:ci-parity` is what holds those two ends together. Writing a header here would hand the step to `gate:bind`, which is a
different change from moving which file the step runs.

INVARIANT 5 IS DISCHARGED, W7 P5. `.ci/scripts/quality/check-commit-identity.sh` and its gate test `.ci/scripts/test/gates/test-commit-identity.sh` are both deleted: the fixture behaviour the test proved is now carried by `.ci/rediacc_ci/tests/gates/test_gate_commit_identity.py`, retargeted at this entry point and checked to reach the same 10 verdicts on the same 10
fixtures before the twin left.

THE LEDGER CONDITION WAS MET. Driven 2026-09-08:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-commit-identity --assert --k 5
    -> equivalence holds over 5 distinct trees
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import commit_identity

if __name__ == "__main__":
    raise SystemExit(commit_identity.main(sys.argv[1:]))
