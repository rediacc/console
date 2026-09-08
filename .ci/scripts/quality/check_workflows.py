#!/usr/bin/env python3
"""Entry point for the ported workflow-banned-patterns gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can
see it; the logic lives in `rediacc_ci.quality.workflows`, which pytest and the port's
own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 8b). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL, rather than registering the module. `check_npmrc.py`
states both measured reasons. A port cannot be run by path (nothing puts `.ci`
on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.workflows`
works but is the wrong registration: `check:ci-parity`'s tokenizer cannot read
`-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD. It was extracted from
`.ci/scripts/quality/check-workflows.sh` PROGRAMMATICALLY, de-commented, and diffed
as an ordered list of WHOLE LINES against the block in this docstring; the diff
is empty over 5 line(s). The twin carried exactly these fields, in this
order: `step`, `needs`, `selftest`. NO `id:`, NO `emit:`, NO `lane:`, all three absent in the twin. The step sits
INSIDE a `# >>> gate-bind` region in `ci-quality.yml` (job quality-code), so it
is emitted and needs no hand-written-step suppression.
The pilot lost `emit: false` plus a blocker off a header and SEVEN GATES PASSED
ANYWAY, because `emit: false` suppresses only the three workflow-region checks
(`gate-bind.ts:1724`) while the registration assertions above them still ran.

THE RESOLVED NEED SET DOES NOT MOVE, verified by CALLING `bind()` on both files
and comparing every bound field except `file` and `run`, not by reading them.
`bind()` unions declared needs with `inferredNeeds(source)`; the twin infers
`node`, from its own body from its body and this two-import entry point infers nothing, because
`inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`).
Both sides bind to `needs: ['node']`.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-workflows.sh
      -> exit 0
    .ci/scripts/quality/check_workflows.py
      -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 140 bytes, sha256 aa6e7d617f5519f4...

NO NORMALISATION WAS APPLIED and none was needed. The twin was run TWICE against
an unchanged tree FIRST, to establish that its own output is byte-stable against
itself; it is, on both streams.

DRIVEN RED AS WELL, which is the half that matters.
NO REAL-TREE PLANT WAS NEEDED, and none was made: `.github/workflows/**` is not
this change's to edit even transiently. The gate offers `WORKFLOW_DIR` plus
`WORKFLOW_INLINE_ONLY=1`, which empties the banned-pattern file list and points
the inline-run rule at a fixture; both implementations read both names. The
fixture is one `probe.yml` whose `run:` block carries 16 logic lines against a
cap of 8. BOTH DIRECTIONS on the same seam: the fat block reds both sides
identically, and a second fixture whose step runs one thin command greens both
sides identically, so the red is the plant's and not the fixture's.
Both sides -> exit 1, stdout 276 bytes, sha256 cd8229d78325ce47..., stderr 219 bytes, sha256 369083d9543b466a....

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-workflows.sh` is NOT deleted
by this change. It stays on disk as the differential twin that
`.ci/rediacc_ci/tests/test_quality_workflows.py` compares this port against, and
deleting it is W7 P5's job in a later change.

---- gate ----
step: Workflow banned patterns
needs: node
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import workflows

if __name__ == "__main__":
    raise SystemExit(workflows.main(sys.argv[1:]))
