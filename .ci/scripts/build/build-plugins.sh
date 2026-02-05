#!/bin/bash
# Build Docker plugin images
# Usage: build-plugins.sh [--push] [--dry-run] [--registry <url>]
#
# Options:
#   --push       Push images to registry (requires GITHUB_TOKEN)
#   --dry-run    Build without pushing (implies --no-push)
#   --registry   Custom registry URL (default: from constants.sh)
#
# Environment variables:
#   GITHUB_TOKEN       - GitHub token for GHCR authentication (required for --push)
#   GITHUB_ACTOR       - GitHub username for GHCR login (optional, defaults to $(whoami))
#   GITHUB_REF         - Git reference (for tag detection)
#   BASE_IMAGE         - Base image to use (default: ubuntu:24.04)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# Configuration
BASE_IMAGE="${BASE_IMAGE:-ubuntu:24.04}"
PUSH=false
DRY_RUN=false
REGISTRY=""
PLUGINS_DIR="$(get_repo_root)/packages/plugins"

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --push) PUSH=true ;;
        --dry-run)
            DRY_RUN=true
            PUSH=false
            ;;
        --registry=*) REGISTRY="${arg#*=}" ;;
        --registry)
            shift
            REGISTRY="$1"
            ;;
    esac
done

# Determine tags based on git reference
determine_tags() {
    local plugin_name=$1
    local image_base

    if [[ -n "$REGISTRY" ]]; then
        image_base="${REGISTRY}/rediacc/plugin-${plugin_name}"
    else
        image_base="${PUBLISH_DOCKER_REGISTRY}/plugin-${plugin_name}"
    fi

    local tags="${image_base}:latest"

    # Add version tag if on a version tag
    if [[ -n "${GITHUB_REF:-}" ]] && [[ "$GITHUB_REF" == refs/tags/v* ]]; then
        local version_tag="${GITHUB_REF#refs/tags/}"
        tags="${tags},${image_base}:${version_tag}"
        log_info "Building for version tag: ${version_tag}"
    fi

    # Add date tag
    local date_tag
    date_tag=$(date +%Y-%m-%d)
    tags="${tags},${image_base}:${date_tag}"

    echo "$tags"
}

# Setup buildx for multi-arch builds
setup_buildx() {
    log_step "Setting up Docker Buildx..."

    # Create builder if it doesn't exist
    if ! docker buildx inspect rediacc-builder &>/dev/null; then
        docker buildx create --name rediacc-builder --driver docker-container --bootstrap
    fi

    docker buildx use rediacc-builder
    log_info "Buildx ready"
}

# Docker login (GHCR)
docker_login() {
    if [[ -z "${GITHUB_TOKEN:-}" ]]; then
        log_error "GITHUB_TOKEN must be set for push"
        exit 1
    fi

    log_step "Logging into GHCR..."
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "${GITHUB_ACTOR:-$(whoami)}" --password-stdin
    log_info "Docker login successful"
}

# Build a single plugin
build_plugin() {
    local plugin_dir=$1
    local plugin_name
    plugin_name=$(basename "$plugin_dir")

    if [[ ! -f "$plugin_dir/Dockerfile" ]]; then
        log_warn "No Dockerfile found in $plugin_dir, skipping..."
        return 0
    fi

    log_step "Building plugin: ${plugin_name}"

    local tags
    tags=$(determine_tags "$plugin_name")
    log_info "Tags: ${tags}"

    # Build arguments
    local platforms="linux/amd64,linux/arm64"

    # Convert comma-separated tags to multiple -t flags
    local tag_flags=""
    IFS=',' read -ra TAG_ARRAY <<<"$tags"
    for tag in "${TAG_ARRAY[@]}"; do
        tag_flags="${tag_flags} -t ${tag}"
    done

    # Determine push flag
    local push_flag=""
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "DRY_RUN mode: skipping push"
    elif [[ "$PUSH" == "true" ]]; then
        push_flag="--push"
    fi

    log_info "Building multi-arch image for platforms: ${platforms}"

    # Build
    # shellcheck disable=SC2086
    if ! docker buildx build \
        --platform "${platforms}" \
        --build-arg BASE_IMAGE="${BASE_IMAGE}" \
        ${tag_flags} \
        ${push_flag} \
        "$plugin_dir"; then
        log_error "Failed to build ${plugin_name}"
        return 1
    fi

    log_info "Successfully built ${plugin_name}"

    # Output summary
    echo "---"
    echo "Plugin: ${plugin_name}"
    echo "Images:"
    for tag in "${TAG_ARRAY[@]}"; do
        echo "  - ${tag}"
    done
    echo "---"
}

# Main execution
main() {
    local start_time
    start_time=$(date +%s)

    log_step "Starting Rediacc Plugins Build"
    log_info "Base Image: ${BASE_IMAGE}"
    log_info "Push: ${PUSH}"
    log_info "Dry Run: ${DRY_RUN}"

    # Verify plugins directory exists
    if [[ ! -d "$PLUGINS_DIR" ]]; then
        log_error "Plugins directory not found: $PLUGINS_DIR"
        exit 1
    fi

    # Login to GHCR if pushing
    if [[ "$PUSH" == "true" ]] && [[ "$DRY_RUN" != "true" ]]; then
        docker_login
    fi

    # Setup buildx
    setup_buildx

    # Find and build all plugins
    local plugin_count=0
    local failed_plugins=()
    local successful_plugins=()

    for plugin_dir in "$PLUGINS_DIR"/*/; do
        if [[ -d "$plugin_dir" ]] && [[ -f "$plugin_dir/Dockerfile" ]]; then
            plugin_count=$((plugin_count + 1))
            local plugin_name
            plugin_name=$(basename "$plugin_dir")

            if build_plugin "$plugin_dir"; then
                successful_plugins+=("$plugin_name")
            else
                failed_plugins+=("$plugin_name")
            fi
        fi
    done

    if [[ $plugin_count -eq 0 ]]; then
        log_error "No plugins found to build in $PLUGINS_DIR"
        exit 1
    fi

    # Print summary
    local end_time
    end_time=$(date +%s)
    local duration=$((end_time - start_time))

    echo ""
    echo "================================================"
    echo "Plugin Build Summary"
    echo "================================================"

    if [[ ${#successful_plugins[@]} -gt 0 ]]; then
        log_info "Successfully Built (${#successful_plugins[@]}):"
        for plugin in "${successful_plugins[@]}"; do
            echo "  - $plugin"
        done
    fi

    if [[ ${#failed_plugins[@]} -gt 0 ]]; then
        echo ""
        log_error "Failed to Build (${#failed_plugins[@]}):"
        for plugin in "${failed_plugins[@]}"; do
            echo "  - $plugin"
        done
        echo ""
        log_error "Plugin Build FAILED"
        echo "Duration: ${duration}s"
        exit 1
    fi

    echo ""
    log_info "All plugins built successfully!"
    echo "Total: $plugin_count plugin(s)"
    echo "Duration: ${duration}s"
}

# Run main
main
