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
CONTAINERS=(
    rediacc-web
    rediacc-api
    rediacc-sql
    rediacc-license-server
    rediacc-license-rustfs
    rediacc-license-rustfs-init
    rediacc-license-rustfs-volume-init
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
# SQL Server data directory (may be owned by UID 10001)
MSSQL_DIR="$CI_DOCKER_DIR/mssql"
if [[ -d "$MSSQL_DIR" ]]; then
    echo "  Cleaning up SQL Server data..."
    sudo rm -rf "$MSSQL_DIR" 2>/dev/null || rm -rf "$MSSQL_DIR" 2>/dev/null || true
fi

# Backend state file (local dev tracking)
rm -f "$BACKEND_STATE_FILE" 2>/dev/null || true

echo "All services stopped"
