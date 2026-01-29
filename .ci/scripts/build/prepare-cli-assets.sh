#!/bin/bash
# Prepare renet binaries and metadata for CLI SEA embedding
#
# This script copies renet Linux binaries to the CLI assets directory
# and generates a metadata file with SHA256 hashes for verification.
#
# Usage:
#   prepare-cli-assets.sh
#
# Environment:
#   RENET_VERSION - Override version (default: from package.json)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
CLI_ASSETS_DIR="$REPO_ROOT/packages/cli/dist/assets"
RENET_BIN_DIR="$REPO_ROOT/private/bin"

log_step "Preparing CLI embedded assets..."

# Create assets directory
mkdir -p "$CLI_ASSETS_DIR"

# Copy renet binaries
for arch in amd64 arm64; do
    BINARY="$RENET_BIN_DIR/renet-linux-$arch"
    if [[ -f "$BINARY" ]]; then
        log_info "Copying renet-linux-$arch..."
        cp "$BINARY" "$CLI_ASSETS_DIR/"
    else
        log_error "Missing renet binary: $BINARY"
        exit 1
    fi
done

# Get version (from env or package.json)
# Use jq instead of node to avoid MSYS path translation issues on Windows
VERSION="${RENET_VERSION:-$(jq -r '.version' "$REPO_ROOT/packages/cli/package.json")}"

# Generate metadata with SHA256 hashes
log_step "Generating renet metadata..."

AMD64_SIZE=$(stat -c%s "$CLI_ASSETS_DIR/renet-linux-amd64" 2>/dev/null || stat -f%z "$CLI_ASSETS_DIR/renet-linux-amd64")
ARM64_SIZE=$(stat -c%s "$CLI_ASSETS_DIR/renet-linux-arm64" 2>/dev/null || stat -f%z "$CLI_ASSETS_DIR/renet-linux-arm64")

# Compute SHA256 (handle both Linux sha256sum and macOS shasum)
if command -v sha256sum &>/dev/null; then
    AMD64_SHA256=$(sha256sum "$CLI_ASSETS_DIR/renet-linux-amd64" | cut -d' ' -f1)
    ARM64_SHA256=$(sha256sum "$CLI_ASSETS_DIR/renet-linux-arm64" | cut -d' ' -f1)
elif command -v shasum &>/dev/null; then
    AMD64_SHA256=$(shasum -a 256 "$CLI_ASSETS_DIR/renet-linux-amd64" | cut -d' ' -f1)
    ARM64_SHA256=$(shasum -a 256 "$CLI_ASSETS_DIR/renet-linux-arm64" | cut -d' ' -f1)
else
    log_error "No sha256sum or shasum available"
    exit 1
fi

jq -n \
  --arg version "$VERSION" \
  --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson amd64Size "$AMD64_SIZE" \
  --arg amd64Sha256 "$AMD64_SHA256" \
  --argjson arm64Size "$ARM64_SIZE" \
  --arg arm64Sha256 "$ARM64_SHA256" \
  '{
    version: $version,
    generatedAt: $generatedAt,
    binaries: {
      amd64: { size: $amd64Size, sha256: $amd64Sha256 },
      arm64: { size: $arm64Size, sha256: $arm64Sha256 }
    }
  }' > "$CLI_ASSETS_DIR/renet-metadata.json"

log_info "Metadata written to $CLI_ASSETS_DIR/renet-metadata.json"
log_info "  Version: $VERSION"
log_info "  amd64: $AMD64_SIZE bytes, sha256=$AMD64_SHA256"
log_info "  arm64: $ARM64_SIZE bytes, sha256=$ARM64_SHA256"

log_info "CLI assets prepared successfully"
