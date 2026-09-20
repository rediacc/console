#!/usr/bin/env python3
"""Entry point for the ported docker-compose env-var completeness gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.compose_env`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 3). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.compose_env` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly three fields -- `step`, `needs`, `selftest` -- and NO `lane:`, no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`. The absent `lane:` is the twin's shape and is deliberately preserved: this gate's lane is `quality-static` in the manifest, and pinning
it here would be a new assertion, not a carried one. The batch before this lost `emit: false` and a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran and still agreed.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

THE RESOLVED NEED SET DOES NOT MOVE. `bind()` unions the declared needs with `inferredNeeds(source)`; the twin is pure grep/sed and inferred nothing, and this two-import entry point infers nothing either, so both resolve to the empty set `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY:

    .ci/scripts/quality/check-compose-env.sh  -> exit 0
    .ci/scripts/quality/check_compose_env.py  -> exit 0
    stdout: byte-identical (EMPTY on both sides)

and driven RED as well, against a fixture root whose compose file references a variable `ci-env.sh` does not persist: both sides exit 1 with byte-identical stdout, the two-line fix advice plus the `See:` pointer. THE RED DRIVE IS THE LOAD-BEARING ONE for this pair, because the clean stdout is empty and an empty comparison proves only that neither side crashed.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-compose-env.sh` was the differential twin, and W7 P5 retired it; the shadow ledger under `.ci/shadow/` is the licence record.

---- gate ----
step: Compose env
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import compose_env

if __name__ == "__main__":
    raise SystemExit(compose_env.main(sys.argv[1:]))
