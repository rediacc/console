#!/usr/bin/env python3
"""Entry point for the ported script-exec-bit gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.script_exec_bit`, which pytest
and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 2). Measured that day:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-script-exec-bit --assert --k 5
    -> 6 row(s), 6 distinct clean tree(s), 6 distinct finding set(s)
    -> equivalence holds over 6 distinct trees

and driven again on this tree, both streams captured SEPARATELY: the twin and this port exit 0 with byte-identical stdout and byte-identical stderr (230 bytes of stdout, 0 of stderr).

DRIVEN RED AS WELL, because two greens prove nothing. In a fixture repository holding a copy of `.ci`, `scripts/dev/victim.sh` was committed at mode 100644 and `scripts/dev/caller.sh` invoked it as `./victim.sh`. Both sides exit 1 and print the same 1 offender, `scripts/dev/victim.sh (mode 100644)`, on stderr with byte-identical stdout and stderr.

WHY AN ENTRY POINT AT ALL, rather than registering the module. Both reasons are measured, and `check_npmrc.py` states them at length: a port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the three-line insert below), and `python3 -m rediacc_ci.quality.script_exec_bit` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and
resolves the leaves to `[python3]`. The registered command is the bare path to this file.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. `emit: false`, the `blocker:` it carries, `needs: none`, `selftest: true` and `lane: quality-code` all moved across unchanged. Dropping any of them is invisible to the gates for a while: `emit: false` suppresses only the three workflow-region checks while the registration assertions still agree, so the loss surfaces later as a
duplicate step written into the emitted region by `gate:bind --write`.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-script-exec-bit.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5.

---- gate ---- step: Block non-executable invoked scripts emit: false blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails. needs: none selftest: true lane: quality-code slow: true ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import script_exec_bit

if __name__ == "__main__":
    raise SystemExit(script_exec_bit.main(sys.argv[1:]))
