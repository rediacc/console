#!/usr/bin/env python3
"""Entry point for the ported plan-file-housekeeping gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.plan_housekeeping`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.plan_housekeeping` works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from `.ci/scripts/quality/check-plan-housekeeping.sh` PROGRAMMATICALLY, de-commented, and diffed as an ordered list of WHOLE LINES against the block in this docstring; the diff is empty over 6 line(s). The twin carried exactly these fields, in this order: `step`, `needs`, `selftest`, `lane`. NO `id:` and NO `emit:`;
`lane: quality-i18n` IS present and moved with the rest. The step sits inside a `# >>> gate-bind` region in that job, so it is emitted rather than hand-written. The pilot lost `emit: false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above
them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files and comparing every bound field except `file` and `run`, not by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing from its body and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:301`). Both sides bind to `needs: []`, which is what `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-plan-housekeeping.sh
      -> exit 0
    .ci/scripts/quality/check_plan_housekeeping.py
      -> exit 0
    stdout: BYTE-IDENTICAL, 446 bytes, sha256 4ea1f773150c3ce3...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against an unchanged tree FIRST, to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters. NO REAL-TREE PLANT WAS NEEDED. Both implementations honour the same four seams -- `PLAN_HK_ROOT`, `PLAN_HK_CONFIG`, `PLAN_HK_ALLOWLIST` and `PLAN_HK_MIN_FILES` -- so the fixture is a throwaway git repository in /tmp holding four plan files, built with `cp`-free literal writes and never a symlink. BOTH DIRECTIONS on the same
builder: commit the plans with a BACKDATED committer date and both sides exit 1 naming all four as unchanged for more than 33 days; commit the identical tree with TODAY's date and both sides exit 0 with byte-identical streams. The red is therefore the backdate's and not the fixture's. Both sides -> exit 1, stdout 253 bytes, sha256 a3864c24435671ba..., stderr 2049 bytes, sha256
35b802ff561bad2f....

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-plan-housekeeping.sh` is NOT deleted by this change. It stays on disk as the differential twin that `.ci/rediacc_ci/tests/test_quality_plan_housekeeping.py` compares this port against, and deleting it is W7 P5's job in a later change.

---- gate ----
step: Plan file housekeeping
needs: none
selftest: true
lane: quality-i18n
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import plan_housekeeping

if __name__ == "__main__":
    raise SystemExit(plan_housekeeping.main(sys.argv[1:]))
