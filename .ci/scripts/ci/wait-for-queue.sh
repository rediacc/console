#!/bin/bash
# Wait for other CI runs to complete before proceeding (global serialization)
# This ensures only one CI runs at a time to avoid exhausting runner limits.
#
# Usage: wait-for-queue.sh [--timeout <seconds>] [--poll-interval <seconds>]
#
# Options:
#   --timeout        Maximum wait time in seconds (default: 7200 = 2 hours)
#   --poll-interval  Polling interval in seconds (default: 30)
#   --workflow       Workflow filename to check (default: ci.yml)
#
# Environment:
#   GITHUB_RUN_ID    Current workflow run ID (set by GitHub Actions)
#   GITHUB_REPOSITORY  Repository in owner/repo format
#   GH_TOKEN         GitHub token for API access
#
# Example:
#   .ci/scripts/ci/wait-for-queue.sh --timeout 3600

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

TIMEOUT="${ARG_TIMEOUT:-7200}"
POLL_INTERVAL="${ARG_POLL_INTERVAL:-30}"
WORKFLOW="${ARG_WORKFLOW:-ci.yml}"

# Validate environment
if [[ -z "${GITHUB_RUN_ID:-}" ]]; then
    log_warn "GITHUB_RUN_ID not set - skipping queue check (not running in GitHub Actions)"
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

log_step "Checking for other in-progress CI runs..."

START_TIME=$(date +%s)
CURRENT_RUN_ID="$GITHUB_RUN_ID"

# Get current run's created_at timestamp with explicit error handling
log_info "Fetching info for run #${CURRENT_RUN_ID}..."
API_RESPONSE=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${CURRENT_RUN_ID}" 2>&1) || {
    log_warn "API call failed: $API_RESPONSE"
    log_error "Failed to perform queue check - cannot guarantee serialization"
    exit 1
}

CURRENT_RUN_CREATED=$(echo "$API_RESPONSE" | jq -r '.created_at // empty')

if [[ -z "$CURRENT_RUN_CREATED" ]]; then
    log_warn "Could not parse run info from API response - proceeding without queue"
    exit 0
fi

log_info "Current run: #${CURRENT_RUN_ID} (created: ${CURRENT_RUN_CREATED})"

while true; do
    ELAPSED=$(($(date +%s) - START_TIME))

    if [[ $ELAPSED -ge $TIMEOUT ]]; then
        log_error "Timed out waiting for other CI runs (${TIMEOUT}s limit)"
        exit 1
    fi

    # Get in-progress runs for the same workflow
    # Note: We capture stderr separately to detect API errors vs empty results
    API_ERROR_FILE=$(mktemp)
    OLDER_RUNS=$(gh api "repos/${GITHUB_REPOSITORY}/actions/workflows/${WORKFLOW}/runs?status=in_progress&per_page=10" \
        --jq --arg current_id "$CURRENT_RUN_ID" --arg current_created "$CURRENT_RUN_CREATED" \
        '[.workflow_runs[] | select(.id != ($current_id | tonumber) and .created_at < $current_created) | {id: .id, run_number: .run_number, branch: .head_branch, created_at: .created_at}]' \
        2>"$API_ERROR_FILE") || {
        local api_err
        api_err=$(<"$API_ERROR_FILE")
        rm -f "$API_ERROR_FILE"
        # Log warning but continue with empty array to avoid blocking CI
        log_warn "API call to fetch older runs failed: $api_err"
        OLDER_RUNS="[]"
    }
    rm -f "$API_ERROR_FILE"

    OLDER_COUNT=$(echo "$OLDER_RUNS" | jq 'length')

    if [[ "$OLDER_COUNT" -eq 0 ]]; then
        log_info "No older CI runs in progress - proceeding"
        exit 0
    fi

    ELAPSED_MIN=$((ELAPSED / 60))
    log_info "Waiting for ${OLDER_COUNT} older CI run(s) to complete... (${ELAPSED_MIN}m elapsed)"

    # Log details of older runs
    echo "$OLDER_RUNS" | jq -r '.[] | "  - Run #\(.run_number) (\(.branch)) started at \(.created_at)"'

    sleep "$POLL_INTERVAL"
done
