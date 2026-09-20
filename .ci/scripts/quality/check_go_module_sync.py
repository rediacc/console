#!/usr/bin/env python3
"""Entry point for the ported Go-module-sync gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.go_module_sync`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 4). See DRIVEN, below, for the measurement taken on this tree that licences the flip.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.go_module_sync` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`, no `kind:`. An earlier batch lost `emit: false` and a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses
only the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran and still agreed.

`needs: none` IS LOAD-BEARING AND IS NOT A NO-OP HERE. `bind()` unions the declared needs with `inferredNeeds(source)`, and the twin's own body carries `go build`-shaped strings; this two-import entry point carries none outside its docstring, and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`), so it infers NOTHING. Declaring `none` verbatim keeps the
declared side identical; what the twin inferred for free is discussed under DRIVEN, because the gate itself probes for `go` and answers 2 when it is absent rather than pretending to have checked.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`, `selftestIsReal`), so for a `.py` gate it decides nothing. It is true of the port regardless -- `go_module_sync.main(["--selftest"])` runs a real control battery.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-go-module-sync.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Check Go module sync against the renet worktree
needs: none
selftest: true
lane: quality-go
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import go_module_sync

if __name__ == "__main__":
    raise SystemExit(go_module_sync.main(sys.argv[1:]))
