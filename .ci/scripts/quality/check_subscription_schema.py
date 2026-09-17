#!/usr/bin/env python3
"""Entry point for the ported subscription-schema consistency gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.subscription_schema`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 4). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.subscription_schema` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly three fields -- `step`, `needs`, `selftest` -- and NO `lane:`, no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`, no `kind:`. The absent `lane:` is the twin's shape, deliberately preserved: the manifest puts this gate in `quality-go`, and pinning a
lane here would be a new assertion rather than a carried one.

`needs: go, node, submodules` IS THE LOAD-BEARING FIELD OF THIS MOVE. `bind()` unions the declared needs with `inferredNeeds(source)`, and the twin got its set partly for free from its own body (a `go run` of the generator, an `npx biome` call, and `private/renet` paths). This entry point contains none of those strings outside its docstring, and `inferredNeeds` strips Python
docstrings as prose (`gate-header.ts:300`), so it infers NOTHING. Dropping the declaration would move the gate into a lane with no Go toolchain and no submodules, where it would bail early and report having verified something it never read. Carried
whole, both sides resolve to {go, node, submodules}, unchanged.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-subscription-schema.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: Check subscription schema consistency needs: go, node, submodules selftest: true ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import subscription_schema

if __name__ == "__main__":
    raise SystemExit(subscription_schema.main(sys.argv[1:]))
