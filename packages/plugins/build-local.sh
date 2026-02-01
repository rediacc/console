#!/bin/bash
# Local build script for Rediacc plugins - build only (no push)
# Usage: ./build-local.sh
#
# Environment variables:
#   SYSTEM_BASE_IMAGE - Base image to use (default: ubuntu:24.04)
#   DOCKER_REGISTRY   - Custom registry prefix (optional)

set -euo pipefail

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Try to load environment variables from monorepo root .env
MONOREPO_ROOT="$SCRIPT_DIR/../../.."
if [[ -f "$MONOREPO_ROOT/.env" ]]; then
    # shellcheck disable=SC1091
    source "$MONOREPO_ROOT/.env"
fi

# Load constants (provides DOCKER_REGISTRY default: ghcr.io/rediacc/elite)
source "$SCRIPT_DIR/../../.ci/config/constants.sh"

# Configuration
BASE_IMAGE="${SYSTEM_BASE_IMAGE:-ubuntu:24.04}"

echo "Building Rediacc plugin Docker images..."
echo "Base image: $BASE_IMAGE"
echo "Registry: ${DOCKER_REGISTRY:-<none>}"
echo ""

# Track results
failed=0
built=0

# Loop through each folder in the script directory
for folder in "$SCRIPT_DIR"/*/; do
    if [[ -d "$folder" ]] && [[ -f "$folder/Dockerfile" ]]; then
        plugin_name=$(basename "$folder")

        # Determine image name
        if [[ -n "$DOCKER_REGISTRY" ]]; then
            # Handle multi-level registries (e.g., ghcr.io/org/repo)
            slash_count=$(echo "$DOCKER_REGISTRY" | tr -cd '/' | wc -c)
            if [[ $slash_count -ge 2 ]]; then
                image="${DOCKER_REGISTRY}/plugin-$plugin_name"
            else
                image="${DOCKER_REGISTRY}/rediacc/plugin-$plugin_name"
            fi
        else
            image="ghcr.io/rediacc/elite/plugin-$plugin_name"
        fi

        echo "Building $image:latest..."
        if docker build --build-arg BASE_IMAGE="$BASE_IMAGE" -t "$image:latest" "$folder"; then
            echo "  Successfully built $image:latest"
            built=$((built + 1))
        else
            echo "  Failed to build $image:latest"
            failed=$((failed + 1))
        fi
        echo ""
    fi
done

# Summary
echo "================================================"
echo "Build Summary"
echo "================================================"
echo "Built: $built plugin(s)"

if [[ $failed -gt 0 ]]; then
    echo "Failed: $failed plugin(s)"
    exit 1
fi

echo ""
echo "All plugin images built successfully!"
