#!/bin/bash
# CI Elite Service Shutdown Script
# Stops elite on-premise services and cleans up resources
#
# Usage:
#   .ci/scripts/infra/ci-stop-elite.sh

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ELITE_DIR="$CONSOLE_ROOT/private/elite"

echo "Stopping Rediacc Elite CI services..."

# =============================================================================
# STOP DOCKER COMPOSE SERVICES
# =============================================================================
if [[ -d "$ELITE_DIR" ]]; then
    echo "  Stopping Elite Docker Compose services..."
    (cd "$ELITE_DIR" && docker compose -f docker-compose.yml -f docker-compose.standalone.yml down --volumes --remove-orphans) || {
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
MSSQL_DIR="$ELITE_DIR/mssql"
if [[ -d "$MSSQL_DIR" ]]; then
    echo "  Cleaning up SQL Server data..."
    sudo rm -rf "$MSSQL_DIR" 2>/dev/null || rm -rf "$MSSQL_DIR" 2>/dev/null || true
fi

echo "All Elite services stopped"
