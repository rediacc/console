#!/bin/bash
# Skip-plan reconciliation, SHADOW mode: report whether the attested plan
# MATCHED what the run actually did, and fail nothing.
#
# This is the evidence that has to exist before the reconciler can be wired for
# real. The reconciler itself hard-fails on a mismatch (proven: an honest plan
# exits 0, a planted invisible cell exits 1 with `planned-run-but-skipped`), so
# turning it on blind would make a required check red for every PR whose plan
# mispredicts a job for reasons that have nothing to do with scope: `full_suite`
# is false on push-to-main, `pointer_bump_only` skips legs, and the shadow plan
# encodes none of that yet.
#
# So this runs the REAL reconciler against the REAL per-job outcomes and prints
# the verdict, without acting on it. What it is looking for is a run of PRs
# where the verdict is clean. Until that exists, wiring the gate is a guess.
#
# REQUIRED ENV
#   GH_TOKEN            needs `actions: read` to download the plan and read jobs
#   GITHUB_REPOSITORY   owner/name
#   GITHUB_RUN_ID       the run being reconciled
#   GITHUB_STEP_SUMMARY optional; falls back to stdout when running locally
#
# LOCAL RUN
#   GITHUB_REPOSITORY=rediacc/console GITHUB_RUN_ID=<id> \
#     .ci/scripts/ci/scope-reconcile-shadow.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECONCILER="$SCRIPT_DIR/skip-plan-reconcile.cjs"
SUMMARY="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
OUT_DIR="${SCOPE_SHADOW_OUT:-$SCRIPT_DIR/../../cache/scope-shadow}"
mkdir -p "$OUT_DIR"

emit() { printf '%s\n' "$@" >>"$SUMMARY"; }

emit "### Skip-plan reconciliation (shadow, fails nothing)" ""

# The plan was uploaded by initialize's shadow step earlier in THIS run. The
# name is the bare `ci-skip-plan`, NOT run-id-suffixed: artifact names are
# already scoped per run, and scope-engine's createRepoIo looks up exactly this
# name when a LATER run goes hunting for a baseline. A suffixed name would be
# undiscoverable by the very consumer it exists for.
if ! gh run download "${GITHUB_RUN_ID}" --repo "${GITHUB_REPOSITORY}" \
    -n "ci-skip-plan" -D "$OUT_DIR/plan-dl" >/dev/null 2>&1; then
    emit "_no attested plan for this run: nothing to reconcile (expected on push-to-main," \
        "where the shadow attestation does not run)._" ""
    exit 0
fi

# Per-job outcomes, the thing the reconciler compares intent against.
if ! gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?per_page=100" \
    --paginate >"$OUT_DIR/jobs.json" 2>/dev/null; then
    emit "_could not read the jobs API; reconciliation skipped (this is a gap in the" \
        "evidence, NOT a clean result)._" ""
    exit 0
fi

set +e
node "$RECONCILER" --plan "$OUT_DIR/plan-dl/plan.json" \
    --jobs "$OUT_DIR/jobs.json" --run-id "${GITHUB_RUN_ID}" \
    >"$OUT_DIR/reconcile.out" 2>"$OUT_DIR/reconcile.err"
rc=$?
set -e

if [[ $rc -eq 0 ]]; then
    emit "**WOULD HAVE PASSED** (exit 0). One more data point toward wiring this for real." ""
else
    emit "**WOULD HAVE FAILED** (exit ${rc}). Read the reason before blaming the plan:" \
        "a mismatch here is usually the plan failing to encode a pre-existing skip" \
        "condition, not the run skipping attested work." ""
fi
emit '```'
head -c 3000 "$OUT_DIR/reconcile.err" 2>/dev/null >>"$SUMMARY"
head -c 1500 "$OUT_DIR/reconcile.out" 2>/dev/null >>"$SUMMARY"
emit '```'

# Always green. A shadow observer that can red a run is not a shadow observer.
exit 0
