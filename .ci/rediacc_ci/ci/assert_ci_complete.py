#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/assert-ci-complete.sh` (89 lines).

The body of the `CI Complete` gate: fail unless every CI job reached an
acceptable conclusion. The twin's header owns the contract -- the HARD/SOFT
tiers, why `RUN_SH_TESTS` is hard, why `MIGRATION_TEST` is absent, why
`BREAKPOINT_LIFECYCLE` and `LABEL_GUIDE` are soft -- and it is not restated
here. The tier membership below is a copy of the twin's two arrays; the
per-member reasoning stays in the twin, which is the file
`.ci/rediacc_ci/tests/gates/test_gate_ci_complete_tiers.py` reads.

LIVE CALLER, not repointed: `.github/workflows/ci.yml:1736`
`run: .ci/scripts/ci/assert-ci-complete.sh`, with one `RESULT_*` env var per
job at :1738-1760. The bash twin stays the registered gate; this module is its
verified-equivalent alternative and the cutover is a separate, later,
driver-only step.

Ledger: `.ci/shadow/w7p6-assert-ci-complete.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-ci-complete --assert
--k 5`).

-----------------------------------------------------------------------------
A REAL HOLE IN THE TWIN, REPRODUCED RATHER THAN FIXED
-----------------------------------------------------------------------------
`POINTER_BUMP_ONLY=true` REPLACES the hard tier with `(INITIALIZE)` and moves
the three build jobs into the soft tier. `RUN_SH_TESTS` is dropped from hard
and added to NEITHER tier, so on a pointer-bump PR it is judged by nothing:

    $ env -i PATH=/usr/bin:/bin HOME=/tmp POINTER_BUMP_ONLY=true \\
        RESULT_INITIALIZE=success RESULT_RUN_SH_TESTS=failure \\
        <every soft var>=skipped bash .ci/scripts/ci/assert-ci-complete.sh
    ✓ All CI jobs passed successfully!
    exit 0

It is LIVE rather than latent: `ci.yml:532-538` gates `run-sh-tests` on
`is_bot` only, so the job really does run on a pointer-bump PR and a genuine
failure of the hermetic entry-point suite reads as green. Fixing the twin is a
cutover-box decision, so this port reproduces the hole exactly and
`test_ci_assert_ci_complete.py::test_pointer_bump_drops_run_sh_tests_from_both
_tiers` pins both sides of it.

-----------------------------------------------------------------------------
`${!var:-<unset>}` TREATS EMPTY AS UNSET, AND SO DOES THIS
-----------------------------------------------------------------------------
The twin uses `:-`, not `-`, so `RESULT_TESTS=` (set but empty, which is what a
workflow expression yielding nothing produces) reports `<unset>` and fails,
rather than falling through some empty-string arm. `os.environ.get(name, "")
or UNSET` is the same rule.
"""

from __future__ import annotations

import os
import sys

from rediacc_ci import log

# The literal the twin substitutes for a missing conclusion. It is printed, not just compared, so a renamed job breaks loudly in the log.
UNSET = "<unset>"

HARD_REQUIRED = ("INITIALIZE", "BUILD_DOCKER", "BUILD_DOCKER_FAST", "BUILD_CLI", "RUN_SH_TESTS")

SOFT_REQUIRED = (
    "QUALITY",
    "REVIEW_GATE",
    "STRIPE_SANDBOX",
    "PACKAGE_TESTS",
    "STAGE_ARTIFACTS",
    "LABEL_GUIDE",
    "VALIDATE_INSTALL",
    "VALIDATE_PROMOTE",
    "TESTS",
    "ELITE_RUN_TEST",
    "OPS_TESTS",
    "UPDATE_FLOW_TEST",
    "DEPLOY_PREVIEW",
    "SMOKE_TEST_PREVIEW",
    "BREAKPOINT_LIFECYCLE",
    "CHECK_RELEASE_STATE",
)

# The pointer-bump fast path (see `.ci/scripts/ci/detect-pointer-bump.sh`): the three build jobs are DELIBERATELY skipped by ci.yml, so their skips must read as green. Soft still blocks on "failure", so a genuine build failure is not forgiven. RUN_SH_TESTS is deliberately absent from this list because it is absent from the twin's -- see the hole documented above.
POINTER_BUMP_HARD = ("INITIALIZE",)
POINTER_BUMP_EXTRA_SOFT = ("BUILD_DOCKER", "BUILD_DOCKER_FAST", "BUILD_CLI")


def conclusion(job: str) -> str:
    """The reported conclusion of one job, or `<unset>`. Empty counts as unset."""
    return os.environ.get("RESULT_%s" % job, "") or UNSET


def tiers() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(hard, soft) for this run, after the pointer-bump fast path is applied."""
    if os.environ.get("POINTER_BUMP_ONLY", "") == "true":
        return POINTER_BUMP_HARD, SOFT_REQUIRED + POINTER_BUMP_EXTRA_SOFT
    return HARD_REQUIRED, SOFT_REQUIRED


def main(argv: list[str]) -> int:
    del argv
    hard, soft = tiers()
    failed = False

    for job in hard:
        value = conclusion(job)
        if value != "success":
            log.error("%s: %s (hard-required, must be 'success')" % (job, value))
            failed = True

    for job in soft:
        value = conclusion(job)
        if value not in ("success", "skipped"):
            log.error("%s: %s (soft-required, must be 'success' or 'skipped')" % (job, value))
            failed = True

    if failed:
        log.error("One or more CI jobs did not reach an acceptable conclusion (see above)")
        return 1

    log.info("All CI jobs passed successfully!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
