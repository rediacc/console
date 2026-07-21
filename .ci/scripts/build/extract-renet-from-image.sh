#!/bin/bash
# Extract renet binaries from existing Docker renet image
# Used when skipping full renet build (renet_exists=true)
#
# Usage: extract-renet-from-image.sh --tag TAG --output DIR
#   --tag TAG       Renet image tag to extract from (required)
#   --output DIR    Output directory for binaries (default: private/bin)
#   --registry REG  Docker registry (default: ghcr.io/rediacc)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
TAG=""
OUTPUT_DIR=""
REGISTRY="ghcr.io/rediacc"

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

# Stage the embedded Linux assets into the PER-ARCH layout the go:embed
# directives read (pkg/embed/embed_assets_{amd64,arm64}.go -> assets/<arch>/), so
# the cross-compiled darwin/windows renet actually carries them. Writing a FLAT
# assets/ dir here — the pre-per-arch behavior this script never got updated from
# — is what silently shipped assetless darwin/windows binaries: the per-arch
# embeds found nothing, so `ops up` failed with "embedded assets missing".
#
# Best-effort per asset, on purpose. This is the CACHED fast-path: it reuses an
# already-built renet image that may predate an asset (an older image has no
# /opt/zot or /opt/k3s). criu/rsync/rclone are the floor for basic provisioning
# and are required; the cluster assets (zot/k3s + CSI sidecars) are embedded when
# the reused image has them. The authoritative, complete asset set is guaranteed
# by the full 'Renet (Full)' build (build.sh embed_assets, which hard-requires
# them) — we deliberately do NOT delegate to it here, because its strictness
# would fail this path on a legitimately older cached image.
log_step "Staging embedded assets (per-arch, per-class) from container..."
EMBED_DIR="$REPO_ROOT/private/renet/pkg/embed/assets"
EMBED_LOCKFILE="$REPO_ROOT/private/renet/embed-assets.lock.json"
require_cmd jq
require_cmd zstd
[[ -f "$EMBED_LOCKFILE" ]] || {
    log_error "embed lockfile not found: $EMBED_LOCKFILE"
    exit 1
}

# Start clean so the embedded set is EXACTLY what this image contains — a stale
# artifact from a prior extraction must not leak into the binary. (CI checks out
# fresh; this makes local/repeated runs deterministic too.) The glob depth must
# track the staged layout: a pattern one level too shallow silently matches
# nothing and leaves the stale payloads in place.
rm -f "$EMBED_DIR"/*/*/*.zst

# The component list, its per-arch coverage, where each lives in the image, and
# whether it is base or cluster ALL come from the lockfile. This script used to
# carry its own REQUIRED_TOOLS/OPTIONAL_TOOLS split that disagreed with
# build.sh's, which is how the CSI sidecars ended up optional in one place and
# mandatory in the other.
missing=""
while IFS=$'\t' read -r base image_dir arch class; do
    [[ -n "$base" ]] || continue
    asset="$base-linux-$arch"
    mkdir -p "$EMBED_DIR/$arch/$class"
    if docker cp "$CONTAINER_ID:$image_dir/$asset" "$EMBED_DIR/$arch/$class/$asset" 2>/dev/null; then
        zstd -19 -T0 -q --rm -f "$EMBED_DIR/$arch/$class/$asset"
    else
        missing="$missing $asset"
    fi
done < <(jq -r '
    .components
    | to_entries[]
    | .value as $c
    | $c.arches
    | keys[]
    | [$c.assetBase, $c.imageDir, ., $c.class]
    | @tsv
' "$EMBED_LOCKFILE")

if [[ -n "$missing" ]]; then
    log_error "Cached renet image is missing assets the lockfile declares:$missing"
    log_error "Rebuild it with: (cd private/renet && ./build.sh docker_image)"
    exit 1
fi

log_info "Embedded assets (per-arch, per-class):"
ls -la "$EMBED_DIR"/*/*/*.zst 2>/dev/null || true

# Stage the proxy compose for go:embed via build.sh (single source of truth for
# that step). embed_proxy stages ONLY the proxy compose; the datastore README is
# a tracked embed file and must NOT be overwritten — the old cp here corrupted it.
log_step "Staging proxy compose for embedding..."
(cd "$REPO_ROOT/private/renet" && ./build.sh embed_proxy)

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
