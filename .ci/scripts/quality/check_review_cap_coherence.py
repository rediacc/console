#!/usr/bin/env python3
"""Entry point for the ported review-cap coherence gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.review_cap_coherence`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.review_cap_coherence` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-review-cap-coherence.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `lane:`, no `emit:`, no `blocker:`, no
`id:`, no `run:`, no `kind:`, no `why:`.

THE MISSING `lane:` IS THE TWIN'S SHAPE and is carried as an absence rather than filled in. The manifest already places this step in `quality-static` and its workflow step sits inside that lane's `# >>> gate-bind` region, so a `lane:` declared here would be a NEW claim rather than a moved one.

NO `id:` IS CORRECT HERE, checked rather than assumed: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-review-cap-coherence`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`headerLines` emits it only for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and because `review_cap_coherence.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. `bind()` unions declared needs with `inferredNeeds(source)`; the twin infers `[]` and this entry point infers `[]`, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both resolve to the empty set.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-review-cap-coherence.sh   -> exit 0
    .ci/scripts/quality/check_review_cap_coherence.py   -> exit 0
    stdout: BYTE-IDENTICAL, 207 bytes, sha256 852736e57b260bfe...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

NO NORMALISATION WAS APPLIED and none was needed. The twin was first run TWICE against an unchanged tree to establish byte-stability against itself; it is stable on both streams, and the port then matched it byte for byte including the ANSI colour both emit to a redirected stream.

DRIVEN RED AS WELL. The plant is the actual 2026-08-07 defect, inserted into the real `.ci/scripts/review/review-status.sh` as one added line:

    review_count="$(review_report_count "$pr")"

THE CONTROL WAS PROVED IN BOTH DIRECTIONS BEFORE EITHER SIDE RAN, and the second direction is the one that earns its keep here. This gate carries its own control, which builds a mutant by substituting the ORIGINAL `review_spend_total` assignment; had the plant REPLACED that line, the gate would have aborted early with "the control could not plant its defect" and the red would have
proved only that the gate refuses a broken control. So the plant ADDS a line and leaves the anchor intact, and both facts were verified with `grep -F` first: the forbidden shape present once, the control's anchor still present once.

    both sides -> exit 1, stdout BYTE-IDENTICAL, stderr BYTE-IDENTICAL
    (516 bytes, sha256 68263412a70c2fbf...):

    DRY-NUMERATOR: review-status.sh derives its cap numerator from
    review_report_count (posted reports ONLY) -- spent attempts are invisible
    to it, which is the #553 deadlock

The plant was reverted by restoring the file from a `cp` backup, verified back at its pre-plant sha256 with `sha256sum -c`, and `git status --porcelain` diffed against its pre-plant capture with no difference.

INVARIANT 5 IS DISCHARGED: `.ci/scripts/quality/check-review-cap-coherence.sh` was the differential twin, and W7 P5 retired it; the shadow ledger under `.ci/shadow/` is the licence record.

---- gate ----
step: Review cap is measured coherently
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import review_cap_coherence

if __name__ == "__main__":
    raise SystemExit(review_cap_coherence.main(sys.argv[1:]))
