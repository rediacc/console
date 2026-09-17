#!/usr/bin/env python3
"""Entry point for the ported `.npmrc` supply-chain hardening gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.npmrc`.

THIS ONE CARRIES A HEADER, AND ITS SIBLINGS DELIBERATELY DO NOT. The pattern file `check_autopilot_breakpoint_alignment.py` states the condition in its own docstring: no header, because "the bash twin remains the registered gate until the differential ledger says the port kept its verdict". For this pair the ledger now says it. Measured 2026-09-07:

    npx tsx scripts/lib/shadow-gate.ts --pair w7p2-npmrc --assert --k 5
    -> equivalence holds over 5 distinct trees

and driven again on this tree the same day, both streams captured separately: the twin exits 0 and this port exits 0 with BYTE-IDENTICAL stdout. So the condition the siblings are waiting for is met here, and only here so far.

WHY AN ENTRY POINT AT ALL, rather than registering the module directly. Two independent reasons, both measured rather than assumed:

  1. A port CANNOT be run by path. `python3 .ci/rediacc_ci/quality/npmrc.py`
     dies at `from rediacc_ci import log, paths` because nothing put `.ci` on
     `sys.path`. The three-line insert below is what makes a path invocation
     work, and a path invocation is what the registry needs.
  2. `python3 -m rediacc_ci.quality.npmrc` DOES work, and is still wrong here:
     `check-ci-parity`'s tokenizer cannot read `-m`, so it resolves the leaves
     to `[python3]` and the gate fails parity. `gate-header.ts`'s `derivedRun`
     documents that exact trap for `.py`, which is why the registered command
     is the bare path to this file.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-npmrc.sh` is NOT deleted by this change. It stays on disk as the twin, and deleting it is W7 P5's job, in a later change. What moves here is only which of the two the registry invokes.

A HEADER MOVE MUST CARRY EVERY FIELD, and this one did not on its first pass. The twin's header held `emit: false`, its blocker, `needs: none` and
`selftest: true`; the port was written with only `step`, `lane` and `why`, and
SEVEN GATES PASSED ANYWAY. They could not see it: `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`), while the registration assertions above it still ran and still agreed. The loss would have surfaced first as damage -- on the next `gate:bind --write` a second copy of this step lands inside the emitted region, `gate-bind` reds with two steps of
one name in `quality-code`, and the guard the blocker exists to protect is gone. Restored 2026-09-07, verbatim from the twin, by a reviewer reading the two headers side by side rather than by any gate.

---- gate ---- step: Block legacy-peer-deps workarounds
     # The step name is the EXISTING one, not a tidier one. gate-bind matches a
     # header against the workflow step that already runs, and renaming the step
     # is a separate change from moving which file it invokes.
emit: false blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails. needs: none selftest: true lane: quality-code
why: `.npmrc` must keep ignore-scripts, allow-git=none and minimum-release-age,
     enforced in BOTH directions so neither a missing file nor a weakened value
     passes. First port cut over from bash to Python under W7 P4, on the
     ledger condition its own sibling entry points name.
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import npmrc

if __name__ == "__main__":
    raise SystemExit(npmrc.main(sys.argv[1:]))
