#!/bin/bash
# Download and inject tutorial recordings into a pages directory
#
# Downloads tutorial-recordings artifacts and extracts .cast files into the
# target directory so the documentation site shows recorded terminal sessions
# in the interactive player instead of empty placeholders.
#
# Modes:
#   Same-run:     --run-id <id> --artifact-name <name>  (CI deploy-preview)
#   Cross-run:    --search-latest                        (CD production deploy)
#
# Usage:
#   # PR preview (same workflow run):
#   .ci/scripts/docs/inject-tutorials.sh \
#     --run-id "$GITHUB_RUN_ID" \
#     --artifact-name "tutorial-recordings-abc123" \
#     --output dist/pages/assets/tutorials/
#
#   # Production (find latest from any CI run):
#   .ci/scripts/docs/inject-tutorials.sh \
#     --search-latest \
#     --output dist/pages/assets/tutorials/
#
# Environment:
#   GH_TOKEN            - GitHub token for API access
#   GITHUB_REPOSITORY   - owner/repo (set automatically in GitHub Actions)
#
# Exit codes:
#   0 - Tutorials injected successfully
#   1 - No tutorials found or download failed

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
RUN_ID=""
ARTIFACT_NAME=""
OUTPUT_DIR=""
SEARCH_LATEST="false"

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
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --search-latest)
            SEARCH_LATEST="true"
            shift
            ;;
        *) shift ;;
    esac
done

# Validate
if [[ -z "$OUTPUT_DIR" ]]; then
    log_error "Usage: inject-tutorials.sh --output <dir> [--run-id <id> --artifact-name <name>] [--search-latest]"
    exit 1
fi

require_cmd gh
require_var GITHUB_REPOSITORY

# ---------------------------------------------------------------------------
# Find the artifact
# ---------------------------------------------------------------------------
ARTIFACT_ID=""

if [[ -n "$RUN_ID" && -n "$ARTIFACT_NAME" ]]; then
    # Mode 1: Same workflow run — look for a specific artifact by name
    log_step "Looking for artifact '$ARTIFACT_NAME' in run $RUN_ID..."
    ARTIFACT_ID=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}/artifacts?per_page=100" \
        --jq "[.artifacts[] | select(.name == \"$ARTIFACT_NAME\")] | sort_by(.created_at) | last | .id // empty" 2>/dev/null || echo "")

elif [[ "$SEARCH_LATEST" == "true" ]]; then
    # Mode 2: Cross-workflow — find the most recent tutorial-recordings artifact
    log_step "Searching for latest tutorial-recordings artifact..."
    ARTIFACT_ID=$(gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts?per_page=30" \
        --jq '[.artifacts[] | select(.name | startswith("tutorial-recordings-")) | select(.expired == false)] | sort_by(.created_at) | last | .id // empty' 2>/dev/null || echo "")
else
    log_error "Must specify either --run-id + --artifact-name, or --search-latest"
    exit 1
fi

if [[ -z "$ARTIFACT_ID" ]]; then
    log_warn "No tutorial recording artifact found — placeholders will be shown on the docs site"
    exit 1
fi

log_info "Found artifact ID: $ARTIFACT_ID"

# ---------------------------------------------------------------------------
# Download and extract
# ---------------------------------------------------------------------------
DOWNLOAD_DIR="$(mktemp -d)"
trap 'rm -rf "$DOWNLOAD_DIR"' EXIT

log_step "Downloading artifact..."
if ! gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/${ARTIFACT_ID}/zip" >"$DOWNLOAD_DIR/artifact.zip" 2>/dev/null; then
    log_error "Failed to download artifact $ARTIFACT_ID"
    exit 1
fi

log_step "Extracting tutorials..."
if command -v unzip &>/dev/null; then
    unzip -o -q "$DOWNLOAD_DIR/artifact.zip" -d "$DOWNLOAD_DIR/extracted"
else
    python3 -c "
import zipfile
z = zipfile.ZipFile('$DOWNLOAD_DIR/artifact.zip')
z.extractall('$DOWNLOAD_DIR/extracted')
"
fi

# Count .cast files
CAST_COUNT=$(find "$DOWNLOAD_DIR/extracted" -name "*.cast" -type f 2>/dev/null | wc -l)

if [[ "$CAST_COUNT" -eq 0 ]]; then
    log_warn "Artifact contained no .cast files"
    exit 1
fi

# Copy to output directory
mkdir -p "$OUTPUT_DIR"
find "$DOWNLOAD_DIR/extracted" -name "*.cast" -type f -exec cp {} "$OUTPUT_DIR/" \;

log_info "Injected $CAST_COUNT tutorial(s) into $OUTPUT_DIR"
