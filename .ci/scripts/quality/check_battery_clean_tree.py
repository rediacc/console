#!/usr/bin/env python3
"""Entry point for the ported battery clean-tree guard gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.battery_clean_tree`, which pytest
and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 5). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port
cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below),
and `python3 -m rediacc_ci.quality.battery_clean_tree` works but is the wrong
registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves
the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than
retyped. The twin carried exactly three fields -- `step`, `needs`, `selftest` --
and no `emit:`, no `blocker:`, no `id:`, no `kind:`, no `lane:`, no `run:`, no
`why:`.

`needs: none` IS THE MEASURED ANSWER ON BOTH SIDES. `inferredNeeds(twin)` is
`[]` and `inferredNeeds(this file)` is `[]`, so the union does not move.

DRIVEN, on this tree, both streams captured SEPARATELY:

    CI=true .ci/scripts/quality/check-battery-clean-tree.sh  -> exit 0
    CI=true .ci/scripts/quality/check_battery_clean_tree.py  -> exit 0
    stdout: byte-identical, 505 bytes (the three PASS lines, the verdict and its
      stated blind spot)
    stderr: empty on both sides

The three PASS lines are on STDOUT on both sides, which is unusual for this repo
and is the twin's contract rather than an oversight: a caller reading this
gate's stdout sees the whole tally. The port's own docstring states it.

DRIVEN RED AS WELL, by planting the exact defect the gate exists for into
`.ci/scripts/test/run-all.sh`: the `{ grep -v '^??' || true; }` in `tree_state`
reduced to a bare `grep -v '^??'`, which under `set -euo pipefail` aborts the
snapshot on a CLEAN tree. Both sides exit 1 with byte-identical stdout (242
bytes) and byte-identical stderr (43 bytes): the middle assertion reds with
`rc=1 out=` while BOTH controls still pass, so the instrument is shown intact.
Reverted by its exact inverse and the file verified byte-identical to its
pre-plant state (it carried an unrelated modification from another session at
baseline, so the comparison was against a `cp` taken immediately before the
plant, not against HEAD), with the twin back at exit 0.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-battery-clean-tree.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Battery clean-tree guard
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import battery_clean_tree

if __name__ == "__main__":
    raise SystemExit(battery_clean_tree.main(sys.argv[1:]))
