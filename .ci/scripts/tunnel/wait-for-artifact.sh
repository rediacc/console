#!/bin/bash
# Wait for tunnel-url artifact to exist (API check only, no download)
# Usage: wait-for-artifact.sh --run-id <run_id> [--artifact-name <name>] [--timeout <seconds>]
#
# Polls GitHub Actions API to check if artifact exists.
# Used as a gateway job so test jobs don't poll independently.
#
# Artifact names are stable (e.g., tunnel-url) across attempts. The download
# script selects the most recently created matching artifact, so stale artifacts
# from previous attempts are naturally ignored.
#
# Options:
#   --run-id         Workflow run ID (required)
#   --artifact-name  Comma-separated artifact names to wait for (default: tunnel-url,tunnel-url-pinggy)
#   --timeout        Maximum wait time in seconds (default: 1200)
#   --interval       Polling interval in seconds (default: 15)
#
# Required environment variables:
#   GH_TOKEN            GitHub token for API calls
#   GITHUB_REPOSITORY   Repository in owner/repo format
#
# Example:
#   .ci/scripts/tunnel/wait-for-artifact.sh --run-id 12345 --artifact-name "tunnel-url,tunnel-url-pinggy"

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

log_step "Waiting for any artifact in '$ARTIFACT_NAMES' (run: $RUN_ID, timeout: ${TIMEOUT}s)..."

# Determine the start time of the latest workflow attempt. Artifacts created
# before this time are considered stale (left over from a previous attempt).
get_attempt_start() {
    local attempt
    attempt=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}" \
        --jq '.run_attempt' 2>/dev/null || echo "1")
    gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/attempts/${attempt}" \
        --jq '.run_started_at' 2>/dev/null || echo ""
}

# Convert an ISO 8601 timestamp to a Unix epoch integer.
# Runs on Linux (ubuntu-slim) so `date -d` is available.
to_epoch() {
    date -d "$1" +%s 2>/dev/null || echo "0"
}

ATTEMPT_START_ISO=$(get_attempt_start)
ATTEMPT_START_EPOCH=$(to_epoch "$ATTEMPT_START_ISO")
if [[ -n "$ATTEMPT_START_ISO" ]]; then
    log_info "Current attempt started at ${ATTEMPT_START_ISO} (epoch: ${ATTEMPT_START_EPOCH})"
fi

# Check if any matching artifact exists via GitHub API and was created during
# the current attempt. Supports comma-separated names — returns 0 if ANY fresh
# match is found.
artifact_exists() {
    IFS=',' read -ra NAMES <<<"$ARTIFACT_NAMES"
    for name in "${NAMES[@]}"; do
        name="$(echo "$name" | xargs)" # trim whitespace
        local latest_created
        latest_created=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/artifacts?per_page=100" \
            --jq "[.artifacts[] | select(.name == \"$name\")] | sort_by(.created_at) | last | .created_at // empty" 2>/dev/null || echo "")
        if [[ -z "$latest_created" ]]; then
            continue
        fi
        # If we couldn't determine the attempt start time, accept the artifact
        # (fallback for API errors). Otherwise require it to be fresh.
        if [[ "$ATTEMPT_START_EPOCH" -eq 0 ]] || [[ "$(to_epoch "$latest_created")" -ge "$ATTEMPT_START_EPOCH" ]]; then
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
