#!/bin/bash
# Run an externally-dependent quality gate under the external_quality mode.
#
# WHY THIS EXISTS. 5 of the 8 nightlies before 2026-08-04 failed on nothing but
# external drift (a new rclone release, freshly published npm advisories, a new
# action version): the world moved, not this tree. The `no-external-quality`
# label cannot help there, because the nightly fires on `schedule` where no PR
# label can ever apply. The fix is a three-state flag computed by ci.yml's
# initialize job (`external_quality`: hard | skip | soft):
#
#   hard  pull request without the label  -> a failure blocks, exit code kept
#   skip  pull request with the label     -> the step does not run at all
#         (expressed in the step's `if:`, this wrapper never sees it)
#   soft  schedule / workflow_dispatch    -> the gate RUNS and REPORTS, but a
#         failure becomes a ::warning:: + step summary + exit 0, so external
#         drift shows as yellow instead of reddening the only suite that
#         validates main (and issue #544 stops crying wolf).
#
# continue-on-error is NOT an option here: check-workflows.sh bans it
# repo-wide, and the repo's precedent for non-blocking behaviour is a
# script-level soft-fail (see scripts/check-embed-asset-freshness.ts, "FAIL
# SOFT"). This wrapper is that precedent, factored out once instead of being
# re-implemented inside every external gate.
#
# Usage: EXTERNAL_QUALITY_MODE=hard|soft run-external-gate.sh <command...>
#        (unset EXTERNAL_QUALITY_MODE means hard: fail closed, a wiring break
#        must never silently disable a blocking gate)

set -euo pipefail

MODE="${EXTERNAL_QUALITY_MODE:-hard}"

if [ "$#" -eq 0 ]; then
    echo "usage: EXTERNAL_QUALITY_MODE=hard|soft $0 <command...>" >&2
    exit 2
fi

case "$MODE" in
    hard | soft) ;;
    *)
        # Fail closed: an unknown mode means the workflow wiring broke, and
        # guessing 'soft' would quietly disable a blocking gate.
        echo "run-external-gate: unknown EXTERNAL_QUALITY_MODE '$MODE' (expected hard|soft)" >&2
        exit 2
        ;;
esac

rc=0
"$@" || rc=$?

if [ "$rc" -eq 0 ]; then
    exit 0
fi

if [ "$MODE" = "soft" ]; then
    echo "::warning::external gate '$*' failed (exit $rc) in soft mode: external drift reported, run stays green (blocking on pull requests)"
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
        {
            echo "### External gate soft-failed: \`$*\` (exit $rc)"
            echo ""
            echo "Scheduled runs report external drift (new upstream releases,"
            echo "new advisories) as a warning instead of a red; the identical"
            echo "failure blocks on a pull request. See docs/agent-reference/ci-gates.md."
        } >>"$GITHUB_STEP_SUMMARY"
    fi
    exit 0
fi

exit "$rc"
