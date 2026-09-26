#!/usr/bin/env python3
"""Entry point for the ported toolchain-pins single-source gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.toolchain_pins`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.toolchain_pins` works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from `.ci/scripts/quality/check-toolchain-pins.sh` PROGRAMMATICALLY, de-commented, and diffed as an ordered list of WHOLE LINES against the block in this docstring; the diff is empty over 8 line(s). The twin carried exactly these fields, in this order: `step`, `emit`, `blocker`, `needs`, `selftest`, `lane`. NO `id:`:
the basename derives `check:ci-toolchain-pins`, the manifest id. The `blocker:` is 233 characters and moved byte for byte, because it is a live suppression reason under the BLOCKER convention and a reason lost in a file move is a quiet exemption. The pilot lost `emit: false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three
workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files and comparing every bound field except `file` and `run`, not by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing from its body and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:301`). Both sides bind to `needs: []`, which is what `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-toolchain-pins.sh
      -> exit 0
    .ci/scripts/quality/check_toolchain_pins.py
      -> exit 0
    stdout: BYTE-IDENTICAL, 1468 bytes, sha256 0a001d688585d832...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against an unchanged tree FIRST, to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters. The plant is an UNTRACKED `.ci/scripts/quality/__gate_probe_toolchain_pins.sh` that runs `shellcheck` without ever resolving it at the pin, which is A6's shape. Untracked is deliberate and is what the plant is FOR: A6 unions `git ls-files` with `ls-files --others --exclude-standard` precisely because a gate not yet committed was
once invisible to it. THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN, by running that same `--others` enumeration and confirming the probe appears in it. The plant was removed with `rm` and `git status --porcelain` diffed against its pre-plant capture with no difference.

THE PORT NEEDED ONE FIX TO REACH PARITY, and it is recorded here rather than left implicit. The first differential run produced the SAME 21 lines and the SAME 1468 bytes on both sides in a DIFFERENT ORDER: the port ran every control
from one tail block, while the twin prints the two A8 controls between A8 and A6
(twin lines 181-197) and the A9 control right after A9 (twin line 286). Same byte count, different bytes, and comparing lengths would have called it equal. `run_controls` was therefore split into `run_a8_controls`, `run_a9_control` and `run_controls`, called at the twin's positions, with the shared fixture-dir `mkdir` moved into the A8 function so the twin's own "mkdir first"
property survives the split. Both sides -> exit 1, stdout 1239 bytes, sha256 43d6c2425a570014..., stderr 109 bytes, sha256 e22bbde06b531536....

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-toolchain-pins.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-toolchain-pins.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch C1 retired it, and this entry point is what the gate runs from.

---- gate ----
step: Toolchain pins
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, and its subject IS the setup path. Emitting it into the region would gate it on setup succeeding, so the gate that explains a broken setup would be the one silenced by it.
needs: none
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import toolchain_pins

if __name__ == "__main__":
    raise SystemExit(toolchain_pins.main(sys.argv[1:]))
