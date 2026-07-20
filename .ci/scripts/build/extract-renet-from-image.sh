#!/bin/bash
# Extract renet binaries from existing Docker renet image
# Used when skipping full renet build (renet_exists=true)
#
# Usage: extract-renet-from-image.sh --tag TAG --output DIR
#   --tag TAG       Renet image tag to extract from (required)
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
RENET_IMAGE="${REGISTRY}/renet:${TAG}"

log_step "Extracting renet binaries from $RENET_IMAGE"

mkdir -p "$OUTPUT_DIR"

# Create a temporary container to extract files
log_info "Creating temporary container..."
CONTAINER_ID=$(docker create "$RENET_IMAGE")

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

# Embed the assets (all eight Linux binaries deployed INTO VMs — needed on every
# host, Linux KVM or macOS QEMU) and stage the proxy compose by DELEGATING to
# renet's build.sh, the single source of truth for the per-arch assets/<arch>/
# layout the go:embed directives read (pkg/embed/embed_assets_{amd64,arm64}.go).
# This image is the same full renet image build.sh itself builds, so retag it to
# the name embed_assets looks for and let it extract from it.
#
# Re-implementing the extraction here is exactly what silently shipped assetless
# darwin/windows binaries: this script predated the per-arch split and kept
# writing a FLAT assets/ dir (only criu/rsync/rclone) that the per-arch embeds no
# longer read, so the cross-compiled darwin/windows renet embedded nothing and
# `ops up` failed with "embedded assets missing". Delegating keeps the two paths
# from drifting again. (embed_proxy stages only the proxy compose; the datastore
# README is a tracked embed file and must NOT be overwritten — see build.sh.)
log_step "Embedding assets via renet build.sh (single source of truth)..."
docker tag "$RENET_IMAGE" rediacc/renet:latest
pushd "$REPO_ROOT/private/renet" >/dev/null
./build.sh embed_assets --force
./build.sh embed_proxy
popd >/dev/null

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
