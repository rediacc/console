#!/usr/bin/env python3
"""Entry point for the ported mutation-runner self-test gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.mutate_check`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 4). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.mutate_check` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly three fields -- `step`, `needs`, `selftest` -- and NO `lane:`, no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`, no `kind:`. The absent `lane:` is the twin's shape, deliberately preserved: the manifest puts this gate in `quality-static`, and
pinning a lane here would be a new assertion rather than a carried one.

`needs: none` is declared verbatim. `bind()` unions declared needs with `inferredNeeds(source)`, and this two-import entry point infers nothing because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`). The SUBJECT of this gate is `.ci/scripts/test/mutate-check.sh`, driven against a miniature fixture suite, so the gate genuinely needs nothing beyond bash; the
declaration says so on both sides.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-mutate-check.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Mutation runner self-test
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import mutate_check

if __name__ == "__main__":
    raise SystemExit(mutate_check.main(sys.argv[1:]))
