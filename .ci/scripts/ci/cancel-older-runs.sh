#!/bin/bash
# Force-cancel older CI runs on the same branch immediately
# This replaces the concurrency group (which uses slow normal-cancel) and the Queue gate
# (which serialized across all PRs unnecessarily).
#
# Usage: cancel-older-runs.sh [--timeout <seconds>] [--poll-interval <seconds>] [--workflow <name>]
#
# Options:
#   --timeout        Maximum wait time in seconds (default: 60)
#   --poll-interval  Polling interval in seconds (default: 10)
#   --workflow       Workflow filename to check (default: ci.yml)
#
# Environment:
#   GITHUB_RUN_ID        Current workflow run ID (set by GitHub Actions)
#   GITHUB_REPOSITORY    Repository in owner/repo format
#   GH_TOKEN             GitHub token for API access
#
# Behavior:
#   1. Finds in-progress CI runs on the same branch that started before this run
#   2. Force-cancels them immediately
#   3. Verifies cancellation, retries if needed
#
# Example:
#   .ci/scripts/ci/cancel-older-runs.sh --timeout 60 --poll-interval 10

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

TIMEOUT="${ARG_TIMEOUT:-60}"
POLL_INTERVAL="${ARG_POLL_INTERVAL:-10}"
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

# Main loop: find and cancel older runs, retry until all are gone
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

    log_info "Found ${OLDER_COUNT} older run(s) - force-cancelling..."

    # Force-cancel each older run immediately
    for row in $(echo "$OLDER_RUNS" | jq -c '.[]'); do
        RUN_ID=$(echo "$row" | jq -r '.id')
        RUN_NUMBER=$(echo "$row" | jq -r '.run_number')
        force_cancel_run "$RUN_ID" "$RUN_NUMBER"
    done

    # Wait and re-check to confirm cancellation took effect
    sleep "$POLL_INTERVAL"
done
