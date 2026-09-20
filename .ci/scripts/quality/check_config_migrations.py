#!/usr/bin/env python3
"""Entry point for the ported config-migration runner + fixtures gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.config_migrations`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 4). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.config_migrations` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`, no `kind:`.

`needs: node` IS LOAD-BEARING AFTER THE MOVE. `bind()` unions the declared needs
with `inferredNeeds(source)`, and the twin got `node` for free from its own
`npx tsx` call; this entry point runs neither, and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`), so it infers nothing. Carried whole,
both sides resolve to {node}, unchanged -- and it is a real dependency, because
the port still drives a real `npx tsx` harness over every committed fixture.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-config-migrations.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Check config-migration runner + fixtures
needs: node
selftest: true
lane: quality-packages
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import config_migrations

if __name__ == "__main__":
    raise SystemExit(config_migrations.main(sys.argv[1:]))
