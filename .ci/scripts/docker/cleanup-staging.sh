#!/bin/bash
# Delete staging Docker tags from GHCR registry
# Used for cleanup when Phase 1 staging fails or after Phase 2 commit completes
#
# Usage:
#   cleanup-staging.sh --tag staging-abc123
#   cleanup-staging.sh --tag staging-abc123 --dry-run
#
# Options:
#   --tag TAG    Staging tag to delete (e.g., staging-abc123...)
#   --dry-run    Preview without executing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

STAGING_TAG=""
DRY_RUN="${DRY_RUN:-false}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --tag) STAGING_TAG="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help)
            echo "Usage: $0 --tag STAGING_TAG [--dry-run]"
            echo ""
            echo "Delete staging Docker tags from GHCR registry."
            echo ""
            echo "Options:"
            echo "  --tag TAG    Staging tag to delete (e.g., staging-abc123...)"
            echo "  --dry-run    Preview without executing"
            echo ""
            echo "Images to clean: ${PUBLISH_IMAGES[*]}"
            exit 0
            ;;
        *) log_error "Unknown option: $1"; exit 1 ;;
    esac
done

# Validate required arguments
[[ -z "$STAGING_TAG" ]] && { log_error "--tag is required"; exit 1; }

# Validate staging tag format
if [[ ! "$STAGING_TAG" =~ ^staging- ]]; then
    log_error "Tag must start with 'staging-' prefix for safety"
    exit 1
fi

# Extract org and package base from registry URL
# PUBLISH_DOCKER_REGISTRY is typically "ghcr.io/rediacc/elite"
REGISTRY_PATH="${PUBLISH_DOCKER_REGISTRY#ghcr.io/}"  # Remove ghcr.io/ prefix
ORG="${REGISTRY_PATH%%/*}"  # Get org (rediacc)
PACKAGE_BASE="${REGISTRY_PATH#*/}"  # Get package base (elite)

delete_staging_tag() {
    local image_name="$1"
    local package_name="${PACKAGE_BASE}/${image_name}"
    local full_image="${PUBLISH_DOCKER_REGISTRY}/${image_name}:${STAGING_TAG}"

    log_step "Deleting staging tag for $image_name: $STAGING_TAG"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would delete: $full_image"
        return 0
    fi

    # Get version ID for the tag using GitHub API
    # First, list all versions and find the one with matching tag
    local version_id
    version_id=$(gh api \
        "/orgs/${ORG}/packages/container/${package_name}/versions" \
        --paginate \
        --jq ".[] | select(.metadata.container.tags | index(\"${STAGING_TAG}\")) | .id" \
        2>/dev/null || echo "")

    if [[ -z "$version_id" ]]; then
        log_warn "Staging tag not found for $image_name:$STAGING_TAG (may already be deleted)"
        return 0
    fi

    # Delete the version
    if gh api -X DELETE "/orgs/${ORG}/packages/container/${package_name}/versions/${version_id}" 2>/dev/null; then
        log_info "Deleted staging tag: $full_image"
    else
        log_warn "Failed to delete staging tag for $image_name (may require elevated permissions)"
    fi
}

# Main logic
main() {
    local deleted=0
    local failed=0

    log_step "Cleaning up staging tags: $STAGING_TAG"
    echo ""

    for img in "${PUBLISH_IMAGES[@]}"; do
        if delete_staging_tag "$img"; then
            ((deleted++)) || true
        else
            ((failed++)) || true
        fi
    done

    # Summary
    echo ""
    log_info "Cleanup summary: $deleted processed, $failed warnings"

    # Don't fail on cleanup errors - staging tags are harmless if they remain
    return 0
}

main "$@"
