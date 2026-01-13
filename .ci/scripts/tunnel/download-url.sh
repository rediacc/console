#!/bin/bash
# Download tunnel URL artifact with retry logic
# Usage: download-url.sh --run-id <run_id> [--artifact-name <name>] [--max-wait <seconds>]
#
# Outputs the tunnel URL to stdout on success.
# Requires: GH_TOKEN environment variable (or gh auth login)
#
# Example:
#   TUNNEL_URL=$(.ci/scripts/tunnel/download-url.sh --run-id 12345)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

RUN_ID="${ARG_RUN_ID:-}"
ARTIFACT_NAME="${ARG_ARTIFACT_NAME:-tunnel-url}"
MAX_WAIT="${ARG_MAX_WAIT:-1500}"  # 25 minutes default

# Validate required arguments
if [[ -z "$RUN_ID" ]]; then
    log_error "Usage: download-url.sh --run-id <run_id> [--artifact-name <name>] [--max-wait <seconds>]"
    exit 1
fi

# Require gh CLI
require_cmd gh

log_step "Downloading tunnel URL artifact (run: $RUN_ID, artifact: $ARTIFACT_NAME)..."

ELAPSED=0
INTERVAL=10

# Create temp directory for download
DOWNLOAD_DIR="$(mktemp -d)"
trap "rm -rf $DOWNLOAD_DIR" EXIT

cd "$DOWNLOAD_DIR"

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    # Try to download the artifact
    if gh run download "$RUN_ID" -n "$ARTIFACT_NAME" 2>/dev/null; then
        # Check if file exists
        if [[ -f "tunnel-url.txt" ]]; then
            TUNNEL_URL="$(cat tunnel-url.txt | tr -d '\n\r')"
            if [[ -n "$TUNNEL_URL" ]]; then
                log_info "Downloaded tunnel URL" >&2
                echo "$TUNNEL_URL"
                exit 0
            fi
        fi
    fi

    log_warn "Waiting for tunnel URL... (${ELAPSED}s / ${MAX_WAIT}s)" >&2
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

log_error "Failed to download tunnel URL after ${MAX_WAIT}s"
exit 1
