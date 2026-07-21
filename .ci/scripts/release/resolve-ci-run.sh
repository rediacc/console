#!/bin/bash
# Resolve (or validate) the CI run that a release publishes from.
#
# WHY: cd-v2.yml can be dispatched two ways. Auto-dispatch from ci.yml's
# finalize-release-sentinel passes no ci_run_id, so we derive the latest green
# Console CI run on main. A manual dispatch passes one explicitly, and it must
# be checked -- but only for branch + workflow + basic status, NOT for "is this
# the latest green run".
#
# The previous "must be latest green" rule rejected every auto-dispatched
# release: finalize-release-sentinel triggers cd-v2 mid-CI (after stage-artifacts
# seals R2, before housekeeping / pipeline-sentinel finish), so the dispatching
# run is still in-progress, conclusion is empty, and it cannot match "latest
# GREEN". assert-artifact-version.sh catches stale-ci_run_id mismatches directly
# (the actual foot-gun), which makes the latest-green check redundant.
#
# Usage:
#   .ci/scripts/release/resolve-ci-run.sh
#
# Required env:
#   GITHUB_REPOSITORY  owner/repo the CI run belongs to (GitHub sets this)
#   GITHUB_OUTPUT      step-output file to append ci_run_id / ci_sha to
#   GH_TOKEN           token for `gh api` (or any working `gh auth` locally)
#
# Optional env:
#   INPUT_CI_RUN_ID    explicit CI run id; empty means auto-derive
#   ALLOW_STALE        "true" downgrades a non-success conclusion to a warning
#   GITHUB_SHA         fallback head sha when the run lookup fails
#
# Run locally:
#   GITHUB_REPOSITORY=rediacc/console GITHUB_OUTPUT=/dev/stdout \
#     .ci/scripts/release/resolve-ci-run.sh
#
# Shell options: the workflow block already ran under `set -euo pipefail`;
# kept identical here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd jq
: "${GITHUB_REPOSITORY:?resolve-ci-run.sh: GITHUB_REPOSITORY must be set}"
: "${GITHUB_OUTPUT:?resolve-ci-run.sh: GITHUB_OUTPUT must be set}"

INPUT_CI_RUN_ID="${INPUT_CI_RUN_ID:-}"
ALLOW_STALE="${ALLOW_STALE:-}"

if [[ -z "${INPUT_CI_RUN_ID}" ]]; then
    LATEST_ID=$(gh api \
        "repos/${GITHUB_REPOSITORY}/actions/workflows/ci.yml/runs?branch=main&status=success&per_page=1" \
        --jq '.workflow_runs[0].id // empty')
    if [[ -z "${LATEST_ID}" ]]; then
        echo "::error::No green Console CI run found on main. Cannot auto-derive ci_run_id; dispatch will not proceed."
        exit 1
    fi
    CI_RUN_ID="${LATEST_ID}"
    echo "::notice::Auto-derived ci_run_id=${CI_RUN_ID} (latest green Console CI on main)."
else
    CI_RUN_ID="${INPUT_CI_RUN_ID}"
    run_json="$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${CI_RUN_ID}" 2>/dev/null || echo '{}')"
    run_branch="$(echo "$run_json" | jq -r '.head_branch // ""')"
    run_conclusion="$(echo "$run_json" | jq -r '.conclusion // ""')"
    run_status="$(echo "$run_json" | jq -r '.status // ""')"
    run_workflow="$(echo "$run_json" | jq -r '.name // ""')"

    failed=false
    if [[ "$run_branch" != "main" ]]; then
        echo "::error::ci_run_id ${CI_RUN_ID} is on branch '${run_branch}', not 'main'."
        failed=true
    fi
    if [[ "$run_workflow" != "Console CI" ]]; then
        echo "::error::ci_run_id ${CI_RUN_ID} is workflow '${run_workflow}', not 'Console CI'."
        failed=true
    fi
    # In-progress runs are valid (auto-dispatched from finalize-
    # release-sentinel mid-CI). Completed runs must be success.
    if [[ "$run_status" == "completed" && "$run_conclusion" != "success" ]]; then
        if [[ "${ALLOW_STALE}" == "true" ]]; then
            echo "::warning::ci_run_id ${CI_RUN_ID} completed with conclusion '${run_conclusion}'; allow_stale_ci_run_id is set, proceeding anyway."
        else
            echo "::error::ci_run_id ${CI_RUN_ID} completed with conclusion '${run_conclusion}', not 'success'."
            failed=true
        fi
    fi
    if [[ "$failed" == "true" ]]; then
        echo "::error::ci_run_id validation failed -- refusing to dispatch with invalid CI run."
        exit 1
    fi
fi

CI_SHA=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${CI_RUN_ID}" --jq '.head_sha' 2>/dev/null || echo "${GITHUB_SHA:-}")
echo "ci_run_id=${CI_RUN_ID}" >>"$GITHUB_OUTPUT"
echo "ci_sha=${CI_SHA}" >>"$GITHUB_OUTPUT"
