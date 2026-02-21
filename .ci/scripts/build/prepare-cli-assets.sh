#!/bin/bash
# Prepare renet binaries and metadata for CLI SEA embedding
#
# Copies only the renet binaries needed for the target platform to the CLI
# assets directory and generates a metadata file + platform-specific sea-config.
#
# All platforms get Linux binaries (for remote provisioning to Linux machines).
# macOS additionally gets its own platform binary (for local renet execution).
#
# Usage:
#   prepare-cli-assets.sh --platform linux --arch x64
#   prepare-cli-assets.sh --platform mac --arch arm64
#
# Options:
#   --platform PLATFORM  Target platform: linux, mac, win (required)
#   --arch ARCH          Target architecture: x64, arm64 (required)
#
# Environment:
#   RENET_VERSION - Override version (default: from package.json)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
SEA_PLATFORM=""
SEA_ARCH=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform) SEA_PLATFORM="$2"; shift 2 ;;
        --arch)     SEA_ARCH="$2";     shift 2 ;;
        -h | --help)
            echo "Usage: $0 --platform <linux|mac|win> --arch <x64|arm64>"
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

if [[ -z "$SEA_PLATFORM" ]] || [[ -z "$SEA_ARCH" ]]; then
    log_error "Usage: $0 --platform <linux|mac|win> --arch <x64|arm64>"
    exit 1
fi

REPO_ROOT="$(get_repo_root)"
CLI_DIR="$REPO_ROOT/packages/cli"
CLI_ASSETS_DIR="$CLI_DIR/dist/assets"
RENET_BIN_DIR="$REPO_ROOT/private/bin"

# Map CI naming to renet naming
# CI: x64/arm64 -> Renet: amd64/arm64
map_arch() {
    case "$1" in
        x64)   echo "amd64" ;;
        arm64) echo "arm64" ;;
        *)     log_error "Unknown arch: $1"; exit 1 ;;
    esac
}

# Compute the list of required renet binaries for this platform.
# All platforms need both Linux binaries for remote provisioning.
# macOS additionally needs its own platform binary for local execution.
get_required_binaries() {
    local platform="$1"
    local arch="$2"
    local renet_arch
    renet_arch=$(map_arch "$arch")

    echo "linux-amd64"
    echo "linux-arm64"

    if [[ "$platform" == "mac" ]]; then
        echo "darwin-${renet_arch}"
    fi
}

# Map binary name to metadata key (preserves existing scheme)
# linux-amd64 -> "amd64", linux-arm64 -> "arm64"
# darwin-amd64 -> "darwin-amd64", darwin-arm64 -> "darwin-arm64"
binary_to_meta_key() {
    if [[ "$1" == linux-* ]]; then
        echo "${1#linux-}"
    else
        echo "$1"
    fi
}

log_step "Preparing CLI embedded assets for $SEA_PLATFORM-$SEA_ARCH..."

# Create assets directory
mkdir -p "$CLI_ASSETS_DIR"

# Get list of required binaries
REQUIRED_BINARIES=$(get_required_binaries "$SEA_PLATFORM" "$SEA_ARCH")

# Copy only required renet binaries
for binary_name in $REQUIRED_BINARIES; do
    BINARY="$RENET_BIN_DIR/renet-$binary_name"
    if [[ -f "$BINARY" ]]; then
        log_info "Copying renet-$binary_name..."
        cp "$BINARY" "$CLI_ASSETS_DIR/"
    else
        log_error "Missing renet binary: $BINARY"
        exit 1
    fi
done

# Get version (from env or package.json)
# Use jq instead of node to avoid MSYS path translation issues on Windows
VERSION="${RENET_VERSION:-$(jq -r '.version' "$CLI_DIR/package.json")}"

# Generate metadata with SHA256 hashes
log_step "Generating renet metadata..."

# Helper: compute file size (cross-platform)
file_size() {
    stat -c%s "$1" 2>/dev/null || stat -f%z "$1"
}

# Helper: compute SHA256 (cross-platform)
file_sha256() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum &>/dev/null; then
        shasum -a 256 "$1" | cut -d' ' -f1
    else
        log_error "No sha256sum or shasum available"
        exit 1
    fi
}

# Build metadata JSON dynamically for included binaries only
BINARIES_JSON="{}"
for binary_name in $REQUIRED_BINARIES; do
    local_file="$CLI_ASSETS_DIR/renet-$binary_name"
    size=$(file_size "$local_file")
    sha256=$(file_sha256 "$local_file")
    meta_key=$(binary_to_meta_key "$binary_name")

    BINARIES_JSON=$(echo "$BINARIES_JSON" | jq \
        --arg key "$meta_key" \
        --argjson size "$size" \
        --arg sha256 "$sha256" \
        '.[$key] = { size: $size, sha256: $sha256 }')

    log_info "  $binary_name: $size bytes, sha256=$sha256"
done

jq -n \
    --arg version "$VERSION" \
    --arg generatedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --argjson binaries "$BINARIES_JSON" \
    '{ version: $version, generatedAt: $generatedAt, binaries: $binaries }' \
    >"$CLI_ASSETS_DIR/renet-metadata.json"

log_info "Metadata written to $CLI_ASSETS_DIR/renet-metadata.json"
log_info "  Version: $VERSION"

# Generate platform-specific sea-config.json
log_step "Generating platform-specific sea-config..."

ASSETS_JSON='{ "renet-metadata.json": "dist/assets/renet-metadata.json" }'
for binary_name in $REQUIRED_BINARIES; do
    ASSETS_JSON=$(echo "$ASSETS_JSON" | jq \
        --arg key "renet-$binary_name" \
        --arg path "dist/assets/renet-$binary_name" \
        '.[$key] = $path')
done

jq -n \
    --arg main "dist/cli-bundle.cjs" \
    --arg output "dist/sea-prep.blob" \
    --argjson assets "$ASSETS_JSON" \
    '{
      main: $main,
      output: $output,
      disableExperimentalSEAWarning: true,
      useSnapshot: false,
      useCodeCache: false,
      assets: $assets
    }' >"$CLI_DIR/sea-config.generated.json"

log_info "Generated sea-config with $(echo "$ASSETS_JSON" | jq 'length') assets"

log_info "CLI assets prepared successfully"
