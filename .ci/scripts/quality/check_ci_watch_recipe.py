#!/usr/bin/env python3
"""Entry point for the ported CI-watch-recipe single-source gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.ci_watch_recipe`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.ci_watch_recipe` works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from `.ci/scripts/quality/check-ci-watch-recipe.sh` PROGRAMMATICALLY, de-commented, and diffed as an ordered list of WHOLE LINES against the block in this docstring; the diff is empty over 9 line(s). The twin carried exactly these fields, in this order: `step`, `emit`, `blocker`, `needs`, `id`, `selftest`, `lane`.
THE `id:` LINE IS LOAD-BEARING AND IS NOT DERIVABLE. This basename is `check_ci_watch_recipe.py`, so `derivedId` (`gate-header.ts:260`) yields `check:ci-ci-watch-recipe`, with `ci-` twice. The registered id is `check:ci-watch-recipe`. The twin carried the same override for the same reason and it is copied verbatim; dropping it would have renamed the gate. The pilot lost `emit:
false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files and comparing every bound field except `file` and `run`, not by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing from its body and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose
(`gate-header.ts:301`). Both sides bind to `needs: []`, which is what `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-ci-watch-recipe.sh
      -> exit 0
    .ci/scripts/quality/check_ci_watch_recipe.py
      -> exit 0
    stdout: BYTE-IDENTICAL, 1010 bytes, sha256 ef17e8db85abb6c2...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against an unchanged tree FIRST, to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters. The plant is rule C's banned invocation (`gh run watch ... --exit-status --interval`) appended to the TRACKED file `.claude/commands/ask.md`. Tracked is required, not incidental: `scan_files` enumerates with `git ls-files`, so an untracked probe would never have been read and the plant would have looked like a gate that cannot
fail. The file was restored from a `cp` taken before the plant and its sha256 compared byte for byte with the pre-plant value (472a1877bc9e57da...), identical. Both sides -> exit 1, stdout 716 bytes, sha256 cf9603c7f3f927f3..., stderr 84 bytes, sha256 8631886f416f29fd....

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-ci-watch-recipe.sh` was the differential twin that `.ci/rediacc_ci/tests/test_quality_ci_watch_recipe.py` compared this port against, and W7 P5 retired it; the shadow ledger under `.ci/shadow/` is the licence record.

---- gate ----
step: CI-watch recipe has one source
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
id: check:ci-watch-recipe
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import ci_watch_recipe

if __name__ == "__main__":
    raise SystemExit(ci_watch_recipe.main(sys.argv[1:]))
