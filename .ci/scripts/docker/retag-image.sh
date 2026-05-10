#!/bin/bash
# Re-tag Docker images from CI tag to semantic version
# Used in publish stage to promote CI images to release versions
#
# Usage:
#   retag-image.sh --image api --from 20260120-104603 --to 0.5.0
#   retag-image.sh --all --from 20260120-104603 --to 0.5.0 [--push-latest]
#   retag-image.sh --image-path ghcr.io/rediacc/server --from 0.5.0-abc --to 0.5.0 [--push-latest]
#
# Options:
#   --image NAME       Re-tag specific image relative to PUBLISH_DOCKER_REGISTRY
#                      (api, bridge, plugin-terminal, plugin-browser, web, cli).
#                      Mutually exclusive with --image-path.
#   --image-path PATH  Full image path, ignores PUBLISH_DOCKER_REGISTRY (e.g.,
#                      ghcr.io/rediacc/server). Mutually exclusive with --image.
#   --all              Re-tag all images in PUBLISH_IMAGES
#   --from TAG         Source CI tag (e.g., 20260120-104603)
#   --to VERSION       Target semantic version (e.g., 0.5.0)
#   --push-latest      Also push :latest tag
#   --skip-if-exists   Skip retagging if destination already exists (idempotent retries)
#   --dry-run          Preview without executing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

IMAGE_NAME=""
IMAGE_PATH=""
RETAG_ALL=false
FROM_TAG=""
TO_TAG=""
PUSH_LATEST=false
SKIP_IF_EXISTS=false
DRY_RUN="${DRY_RUN:-false}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)
            IMAGE_NAME="$2"
            shift 2
            ;;
        --image-path)
            IMAGE_PATH="$2"
            shift 2
            ;;
        --all)
            RETAG_ALL=true
            shift
            ;;
        --from)
            FROM_TAG="$2"
            shift 2
            ;;
        --to)
            TO_TAG="$2"
            shift 2
            ;;
        --push-latest)
            PUSH_LATEST=true
            shift
            ;;
        --skip-if-exists)
            SKIP_IF_EXISTS=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --image NAME --from CI_TAG --to VERSION [--push-latest]"
            echo "       $0 --image-path PATH --from CI_TAG --to VERSION [--push-latest]"
            echo "       $0 --all --from CI_TAG --to VERSION [--push-latest]"
            echo ""
            echo "Options:"
            echo "  --image NAME       Re-tag image relative to PUBLISH_DOCKER_REGISTRY"
            echo "  --image-path PATH  Re-tag full image path (e.g., ghcr.io/rediacc/server)"
            echo "  --all              Re-tag all images in PUBLISH_IMAGES"
            echo "  --from TAG         Source CI tag"
            echo "  --to VERSION       Target semantic version"
            echo "  --push-latest      Also push :latest tag"
            echo "  --skip-if-exists   Skip if destination exists (idempotent)"
            echo "  --dry-run          Preview without executing"
            echo ""
            echo "Available images: ${PUBLISH_IMAGES[*]}"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
[[ -z "$FROM_TAG" ]] && {
    log_error "--from is required"
    exit 1
}
[[ -z "$TO_TAG" ]] && {
    log_error "--to is required"
    exit 1
}
if [[ -n "$IMAGE_NAME" && -n "$IMAGE_PATH" ]]; then
    log_error "--image and --image-path are mutually exclusive"
    exit 1
fi
if [[ "$RETAG_ALL" == "true" && (-n "$IMAGE_NAME" || -n "$IMAGE_PATH") ]]; then
    log_error "--all is mutually exclusive with --image / --image-path"
    exit 1
fi
if [[ "$RETAG_ALL" == "false" && -z "$IMAGE_NAME" && -z "$IMAGE_PATH" ]]; then
    log_error "--image, --image-path, or --all required"
    exit 1
fi

retag_image() {
    # Accepts either a relative name (resolved against PUBLISH_DOCKER_REGISTRY)
    # or a full image path. The "label" used for log lines and the source image
    # path differ depending on which mode the caller picked.
    local name="$1"
    local label image_root
    if [[ "$name" == *"/"* ]]; then
        image_root="$name"
        label="$(basename "$name")"
    else
        image_root="${PUBLISH_DOCKER_REGISTRY}/${name}"
        label="$name"
    fi
    local src="${image_root}:${FROM_TAG}"
    local dst="${image_root}:${TO_TAG}"
    local dst_latest="${image_root}:latest"

    log_step "Re-tagging $label: $FROM_TAG -> $TO_TAG"

    # Skip if destination exists AND already points at the source's digest
    # (idempotent retries in Phase 2). The digest compare matters because a
    # stale destination tag from a previous failed release at the same
    # version would otherwise silently lock the new image out of promotion
    # — the symptom is post-publish Docker pull tests reading the old
    # version. If the source can't be inspected (e.g., transient registry
    # error), fall through to the retag path so we don't silently skip.
    if [[ "$SKIP_IF_EXISTS" == "true" ]]; then
        local dst_digest src_digest
        dst_digest=$(docker buildx imagetools inspect "$dst" --format '{{.Manifest.Digest}}' 2>/dev/null || true)
        if [[ -n "$dst_digest" ]]; then
            src_digest=$(docker buildx imagetools inspect "$src" --format '{{.Manifest.Digest}}' 2>/dev/null || true)
            if [[ -n "$src_digest" && "$dst_digest" == "$src_digest" ]]; then
                log_info "Destination matches source digest, skipping: $dst ($dst_digest)"
                return 0
            fi
            log_info "Destination exists but digest differs (dst=$dst_digest src=${src_digest:-unknown}), retagging: $dst"
        fi
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Verifying source image: $src"
        if ! docker buildx imagetools inspect "$src" >/dev/null; then
            log_error "[DRY-RUN] Failed to inspect source image: $src"
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
        # Note: :stable tag is pushed by promote-stable.yml after 7-day soak
    fi

    log_info "Re-tagged $label successfully"
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
        # --image takes a relative name; --image-path takes a full path. retag_image
        # detects which by checking for a "/" in the argument.
        local target="${IMAGE_NAME:-$IMAGE_PATH}"
        if retag_image "$target"; then
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
