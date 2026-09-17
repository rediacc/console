#!/usr/bin/env python3
"""Entry point for the ported App-admin-permission gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.no_app_admin_perm`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 4). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.no_app_admin_perm` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, diffed side by side rather than retyped from memory. The twin carried exactly FIVE fields -- `step`, `needs`, `id`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `run:`, no `why:`, no `kind:`. The `id:` is the field most easily lost in a move, because four of the six gates in this batch do not carry one: this gate's file
basename does not derive `check:ci-app-admin-perm`, so without the explicit `id:` the header would bind to a different id than the manifest declares. Carried verbatim, and its ORDER is the twin's too (`needs` before `id`), so a side-by-side diff of the two blocks is line-for-line.

`needs: none` is declared verbatim. `bind()` unions declared needs with `inferredNeeds(source)`; this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:300`), and the twin inferred nothing either (a `grep -rn` over `.github/` matches no runtime pattern), so both sides resolve to the same empty set.

`selftest: true` IS INERT HERE and is carried anyway: `headerLines` emits that field only for `.ts` (`gate-bind.ts:598`), so for a `.py` gate it decides nothing. It is true of the port regardless.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-no-app-admin-perm.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ---- step: App admin permission needs: none id: check:ci-app-admin-perm selftest: true lane: quality-code ---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import no_app_admin_perm

if __name__ == "__main__":
    raise SystemExit(no_app_admin_perm.main(sys.argv[1:]))
