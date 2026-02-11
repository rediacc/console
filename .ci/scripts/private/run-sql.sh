#!/bin/bash
# Run SQL submodule CI if available
#
# Usage: .ci/scripts/private/run-sql.sh [stage]
#   Stages: quality, test-standalone (default: quality)
#
# This is a thin wrapper that delegates to the sql submodule's test
# infrastructure. If the submodule is not available, it exits cleanly.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STAGE="${1:-quality}"
REPO_ROOT="$(get_repo_root)"
SQL_DIR="$REPO_ROOT/private/sql"
COORDINATOR_DIR="$SQL_DIR/coordinator"

# Check if sql submodule is available
if [[ ! -d "$SQL_DIR" ]] || [[ ! -f "$SQL_DIR/run.sh" ]]; then
    log_warn "SQL submodule not available, skipping"
    exit 0
fi

run_quality() {
    # Coordinator quality: lint, format, typecheck, integration tests
    if [[ ! -f "$COORDINATOR_DIR/package.json" ]]; then
        log_warn "SQL coordinator not available, skipping"
        exit 0
    fi

    cd "$COORDINATOR_DIR"

    if [[ ! -d "node_modules" ]]; then
        log_step "Installing coordinator dependencies..."
        npm ci
    fi

    if [[ -f "biome.json" ]] || [[ -f "biome.jsonc" ]]; then
        log_step "Running coordinator quality checks..."
        npm run check
    else
        log_warn "No biome config found, skipping lint/format checks"
    fi

    log_step "Running coordinator typecheck..."
    npm run typecheck

    log_step "Starting test infrastructure..."
    npm run test:setup

    log_step "Running coordinator tests..."
    local rc=0
    npm run test || rc=$?

    log_step "Stopping test infrastructure..."
    npm run test:teardown

    return $rc
}

run_test_standalone() {
    # Standalone SQL Server + HAProxy: start, health check, connection test
    cd "$SQL_DIR"

    # Create .env from template if not present
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.template" ]]; then
            cp .env.template .env
        else
            log_error "No .env or .env.template found in sql submodule"
            exit 1
        fi
    fi

    log_step "Starting standalone SQL Server..."
    ./run.sh up

    log_step "Waiting for SQL Server health..."
    local attempts=0
    while [[ $attempts -lt 20 ]]; do
        if docker exec sqlserver-sql /opt/mssql-tools18/bin/sqlcmd \
            -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1" -C \
            >/dev/null 2>&1; then
            log_step "SQL Server is healthy"
            break
        fi
        sleep 5
        attempts=$((attempts + 1))
    done

    if [[ $attempts -ge 20 ]]; then
        log_error "SQL Server failed to become healthy"
        ./run.sh down
        exit 1
    fi

    log_step "Running standalone tests..."
    ./run.sh harden
    ./run.sh db create testdb
    local rc=0
    ./run.sh test tls || rc=$?

    log_step "Stopping SQL Server..."
    ./run.sh down

    return $rc
}

case "$STAGE" in
    quality)
        run_quality
        ;;
    test-standalone)
        run_test_standalone
        ;;
    *)
        log_error "Unknown stage: $STAGE"
        echo "Valid stages: quality, test-standalone"
        exit 1
        ;;
esac
