#!/usr/bin/env python3
"""Entry point for the ported renet licence tier-map gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.renet_tier_map`, which pytest
imports directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 4). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.renet_tier_map` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. THIS IS THE ODD ONE OF THE SIX and the one where a field-for-field diff earns its keep: the twin carried `kind`, `id`, `blocker` and `needs`, and carried NO `step:`, NO `selftest:` and NO `lane:`. Every one of those four presences and three absences is deliberate.

  `kind: local-only`  no CI step invokes this gate at all, so there is no step
                      name to bind and no lane to place it in. Losing this field
                      turns the gate into one that CLAIMS a CI step, which is
                      the exact assertion the blocker below exists to refuse.
  `id:`               the file basename does not derive `check:ci-renet-tiers`
                      (the module is `renet_tier_map`), so without the explicit
                      `id:` the header binds to an id the manifest does not have.
  `blocker:`          carried BYTE FOR BYTE from the twin. It is a live
                      suppression reason under the BLOCKER convention, and a
                      suppression whose reason went missing in a file move is a
                      quiet exemption, which is how a gate stops meaning what its
                      name says.
  no `step:`          a local-only gate has none; adding one would be a new
                      claim, not a carried one.
  no `selftest:`      the twin did not declare it, and the field is inert for
                      `.py` anyway (`headerLines` emits it only for `.ts`,
                      `gate-bind.ts:598`). Not invented here.

`needs: go, submodules` IS LOAD-BEARING AFTER THE MOVE. `bind()` unions the declared needs with `inferredNeeds(source)`, and the twin got both for free from its own body (`go test` matches the go pattern, `private/renet` the submodule one). This entry point contains neither string outside its docstring, and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`),
so it
infers NOTHING. Carried whole, both sides resolve to {go, submodules}.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-renet-tier-map.sh` is NOT
deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- kind: local-only id: check:ci-renet-tiers
blocker: BLOCKER: no CI step invokes this script; the seven tier-map tests it drives already run in CI inside .ci/scripts/private/run-renet.sh test (ct-tests.yml job test-renet, step "Run renet tests"), which resolves to that leaf and not this one, so a step pointer would claim CI runs a script it never invokes
needs: go, submodules ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import renet_tier_map

if __name__ == "__main__":
    raise SystemExit(renet_tier_map.main(sys.argv[1:]))
