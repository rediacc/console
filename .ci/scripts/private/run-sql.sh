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

    # Generate secrets (gitignored, required by docker-compose)
    local sa_password
    sa_password="SqlCI$(openssl rand -hex 12)!"
    mkdir -p secrets
    echo -n "$sa_password" >secrets/sa_password.txt
    echo -n "$sa_password" >secrets/admin_password.txt
    export MSSQL_SA_PASSWORD="$sa_password"

    # CI mssql.conf: no TLS (certs don't exist in CI), lower memory
    cat >mssql.ci.conf <<CONF
[telemetry]
customerfeedback = false

[memory]
memorylimitmb = 2048
CONF

    # CI override: no TLS config, healthcheck uses sa (sqladmin doesn't exist until harden)
    cat >docker-compose.ci.yml <<YAML
services:
  sql:
    volumes:
      - ./mssql:/var/opt/mssql
      - ./mssql.ci.conf:/var/opt/mssql/mssql.conf
    healthcheck:
      test: ["CMD-SHELL", "/opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P \"\$\$(cat /run/secrets/sa_password)\" -Q 'SELECT 1' -C || exit 1"]
YAML
    export COMPOSE_FILE="docker-compose.yml:docker-compose.ci.yml"

    log_step "Starting standalone SQL Server..."
    ./run.sh up

    log_step "Waiting for SQL Server health..."
    local attempts=0
    while [[ $attempts -lt 30 ]]; do
        if docker exec sqlserver-sql /opt/mssql-tools18/bin/sqlcmd \
            -S localhost -U sa -P "$MSSQL_SA_PASSWORD" -Q "SELECT 1" -C \
            >/dev/null 2>&1; then
            log_step "SQL Server is healthy"
            break
        fi
        sleep 5
        attempts=$((attempts + 1))
    done

    if [[ $attempts -ge 30 ]]; then
        log_error "SQL Server failed to become healthy"
        docker logs sqlserver-sql --tail 50 2>&1 || true
        ./run.sh down
        exit 1
    fi

    log_step "Running standalone tests..."
    ./run.sh harden
    ./run.sh db create testdb

    # Verify connectivity through HAProxy (port 1433 on host)
    local admin_pass
    admin_pass=$(cat secrets/admin_password.txt)
    log_step "Testing HAProxy connectivity..."
    local rc=0
    docker run --rm --network sqlserver_public \
        mcr.microsoft.com/mssql-tools18:latest \
        /opt/mssql-tools18/bin/sqlcmd \
        -S sqlserver-haproxy,1433 -U sqladmin -P "$admin_pass" \
        -Q "SELECT DB_NAME() AS current_db, @@SERVERNAME AS server" -C || rc=$?

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
