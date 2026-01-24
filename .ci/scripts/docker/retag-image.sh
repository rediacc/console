#!/bin/bash
# Re-tag Docker images from CI tag to semantic version
# Used in publish stage to promote CI images to release versions
#
# Usage:
#   retag-image.sh --image api --from 20260120-104603 --to 0.5.0
#   retag-image.sh --all --from 20260120-104603 --to 0.5.0 [--push-latest]
#
# Options:
#   --image NAME     Re-tag specific image (api, bridge, plugin-terminal, plugin-browser)
#   --all            Re-tag all images
#   --from TAG       Source CI tag (e.g., 20260120-104603)
#   --to VERSION     Target semantic version (e.g., 0.5.0)
#   --push-latest    Also push :latest tag
#   --dry-run        Preview without executing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

IMAGE_NAME=""
RETAG_ALL=false
FROM_TAG=""
TO_TAG=""
PUSH_LATEST=false
DRY_RUN="${DRY_RUN:-false}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --image) IMAGE_NAME="$2"; shift 2 ;;
        --all) RETAG_ALL=true; shift ;;
        --from) FROM_TAG="$2"; shift 2 ;;
        --to) TO_TAG="$2"; shift 2 ;;
        --push-latest) PUSH_LATEST=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help)
            echo "Usage: $0 --image NAME --from CI_TAG --to VERSION [--push-latest]"
            echo "       $0 --all --from CI_TAG --to VERSION [--push-latest]"
            echo ""
            echo "Options:"
            echo "  --image NAME     Re-tag specific image"
            echo "  --all            Re-tag all images"
            echo "  --from TAG       Source CI tag"
            echo "  --to VERSION     Target semantic version"
            echo "  --push-latest    Also push :latest tag"
            echo "  --dry-run        Preview without executing"
            echo ""
            echo "Available images: ${PUBLISH_IMAGES[*]}"
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# Validate required arguments
[[ -z "$FROM_TAG" ]] && { log_error "--from is required"; exit 1; }
[[ -z "$TO_TAG" ]] && { log_error "--to is required"; exit 1; }
[[ "$RETAG_ALL" == "false" ]] && [[ -z "$IMAGE_NAME" ]] && { log_error "--image or --all required"; exit 1; }

retag_image() {
    local name="$1"
    local src="${PUBLISH_DOCKER_REGISTRY}/${name}:${FROM_TAG}"
    local dst="${PUBLISH_DOCKER_REGISTRY}/${name}:${TO_TAG}"
    local dst_latest="${PUBLISH_DOCKER_REGISTRY}/${name}:latest"

    log_step "Re-tagging $name: $FROM_TAG -> $TO_TAG"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Verifying source image: $src"
        if ! docker buildx imagetools inspect "$src" > /dev/null 2>&1; then
            log_error "[DRY-RUN] Source image NOT found: $src"
            return 1
        fi
        log_info "[DRY-RUN] Verified source exists, would re-tag to: $dst"
        [[ "$PUSH_LATEST" == "true" ]] && log_info "[DRY-RUN] Would also tag: $dst_latest"
        return 0
    fi

    # Use docker buildx imagetools to re-tag multi-arch manifests
    # This preserves all architecture variants without pulling/pushing individual images
    if ! docker buildx imagetools create -t "$dst" "$src"; then
        log_error "Failed to re-tag $src -> $dst"
        return 1
    fi

    if [[ "$PUSH_LATEST" == "true" ]]; then
        if ! docker buildx imagetools create -t "$dst_latest" "$src"; then
            log_error "Failed to re-tag $src -> $dst_latest"
            return 1
        fi
        log_info "Pushed :latest tag"
    fi

    log_info "Re-tagged $name successfully"
}

# Main logic
main() {
    local failed=0
    local retagged=0

    if [[ "$RETAG_ALL" == "true" ]]; then
        log_step "Re-tagging all images..."
        for img in "${PUBLISH_IMAGES[@]}"; do
            if retag_image "$img"; then
                ((retagged++)) || true
            else
                ((failed++)) || true
            fi
        done
    else
        if retag_image "$IMAGE_NAME"; then
            ((retagged++)) || true
        else
            ((failed++)) || true
        fi
    fi

    # Summary
    echo ""
    log_info "Re-tag summary: $retagged succeeded, $failed failed"

    if [[ $failed -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
