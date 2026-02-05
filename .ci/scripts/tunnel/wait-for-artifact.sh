#!/bin/bash
# Wait for tunnel-url artifact to exist (API check only, no download)
# Usage: wait-for-artifact.sh --run-id <run_id> [--artifact-name <name>] [--timeout <seconds>]
#
# Polls GitHub Actions API to check if artifact exists.
# Used as a gateway job so test jobs don't poll independently.
#
# Artifact names include the run attempt suffix (e.g., tunnel-url-attempt-2)
# so retries naturally avoid stale artifacts from previous attempts.
#
# Options:
#   --run-id         Workflow run ID (required)
#   --artifact-name  Comma-separated artifact names to wait for (default: tunnel-url-attempt-1,tunnel-url-pinggy-attempt-1)
#   --timeout        Maximum wait time in seconds (default: 1200)
#   --interval       Polling interval in seconds (default: 15)
#
# Required environment variables:
#   GH_TOKEN            GitHub token for API calls
#   GITHUB_REPOSITORY   Repository in owner/repo format
#
# Example:
#   .ci/scripts/tunnel/wait-for-artifact.sh --run-id 12345 --artifact-name "tunnel-url-attempt-1,tunnel-url-pinggy-attempt-1"

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

RUN_ID="${ARG_RUN_ID:-}"
ARTIFACT_NAMES="${ARG_ARTIFACT_NAME:-tunnel-url-attempt-1,tunnel-url-pinggy-attempt-1}"
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

# Check if any artifact exists via GitHub API
# Supports comma-separated names — returns 0 if ANY match is found
# Artifact names include attempt suffix, so stale artifacts are naturally excluded
artifact_exists() {
    local artifacts
    artifacts=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/artifacts?per_page=100" \
        --jq '.artifacts[].name' 2>/dev/null || echo "")

    IFS=',' read -ra NAMES <<<"$ARTIFACT_NAMES"
    for name in "${NAMES[@]}"; do
        name="$(echo "$name" | xargs)" # trim whitespace
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
