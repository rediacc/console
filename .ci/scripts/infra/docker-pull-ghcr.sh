#!/bin/bash
# Pull Docker image from GitHub Container Registry
# Usage: docker-pull-ghcr.sh --image <image> [options]
#
# Authenticates with GHCR and pulls the specified image.
# Logs out of GHCR after pull (preserves other Docker credentials).
#
# Options:
#   --image     Full image path (required, e.g., ghcr.io/org/repo:tag)
#   --token     GitHub token for authentication (default: GITHUB_TOKEN env var)
#   --actor     GitHub actor/username (default: GITHUB_ACTOR env var)
#   --quiet     Suppress docker pull progress output
#
# Example:
#   .ci/scripts/infra/docker-pull-ghcr.sh --image ghcr.io/rediacc/elite/bridge:latest
#   .ci/scripts/infra/docker-pull-ghcr.sh --image ghcr.io/rediacc/elite/bridge:latest --quiet

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

IMAGE="${ARG_IMAGE:-}"
TOKEN="${ARG_TOKEN:-${GITHUB_TOKEN:-}}"
ACTOR="${ARG_ACTOR:-${GITHUB_ACTOR:-}}"
QUIET="${ARG_QUIET:-false}"

# Validate required arguments
if [[ -z "$IMAGE" ]]; then
    log_error "Usage: docker-pull-ghcr.sh --image <ghcr.io/org/repo:tag> [--token <token>] [--actor <actor>]"
    exit 1
fi

# Validate :latest usage in CI
# - USE_CI_IMAGES=true  + :latest → ERROR (should be using CI tag)
# - USE_CI_IMAGES=false + :latest → OK (expected fallback when builds skipped)
# - CI without USE_CI_IMAGES + :latest → ERROR (legacy check)
if [[ -n "${CI:-}" ]] && [[ "$IMAGE" == *":latest" ]]; then
    if [[ "${USE_CI_IMAGES:-}" == "true" ]]; then
        log_error "ERROR: Pulling :latest tag when USE_CI_IMAGES=true"
        log_error "This indicates a configuration error - CI tag should be used"
        log_error "Image requested: $IMAGE"
        exit 1
    elif [[ "${USE_CI_IMAGES:-}" == "false" ]]; then
        log_warn "Using :latest tag (builds were skipped due to no private repo access)"
    else
        # Legacy fallback: reject :latest in CI without explicit flag
        log_error "ERROR: Pulling :latest tag is not allowed in CI"
        log_error "Set USE_CI_IMAGES=false to explicitly allow :latest, or use CI tag"
        log_error "Image requested: $IMAGE"
        exit 1
    fi
fi

if [[ -z "$TOKEN" ]]; then
    log_error "GitHub token required (--token or GITHUB_TOKEN environment variable)"
    exit 1
fi

if [[ -z "$ACTOR" ]]; then
    log_error "GitHub actor required (--actor or GITHUB_ACTOR environment variable)"
    exit 1
fi

require_cmd docker

log_step "Authenticating with ghcr.io..."
echo "$TOKEN" | docker login ghcr.io -u "$ACTOR" --password-stdin

log_step "Pulling $IMAGE..."
PULL_ARGS=()
[[ "$QUIET" == "true" ]] && PULL_ARGS+=("--quiet")
docker pull "${PULL_ARGS[@]}" "$IMAGE"

log_step "Cleaning up GHCR credentials..."
docker logout ghcr.io

log_info "Successfully pulled $IMAGE"
