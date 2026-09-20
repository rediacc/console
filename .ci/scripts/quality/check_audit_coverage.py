#!/usr/bin/env python3
"""Entry point for the ported CLI audit-logging coverage gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.audit_coverage`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 7). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.audit_coverage` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-audit-coverage.sh` by an awk range over its `---- gate ----` block, de-commented, and diffed as an ordered list of whole lines against the block in this docstring. The twin carried exactly THREE fields in this order: `step`, `needs`, `selftest`. No `lane:`, no `emit:`, no `blocker:`, no
`id:`, no `run:`, no `kind:`, no `why:`. The missing `lane:` is carried as an absence: the manifest places this step in `quality-static` already.

THE `step:` VALUE IS THE LONG EXISTING ONE, "Check audit logging coverage for CLI operations", and it is copied rather than tidied. `gate-bind` matches a header against the workflow step that already runs by NAME, so shortening the step name would unbind the gate, and renaming a step is a separate change from moving which file it invokes.

NO `id:` IS CORRECT HERE: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-audit-coverage`, which is the manifest id.

`selftest: true` is inert for a `.py` gate (`gate-bind.ts:598`) and is carried because the twin declared it and because `audit_coverage.main(["--selftest"])` exits 0.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files. Both infer `[]` and both resolve to the empty set `needs: none` declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-audit-coverage.sh   -> exit 0
    .ci/scripts/quality/check_audit_coverage.py   -> exit 0
    stdout: BYTE-IDENTICAL, EMPTY on both sides
    stderr: BYTE-IDENTICAL, 807 bytes, sha256 512c10e4c4642175...

THE WHOLE REPORT IS ON STDERR AND STDOUT IS EMPTY, which is worth stating rather than glossing: comparing stdout alone would have compared nothing at all on this pair, and would have "agreed" no matter what either side did. Both streams were captured to separate files for exactly that reason. No normalisation was applied and none was needed; the twin was first run TWICE against an
unchanged tree and is byte-stable against itself on both streams.

DRIVEN RED AS WELL. The plant renames the audit hook in the real `packages/cli/src/services/executor/local-executor.ts`, turning `auditService.recordOperation` into `auditSvcRenamed.recordOperation`, which is the phase-2 defect this gate exists for: every SSH-based operation silently stops being audit-logged.

THE CONTROL WAS PROVED BEFORE EITHER SIDE RAN, and the rename was chosen so that it CANNOT leave the guarded literal intact. A rename to `recordOperationRenamed` would still contain the substring `auditService.recordOperation` and the gate would correctly stay green while looking like a gate that cannot fire; the prefix was renamed instead, and the occurrence count for the exact
grep the gate uses was measured at 1 before and 0 after.

    both sides -> exit 1, stdout empty on both, stderr BYTE-IDENTICAL
    (1268 bytes, sha256 8abbedf4b2edae1e...):

    localExecutorService.execute() does not contain
    auditService.recordOperation()

The plant was reverted from a `cp` backup, verified back at its pre-plant sha256
with `sha256sum -c`, and `git status --porcelain` diffed against its pre-plant
capture with no difference.

INVARIANT 5 IS INTACT: `.ci/scripts/quality/check-audit-coverage.sh` is NOT deleted here. It stays on disk as the differential twin; deletion is W7 P5's job.

---- gate ----
step: Check audit logging coverage for CLI operations
needs: none
selftest: true
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import audit_coverage

if __name__ == "__main__":
    raise SystemExit(audit_coverage.main(sys.argv[1:]))
