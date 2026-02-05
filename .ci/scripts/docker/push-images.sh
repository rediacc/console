#!/bin/bash
# Push Docker images to GHCR
# Wrapper around build-image.sh that handles authentication and verification
#
# Usage:
#   push-images.sh --version 0.4.30          # Push all with version tag
#   push-images.sh --tag pr-123              # Push with PR tag (for testing)
#   push-images.sh --image api --version 1.0 # Push specific image
#
# Options:
#   --version X.Y.Z  Version tag for images
#   --tag TAG        Custom tag (e.g., pr-123 for PR testing)
#   --image NAME     Push specific image only
#   --skip-verify    Skip verification step
#   --dry-run        Preview without pushing
#
# Environment variables:
#   GITHUB_TOKEN     - Required for GHCR authentication
#   GITHUB_ACTOR     - Username for GHCR (defaults to current user)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

DRY_RUN="${DRY_RUN:-false}"
VERSION=""
CUSTOM_TAG=""
IMAGE_NAME=""
SKIP_VERIFY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --tag)
            CUSTOM_TAG="$2"
            shift 2
            ;;
        --image)
            IMAGE_NAME="$2"
            shift 2
            ;;
        --skip-verify)
            SKIP_VERIFY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 [--version X.Y.Z | --tag TAG] [--image NAME] [--dry-run]"
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

# Validate arguments
if [[ -z "$VERSION" ]] && [[ -z "$CUSTOM_TAG" ]]; then
    log_error "Must specify --version or --tag"
    exit 1
fi

# Determine effective tag
EFFECTIVE_TAG="${CUSTOM_TAG:-$VERSION}"

# Login to GHCR
ghcr_login() {
    log_step "Logging into GHCR..."

    if [[ -z "${GITHUB_TOKEN:-}" ]]; then
        log_error "GITHUB_TOKEN required for GHCR authentication"
        exit 1
    fi

    local username="${GITHUB_ACTOR:-$(whoami)}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would login to ghcr.io as $username"
        return 0
    fi

    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$username" --password-stdin
    log_info "GHCR login successful"
}

# Verify image exists in registry
verify_image() {
    local image_name="$1"
    local tag="$2"
    local full_path="${PUBLISH_DOCKER_REGISTRY}/${image_name}:${tag}"

    log_step "Verifying $full_path..."

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would verify $full_path"
        return 0
    fi

    if docker manifest inspect "$full_path" &>/dev/null; then
        log_info "Verified: $full_path exists"
        return 0
    else
        log_error "Verification failed: $full_path not found"
        return 1
    fi
}

# Build and push single image
push_image() {
    local name="$1"

    log_step "Building and pushing $name..."

    local build_args="--image $name --push"

    if [[ -n "$VERSION" ]]; then
        build_args="$build_args --version $VERSION"
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        build_args="$build_args --dry-run"
    fi

    # Use build-image.sh with push flag
    "$SCRIPT_DIR/build-image.sh" $build_args
}

# Main logic
main() {
    log_info "Push configuration:"
    log_info "  Registry: $PUBLISH_DOCKER_REGISTRY"
    log_info "  Tag: $EFFECTIVE_TAG"
    if [[ -n "$IMAGE_NAME" ]]; then
        log_info "  Image: $IMAGE_NAME"
    else
        log_info "  Images: ${PUBLISH_IMAGES[*]}"
    fi

    # Login to registry
    ghcr_login

    local pushed=0
    local failed=0
    local images_to_push=()

    # Determine which images to push
    if [[ -n "$IMAGE_NAME" ]]; then
        images_to_push=("$IMAGE_NAME")
    else
        images_to_push=("${PUBLISH_IMAGES[@]}")
    fi

    # Build and push
    for img in "${images_to_push[@]}"; do
        if push_image "$img"; then
            ((pushed++)) || true
        else
            log_error "Failed to push $img"
            ((failed++)) || true
        fi
    done

    # Verify (unless skipped)
    if [[ "$SKIP_VERIFY" != "true" ]] && [[ "$DRY_RUN" != "true" ]]; then
        log_step "Verifying pushed images..."
        local verify_failed=0

        for img in "${images_to_push[@]}"; do
            # Verify latest tag
            if ! verify_image "$img" "latest"; then
                ((verify_failed++)) || true
            fi

            # Verify version tag if specified
            if [[ -n "$VERSION" ]]; then
                if ! verify_image "$img" "$VERSION"; then
                    ((verify_failed++)) || true
                fi
            fi
        done

        if [[ $verify_failed -gt 0 ]]; then
            log_error "Verification failed for $verify_failed images"
            failed=$((failed + verify_failed))
        fi
    fi

    # Summary
    echo ""
    echo "========================================"
    echo "Push Summary"
    echo "========================================"
    echo "  Registry: $PUBLISH_DOCKER_REGISTRY"
    echo "  Tag: $EFFECTIVE_TAG"
    echo "  Pushed: $pushed"
    echo "  Failed: $failed"
    echo "========================================"

    if [[ $failed -gt 0 ]]; then
        log_error "Push completed with $failed failure(s)"
        exit 1
    fi

    log_info "All images pushed successfully"
}

main "$@"
