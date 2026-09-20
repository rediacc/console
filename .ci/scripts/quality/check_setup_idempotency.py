#!/usr/bin/env python3
"""Entry point for the ported setup-path-idempotency gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.setup_idempotency`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.setup_idempotency` works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from `.ci/scripts/quality/check-setup-idempotency.sh` PROGRAMMATICALLY, de-commented, and diffed as an ordered list of WHOLE LINES against the block in this docstring; the diff is empty over 8 line(s). The twin carried exactly these fields, in this order: `step`, `emit`, `blocker`, `needs`, `selftest`, `lane`. NO
`id:`: the basename derives `check:ci-setup-idempotency`, the manifest id. The pilot lost `emit: false` plus a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files and comparing every bound field except `file` and `run`, not by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers nothing beyond what it declares from its body and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as
prose (`gate-header.ts:301`). Both sides bind to `needs: ['submodules']`.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-setup-idempotency.sh
      -> exit 0
    .ci/scripts/quality/check_setup_idempotency.py
      -> exit 0
    stdout: BYTE-IDENTICAL, 554 bytes, sha256 436b845d1537bad8...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against an unchanged tree FIRST, to establish that its own output is byte-stable against itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters. `needs: submodules` IS THE FIELD THIS GATE WAS MOST LIKELY TO LOSE, and it is the reason the `bind()` comparison above is a measurement and not a reading. A bash twin can infer a need from its body; a two-import Python entry point infers nothing at all, so a `needs:` line dropped in the move would not have been replaced by
inference. It is declared here, and both sides bind to `['submodules']`.

The plant replaces `if devbox_image_present && ...` with `if false && ...` inside `devbox_ensure_image` in the TRACKED `.ci/lib/devbox.sh`, so the function still pulls and no longer carries its guard, which is rule A's shape. THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN by re-extracting the function body
with the same awk range the gate uses and counting ZERO occurrences of the
guard token in it. The file was restored from a `cp` and its sha256 compared
with the pre-plant value (dd63548fda6b1264...), identical.
Both sides -> exit 1, stdout 484 bytes, sha256 790164231f5864e6..., stderr 155 bytes, sha256 dfe461906b46d424....

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-setup-idempotency.sh` is NOT deleted by this change. It stays on disk as the differential twin that `.ci/rediacc_ci/tests/test_quality_setup_idempotency.py` compares this port against, and deleting it is W7 P5's job in a later change.

---- gate ----
step: Setup path idempotency
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, and its subject IS the setup path. Emitting it into the region would gate it on setup succeeding, so the gate that explains a broken setup would be the one silenced by it.
needs: submodules
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import setup_idempotency

if __name__ == "__main__":
    raise SystemExit(setup_idempotency.main(sys.argv[1:]))
