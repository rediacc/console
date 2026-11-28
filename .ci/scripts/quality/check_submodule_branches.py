#!/usr/bin/env python3
"""Entry point for the ported submodule branches gate.

The logic lives in `rediacc_ci.quality.submodule_branches`; this file exists so the registry can invoke the port BY PATH. `python3 -m rediacc_ci.quality.submodule_branches` also works and is still wrong here: `check-ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`, so the gate fails parity. `gate-header.ts`'s `derivedRun` records that trap for every
`.py`.

The three-line hop below is what makes a path invocation work at all: nothing puts `.ci` on `sys.path` for a gate run by path, so the import beneath it would die. Nothing follows the hop but that import, because a stdlib import placed after it fragments the block into a ruff I001.

NO `---- gate ----` HEADER, deliberately. `.ci/scripts/quality/check-submodule-branches.sh` carries none either: this pair is hand-registered in `.github/workflows/ci-quality.yml` and excused from the local gate set by `.ci/policy/.ci-parity-exempt`, and `check:ci-parity` is what holds those two ends together. Writing a header here would hand the step to `gate:bind`, which is a
different change from moving which file the step runs.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-submodule-branches.sh` is NOT deleted by this change. It stays on disk as the twin this port is proven against; deleting it is W7 P5's job, in a later change.

THE LEDGER CONDITION WAS MET. Driven 2026-09-08 with the shadow gate (deleted in commit:bf054adcd4): equivalence holds over 14 distinct trees.
"""

import sys

import _cipath
import _gate_args
from rediacc_ci.quality import submodule_branches

if __name__ == "__main__":
    _gate_args.parse("check_submodule_branches.py", sys.argv[1:], switches=("--selftest",))
    raise SystemExit(submodule_branches.main(sys.argv[1:]))
