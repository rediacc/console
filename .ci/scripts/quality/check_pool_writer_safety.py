#!/usr/bin/env python3
"""Entry point for the ported pool-writer-safety gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.pool_writer_safety`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.pool_writer_safety` works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from `.ci/scripts/quality/check-pool-writer-safety.sh` PROGRAMMATICALLY, de-commented, and diffed as an ordered list of WHOLE LINES against the block in this docstring; the diff is empty over 5 line(s). The twin carried exactly these fields, in this order: `step`, `needs`, `selftest`. NO `id:`, NO `emit:`, NO
`lane:`, and the absences are the twin's. This gate's step sits INSIDE a `# >>> gate-bind` region in `ci-quality.yml` (job quality-static), so it is emitted rather than hand-written, which is why it carries no `emit: false` and no blocker to justify one. The pilot lost `emit: false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the
three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files and comparing every bound field except `file` and `run`, not by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing from its body and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:301`). Both sides bind to `needs: []`, which is what `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-pool-writer-safety.sh
      -> exit 0
    .ci/scripts/quality/check_pool_writer_safety.py
      -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 139 bytes, sha256 1db167600d8704fa...

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against an unchanged tree FIRST, to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters. NO REAL-TREE PLANT WAS NEEDED, because this gate offers two seams both implementations honour: `POOL_SAFETY_GATES_DIR` and `POOL_SAFETY_RUNNER`. The fixture is a `cp -r` of the real gate battery and runner into /tmp -- copied, never symlinked, because `mutate-check.sh:122` resolves symlinks with `realpath --relative-to` and a
symlinked fixture makes a runner write the real tree, after which twin and port "agree" by both reading one corrupted tree. Into that copy goes one unregistered real-tree writer, `test-__gate_probe_pool_writer.sh`. BOTH DIRECTIONS were driven on the SAME fixture: with the plant both sides exit 1 and name it; with the plant deleted and nothing else changed both sides exit 0 with
byte-identical streams, so the red is attributable to the plant and not to the fixture. Both sides -> exit 1, stdout EMPTY on both sides, stderr 563 bytes, sha256 136adf7621296d01....

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-pool-writer-safety.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-pool-writer.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch A2 retired it, and the cases that ran it were retired with it.

---- gate ----
step: Pool-registered tests do not write the real tree
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import pool_writer_safety

if __name__ == "__main__":
    raise SystemExit(pool_writer_safety.main(sys.argv[1:]))
