#!/usr/bin/env python3
"""Entry point for the ported release-signing-coverage gate. Logic is in the package.

Contract section 5d puts a gate's entry point where `scripts/gate-bind.ts` can see it; the logic lives in `rediacc_ci.quality.release_signing_coverage`, which pytest and the port's own `--selftest` import directly.

CUT OVER FROM BASH 2026-09-08 (W7 P4 batch 6). See DRIVEN, below.

WHY AN ENTRY POINT AT ALL: `check_npmrc.py` states both measured reasons. A port cannot be run by path (nothing puts `.ci` on `sys.path`, hence the insert below), and `python3 -m rediacc_ci.quality.release_signing_coverage` works but is the wrong registration because `check:ci-parity`'s tokenizer cannot read `-m` and resolves the leaves to `[python3]`.

THE HEADER BELOW IS THE TWIN'S, FIELD FOR FIELD, extracted from `.ci/scripts/quality/check-release-signing-coverage.sh` with an awk range over its `---- gate ----` block and diffed line by line against this one. The twin carried exactly four fields -- `step`, `needs`, `selftest`, `lane` -- and no `emit:`, no `blocker:`, no `id:`, no `run:`, no `kind:`, no `why:`. The absences are
carried as deliberately as the presences: this gate's step sits INSIDE the `# >>> gate-bind` region of `quality-security` (ci-quality.yml:1828), so an `emit: false` invented here would suppress the three workflow-region checks that today keep that step honest.

NO `id:` IS CORRECT HERE, checked rather than assumed: `derivedId` (`gate-header.ts:260`) maps this basename to `check:ci-release-signing-coverage`, the manifest id.

`selftest: true` is inert for a `.py` gate (`headerLines` emits it only for `.ts`, `gate-bind.ts:598`) and is carried because the twin declared it and because `release_signing_coverage.main(["--selftest"])` exits 0 over a real control battery.

THE RESOLVED NEED SET DOES NOT MOVE, verified by calling `bind()` on both files rather than by reading them. `bind()` unions declared needs with `inferredNeeds(source)`; the twin's sed/awk body infers nothing and this two-import entry point infers nothing, because `inferredNeeds` strips Python docstrings as prose (`gate-header.ts:301`). Both resolve to the empty set `needs: none`
declares.

DRIVEN, on this tree, both streams captured SEPARATELY, `CI=true` on both:

    .ci/scripts/quality/check-release-signing-coverage.sh   -> exit 0
    .ci/scripts/quality/check_release_signing_coverage.py   -> exit 0
    stdout: BYTE-IDENTICAL, 590 bytes, sha256 bd66e4758fdd736e...
    stderr: BYTE-IDENTICAL, and EMPTY on both sides

DRIVEN RED AS WELL, and against a HARD-COPIED FIXTURE rather than the live tree, because both implementations honour `SIGNING_COVERAGE_ROOT` and so can be pointed at one. The fixture was built with `cp -r` and checked with `find -type l` for zero symlinks: batch 4 damaged a tracked file because `mutate-check.sh:122` resolves symlinks with `realpath --relative-to`, and a run against
a linked fixture shows twin and port AGREEING for the worst possible reason, both reading the same corrupted real tree.

The plant deletes the `RELEASE_SIGNING_REQUIRED` refusal block from the `rpm | deb)` arm of `build-linux-pkg.sh`, which is the exact 2026-09-05 shape this gate exists for (an empty key shipping an unsigned package, green). Both sides exit 1 with BYTE-IDENTICAL 375-byte stdout and BYTE-IDENTICAL 302-byte stderr:

    FAIL  'deb' refuses to ship unsigned when signing is required (got 'no' want 'yes')
    FAIL  'rpm' refuses to ship unsigned when signing is required (got 'no' want 'yes')
    release signing coverage: 2 of 9 control(s) failed

THE FIRST PLANT DID NOT FIRE, AND THE FAULT WAS THE CONTROL. It renamed `RELEASE_SIGNING_REQUIRED` on the `if` line ALONE, and `guarded_in` scans the arm body for the literal anywhere -- which the `log_error` message on the very next line still carried. Both sides stayed green, correctly. Deleting the whole block turned both red. Recorded because a one-line rename looks like a
sufficient mutation and is not.

The fixture was restored from its `.orig` copy and `git status --porcelain` diffed against its pre-plant capture with no difference.

INVARIANT 5 HELD UNTIL THE LEDGER LICENSED THIS PORT: `.ci/scripts/quality/check-release-signing-coverage.sh` stayed on disk as the differential twin until `.ci/shadow/w7p2-signing-coverage.observations.jsonl` asserted equivalence over five distinct trees. W7 P5 batch C1 retired it, and this entry point is what the gate runs from.

---- gate ----
step: Release signing coverage
needs: none
selftest: true
lane: quality-security
---- end gate ----
"""

import sys

import _cipath  # noqa: F401
from rediacc_ci.quality import release_signing_coverage

if __name__ == "__main__":
    raise SystemExit(release_signing_coverage.main(sys.argv[1:]))
