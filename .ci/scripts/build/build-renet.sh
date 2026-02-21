#!/bin/bash
# Build full renet binaries with embedded CRIU/rsync assets
#
# Usage:
#   build-renet.sh --version 1.2.3 --output ./bin
#   build-renet.sh --version 1.2.3 --assets-dir ./assets --output ./bin
#
# Options:
#   --version VERSION    Version to embed in binary (required)
#   --assets-dir DIR     Directory containing CRIU/rsync binaries (default: auto-detect)
#   --output DIR         Output directory for renet binaries (default: private/bin)
#   --skip-embed         Build without embedded assets (lightweight, for testing)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
VERSION=""
ASSETS_DIR=""
OUTPUT_DIR=""
SKIP_EMBED=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --assets-dir)
            ASSETS_DIR="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --skip-embed)
            SKIP_EMBED=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --version VERSION [--assets-dir DIR] [--output DIR] [--skip-embed]"
            echo ""
            echo "Build full renet binaries with embedded CRIU/rsync assets"
            echo ""
            echo "Options:"
            echo "  --version VERSION    Version to embed in binary (required)"
            echo "  --assets-dir DIR     Directory containing CRIU/rsync binaries"
            echo "  --output DIR         Output directory for renet binaries"
            echo "  --skip-embed         Build without embedded assets"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

[[ -z "$VERSION" ]] && {
    log_error "--version is required"
    exit 1
}

REPO_ROOT="$(get_repo_root)"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/private/bin}"
RENET_DIR="$REPO_ROOT/private/renet"

# Convert to absolute path (handles relative paths, symlinks, and ..)
OUTPUT_DIR="$(readlink -f "$OUTPUT_DIR")"

mkdir -p "$OUTPUT_DIR"

log_step "Building renet binaries (release)"
log_info "  Version: $VERSION"
log_info "  Output: $OUTPUT_DIR"

# Embed assets if not skipped
if [[ "$SKIP_EMBED" != "true" ]]; then
    log_step "Preparing embedded assets..."

    ASSETS_DIR="${ASSETS_DIR:-$REPO_ROOT/binaries}"

    # Convert to absolute path (handles relative paths, symlinks, and ..)
    ASSETS_DIR="$(readlink -f "$ASSETS_DIR")"

    EMBED_DIR="$RENET_DIR/pkg/embed/assets"
    mkdir -p "$EMBED_DIR"

    for asset in criu-linux-amd64 criu-linux-arm64 rsync-linux-amd64 rsync-linux-arm64; do
        if [[ -f "$ASSETS_DIR/$asset" ]]; then
            log_info "Embedding $asset..."
            gzip -c "$ASSETS_DIR/$asset" >"$EMBED_DIR/$asset.gz"
        else
            log_error "Missing asset: $ASSETS_DIR/$asset"
            exit 1
        fi
    done

    log_info "Embedded assets:"
    ls -la "$EMBED_DIR"
else
    log_info "Skipping asset embedding (--skip-embed)"
fi

# Build renet binaries (release mode: stripped)
log_step "Building renet binaries (release)..."

require_cmd go

cd "$RENET_DIR"

for os in linux darwin; do
    for arch in amd64 arm64; do
        log_info "Building renet-$os-$arch..."
        CGO_ENABLED=0 GOOS=$os GOARCH=$arch go build \
            -ldflags="-s -w -X main.Version=$VERSION" \
            -o "$OUTPUT_DIR/renet-$os-$arch" ./cmd/renet
    done
done

# Generate checksums
log_step "Generating checksums..."
cd "$OUTPUT_DIR"
sha256sum renet-* >checksums.sha256

log_info "Renet binaries built successfully:"
ls -la "$OUTPUT_DIR"/renet-*
cat "$OUTPUT_DIR/checksums.sha256"

# Verify release build (no debug info)
log_step "Verifying release builds..."
for os in linux darwin; do
    for arch in amd64 arm64; do
        binary="$OUTPUT_DIR/renet-$os-$arch"
        if file "$binary" | grep -q "stripped\|Mach-O"; then
            log_info "renet-$os-$arch: release build"
        else
            log_warn "renet-$os-$arch: may contain debug symbols"
        fi
    done
done
