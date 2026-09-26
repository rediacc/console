#!/usr/bin/env python3
"""Entry point for the ported label-reference gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.label_references`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.label_references` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-label-references.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. THIS IS THE ODD ONE OF THE TEN and the one where a field-for-field diff earns its keep. The twin carried exactly FIVE fields in
this order: `kind`, `id`, `test`, `blocker`, `needs`. It carried NO `step:`, NO `lane:`, NO `emit:`, NO `selftest:`, NO `run:`, NO `why:`. Every one of those five presences and six absences is deliberate.

  `kind: test`   no workflow step invokes this gate directly. It is driven by
                 `.ci/rediacc_ci/tests/gates/test_gate_label_references.py` inside
                 the pytest lane, so there is no step to bind and no lane to place it
                 in. Losing this field would turn the gate into one that CLAIMS a
                 CI step, which is exactly what the blocker below refuses.
  `id:`          THE BASENAME DOES NOT DERIVE THE MANIFEST ID. `derivedId`
                 (`gate-header.ts:260`) maps `check_label_references.py` to
                 `check:ci-label-references`, but the manifest id is
                 `check:ci-label-refs`. Without the explicit `id:` this header
                 binds to an id the manifest does not have. This is the mismatch
                 the batch brief warned about, confirmed by running `derivedId`
                 rather than by reading the module name.
  `test:`        the harness path. It named the bash harness until W7 P5 retired
                 that file, and now names the pytest port; see the pin note
                 below.
  `blocker:`     carried BYTE FOR BYTE from the twin. It is a live suppression
                 reason under the BLOCKER convention.
  no `step:`     a test-kind gate has none; adding one would be a new claim.
  no `selftest:` the twin did not declare it, and the field is inert for `.py`
                 anyway (`gate-bind.ts:598`). Not invented here.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

PINNED BY PATH, in two places rather than one, so say which. `test_quality_label_references.py:35` and `test_gate_label_references.py:63` name the twin path, and the manifest's `test:` points at the second. Both still exercise the bash twin, so the registry flip alone does not move them. Repointing is the driver's call, and the rows differ in kind: the harness RUNS the
script by path, so it must be repointed at the ENTRY POINT (a module is not runnable by path),
while any row asserting a behavioural needle belongs on the MODULE.

THE TWIN'S SELF-EXCLUSION DID NOT COVER THIS FILE, and that was checked rather than assumed. `check-label-references.sh:80` excluded exactly two BASENAMES, `check-label-references.sh` and `test-label-references.sh`, because each carries planted sample lines. This entry point carries none, and neither do its nine batch-mates: ALL TEN of the twin's extractor pipelines were run over
`.github .ci` twice, once as the gate runs them and once with the ten new `check_*.py` basenames excluded, and the two sorted result sets are identical at 13 names. So the cutover adds nothing to the swept corpus and the exclusion list correctly does not need to grow.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-label-references.sh   -> exit 0
    .ci/scripts/quality/check_label_references.py   -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 69 bytes, sha256 e262cdef2577de2d...

THE WHOLE REPORT IS ON STDERR AND STDOUT IS EMPTY on this pair, so comparing stdout alone would have compared nothing. Both streams were captured to separate files. No normalisation was applied and none was needed; the twin was first run TWICE against an unchanged tree and is byte-stable against itself on both streams.

DRIVEN RED AS WELL. The plant is a one-line file at `.ci/scripts/__gate_probe_labelref.yml` carrying the `workflow-contains` shape
for a name no inventory declares.

THE CONTROL WAS PROVED IN BOTH DIRECTIONS BEFORE EITHER SIDE RAN: the twin's own `workflow-contains` extractor, run standalone over the same `.github .ci` scan roots with the same two basename exclusions, returns the planted name exactly once, AND `.github/labels.yml` declares it zero times. Either half alone would have left a non-firing plant ambiguous.

    both sides -> exit 1, stdout empty on both, stderr BYTE-IDENTICAL
    (270 bytes, sha256 7e606fc2e73cd353...), naming the referencing site:

    ... is referenced by code but not declared in .github/labels.yml
    (sites: .ci/scripts/__gate_probe_labelref.yml )

The plant was removed with `rm` and `git status --porcelain` diffed against its pre-plant capture with no difference.

THE TWIN IS GONE: W7 P5 froze `.ci/scripts/quality/check-label-references.sh`'s output into `.ci/rediacc_ci/tests/goldens/label-references/` and deleted it, so the differential now compares this port against the bytes the twin recorded rather than against a second live implementation.

---- gate ----
kind: test
id: check:ci-label-refs
test: .ci/rediacc_ci/tests/gates/test_gate_label_references.py
blocker: BLOCKER: test_gate_label_references.py:test_real_tree_is_clean_and_excludes_this_file runs the gate seam-free against the real tree under check:ci-pytest (ci-quality.yml quality-security, "Python package tests"), so the real sweep over .github/.ci executes every CI run; the fixture cases around it prove both fire directions
needs: none
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import label_references

if __name__ == "__main__":
    raise SystemExit(label_references.main(sys.argv[1:]))
