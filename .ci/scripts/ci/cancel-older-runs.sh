#!/bin/bash
# Force-cancel older CI runs on the same branch after their Quality checks complete
# This replaces the concurrency group (which uses slow normal-cancel) and the Queue gate
# (which serialized across all PRs unnecessarily).
#
# Usage: cancel-older-runs.sh [--timeout <seconds>] [--poll-interval <seconds>] [--workflow <name>]
#
# Options:
#   --timeout        Maximum wait time in seconds (default: 300 = 5 minutes)
#   --poll-interval  Polling interval in seconds (default: 15)
#   --workflow       Workflow filename to check (default: ci.yml)
#
# Environment:
#   GITHUB_RUN_ID        Current workflow run ID (set by GitHub Actions)
#   GITHUB_REPOSITORY    Repository in owner/repo format
#   GH_TOKEN             GitHub token for API access
#
# Behavior:
#   1. Finds in-progress CI runs on the same branch that started before this run
#   2. Waits for their Quality checks to complete (Quality is cheap, let it finish)
#   3. Force-cancels them once Quality is done (they're now in expensive build/test phase)
#   4. Exits when all older runs are cancelled or timeout is reached
#
# Example:
#   .ci/scripts/ci/cancel-older-runs.sh --timeout 300 --poll-interval 15

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

TIMEOUT="${ARG_TIMEOUT:-300}"
POLL_INTERVAL="${ARG_POLL_INTERVAL:-15}"
WORKFLOW="${ARG_WORKFLOW:-ci.yml}"

# Validate environment
if [[ -z "${GITHUB_RUN_ID:-}" ]]; then
    log_warn "GITHUB_RUN_ID not set - skipping (not running in GitHub Actions)"
    exit 0
fi

if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
    log_error "GITHUB_REPOSITORY not set"
    exit 1
fi

if [[ -z "${GH_TOKEN:-}" ]]; then
    log_error "GH_TOKEN not set"
    exit 1
fi

# Get current run info
log_step "Checking for older in-progress CI runs..."

CURRENT_RUN_ID="$GITHUB_RUN_ID"
RUN_INFO=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${CURRENT_RUN_ID}" 2>&1) || {
    log_warn "Failed to fetch current run info: $RUN_INFO"
    exit 0
}

CURRENT_CREATED=$(echo "$RUN_INFO" | jq -r '.created_at // empty')
HEAD_BRANCH=$(echo "$RUN_INFO" | jq -r '.head_branch // empty')

if [[ -z "$CURRENT_CREATED" ]] || [[ -z "$HEAD_BRANCH" ]]; then
    log_warn "Could not parse run info - skipping"
    exit 0
fi

log_info "Current run: #${CURRENT_RUN_ID} (branch: ${HEAD_BRANCH}, created: ${CURRENT_CREATED})"

# Force-cancel a single run (with fallback to regular cancel)
force_cancel_run() {
    local run_id="$1"
    local run_number="$2"

    if gh api -X POST "repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}/force-cancel" 2>/dev/null; then
        log_info "Force-cancelled run #${run_number}"
    elif gh api -X POST "repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}/cancel" 2>/dev/null; then
        log_info "Cancelled run #${run_number} (force-cancel unavailable)"
    else
        log_warn "Failed to cancel run #${run_number}"
    fi
}

# Check if Quality is done for a given run
check_quality_done() {
    local run_id="$1"
    local jobs_json

    jobs_json=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${run_id}/jobs?per_page=30" 2>/dev/null) || return 1

    # Quality is a reusable workflow, sub-jobs appear as "Quality / Lint", "Quality / Test", etc.
    local quality_total quality_completed
    quality_total=$(echo "$jobs_json" | jq '[.jobs[] | select(.name | startswith("Quality"))] | length')
    quality_completed=$(echo "$jobs_json" | jq '[.jobs[] | select(.name | startswith("Quality")) | select(.status == "completed")] | length')

    # Quality is done when all sub-jobs exist and are completed
    [[ "$quality_total" -gt 0 ]] && [[ "$quality_total" -eq "$quality_completed" ]]
}

# Main polling loop
START_TIME=$(date +%s)

while true; do
    ELAPSED=$(( $(date +%s) - START_TIME ))

    if [[ $ELAPSED -ge $TIMEOUT ]]; then
        log_warn "Timeout reached (${TIMEOUT}s) - some older runs may not have been cancelled"
        exit 0
    fi

    # Find in-progress runs on the same branch
    RUNS_JSON=$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/${WORKFLOW}/runs?status=in_progress&branch=${HEAD_BRANCH}&per_page=10" 2>/dev/null) || {
        log_warn "Failed to list workflow runs - retrying..."
        sleep "$POLL_INTERVAL"
        continue
    }

    # Filter to runs created before current run
    OLDER_RUNS=$(echo "$RUNS_JSON" | jq -c "[.workflow_runs[] | select(.id != ${CURRENT_RUN_ID} and .created_at < \"${CURRENT_CREATED}\") | {id: .id, run_number: .run_number}]")
    OLDER_COUNT=$(echo "$OLDER_RUNS" | jq 'length')

    if [[ "$OLDER_COUNT" -eq 0 ]]; then
        log_info "No older CI runs in progress - done"
        exit 0
    fi

    ELAPSED_MIN=$((ELAPSED / 60))
    log_info "Found ${OLDER_COUNT} older run(s) (${ELAPSED_MIN}m elapsed)"

    # Check each older run
    ALL_HANDLED=true
    for row in $(echo "$OLDER_RUNS" | jq -c '.[]'); do
        RUN_ID=$(echo "$row" | jq -r '.id')
        RUN_NUMBER=$(echo "$row" | jq -r '.run_number')

        if check_quality_done "$RUN_ID"; then
            log_step "Run #${RUN_NUMBER}: Quality completed - force-cancelling..."
            force_cancel_run "$RUN_ID" "$RUN_NUMBER"
        else
            log_info "Run #${RUN_NUMBER}: still in Quality - skipping"
            ALL_HANDLED=false
        fi
    done

    if [[ "$ALL_HANDLED" == "true" ]]; then
        log_info "All older runs handled"
        exit 0
    fi

    sleep "$POLL_INTERVAL"
done
