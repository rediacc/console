#!/bin/bash
# Extract renet binaries from existing Docker bridge image
# Used when skipping full renet build (bridge_exists=true)
#
# Usage: extract-renet-from-image.sh --tag TAG --output DIR
#   --tag TAG       Bridge image tag to extract from (required)
#   --output DIR    Output directory for binaries (default: private/bin)
#   --registry REG  Docker registry (default: ghcr.io/rediacc/elite)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
TAG=""
OUTPUT_DIR=""
REGISTRY="ghcr.io/rediacc/elite"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag)
            TAG="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --registry)
            REGISTRY="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validation
if [[ -z "$TAG" ]]; then
    log_error "--tag is required"
    exit 1
fi

REPO_ROOT="$(get_repo_root)"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/private/bin}"
BRIDGE_IMAGE="${REGISTRY}/bridge:${TAG}"

log_step "Extracting renet binaries from $BRIDGE_IMAGE"

mkdir -p "$OUTPUT_DIR"

# Create a temporary container to extract files
log_info "Creating temporary container..."
CONTAINER_ID=$(docker create "$BRIDGE_IMAGE")

cleanup() {
    if [[ -n "${CONTAINER_ID:-}" ]]; then
        docker rm "$CONTAINER_ID" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# Extract renet binaries from /opt/renet/
log_info "Extracting renet-linux-amd64..."
docker cp "$CONTAINER_ID:/opt/renet/renet-linux-amd64" "$OUTPUT_DIR/"

log_info "Extracting renet-linux-arm64..."
docker cp "$CONTAINER_ID:/opt/renet/renet-linux-arm64" "$OUTPUT_DIR/"

# Resolve OUTPUT_DIR to absolute path before changing directories
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"

# Extract embedded assets (CRIU/rsync/rclone) from the bridge container.
# These are Linux binaries deployed INTO VMs during provisioning — needed
# regardless of host platform (Linux KVM or macOS QEMU).
log_step "Extracting embedded assets from container..."
EMBED_DIR="$REPO_ROOT/private/renet/pkg/embed/assets"
mkdir -p "$EMBED_DIR"

for tool in criu rsync rclone; do
    for arch in amd64 arm64; do
        asset="$tool-linux-$arch"
        log_info "Extracting $asset..."
        docker cp "$CONTAINER_ID:/opt/$tool/$asset" "$EMBED_DIR/" 2>/dev/null || {
            log_error "Failed to extract $asset from container"
            exit 1
        }
    done
done

log_info "Compressing assets..."
for f in "$EMBED_DIR"/*-linux-*; do
    [ -f "$f" ] && [ "${f##*.}" != "gz" ] && gzip -f "$f"
done

log_info "Embedded assets:"
ls -la "$EMBED_DIR"/*.gz

# Stage proxy and datastore docs for go:embed
log_step "Staging proxy/datastore for embedding..."
cp "$REPO_ROOT/private/renet/proxy/docker-compose.yml" "$REPO_ROOT/private/renet/pkg/embed/proxy/"
cp "$REPO_ROOT/private/renet/docs/datastore/README.md" "$REPO_ROOT/private/renet/pkg/embed/datastore/"

# Cross-compile Darwin binaries (with embedded assets for VM provisioning)
log_step "Cross-compiling renet Darwin binaries..."
pushd "$REPO_ROOT/private/renet" >/dev/null
for arch in amd64 arm64; do
    log_info "Building renet-darwin-$arch..."
    CGO_ENABLED=0 GOOS=darwin GOARCH=$arch go build \
        -ldflags="-s -w" \
        -o "$OUTPUT_DIR/renet-darwin-$arch" \
        ./cmd/renet
done
popd >/dev/null

# Cross-compile Windows binaries (Hyper-V backend)
log_step "Cross-compiling renet Windows binaries..."
pushd "$REPO_ROOT/private/renet" >/dev/null
for arch in amd64 arm64; do
    log_info "Building renet-windows-$arch..."
    CGO_ENABLED=0 GOOS=windows GOARCH=$arch go build \
        -ldflags="-s -w" \
        -o "$OUTPUT_DIR/renet-windows-$arch.exe" \
        ./cmd/renet
done
popd >/dev/null

log_step "Generating checksums..."
cd "$OUTPUT_DIR"
sha256sum renet-* >checksums.sha256

log_info "Renet binaries ready:"
ls -la renet-*
cat checksums.sha256
