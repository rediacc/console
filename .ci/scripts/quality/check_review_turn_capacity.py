#!/usr/bin/env python3
"""Entry point for the ported review-turn-capacity gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.review_turn_capacity`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.review_turn_capacity` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-review-turn-capacity.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `lane:`, no `emit:`, no `blocker:`, no
`id:`, no `run:`, no `kind:`, no `why:`. The missing `lane:` is carried as an absence: the manifest places this step in `quality-static` already, so a `lane:` here would be a new claim.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-review-turn-capacity`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried because the twin declared it and because `review_turn_capacity.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

THIS TWIN IS ANOTHER GATE'S CONTROL SOURCE, which is the reason invariant 5 matters more here than usual. `check-control-vacuity.sh:159` pins `check-review-turn-capacity.sh` BY PATH, strips its
`[[ "$MUTANT" == "$FN" ]]` proof-of-plant guard, and requires the stripped copy
to be judged non-compliant; if that file were gone, control-vacuity would fail
with "CONTROL SOURCE MISSING" rather than silently pass. The bash twin stays on
disk, so the control keeps firing. This is stated here so that W7 P5's deletion pass finds the dependency written down at BOTH ends rather than only at the consumer.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-review-turn-capacity.sh   -> exit 0
    .ci/scripts/quality/check_review_turn_capacity.py   -> exit 0
    stdout: BYTE-IDENTICAL, 237 bytes, sha256 469b7e8e03e1b912...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

No normalisation was applied and none was needed; the twin was first run TWICE against an unchanged tree and is byte-stable against itself on both streams, ANSI colour included.

DRIVEN RED AS WELL. The plant lowers the turn ceiling in the real
`.ci/scripts/review/claude-review-gate.sh:171`, `max_turns=140` to
`max_turns=50`, which re-creates the measured starvation: a 2802-line diff
routes to 50 turns again, the exact budget that killed the review of PR #553.

THE PLANT WAS CHOSEN SPECIFICALLY TO LEAVE THE GATE'S OWN CONTROL ANCHOR
INTACT, and that is the whole design of it. This gate builds its control by
substituting `per_kloc=25`; a plant that edited THAT constant would have made
the substitution find nothing, and the gate would have aborted with "the control could not plant its defect" -- a red that proves the gate refuses a broken control, and nothing about the property under test. So a different constant on
the same line was moved, and `grep -c 'per_kloc=25'` was confirmed still 1
after planting.

    both sides -> exit 1, stdout empty on both, stderr BYTE-IDENTICAL
    (392 bytes, sha256 9cc8bb69171e9882...):

    REGRESSION: 2802 lines still routes to 50 turns; 50 is the budget that
    starved PR #553

The plant was reverted from a `cp` backup, verified back at its pre-plant sha256
with `sha256sum -c`, and `git status --porcelain` diffed against its pre-plant
capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-review-turn-capacity.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Review turn budget cannot starve a routed review
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import review_turn_capacity

if __name__ == "__main__":
    raise SystemExit(review_turn_capacity.main(sys.argv[1:]))
