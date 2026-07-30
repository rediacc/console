#!/bin/bash
# CI Service Shutdown Script
# Stops backend services and cleans up resources
#
# Usage:
#   .ci/scripts/infra/ci-stop.sh

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "Stopping Rediacc CI services..."

# =============================================================================
# RESOLVE PATHS
# =============================================================================
CI_DOCKER_DIR="$CONSOLE_ROOT/.ci/docker/ci"
BACKEND_STATE_FILE="$CONSOLE_ROOT/.backend-state"

# =============================================================================
# STOP DOCKER COMPOSE SERVICES
# =============================================================================
if [[ -d "$CI_DOCKER_DIR" ]]; then
    echo "  Stopping Docker Compose services..."
    (cd "$CI_DOCKER_DIR" && docker compose -f docker-compose.yml down --volumes --remove-orphans) || {
        echo "  Docker compose down failed, forcing container removal"
    }
fi

# =============================================================================
# FORCE REMOVE CONTAINERS (if compose down failed)
# =============================================================================
# rediacc-web was removed: the `web:` service it named is gone from
# .ci/docker/ci/docker-compose.yml (issue #533 -- nothing ever started it, and it
# named an image CI does not publish). ci-stop-elite.sh keeps its own
# rediacc-web entry, which is correct: that one is elite's container.
CONTAINERS=(
    rediacc-account-server
)

for container in "${CONTAINERS[@]}"; do
    if docker ps -a --format "{{.Names}}" 2>/dev/null | grep -q "^${container}$"; then
        echo "  Force removing: $container"
        docker stop "$container" 2>/dev/null || true
        docker rm "$container" 2>/dev/null || true
    fi
done

# =============================================================================
# CLEANUP DATA
# =============================================================================
# Backend state file (local dev tracking)
rm -f "$BACKEND_STATE_FILE" 2>/dev/null || true

echo "All services stopped"
