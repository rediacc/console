#!/usr/bin/env python3
"""Entry point for the ported account-portal typecheck-and-build gate.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.account_portal`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 3). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.account_portal` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `id:`, no `run:`, no `why:`. The batch before this one lost `emit: false` and a blocker off a header and SEVEN GATES PASSED ANYWAY, because `emit: false` suppresses only
the three workflow-region checks (`gate-bind.ts:1724`) while the registration assertions above them still ran and still agreed.

`needs: node, submodules` IS THE LOAD-BEARING FIELD OF THIS MOVE, and it is the one a careless copy loses. `bind()` unions the declared needs with `inferredNeeds(source)`, and the twin got BOTH for free from its own body: `npx tsc` matches the node pattern and the literal `private/account/web` matches the submodule one. This entry point contains neither string outside its
docstring, and `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`), so
it infers NOTHING. Carried whole, both sides resolve to {node, submodules},
unchanged. Dropping either would have put the heaviest gate in the estate in a lane that cannot run it.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

DRIVEN, on this tree, both streams captured SEPARATELY. Both run all seven real phases: tsc over the frontend, the backend and the e2e suite, biome, the onboarding generator and a real `vite build`.

STDOUT IS NOT BYTE-STABLE FOR EITHER SIDE, and that is a property of the SUBJECT, not of the port. Both implementations INHERIT the children's streams, so vite's own build report (per-asset gzip sizes and a wall-clock "built in NNNms") lands on stdout verbatim. Two consecutive runs of the TWIN disagree on those numbers, so "byte-identical stdout" is not a claim this pair can make
in either direction. What was measured instead: the twin against ITSELF and the twin against this port, both after normalising the build duration, and the port matches the twin exactly as well as the twin matches itself: three runs (twin, twin, port), one normalised sha256, 33b9e71ede60d775ac5108988dc8508b8296e077c6b60c707190178dd77930ec. STDERR is unstable in the same way and for
the same reason: rollup emits its `@__PURE__` annotation warnings in an order that differs between two runs of the TWIN, so the two sides were compared as multisets and agree exactly.

DRIVEN RED TWICE, on a fixture root with PATH shims, because a seven-phase gate whose phases are ordered can agree on the clean path and still disagree on where it stops. Plant A fails `npx tsc` in phase 2: both sides exit 1 after "Frontend typecheck failed!", with identical stdout and stderr. Plant B lets all seven phases succeed and removes the build output: both sides run every
phase in the twin's order and then exit 1 on "Expected build output not found", again identically. The second plant is the one that proves the ORDER survived the port.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-account-portal.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Check account portal (typecheck + build)
needs: node, submodules
selftest: true
lane: quality-packages
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import account_portal

if __name__ == "__main__":
    raise SystemExit(account_portal.main(sys.argv[1:]))
