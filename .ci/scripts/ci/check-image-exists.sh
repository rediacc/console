#!/bin/bash
# Check if Docker image exists in GHCR without pulling
#
# Usage:
#   check-image-exists.sh --image api --tag fb33b0f
#   check-image-exists.sh --image bridge --tag 77596e0 --github-output
#
# Requires:
#   - GITHUB_TOKEN for authentication (optional but recommended)
#   - GITHUB_ACTOR for authentication (defaults to 'github-actions')
#
# Exit codes:
#   0 - Image exists
#   1 - Image not found or error
#
# GitHub Output (with --github-output):
#   exists=true|false

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

IMAGE_NAME=""
TAG=""
GITHUB_OUTPUT_MODE=false
OUTPUT_VAR_NAME=""

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
        --github-output)
            GITHUB_OUTPUT_MODE=true
            shift
            ;;
        --output-var)
            OUTPUT_VAR_NAME="$2"
            shift 2
            ;;
        -h | --help)
            echo "Usage: $0 --image NAME --tag TAG [OPTIONS]"
            echo ""
            echo "Required:"
            echo "  --image NAME         Image name (e.g., api, bridge, plugin-terminal)"
            echo "  --tag TAG            Image tag to check (e.g., fb33b0f, latest)"
            echo ""
            echo "Options:"
            echo "  --github-output      Write result to GITHUB_OUTPUT"
            echo "  --output-var NAME    Variable name for GITHUB_OUTPUT (default: exists)"
            echo "  -h, --help           Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0 --image api --tag fb33b0f"
            echo "  $0 --image bridge --tag 77596e0 --github-output --output-var bridge_exists"
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
    log_error "Missing required argument: --image"
    exit 1
fi

if [[ -z "$TAG" ]]; then
    log_error "Missing required argument: --tag"
    exit 1
fi

# Default output variable name
if [[ -z "$OUTPUT_VAR_NAME" ]]; then
    OUTPUT_VAR_NAME="exists"
fi

# Build full image reference
FULL_IMAGE="${PUBLISH_DOCKER_REGISTRY}/${IMAGE_NAME}:${TAG}"

log_step "Checking if image exists: $FULL_IMAGE"

# Authenticate with GHCR if token is available
if [[ -n "${GITHUB_TOKEN:-}" ]]; then
    log_debug "Authenticating with GHCR..."
    if ! echo "${GITHUB_TOKEN}" | docker login ghcr.io -u "${GITHUB_ACTOR:-github-actions}" --password-stdin &>/dev/null; then
        log_warn "GHCR authentication failed, proceeding without auth"
    fi
fi

# Check if image exists using docker manifest inspect
# This doesn't pull the image, just checks the manifest
IMAGE_EXISTS="false"
if docker manifest inspect "$FULL_IMAGE" &>/dev/null; then
    IMAGE_EXISTS="true"
    log_info "Image exists: $FULL_IMAGE"
else
    log_info "Image not found: $FULL_IMAGE"
fi

# Output to GITHUB_OUTPUT if requested
if [[ "$GITHUB_OUTPUT_MODE" == "true" ]] && [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "${OUTPUT_VAR_NAME}=${IMAGE_EXISTS}" >>"$GITHUB_OUTPUT"
    log_info "Set GITHUB_OUTPUT: ${OUTPUT_VAR_NAME}=${IMAGE_EXISTS}"
fi

# Exit with appropriate code
if [[ "$IMAGE_EXISTS" == "true" ]]; then
    exit 0
else
    exit 1
fi
