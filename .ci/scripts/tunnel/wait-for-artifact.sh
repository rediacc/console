#!/bin/bash
# Wait for tunnel-url artifact to exist (API check only, no download)
# Usage: wait-for-artifact.sh --run-id <run_id> [--artifact-name <name>] [--timeout <seconds>]
#
# Polls GitHub Actions API to check if artifact exists.
# Used as a gateway job so test jobs don't poll independently.
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
ARTIFACT_NAME="${ARG_ARTIFACT_NAME:-tunnel-url}"
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

log_step "Waiting for artifact '$ARTIFACT_NAME' (run: $RUN_ID, timeout: ${TIMEOUT}s)..."

# Check if artifact exists via GitHub API
artifact_exists() {
    local artifacts
    artifacts=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/artifacts" \
        --jq '.artifacts[].name' 2>/dev/null || echo "")

    if echo "$artifacts" | grep -q "^${ARTIFACT_NAME}$"; then
        return 0
    fi
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
    log_info "Artifact '$ARTIFACT_NAME' is available!"
    exit 0
fi

# Timeout reached
log_error "Timeout: artifact '$ARTIFACT_NAME' not found after ${TIMEOUT}s"
exit 1
