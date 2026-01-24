#!/bin/bash
# Generate CLI update manifest.json from built binaries and their checksums.
#
# Usage:
#   generate-cli-manifest.sh --version 0.4.42 --input dist/cli/ --output dist/cli/manifest.json
#   generate-cli-manifest.sh --version 0.4.42 --input dist/cli/ --repo rediacc/console
#
# Options:
#   --version VERSION    Release version (required)
#   --input DIR          Directory containing binaries and .sha256 files (default: dist/cli/)
#   --output PATH        Output manifest path (default: <input>/manifest.json)
#   --repo REPO          GitHub repository for download URLs (default: rediacc/console)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

VERSION=""
INPUT_DIR=""
OUTPUT_PATH=""
REPO="rediacc/console"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --input)
            INPUT_DIR="$2"
            shift 2
            ;;
        --output)
            OUTPUT_PATH="$2"
            shift 2
            ;;
        --repo)
            REPO="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 --version VERSION [--input DIR] [--output PATH] [--repo REPO]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    log_error "--version is required"
    exit 1
fi

REPO_ROOT="$(get_repo_root)"
if [[ -z "$INPUT_DIR" ]]; then
    INPUT_DIR="$REPO_ROOT/dist/cli"
fi
if [[ -z "$OUTPUT_PATH" ]]; then
    OUTPUT_PATH="$INPUT_DIR/manifest.json"
fi

RELEASE_URL="https://github.com/$REPO/releases/tag/v$VERSION"
DOWNLOAD_BASE="https://github.com/$REPO/releases/download/v$VERSION"
RELEASE_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

log_step "Generating CLI manifest v$VERSION"
log_info "  Input: $INPUT_DIR"
log_info "  Output: $OUTPUT_PATH"

# Require jq for reliable JSON construction
if ! command -v jq &>/dev/null; then
    log_error "jq is required for manifest generation"
    exit 1
fi

# Build manifest using jq for safe JSON construction
MANIFEST=$(jq -n \
    --arg version "$VERSION" \
    --arg releaseDate "$RELEASE_DATE" \
    --arg releaseNotesUrl "$RELEASE_URL" \
    '{version: $version, releaseDate: $releaseDate, releaseNotesUrl: $releaseNotesUrl, binaries: {}}')

for PLATFORM in linux mac win; do
    for ARCH in x64 arm64; do
        BINARY_NAME="rdc-${PLATFORM}-${ARCH}"
        if [[ "$PLATFORM" == "win" ]]; then
            BINARY_NAME="${BINARY_NAME}.exe"
        fi

        CHECKSUM_FILE="$INPUT_DIR/${BINARY_NAME}.sha256"
        if [[ ! -f "$CHECKSUM_FILE" ]]; then
            log_info "  Skipping $PLATFORM-$ARCH (no checksum file)"
            continue
        fi

        # Extract just the hash from the checksum file (format: "hash  filename")
        SHA256="$(awk '{print $1}' "$CHECKSUM_FILE")"
        if [[ -z "$SHA256" || ${#SHA256} -ne 64 ]]; then
            log_warn "  Invalid checksum for $BINARY_NAME, skipping"
            continue
        fi

        URL="$DOWNLOAD_BASE/$BINARY_NAME"
        KEY="${PLATFORM}-${ARCH}"

        MANIFEST=$(echo "$MANIFEST" | jq \
            --arg key "$KEY" \
            --arg url "$URL" \
            --arg sha256 "$SHA256" \
            '.binaries[$key] = {url: $url, sha256: $sha256}')

        log_info "  Added $KEY: ${SHA256:0:16}..."
    done
done

# Write pretty-printed manifest
echo "$MANIFEST" | jq . > "$OUTPUT_PATH"

log_info "Manifest generated: $OUTPUT_PATH"
