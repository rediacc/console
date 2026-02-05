#!/bin/bash
# CI Pre-pull Docker Images
# Authenticates with GHCR and pulls all required backend images
# Self-contained replacement for elite/action/ci-pull-images.sh
#
# Usage:
#   GITHUB_TOKEN=xxx GITHUB_ACTOR=yyy .ci/scripts/infra/ci-pull-images.sh
#
# Environment variables:
#   GITHUB_TOKEN  - GitHub token for authentication (required)
#   GITHUB_ACTOR  - GitHub username (required)
#   API_TAG       - Tag for API image (default: latest)
#   BRIDGE_TAG    - Tag for bridge image (default: latest)
#   WEB_TAG       - Tag for web image (default: latest)
#   DOCKER_REGISTRY - Registry URL (default: ghcr.io/rediacc/elite)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source common utilities
source "$SCRIPT_DIR/../lib/common.sh"

echo ""
echo "======================================================================"
echo "  Pre-pulling Docker images with temporary authentication..."
echo "======================================================================"

# Validate required environment variables
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    log_error "GITHUB_TOKEN environment variable is required"
    exit 1
fi

if [[ -z "${GITHUB_ACTOR:-}" ]]; then
    log_error "GITHUB_ACTOR environment variable is required"
    exit 1
fi

# Set defaults
DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io/rediacc/elite}"
TAG="${TAG:-latest}"
API_TAG="${API_TAG:-$TAG}"
BRIDGE_TAG="${BRIDGE_TAG:-$TAG}"
WEB_TAG="${WEB_TAG:-$TAG}"

# Use subshell to contain credential exposure
(
    # Authenticate with GHCR
    log_step "Authenticating with ghcr.io..."
    echo "$GITHUB_TOKEN" | docker login ghcr.io -u "$GITHUB_ACTOR" --password-stdin

    # Pull all required images
    log_step "Pulling web:${WEB_TAG}..."
    docker pull --quiet "${DOCKER_REGISTRY}/web:${WEB_TAG}"

    log_step "Pulling api:${API_TAG}..."
    docker pull --quiet "${DOCKER_REGISTRY}/api:${API_TAG}"

    log_step "Pulling bridge:${BRIDGE_TAG}..."
    docker pull --quiet "${DOCKER_REGISTRY}/bridge:${BRIDGE_TAG}"

    log_info "All images pulled successfully"
)

# Cleanup credentials (outside subshell)
echo ""
log_step "Removing Docker credentials..."
docker logout ghcr.io 2>/dev/null || true

# Remove Docker config file to ensure no credentials persist
if [[ -f "$HOME/.docker/config.json" ]]; then
    # Only remove GHCR credentials, keep other registries
    if command -v jq &>/dev/null; then
        jq 'del(.auths["ghcr.io"])' "$HOME/.docker/config.json" >"$HOME/.docker/config.json.tmp" 2>/dev/null &&
            mv "$HOME/.docker/config.json.tmp" "$HOME/.docker/config.json" ||
            rm -f "$HOME/.docker/config.json.tmp"
    fi
fi

# Clear cached credentials from environment
unset GITHUB_TOKEN 2>/dev/null || true
unset DOCKER_REGISTRY_PASSWORD 2>/dev/null || true

log_info "Credentials cleaned - environment is now safe for debug access"
echo "======================================================================"
echo ""

# List pulled images
echo "Pulled images:"
docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" | grep -E "(rediacc|REPOSITORY)" || true
