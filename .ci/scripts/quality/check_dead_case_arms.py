#!/usr/bin/env python3
"""Entry point for the ported dead-case-arm scanner. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.dead_case_arms`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8a, the broad tree-scanning nine). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.dead_case_arms` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-dead-case-arms.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly FOUR fields in this order: `kind`, `test`, `blocker`, `needs`. No `step:`, no `emit:`, no `id:`, no
`run:`, no `lane:`, no `selftest:`, no `why:`.

`kind: test` IS THE LOAD-BEARING ONE. This gate has NO workflow step of its own: it reaches CI through `.ci/scripts/test/gates/test-dead-case-arms.sh` inside the shared "Quality-gate unit tests" step. Grepped every file under `.github/workflows/` for `check-dead-case-arms.sh` and found ZERO hits, which is what `kind: test` predicts and what makes the `blocker:` below the whole of
this gate's CI story. It is carried byte for byte, because a suppression reason that goes missing in a file move is a quiet exemption.

NO `selftest:` IS CORRECT, carried exactly as found: the twin did not declare one. The port does implement `--selftest`, but declaring a field the twin never had would be a NEW claim rather than a moved one, and `selftest:` is inert for a `.py` gate anyway (`gate-bind.ts:598`).

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-dead-case-arms`, which is the manifest id.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

PINNED BY PATH IN FOUR HARNESS ROWS, ALL OF THEM RUN-IN-PLACE, so all four take the ENTRY POINT arm if they are ever repointed:

  - `.ci/scripts/test/gates/test-dead-case-arms.sh:25`   `GATE=` then runs it
  - `.ci/scripts/test/gates/test-media-helpers.sh:31`    `GATE=` then runs it
  - `.ci/rediacc_ci/tests/gates/test_gate_dead_case_arms.py:41`  runs it
  - `.ci/rediacc_ci/tests/gates/test_gate_media_helpers.py:40`   runs it

`.ci/rediacc_ci/tests/test_quality_dead_case_arms.py:42` is the DIFFERENTIAL and must keep naming the twin; it copies the twin's two pipelines verbatim as a comment and pins the twin as the comparison side.

BECAUSE THIS GATE IS `kind: test`, REPOINTING IS NOT COSMETIC HERE, and it is the driver's call, not this writer's: while `test-dead-case-arms.sh:25` still names the `.sh`, CI executes the TWIN and only the local `npm run` executes the port. That is the one-sided shape this programme exists to prevent, so it is called out in the report rather than left in a diff.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-dead-case-arms.sh   -> exit 0
    .ci/scripts/quality/check_dead_case_arms.py   -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 176 bytes, sha256 143260083699ab2c...

No normalisation was applied and none was needed; the twin was run TWICE against an unchanged tree and is byte-stable against itself on both streams.

DRIVEN RED AS WELL, through the twin's own three root overrides (`DEAD_CASE_TEST_DIRS`, `DEAD_CASE_MEDIA_DIRS`, `DEAD_CASE_CODE_DIRS`), which the port reads under the same names. The fixture is three scratch directories: a test
root holding a `case` arm globbing `zzz8aprobe=`, a code root that emits
`livekey=` and never that field, and a media root.

THE FIRST PLANT FIRED ON THE WRONG FINDING, AND THE CONTROL WAS WRONG, NOT THE
GATE. The media root was left EMPTY, so both sides went red on the anti-vacuity refusal `VACUOUS: the media scan root holds no shell files, so scanning it proves nothing` and never reached the detector. Both agreeing on the wrong red is exactly the shape a writer must not accept as evidence. With a shell file added to the media root the fixture goes GREEN first, which is the
control that matters:

    clean fixture -> exit 0, "no dead case arms across <t> <m> (1 media shell
    file(s); the planted-arm control fired and the live-arm control stayed
    silent, so this verdict is real)"

and only then, with the one dead arm restored:

    both sides -> exit 1, stdout EMPTY on both, stderr BYTE-IDENTICAL
    (327 bytes, sha256 d50c46cd31c4d9cd...):

    ✗ .../t/probe.sh:4: case arm globs for 'zzz8aprobe=' but no non-test script
      under .../c emits that field, so this arm is DEAD

The key was also confirmed absent from the whole real tree before the run, so nothing in the repository could have vouched for it. THE REAL TREE WAS NEVER WRITTEN TO for this gate.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-dead-case-arms.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
kind: test
test: .ci/scripts/test/gates/test-dead-case-arms.sh
blocker: BLOCKER: the gate is CONTROL-FIRST -- it plants a dead case arm with a runtime-generated key and refuses to report on the real tree unless its scanner catches that arm, so a green IS the fire proof; test-dead-case-arms.sh:14 runs it seam-free against the real tree inside the gate-test battery (ci-quality.yml quality-security, "Quality-gate unit tests")
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import dead_case_arms

if __name__ == "__main__":
    raise SystemExit(dead_case_arms.main(sys.argv[1:]))
