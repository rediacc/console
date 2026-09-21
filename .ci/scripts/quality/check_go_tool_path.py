#!/usr/bin/env python3
"""Entry point for the ported go-tool-PATH gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.go_tool_path`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 2). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-gotoolpath --assert --k 5
    -> 5 row(s), 5 distinct clean tree(s), 5 distinct finding set(s)
    -> equivalence holds over 5 distinct trees

and driven again on this tree, both streams captured SEPARATELY: the twin and this port exit 0 with byte-identical stdout and byte-identical stderr (373 bytes of stdout, 0 of stderr).

DRIVEN RED AS WELL. In a fixture repository holding a copy of `.ci`, `scripts/dev/plant.sh` was committed with `go install .../goimports@latest` followed by a bare `goimports -w .`, with no GOBIN and no GOPATH/bin on PATH. Both sides exit 1, name `scripts/dev/plant.sh`, and print byte-identical stdout and stderr. Note the port keeps the twin's anti-vacuity floor of 50 tracked shell
files, so the fixture is a real corpus rather than one planted file.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.go_tool_path` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, including `emit: false`, its `blocker:`, `needs: none`, `selftest: true`, `lane:` and the whole `why:` block.

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-go-tool-path.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-gotoolpath.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch B6 retired it, and the header below is what the gate now runs from.

---- gate ----
step: Go tool PATH
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
why: Console's own scripts already use the right shape -- toolchain.sh installs
     with GOBIN and invokes by absolute path, which is why check:ci-shell-format
     passes on a host with no shfmt on PATH. This gate exists so that stays
     true: the defect it names cost four instances in the renet submodule on
     2026-08-27, each one a `go install` followed by a bare invocation, and CI
     could not see any of them because actions/setup-go masks it.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import go_tool_path

if __name__ == "__main__":
    raise SystemExit(go_tool_path.main(sys.argv[1:]))
