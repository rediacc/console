#!/usr/bin/env python3
"""Entry point for the prose-style gate (R1-R18). Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.prose_style`, which pytest and
this file's own `--selftest` import directly.

NOT A PORT. Every other guard and gate in this family was transliterated from a
bash original and is judged against it by a differential. There is no bash
original here and there never was: `.ci/scripts/quality/check_language_policy.py`
freezes the SET of shell files under `.ci` and `.claude` and refuses a new one
("the surface may shrink and may never grow"), so a twin could not have been
written even as a formality. The evidence this gate works is therefore its own,
and it is of three kinds rather than one:

  * `--selftest`, 65 controls, every one of them a PLANT with a MIRROR. Two
    defects were planted into the engine on 2026-09-16 to prove the suite can go
    red -- disabling the inline-code stripper (2 controls failed) and breaking
    reflow's idempotency (7 failed) -- because a green that has never been shown
    to be able to go red is not evidence.
  * `.ci/rediacc_ci/tests/test_quality_prose_style.py`, which generates one case
    per EXAMPLE in the rules file, so a rule whose example stops being detected
    reds without anybody writing a second fixture.
  * the two hook guards, `block_prose_style_edit` and `block_prose_style_commit`,
    with their own per-guard suites beside them in the guards directory.

WHY AN ENTRY POINT AT ALL, the two measured reasons `check_npmrc.py` states: a
port cannot be run by path (nothing puts `.ci` on `sys.path`, hence `_cipath`),
and `python3 -m rediacc_ci.quality.prose_style` works but registers wrong,
because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to
`[python3]`.

WHAT A GREEN HERE DOES AND DOES NOT MEAN, said plainly so nobody reads it as more
than it is:

  * The gate is SHRINK-ONLY against `.ci/config/prose-style-baseline.json`. A
    green means NO NEW finding, not a clean tree. The baselined count is printed
    on the success line for exactly that reason.
  * Nine of the eighteen rules are ADVISORY: documented, not mechanically
    detected, because the pattern that would catch them would also catch their
    own counter-examples. R12's "The project failed." and R3's good example "The
    build failed after the last change." are the same surface shape. The count of
    advisory rules and of examples declared beyond detection is printed on every
    run, so the coverage gap is visible instead of living in a comment.
  * `.sh` is not scanned and `packages/www` is excluded. Both are decisions
    recorded in the rules file, not oversights.

ZERO INPUTS IS A FAILURE HERE, in two places rather than one. Zero files matched
fails; so does a non-empty file set that yields ZERO extracted prose lines, which
is the extractor breaking rather than the glob, and which would otherwise look
exactly like a clean tree.

---- gate ----
step: Check prose style (the work, not the person)
needs: none
selftest: true
lane: quality-content
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import prose_style

if __name__ == "__main__":
    raise SystemExit(prose_style.main(sys.argv[1:]))
