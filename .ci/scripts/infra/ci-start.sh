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
# VERIFY SQLCMD AVAILABILITY
# =============================================================================
# go-sqlcmd should be installed via .ci/scripts/private/run-middleware.sh or install-sqlcmd.sh
if ! command -v sqlcmd &>/dev/null; then
    echo "ERROR: sqlcmd (go-sqlcmd) not found in PATH"
    echo "Install with: sudo $CONSOLE_ROOT/private/middleware/scripts/install-sqlcmd.sh"
    exit 1
fi

# =============================================================================
# PREPARE MSSQL DIRECTORY
# =============================================================================
# SQL Server 2022+ runs as non-root user (UID 10001)
# Must create directory with correct permissions before starting container
MSSQL_DIR="$CI_DOCKER_DIR/mssql"
echo "Preparing SQL Server data directory: $MSSQL_DIR"

if [[ -d "$MSSQL_DIR" ]]; then
    # Use sudo to remove directory owned by SQL Server's UID (10001)
    sudo rm -rf "$MSSQL_DIR" 2>/dev/null || rm -rf "$MSSQL_DIR" 2>/dev/null || true
fi

mkdir -p "$MSSQL_DIR"
# Set ownership to SQL Server's UID (10001) for non-root operation
sudo chown -R 10001:10001 "$MSSQL_DIR" 2>/dev/null || {
    # If sudo fails (CI environment without sudo), try chmod instead
    chmod -R 777 "$MSSQL_DIR"
}

# =============================================================================
# START SERVICES
# =============================================================================
echo "Starting Docker Compose services..."
cd "$CI_DOCKER_DIR"

docker compose -f docker-compose.yml up -d

# =============================================================================
# WAIT FOR HEALTH CHECKS
# =============================================================================
echo "Waiting for services to be ready..."

# Wait for SQL Server (using external go-sqlcmd connection)
wait_for_sql() {
    local timeout=120
    local elapsed=0
    local interval=2
    local sql_port="${SQL_PORT:-1433}"

    echo "  Waiting for SQL Server (via go-sqlcmd on port $sql_port)..."
    while [[ $elapsed -lt $timeout ]]; do
        if SQLCMDPASSWORD="$MSSQL_SA_PASSWORD" sqlcmd \
            -S "localhost,$sql_port" -U sa -Q "SELECT 1" -C &>/dev/null; then
            echo "  SQL Server is ready"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    echo "  SQL Server failed to start within ${timeout}s"
    return 1
}

# Wait for API
wait_for_api() {
    local timeout=180
    local elapsed=0
    local interval=2

    echo "  Waiting for API..."
    while [[ $elapsed -lt $timeout ]]; do
        if docker inspect rediacc-api --format='{{.State.Health.Status}}' 2>/dev/null | grep -q "healthy"; then
            echo "  API is healthy"
            return 0
        fi
        # Also check if container is running
        if ! docker ps --format "{{.Names}}" | grep -q "^rediacc-api$"; then
            echo "  API container stopped unexpectedly"
            docker logs rediacc-api --tail 50 || true
            return 1
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
        if ((elapsed % 20 == 0)); then
            echo "    Still waiting... (${elapsed}s / ${timeout}s)"
        fi
    done
    echo "  API failed to become healthy within ${timeout}s"
    docker logs rediacc-api --tail 100 || true
    return 1
}

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

# Wait for License Server
wait_for_license_server() {
    local timeout=60
    local elapsed=0
    local interval=2

    echo "  Waiting for License Server..."
    while [[ $elapsed -lt $timeout ]]; do
        if curl -sf http://localhost:3000/health &>/dev/null; then
            echo "  License Server is ready"
            return 0
        fi
        # Also check via docker if port mapping isn't exposed
        if docker exec rediacc-license-server node -e "fetch('http://localhost:3000/health').then(r=>{if(!r.ok)process.exit(1)})" &>/dev/null; then
            echo "  License Server is ready (via container)"
            return 0
        fi
        sleep $interval
        elapsed=$((elapsed + interval))
    done
    echo "  License Server failed to start within ${timeout}s"
    return 1
}

# Execute health checks in sequence
wait_for_sql || {
    echo "Service startup failed: SQL Server"
    docker compose logs
    exit 1
}

wait_for_license_server || {
    echo "Service startup failed: License Server"
    docker compose logs license-server license-rustfs
    exit 1
}

wait_for_api || {
    echo "Service startup failed: API"
    docker compose logs
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
