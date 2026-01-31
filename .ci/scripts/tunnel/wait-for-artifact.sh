#!/bin/bash
# Wait for tunnel-url artifact to exist (API check only, no download)
# Usage: wait-for-artifact.sh --run-id <run_id> [--artifact-name <name>] [--timeout <seconds>]
#
# Polls GitHub Actions API to check if artifact exists.
# Used as a gateway job so test jobs don't poll independently.
#
# On retry attempts (attempt > 1), only considers artifacts created after
# the current attempt started, avoiding stale artifacts from attempt 1.
#
# Options:
#   --run-id         Workflow run ID (required)
#   --artifact-name  Artifact name to wait for (default: tunnel-url)
#   --timeout        Maximum wait time in seconds (default: 1200)
#   --interval       Polling interval in seconds (default: 15)
#
# Required environment variables:
#   GH_TOKEN            GitHub token for API calls
#   GITHUB_REPOSITORY   Repository in owner/repo format
#
# Example:
#   .ci/scripts/tunnel/wait-for-artifact.sh --run-id 12345

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

RUN_ID="${ARG_RUN_ID:-}"
ARTIFACT_NAMES="${ARG_ARTIFACT_NAME:-tunnel-url,tunnel-url-pinggy}"
TIMEOUT="${ARG_TIMEOUT:-1200}"
INTERVAL="${ARG_INTERVAL:-15}"

# Validate required arguments
if [[ -z "$RUN_ID" ]]; then
    log_error "Usage: wait-for-artifact.sh --run-id <run_id> [--artifact-name <name>] [--timeout <seconds>]"
    exit 1
fi

# Validate required environment variables
require_var GH_TOKEN
require_var GITHUB_REPOSITORY

# Require gh CLI
require_cmd gh

# Determine the current attempt's start time to filter out stale artifacts.
# On attempt > 1, artifacts from previous attempts may still exist with the
# same name but contain dead tunnel URLs.
ATTEMPT_START=""
RUN_ATTEMPT=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}" \
    --jq '.run_attempt' 2>/dev/null || echo "1")

if [[ "$RUN_ATTEMPT" -gt 1 ]]; then
    ATTEMPT_START=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}" \
        --jq '.run_started_at' 2>/dev/null || echo "")
    if [[ -n "$ATTEMPT_START" ]]; then
        log_info "Run attempt $RUN_ATTEMPT — only considering artifacts created after $ATTEMPT_START"
    fi
fi

log_step "Waiting for any artifact in '$ARTIFACT_NAMES' (run: $RUN_ID, attempt: $RUN_ATTEMPT, timeout: ${TIMEOUT}s)..."

# Check if any fresh artifact exists via GitHub API
# Supports comma-separated names — returns 0 if ANY match is found
# On retry attempts, filters out stale artifacts from previous attempts
artifact_exists() {
    local jq_filter

    if [[ -n "$ATTEMPT_START" ]]; then
        # Only match artifacts created after the current attempt started
        jq_filter=".artifacts[] | select(.created_at >= \"$ATTEMPT_START\") | .name"
    else
        jq_filter=".artifacts[].name"
    fi

    local artifacts
    artifacts=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/artifacts" \
        --jq "$jq_filter" 2>/dev/null || echo "")

    IFS=',' read -ra NAMES <<< "$ARTIFACT_NAMES"
    for name in "${NAMES[@]}"; do
        name="$(echo "$name" | xargs)"  # trim whitespace
        if echo "$artifacts" | grep -q "^${name}$"; then
            return 0
        fi
    done
    return 1
}

# Progress callback
on_poll() {
    local elapsed="$1"
    local timeout="$2"
    log_info "Waiting for artifact... (${elapsed}s / ${timeout}s)"
}

# Main wait loop
if poll_with_watchdog "$TIMEOUT" "$INTERVAL" artifact_exists on_poll; then
    log_info "Tunnel artifact is available!"
    exit 0
fi

# Timeout reached
log_error "Timeout: none of '$ARTIFACT_NAMES' found after ${TIMEOUT}s"
exit 1
