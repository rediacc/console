#!/usr/bin/env python3
"""Entry point for the ported host-toolchain runtime-coverage gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.host_toolchain_coverage`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 5). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.host_toolchain_coverage` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, and this is the one of the six where the diff earns its keep. The twin carried FIVE fields -- `step`, `emit`, `blocker`, `needs`, `selftest` -- and no `id:`, no `kind:`, no `lane:`, no `run:`, no `why:`. The two that a retyped header loses:

  `emit: false`   suppresses the three workflow-region checks
                  (`gate-bind.ts:1724`) and nothing else. Losing it is SILENT:
                  the registration assertions above them still run and still
                  agree, which is exactly how the npmrc pilot dropped this field
                  and seven gates passed anyway. The loss surfaces later as
                  damage, when the next `gate:bind --write` emits a second copy
                  of this step into the region and the binder reds on two steps
                  of one name.
  `blocker:`      carried BYTE FOR BYTE from the twin, all 233 characters of
                  the line including its `blocker:` marker. It is a live
                  suppression reason under the BLOCKER convention, and a
                  suppression whose reason goes missing in a file move is a
                  quiet exemption, which is how a gate stops meaning what its
                  name says.

`needs: node` IS LOAD-BEARING AFTER THE MOVE. `bind()` unions the declared needs
with `inferredNeeds(source)`, and the twin got `node` for free from its own body.
Measured on both files: `inferredNeeds(twin)` is `["node"]`, `inferredNeeds(this file)` is `[]`, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:300`). Carried whole, both sides still resolve to {node}.

DRIVEN, on this tree, both streams captured SEPARATELY:

    CI=true .ci/scripts/quality/check-host-toolchain-coverage.sh  -> exit 0
    CI=true .ci/scripts/quality/check_host_toolchain_coverage.py  -> exit 0
    stdout: byte-identical, 267 bytes (both control lines)
    stderr: empty on both sides

DRIVEN RED AS WELL, by adding `gateprobetool` to `GATED_TOOLS` in `.ci/scripts/quality/check-toolchain-pins.sh` -- a pinned tool the runtime guard does not cover, which is precisely the drift this gate exists for. Both sides exit 1 with byte-identical stdout (122 bytes, both controls still firing) and stderr that agrees on every word.

THE ONE RESIDUE, stated rather than smoothed over: on the two per-finding stderr lines the twin's own `fail()` prints `printf '%s✗%s %s\n'`, three spaces after the marker, while the port's `log.error` prints one. Everything else on that stream is byte-identical, including the summary line and the two indented advice lines, and `diff <(sed 's/^✗ */✗ /' twin.err) <(sed 's/^✗ */✗ /'
port.err)` is empty. Named exactly: the ONLY normalisation applied is collapsing the run of spaces between the `✗` marker and the message to one. Not "fixed" in the port, because the alternative is printing the primary findings raw and abandoning the house logger's tty and NO_COLOR handling for a two-space cosmetic.

The plant was reverted by its exact inverse and `check-toolchain-pins.sh` verified byte-identical to its pre-plant state, with both sides back at exit 0.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-host-toolchain-coverage.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Host toolchain runtime coverage
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, and its subject IS the setup path. Emitting it into the region would gate it on setup succeeding, so the gate that explains a broken setup would be the one silenced by it.
needs: node
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import host_toolchain_coverage

if __name__ == "__main__":
    raise SystemExit(host_toolchain_coverage.main(sys.argv[1:]))
