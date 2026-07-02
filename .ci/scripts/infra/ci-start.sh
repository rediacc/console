#!/bin/bash
# CI Service Startup Script
# Starts backend services and waits for health checks
# Self-contained replacement for elite/action/ci-start.sh
#
# Usage:
#   .ci/scripts/infra/ci-start.sh
#
# Outputs (for GitHub Actions):
#   api-url - The base URL for the API (http://localhost)

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "Starting Rediacc CI services..."

# =============================================================================
# SOURCE ENVIRONMENT
# =============================================================================
# shellcheck source=ci-env.sh
source "$SCRIPT_DIR/ci-env.sh"

# =============================================================================
# START SERVICES
# =============================================================================
echo "Starting Docker Compose services..."
cd "$CI_DOCKER_DIR"

# When running locally (not in CI or Codespaces), build images from source
# to ensure they match the current codebase.
# In CI/Codespaces, images are pre-built and pre-pulled — skip building.
if [[ -z "${GITHUB_ACTIONS:-}" && -z "${CODESPACES:-}" ]]; then
    echo "Building Docker images from source..."
    docker compose -f docker-compose.yml build
fi

docker compose -f docker-compose.yml up -d

# =============================================================================
# WAIT FOR HEALTH CHECKS
# =============================================================================
echo "Waiting for services to be ready..."

# Wait for Web
wait_for_web() {
    local timeout=60
    local elapsed=0
    local interval=2

    echo "  Waiting for Web (nginx)..."
    while [[ $elapsed -lt $timeout ]]; do
        if curl -sf http://localhost/health &>/dev/null; then
            echo "  Web is ready"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    echo "  Web failed to start within ${timeout}s"
    return 1
}

# Wait for Account Server
wait_for_account_server() {
    local timeout=60
    local elapsed=0
    local interval=2

    echo "  Waiting for Account Server..."
    while [[ $elapsed -lt $timeout ]]; do
        if curl -sf http://localhost:3000/health &>/dev/null; then
            echo "  Account Server is ready"
            return 0
        fi
        # Also check via docker if port mapping isn't exposed
        if docker exec rediacc-account-server node -e "fetch('http://localhost:3000/health').then(r=>{if(!r.ok)process.exit(1)})" &>/dev/null; then
            echo "  Account Server is ready (via container)"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    echo "  Account Server failed to start within ${timeout}s"
    return 1
}

# Execute health checks in sequence
wait_for_account_server || {
    echo "Service startup failed: Account Server"
    docker compose logs account-server
    exit 1
}

wait_for_web || {
    echo "Service startup failed: Web"
    docker compose logs
    exit 1
}

echo ""
echo "All services are ready!"

# =============================================================================
# OUTPUT FOR GITHUB ACTIONS
# =============================================================================
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "api-url=http://localhost" >>"$GITHUB_OUTPUT"
    echo "deployment-target=runner" >>"$GITHUB_OUTPUT"
fi

# Show running containers
echo ""
echo "Running containers:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "(NAME|rediacc)" || true
