#!/usr/bin/env python3
"""Entry point for the ported control-vacuity gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.control_vacuity`, which pytest and the
port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port
cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below),
and `python3 -m rediacc_ci.quality.control_vacuity` works but is the wrong registration
because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to
`[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from
`.ci/scripts/quality/check-control-vacuity.sh` by an awk range over its
`---- gate ----` block, de-commented, and diffed as an ordered list of whole
lines against the block in this docstring. The twin carried exactly SIX fields
in this order: `step`, `emit`, `blocker`, `needs`, `selftest`, `lane`. No `id:`,
no `run:`, no `kind:`, no `why:`. The `blocker:` is byte for byte the twin's: it
is a live suppression reason under the BLOCKER convention, and a suppression
whose reason went missing in a file move is a quiet exemption.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename
to `check:ci-control-vacuity`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried
because the twin declared it and because
`control_vacuity.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files.
Both infer `[]` and both resolve to the empty set `needs: none` declares.

THIS ENTRY POINT IS INVISIBLE TO THE GATE IT REGISTERS, checked rather than
assumed, because this gate sweeps the very directory the entry point lands in.
Its corpus loop is `for f in "$GATE_DIR"/check-*.sh` (twin) and the same glob in
the port, so a file named `check_control_vacuity.py` is not enumerated: the glob
requires a HYPHEN after `check` and a `.sh` suffix, and this file has neither.
Verified twice over: structurally, by listing `check-*.sh` in the gate directory
and confirming ZERO `.py` files match it, and behaviourally, by the shape line
the gate prints (5 checked, 8 exempt) being the same on both sides of the
cutover. That matters because a corpus that grew or shrank silently across the
cutover would make the differential meaningless.

ITS CONTROL SOURCE IS UNAFFECTED TOO. `check-control-vacuity.sh:159` pins
`check-review-turn-capacity.sh` BY PATH as the gate whose vacuity guard it
strips to prove the detector fires. That twin is in this same batch and is NOT
deleted (invariant 5), so the control keeps finding its source and keeps firing.
The port pins the same basename in its `CONTROL_GATE` constant, so the two agree.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-control-vacuity.sh   -> exit 0
    .ci/scripts/quality/check_control_vacuity.py   -> exit 0
    stdout: BYTE-IDENTICAL, 259 bytes, sha256 a5ef60f5707c0374...
    stderr: BYTE-IDENTICAL, EMPTY on both sides

    5 pattern-substitution control(s) prove their plant landed; 8 built by
    construction (exempt); 92 python gate(s) NOT scanned here

THAT SHAPE LINE IS THE ANTI-VACUITY EVIDENCE, and it is why the corpus check
above matters: a green whose corpus had silently collapsed to zero would print a
different set of numbers, and the twin refuses a zero corpus outright.

No normalisation was applied and none was needed; the twin was first run TWICE
against an unchanged tree and is byte-stable against itself on both streams.

DRIVEN RED AS WELL. The plant deletes ONE line, the
`if [[ "$MUTANT_STATUS" == "$STATUS_SRC" ]]; then` proof-of-plant guard at
`.ci/scripts/quality/check-review-cap-coherence.sh:132`, leaving the
substitution that builds the mutant intact. That is precisely the defect this
gate exists for: a control that can pass against UNMUTATED source and report a
green proving nothing.

THE CONTROL WAS PROVED ON ALL THREE PRECONDITIONS BEFORE EITHER SIDE RAN,
because this gate only flags a file that satisfies all three, and a plant that
knocked out one of the other two would have made the subject VANISH from the
corpus rather than fail it, which looks identical from outside. Measured after
planting: the guard shape now matches 0 times, `has_control` still matches (2),
and `builds_by_substitution` still matches (1).

    both sides -> exit 1, stdout BYTE-IDENTICAL (82 bytes), stderr
    BYTE-IDENTICAL (450 bytes, sha256 707e7de1ee7d9052...):

    check-review-cap-coherence.sh builds its control by pattern substitution
    but never proves the plant landed.

The plant was reverted from a `cp` backup, verified back at its pre-plant sha256
with `sha256sum -c`, and `git status --porcelain` diffed against its pre-plant
capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-control-vacuity.sh` is NOT deleted
here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Control-first gates prove their plant landed
emit: false
blocker: BLOCKER: runs before this lane's `- id: setup` step, so its hand-written step carries no `steps.setup.outcome` guard. Emitting it into the region would move it below that guard and skip it whenever setup fails.
needs: none
selftest: true
lane: quality-code
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import control_vacuity

if __name__ == "__main__":
    raise SystemExit(control_vacuity.main(sys.argv[1:]))
