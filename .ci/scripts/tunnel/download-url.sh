#!/bin/bash
# Download tunnel URL artifact with retry logic
# Usage: download-url.sh --run-id <run_id> [--artifact-name <name>] [--max-wait <seconds>]
#
# Downloads the latest artifact (by creation time) matching the given name.
# On retry attempts, stale artifacts from previous attempts may coexist with
# fresh ones; this script always picks the most recently created artifact.
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
MAX_WAIT="120"  # Gateway job guarantees artifact exists; this is a safety buffer

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

# Require gh CLI and GITHUB_REPOSITORY env var (default in GitHub Actions)
require_cmd gh
require_var GITHUB_REPOSITORY

log_step "Downloading tunnel URL artifact (run: $RUN_ID, artifact: $ARTIFACT_NAME)..." >&2

ELAPSED=0
INTERVAL=10

# Create temp directory for download
DOWNLOAD_DIR="$(mktemp -d)"
trap 'rm -rf "$DOWNLOAD_DIR"' EXIT

while [[ $ELAPSED -lt $MAX_WAIT ]]; do
    # Use the GitHub API to find the latest artifact by creation time.
    # This avoids downloading stale artifacts from previous retry attempts.
    ARTIFACT_ID=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/artifacts" \
        --jq "[.artifacts[] | select(.name == \"$ARTIFACT_NAME\")] | sort_by(.created_at) | last | .id // empty" 2>/dev/null || echo "")

    if [[ -n "$ARTIFACT_ID" ]]; then
        # Download the specific artifact by ID using the zip endpoint
        rm -rf "${DOWNLOAD_DIR:?}"/*
        if gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/${ARTIFACT_ID}/zip" > "$DOWNLOAD_DIR/artifact.zip" 2>/dev/null; then
            # Extract the zip
            if command -v unzip &>/dev/null; then
                unzip -o -q "$DOWNLOAD_DIR/artifact.zip" -d "$DOWNLOAD_DIR/extracted" 2>/dev/null || true
            else
                python3 -c "
import zipfile, sys
z = zipfile.ZipFile('$DOWNLOAD_DIR/artifact.zip')
z.extractall('$DOWNLOAD_DIR/extracted')
" 2>/dev/null || true
            fi

            # Find the tunnel URL file
            TUNNEL_FILE=""
            if [[ -f "$DOWNLOAD_DIR/extracted/tunnel-url.txt" ]]; then
                TUNNEL_FILE="$DOWNLOAD_DIR/extracted/tunnel-url.txt"
            else
                TUNNEL_FILE=$(find "$DOWNLOAD_DIR/extracted" -name "tunnel-url.txt" -type f 2>/dev/null | head -1)
            fi

            if [[ -n "$TUNNEL_FILE" ]] && [[ -f "$TUNNEL_FILE" ]]; then
                TUNNEL_URL="$(tr -d '\n\r' < "$TUNNEL_FILE")"
                if [[ -n "$TUNNEL_URL" ]]; then
                    log_info "Downloaded tunnel URL: $TUNNEL_URL (artifact ID: $ARTIFACT_ID)" >&2
                    echo "$TUNNEL_URL"
                    exit 0
                fi
            fi

            # Debug: show what's in the extracted dir if file not found
            log_warn "Artifact extracted but tunnel-url.txt not found. Contents:" >&2
            find "$DOWNLOAD_DIR/extracted" -type f >&2 || true
        else
            log_warn "Failed to download artifact ID $ARTIFACT_ID" >&2
        fi
    fi

    log_warn "Waiting for tunnel URL... (${ELAPSED}s / ${MAX_WAIT}s)" >&2
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
done

log_error "Failed to download tunnel URL after ${MAX_WAIT}s"
exit 1
