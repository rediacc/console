#!/usr/bin/env python3
"""check:ci-review-resolutions -- a deferred per-commit review finding blocks the merge.

Logic is in `rediacc_ci.quality.review_resolutions`, which pytest and this file's `--selftest` import directly. The four rules, the resolution grammar and why a waiver is trusted on its grammar are in that module's docstring and are not repeated here (agent/plans/PLAN-deferred-findings-block-merge.md D4).

WHY quality-branch. It is the lane that checks out the PR HEAD ref at fetch-depth 0, which rule iv needs to walk `merge-base(origin/<base>, HEAD)..HEAD`; it rolls into the `quality` job `ci-complete` needs, so a red here cannot be exempted; and it runs on the pointer-bump fast path too.

THE `_cipath` IMPORT TAKES A NAME AND USES IT (`CI_DIR`), so the line carries no unused-import marker; the root is anchored on this file's own location and the gate answers the same from any working directory.

---- gate ----
step: Review resolutions
needs: none
selftest: true
lane: quality-branch
why: a `deferred` resolution counted as resolved in every local reader and no CI step
     read resolutions at all, so 1007-1 merged as PR #599 carrying a deferral. Operator
     ruling 2026-10-08: a finding is fixed before merge, always; the one escape is an
     operator-ruled waiver with an ASKED: minute.
---- end gate ----
"""

import sys

from _cipath import CI_DIR
from rediacc_ci.quality import review_resolutions

if __name__ == "__main__":
    raise SystemExit(review_resolutions.main(sys.argv[1:], root=CI_DIR.parent))
