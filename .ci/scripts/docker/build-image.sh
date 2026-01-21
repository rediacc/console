#!/bin/bash
# Build Docker images for publishing
# Supports multi-architecture builds via Docker Buildx
#
# Usage:
#   build-image.sh --image api                       # Build API image
#   build-image.sh --image bridge --version 0.4.30   # Build with version tag
#   build-image.sh --image api --ci-tag 20260120-104603  # Build with CI tag (no :latest)
#   build-image.sh --all                             # Build all images
#   build-image.sh --all --push                      # Build and push all
#   build-image.sh --dry-run --all                   # Preview builds
#
# Options:
#   --image NAME     Build specific image (api, bridge, plugin-terminal, plugin-browser)
#   --all            Build all images
#   --version X.Y.Z  Version tag (default: latest only)
#   --ci-tag TAG     CI-only tag (YYYYMMDD-HHMMSS format, no :latest pushed)
#   --push           Push to registry (requires login)
#   --dry-run        Preview without building
#   --platform PLAT  Target platform (default: linux/amd64,linux/arm64)
#
# Environment variables:
#   PUBLISH_DOCKER_REGISTRY - Target registry (from constants.sh)
#   DRY_RUN=true            - Preview mode

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

DRY_RUN="${DRY_RUN:-false}"
IMAGE_NAME=""
BUILD_ALL=false
VERSION=""
CI_TAG=""
PUSH=false
PLATFORM="linux/amd64,linux/arm64"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)
            IMAGE_NAME="$2"
            shift 2
            ;;
        --all)
            BUILD_ALL=true
            shift
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --ci-tag)
            CI_TAG="$2"
            shift 2
            ;;
        --push)
            PUSH=true
            shift
            ;;
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--image NAME | --all] [--version X.Y.Z] [--push] [--dry-run]"
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
if [[ "$BUILD_ALL" == "false" ]] && [[ -z "$IMAGE_NAME" ]]; then
    log_error "Must specify --image NAME or --all"
    exit 1
fi

# Setup Docker Buildx
setup_buildx() {
    log_step "Setting up Docker Buildx..."

    # Create builder if it doesn't exist
    if ! docker buildx inspect rediacc-builder &>/dev/null; then
        docker buildx create --name rediacc-builder --driver docker-container --bootstrap
    fi

    docker buildx use rediacc-builder
    log_info "Buildx ready"
}

# Get full image path with registry
get_image_path() {
    local name="$1"
    echo "${PUBLISH_DOCKER_REGISTRY}/${name}"
}

# Build single image
build_image() {
    local name="$1"
    local dockerfile="${DOCKERFILES[$name]:-}"
    local context="${BUILD_CONTEXTS[$name]:-}"

    if [[ -z "$dockerfile" ]]; then
        log_error "Unknown image: $name"
        log_error "Available: ${!DOCKERFILES[*]}"
        return 1
    fi

    local dockerfile_path="$CONSOLE_ROOT_DIR/$dockerfile"
    local context_path="$CONSOLE_ROOT_DIR/$context"

    if [[ ! -f "$dockerfile_path" ]]; then
        log_error "Dockerfile not found: $dockerfile_path"
        return 1
    fi

    local image_path
    image_path=$(get_image_path "$name")

    # Build tags
    local tags=""
    if [[ -n "$CI_TAG" ]]; then
        # CI mode: use CI tag only (no :latest to prevent race conditions)
        tags="--tag ${image_path}:${CI_TAG}"
        if [[ -n "$VERSION" ]]; then
            tags="$tags --tag ${image_path}:${VERSION}"
        fi
    else
        # Local/default mode: use :latest
        tags="--tag ${image_path}:latest"
        if [[ -n "$VERSION" ]]; then
            tags="$tags --tag ${image_path}:${VERSION}"
        fi
    fi

    # Build arguments
    local build_args=""
    if [[ "$name" == "api" ]]; then
        # API image may need version build arg
        build_args="--build-arg VERSION=${VERSION:-dev}"
    elif [[ "$name" == "bridge" ]]; then
        # Bridge image may need version for Go ldflags
        build_args="--build-arg VERSION=${VERSION:-dev}"
    elif [[ "$name" == "web" ]]; then
        # Web image needs version for Vite and build type
        build_args="--build-arg VITE_APP_VERSION=${VERSION:-latest} --build-arg REDIACC_BUILD_TYPE=RELEASE"
    fi

    # Push flag
    local push_flag=""
    if [[ "$PUSH" == "true" ]]; then
        push_flag="--push"
    else
        push_flag="--load"
    fi

    # For multi-arch without push, we can only load single platform
    if [[ "$PUSH" != "true" ]] && [[ "$PLATFORM" == *","* ]]; then
        log_warn "Multi-arch build requires --push, using linux/amd64 only"
        PLATFORM="linux/amd64"
    fi

    log_step "Building $name..."
    log_info "  Dockerfile: $dockerfile"
    log_info "  Context: $context"
    log_info "  Tags: $tags"
    log_info "  Platform: $PLATFORM"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would build $name with:"
        echo "  docker buildx build \\"
        echo "    --file $dockerfile_path \\"
        echo "    --platform $PLATFORM \\"
        echo "    $tags \\"
        echo "    $build_args \\"
        echo "    $push_flag \\"
        echo "    $context_path"
        return 0
    fi

    # Build command
    local cmd="docker buildx build"
    cmd="$cmd --file $dockerfile_path"
    cmd="$cmd --platform $PLATFORM"
    cmd="$cmd $tags"
    [[ -n "$build_args" ]] && cmd="$cmd $build_args"
    cmd="$cmd $push_flag"
    cmd="$cmd $context_path"

    if ! eval "$cmd"; then
        log_error "Failed to build $name"
        return 1
    fi

    log_info "Built $name successfully"
}

# Main logic
main() {
    # Setup buildx
    if [[ "$DRY_RUN" != "true" ]]; then
        setup_buildx
    fi

    local failed=0
    local built=0

    if [[ "$BUILD_ALL" == "true" ]]; then
        log_step "Building all images..."
        for img in "${PUBLISH_IMAGES[@]}"; do
            if build_image "$img"; then
                ((built++)) || true
            else
                ((failed++)) || true
            fi
        done
    else
        if build_image "$IMAGE_NAME"; then
            ((built++)) || true
        else
            ((failed++)) || true
        fi
    fi

    # Summary
    echo ""
    log_info "Build summary: $built succeeded, $failed failed"

    if [[ $failed -gt 0 ]]; then
        exit 1
    fi
}

main "$@"
