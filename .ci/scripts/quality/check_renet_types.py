#!/usr/bin/env python3
"""Entry point for the ported renet generated-types freshness gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.renet_types`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 3). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.renet_types` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly three fields -- `step`, `needs`, `selftest` -- and NO `lane:`, no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`. The absent `lane:` is the twin's shape, deliberately preserved: the manifest puts this gate in `quality-go`, and pinning a lane here
would be a new assertion rather than a carried one. The batch before this one lost `emit: false` and a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`)
while the registration assertions above them still ran and still agreed.

`needs: go, submodules` IS THE LOAD-BEARING FIELD OF THIS MOVE. `bind()` unions the declared needs with `inferredNeeds(source)`, and the twin got BOTH for free
from its own body: `go build` matches the go pattern and the literal
`private/renet` matches the submodule one. This entry point contains neither string outside its docstring, and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`), so it infers NOTHING. Dropping the declaration would therefore have silently moved the gate into a lane with no Go toolchain and no submodules, where it would have skipped on the submodule guard and
reported exit 0 having verified nothing. Carried whole, both sides resolve to
{go, submodules}, unchanged.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

DRIVEN, on this tree, both streams captured SEPARATELY. Both build renet with the real Go toolchain and run the real generator, so this is the gate's whole path and not a stubbed one. Both exit 0 with identical stderr.

STDOUT IS NOT BYTE-STABLE FOR EITHER SIDE, and that is a property of the SUBJECT, not of the port. The generator prints `Generated <TMPDIR>/<file>` for each of its six outputs, and `<TMPDIR>` is a fresh `mktemp -d` every run, so TWO CONSECUTIVE RUNS OF THE TWIN disagree on all six lines. Measured that way rather than asserted: the twin was driven twice and diffed against itself
first. With the temp path normalised, twin and port produce the same six lines, sha256 1a752c96d5dc8baae783336ba8648258385437d0b5c330ddadab95afa65f2a8b for both.

DRIVEN RED AS WELL, against a fixture root holding a copy of `.ci`, a copy of `packages/shared/src/renet-contract/data` with a line appended to `vault.generated.ts`, and a symlink to the real renet submodule. Both sides exit 1, both name `vault.generated.ts` as the one stale file, and their stdout (normalised for the temp path) and stderr are identical.

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-renet-types.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-renet-types.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch A2 retired it, and the cases that ran it were retired with it.

---- gate ----
step: Check renet types freshness
needs: go, submodules
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import renet_types

if __name__ == "__main__":
    raise SystemExit(renet_types.main(sys.argv[1:]))
