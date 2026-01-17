#!/bin/bash
# Extract renet binary from Docker image
# Usage: extract-renet-binary.sh --image <image> [options]
#
# Creates a temporary container from the image, copies the renet binary,
# and removes the container. Sets RENET_BINARY_PATH environment variable.
#
# Options:
#   --image     Docker image containing renet (required)
#   --output    Output path for binary (default: /tmp/renet)
#   --binary    Path to binary inside container (default: /opt/renet/renet-linux-amd64)
#
# Example:
#   .ci/scripts/infra/extract-renet-binary.sh --image ghcr.io/rediacc/elite/bridge:latest
#   .ci/scripts/infra/extract-renet-binary.sh --image myimage:latest --output /usr/local/bin/renet

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

IMAGE="${ARG_IMAGE:-}"
OUTPUT="${ARG_OUTPUT:-/tmp/renet}"
BINARY_PATH="${ARG_BINARY:-/opt/renet/renet-linux-amd64}"

# Validate required arguments
if [[ -z "$IMAGE" ]]; then
    log_error "Usage: extract-renet-binary.sh --image <docker_image> [--output <path>] [--binary <container_path>]"
    exit 1
fi

require_cmd docker

log_step "Extracting renet binary from $IMAGE..."

# Create container (without starting it)
CONTAINER_ID=$(docker create "$IMAGE")
log_debug "Created container: $CONTAINER_ID"

# Copy binary from container
docker cp "$CONTAINER_ID:$BINARY_PATH" "$OUTPUT"

# Remove container
docker rm "$CONTAINER_ID" > /dev/null

# Make executable
chmod +x "$OUTPUT"

log_info "Extracted renet binary to: $OUTPUT"

# Export for GitHub Actions
if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "RENET_BINARY_PATH=$OUTPUT" >> "$GITHUB_ENV"
    log_info "Set RENET_BINARY_PATH in GITHUB_ENV"
fi

# Also print for non-GitHub environments
echo "RENET_BINARY_PATH=$OUTPUT"
