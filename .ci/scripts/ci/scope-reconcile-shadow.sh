#!/bin/bash
# Skip-plan reconciliation, SHADOW mode: report whether the attested plan
# MATCHED what the run actually did, and fail nothing.
#
# This is the evidence that has to exist before the reconciler can be wired for
# real. The reconciler itself hard-fails on a mismatch (proven: an honest plan
# exits 0, a planted invisible cell exits 1 with `planned-run-but-skipped`), so
# turning it on blind would make a required check red for every PR whose plan
# mispredicts a job for reasons that have nothing to do with scope.
#
# THAT CLASS IS NOW ENCODED rather than merely warned about. The plan carries
# the three pre-existing conditions (`full_suite` false on push-to-main,
# `pointer_bump_only` true on a submodule-pointer PR, `is_bot` true on a bot
# push) and the reconciler exempts the keys each one skips, so a run of that
# shape reconciles clean instead of reporting up to seventeen false failures.
# See skip-plan-reconcile.cjs's PREEXISTING_CONDITIONS.
#
# So this runs the REAL reconciler against the REAL per-job outcomes and prints
# the verdict, without acting on it. What it is looking for is a run of PRs
# where the verdict is clean AND the exempt list is short: a clean verdict whose
# every key was excused proves nothing, which is why the CLI prints the exempt
# keys alongside the verdict.
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

# Emit to BOTH the step summary and stdout.
#
# The summary alone was a mistake: GitHub exposes no API for step summaries
# (the job object has no summary field), so everything this script reported was
# readable only by a human in the web UI. An automated caller - the thing most
# likely to be reading a SHADOW observer's verdict - saw an empty job log and
# could not tell "reported nothing" from "never ran". That is the same
# unreadable-instrument failure this whole mechanism exists to avoid.
#
# stdout lands in the job log, which IS in the API.
emit() {
    printf '%s\n' "$@" | tee -a "$SUMMARY"
}

# HARD TIME BOUND on every external call, and this is the important safety
# property of this script, not a nicety.
#
# This runs inside ci-complete, which is `runs-on: ubuntu-slim` with
# `timeout-minutes: 5`. Per docs/agent/ci-gates.md, a slim job that runs out of
# time is marked CANCELLED with NO failed step, "which reads as neither pass nor
# fail and poisons CI Complete" -- the pipeline's single required check. So a
# hung `gh` retry or a slow artifact download in this SHADOW observer could
# cancel the required check for the whole PR.
#
# Bounding each call means the worst case is a missing measurement, which is
# what a shadow observer is allowed to cost. The total ceiling here is well
# under one minute against that 5-minute budget.
GH_TIMEOUT="${SCOPE_SHADOW_TIMEOUT:-45}"
bounded() { timeout "$GH_TIMEOUT" "$@"; }

emit "### Skip-plan reconciliation (shadow, fails nothing)" ""

# TOOL PROBE, and it is not defensive boilerplate. ci-complete runs on
# ubuntu-slim, where NO other job uses node and none sets it up
# (assert-ci-complete.sh is pure bash; only `gh` is evidenced there, by
# finalize-release-sentinel). If node is absent, running the reconciler would
# exit 127 and this script would dutifully print "WOULD HAVE FAILED" on every
# single PR: a fabricated verdict, and the precise dead-instrument failure this
# whole programme exists to eliminate. An absent tool must read as "could not
# measure", never as a result.
for tool in gh node; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        emit "_**cannot reconcile**: \`$tool\` is not available on this runner" \
            "(ci-complete runs on ubuntu-slim). This is a GAP IN THE EVIDENCE, not a" \
            "clean result. Fix by adding setup-node to ci-complete, or by moving this" \
            "step to a job on ubuntu-latest._" ""
        exit 0
    fi
done

# The plan was uploaded by initialize's shadow step earlier in THIS run. The
# name is the bare `ci-skip-plan`, NOT run-id-suffixed: artifact names are
# already scoped per run, and scope-engine's createRepoIo looks up exactly this
# name when a LATER run goes hunting for a baseline. A suffixed name would be
# undiscoverable by the very consumer it exists for.
if ! bounded gh run download "${GITHUB_RUN_ID}" --repo "${GITHUB_REPOSITORY}" \
    -n "ci-skip-plan" -D "$OUT_DIR/plan-dl" >/dev/null 2>&1; then
    emit "_no attested plan for this run: nothing to reconcile (expected on push-to-main," \
        "where the shadow attestation does not run)._" ""
    exit 0
fi

# Per-job outcomes, the thing the reconciler compares intent against.
# gh's stderr is KEPT, not discarded. Same defect class as the plan writer's
# swallowed exception one file over: this branch already says "gap in the
# evidence", but without gh's own explanation a rate limit, an expired token and
# a 404 are one indistinguishable message, and the next session re-derives which
# one it was from nothing.
if ! bounded gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?per_page=100" \
    --paginate >"$OUT_DIR/jobs.json" 2>"$OUT_DIR/jobs.err"; then
    emit "_could not read the jobs API; reconciliation skipped (this is a gap in the" \
        "evidence, NOT a clean result)._" '```'
    head -c 500 "$OUT_DIR/jobs.err" | tee -a "$SUMMARY"
    emit '```' ""
    exit 0
fi

set +e
bounded node "$RECONCILER" --plan "$OUT_DIR/plan-dl/plan.json" \
    --jobs "$OUT_DIR/jobs.json" --run-id "${GITHUB_RUN_ID}" \
    >"$OUT_DIR/reconcile.out" 2>"$OUT_DIR/reconcile.err"
rc=$?
set -e

if [[ $rc -eq 124 ]]; then
    # 124 is `timeout` killing it, NOT the reconciler's verdict. Reporting this
    # as WOULD HAVE FAILED would re-create, one line lower, exactly the
    # fabricated-verdict bug the tool probe above exists to prevent: the
    # reconciler never reached a conclusion, so there is nothing to report.
    emit "_**cannot reconcile**: the reconciler exceeded ${GH_TIMEOUT}s and was killed." \
        "This is a GAP IN THE EVIDENCE, not a verdict._" ""
elif [[ $rc -eq 0 ]]; then
    emit "**WOULD HAVE PASSED** (exit 0). One more data point toward wiring this for real." \
        "Check the \`pre-existing skips\` line below before banking it: a pass whose" \
        "every key was excused by \`full_suite\`, \`pointer_bump_only\` or \`is_bot\` is a" \
        "VACUOUS pass, and the counter that has to move is verified keys, not runs." ""
else
    emit "**WOULD HAVE FAILED** (exit ${rc}). Read the reason before blaming the plan." \
        "\`preexisting-claim-mismatch\` means the plan's annotation disagrees with what" \
        "its own recorded conditions imply, i.e. a tampered artifact or writer/reader" \
        "drift, NOT a scope error." ""
fi
emit '```'
head -c 3000 "$OUT_DIR/reconcile.err" 2>/dev/null | tee -a "$SUMMARY"
head -c 1500 "$OUT_DIR/reconcile.out" 2>/dev/null | tee -a "$SUMMARY"
emit '```'

# Always green. A shadow observer that can red a run is not a shadow observer.
exit 0
