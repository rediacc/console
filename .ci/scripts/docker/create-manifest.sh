#!/bin/bash
# Create multi-arch Docker manifest from architecture-specific images
# Combines :tag-amd64 and :tag-arm64 images into a single :tag manifest
#
# Usage:
#   create-manifest.sh --image api --tag 20260121-120000              # Create and push manifest
#   create-manifest.sh --image api --tag 0.5.0 --push-latest          # Also push :latest
#   create-manifest.sh --dry-run --image api --tag 20260121-120000    # Preview
#
# Options:
#   --image NAME      Image name (api, bridge, web, plugin-terminal, plugin-browser)
#   --tag TAG         Tag for the manifest (e.g., 20260121-120000 or 0.5.0)
#   --push-latest     Also create and push :latest manifest
#   --dry-run         Preview without creating manifest
#
# Environment variables:
#   PUBLISH_DOCKER_REGISTRY - Target registry (from constants.sh)
#   DRY_RUN=true            - Preview mode

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# Configuration
DRY_RUN="${DRY_RUN:-false}"
IMAGE_NAME=""
TAG=""
PUSH_LATEST=false

# Supported architectures
ARCHS=("amd64" "arm64")

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)
            IMAGE_NAME="$2"
            shift 2
            ;;
        --tag)
            TAG="$2"
            shift 2
            ;;
        --push-latest)
            PUSH_LATEST=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --image NAME --tag TAG [--push-latest] [--dry-run]"
            echo ""
            echo "Create multi-arch Docker manifest from architecture-specific images"
            echo ""
            echo "Options:"
            echo "  --image NAME      Image name (api, bridge, etc.)"
            echo "  --tag TAG         Tag for the manifest"
            echo "  --push-latest     Also create and push :latest manifest"
            echo "  --dry-run         Preview without creating manifest"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$IMAGE_NAME" ]]; then
    log_error "--image is required"
    exit 1
fi

if [[ -z "$TAG" ]]; then
    log_error "--tag is required"
    exit 1
fi

# Build full image paths
IMAGE_PATH="${PUBLISH_DOCKER_REGISTRY}/${IMAGE_NAME}"
MANIFEST_TAG="${IMAGE_PATH}:${TAG}"

log_step "Creating multi-arch manifest for $IMAGE_NAME:$TAG"

# Build source image list
SOURCE_IMAGES=""
for arch in "${ARCHS[@]}"; do
    SOURCE_IMAGES="${SOURCE_IMAGES} ${IMAGE_PATH}:${TAG}-${arch}"
done

log_info "  Manifest: $MANIFEST_TAG"
log_info "  Sources: ${SOURCE_IMAGES}"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would create manifest:"
    echo "  docker buildx imagetools create -t $MANIFEST_TAG ${SOURCE_IMAGES}"
    if [[ "$PUSH_LATEST" == "true" ]]; then
        echo "  docker buildx imagetools create -t ${IMAGE_PATH}:latest ${SOURCE_IMAGES}"
    fi
    exit 0
fi

# Create manifest using buildx imagetools (handles multi-arch properly)
create_manifest() {
    local manifest_tag="$1"
    shift
    local sources=("$@")

    log_step "Creating manifest: $manifest_tag"

    # Use docker buildx imagetools to create multi-arch manifest
    # This is more reliable than docker manifest create for cross-registry operations
    if ! docker buildx imagetools create -t "$manifest_tag" "${sources[@]}"; then
        log_error "Failed to create manifest: $manifest_tag"
        return 1
    fi

    log_info "Created manifest: $manifest_tag"
}

# Main logic
main() {
    # Build source array
    local sources=()
    for arch in "${ARCHS[@]}"; do
        sources+=("${IMAGE_PATH}:${TAG}-${arch}")
    done

    # Create main manifest
    create_manifest "$MANIFEST_TAG" "${sources[@]}"

    # Create :latest manifest if requested
    if [[ "$PUSH_LATEST" == "true" ]]; then
        create_manifest "${IMAGE_PATH}:latest" "${sources[@]}"
    fi

    # Verify manifest
    log_step "Verifying manifest..."
    if docker buildx imagetools inspect "$MANIFEST_TAG" &>/dev/null; then
        log_info "Manifest verified: $MANIFEST_TAG"

        # Show platforms
        docker buildx imagetools inspect "$MANIFEST_TAG" 2>/dev/null | grep -E "(Platform:|Name:)" | head -10 || true
    else
        log_warn "Could not verify manifest (may still be pushing)"
    fi

    echo ""
    log_info "Manifest creation complete"
}

main "$@"
