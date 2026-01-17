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

# Simple argument parsing (portable, no bash 4+ features)
RUN_ID=""
ARTIFACT_NAME="tunnel-url"
MAX_WAIT="1500"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --run-id)
            RUN_ID="$2"
            shift 2
            ;;
        --artifact-name)
            ARTIFACT_NAME="$2"
            shift 2
            ;;
        --max-wait)
            MAX_WAIT="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Debug: show what we got
log_step "Arguments: RUN_ID=$RUN_ID, ARTIFACT_NAME=$ARTIFACT_NAME, MAX_WAIT=$MAX_WAIT" >&2

# Validate required arguments
if [[ -z "$RUN_ID" ]]; then
    log_error "Usage: download-url.sh --run-id <run_id> [--artifact-name <name>] [--max-wait <seconds>]"
    exit 1
fi

# Require gh CLI
require_cmd gh

log_step "Downloading tunnel URL artifact (run: $RUN_ID, artifact: $ARTIFACT_NAME)..." >&2

ELAPSED=0
INTERVAL=10

# Create temp directory for download
DOWNLOAD_DIR="$(mktemp -d)"
trap 'rm -rf "$DOWNLOAD_DIR"' EXIT

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    # Try to download the artifact
    # Use -D to specify download directory, suppress errors if artifact not yet available
    if gh run download "$RUN_ID" -n "$ARTIFACT_NAME" -D "$DOWNLOAD_DIR" 2>/dev/null; then
        # Check all possible locations for the file
        TUNNEL_FILE=""
        if [[ -f "$DOWNLOAD_DIR/tunnel-url.txt" ]]; then
            TUNNEL_FILE="$DOWNLOAD_DIR/tunnel-url.txt"
        elif [[ -f "$DOWNLOAD_DIR/$ARTIFACT_NAME/tunnel-url.txt" ]]; then
            TUNNEL_FILE="$DOWNLOAD_DIR/$ARTIFACT_NAME/tunnel-url.txt"
        else
            # Find any tunnel-url.txt
            TUNNEL_FILE=$(find "$DOWNLOAD_DIR" -name "tunnel-url.txt" -type f 2>/dev/null | head -1)
        fi

        if [[ -n "$TUNNEL_FILE" ]] && [[ -f "$TUNNEL_FILE" ]]; then
            TUNNEL_URL="$(cat "$TUNNEL_FILE" | tr -d '\n\r')"
            if [[ -n "$TUNNEL_URL" ]]; then
                log_info "Downloaded tunnel URL: $TUNNEL_URL" >&2
                echo "$TUNNEL_URL"
                exit 0
            fi
        fi

        # Debug: show what's in the download dir if file not found
        log_warn "Artifact downloaded but tunnel-url.txt not found. Contents:" >&2
        find "$DOWNLOAD_DIR" -type f >&2 || true
    fi

    log_warn "Waiting for tunnel URL... (${ELAPSED}s / ${MAX_WAIT}s)" >&2
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

log_error "Failed to download tunnel URL after ${MAX_WAIT}s"
exit 1
