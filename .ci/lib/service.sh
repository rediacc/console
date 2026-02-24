#!/bin/bash
# Service mode: rediacc/web + RustFS
# Lightweight stack for testing the web Docker image locally
#
# Usage:
#   source .ci/lib/service.sh
#   service_start
#   service_status
#   service_stop

# Source constants and utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/constants.sh"
source "$SCRIPT_DIR/../scripts/lib/common.sh"

# =============================================================================
# COMPOSE HELPER
# =============================================================================

_service_compose() {
    docker compose -p rediacc-service -f "$SERVICE_DOCKER_DIR/docker-compose.yml" "$@"
}

# =============================================================================
# SERVICE LIFECYCLE
# =============================================================================

# Start service (build image + start containers)
service_start() {
    check_docker

    local port="${1:-8080}"
    export SERVICE_HTTP_PORT="$port"

    log_step "Starting rediacc/web service (port: $port)"

    # Source environment (generates secrets, writes .env)
    source "$SERVICE_DOCKER_DIR/env.sh"

    # Build the web image
    log_step "Building rediacc/web:local image..."
    _service_compose build web

    # Start all services
    log_step "Starting services..."
    _service_compose up -d

    # Wait for health
    service_health || {
        log_error "Service failed to become healthy"
        log_info "Check logs with: ./run.sh service logs"
        return 1
    }

    # Save state
    echo "started=$(date +%s)" >"$SERVICE_STATE_FILE"
    echo "port=$port" >>"$SERVICE_STATE_FILE"

    log_info ""
    log_info "Service is running!"
    log_info "  Web:            http://localhost:$SERVICE_HTTP_PORT"
    log_info "  Account portal: http://localhost:$SERVICE_HTTP_PORT/account/"
    log_info "  RustFS Console: http://localhost:$SERVICE_RUSTFS_CONSOLE_PORT"
    log_info ""
    log_info "Stop with: ./run.sh service stop"
}

# Wait for service health
service_health() {
    local port="${SERVICE_HTTP_PORT:-8080}"
    local timeout=90
    local elapsed=0
    local interval=2

    log_step "Waiting for service health check (timeout: ${timeout}s)"

    while [[ $elapsed -lt $timeout ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "http://localhost:${port}/health" &>/dev/null; then
            log_info "Service is healthy"
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
        if ((elapsed % 10 == 0)); then
            log_debug "Waiting... (${elapsed}s / ${timeout}s)"
        fi
    done

    log_error "Service health check timed out after ${timeout}s"
    return 1
}

# Stop service
service_stop() {
    check_docker
    log_step "Stopping service"
    _service_compose down --volumes --remove-orphans 2>/dev/null || true

    # Force remove containers if compose down failed
    local containers=(
        rediacc-service-web
        rediacc-service-rustfs
        rediacc-service-rustfs-init
        rediacc-service-rustfs-volume-init
    )
    for container in "${containers[@]}"; do
        if docker ps -a --format "{{.Names}}" 2>/dev/null | grep -q "^${container}$"; then
            docker stop "$container" 2>/dev/null || true
            docker rm "$container" 2>/dev/null || true
        fi
    done

    rm -f "$SERVICE_STATE_FILE" 2>/dev/null || true
    log_info "Service stopped"
}

# =============================================================================
# SERVICE INFO
# =============================================================================

# Show service status
service_status() {
    check_docker

    log_info "Service Status"
    log_info "=============="
    echo ""

    local containers=(rediacc-service-web rediacc-service-rustfs)

    for container in "${containers[@]}"; do
        if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
            local status health
            status=$(docker inspect -f '{{.State.Status}}' "$container")
            health=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "N/A")
            echo -e "${COLOR_GREEN}+${COLOR_NC} $container (status: $status, health: $health)"
        else
            echo -e "${COLOR_RED}x${COLOR_NC} $container (not running)"
        fi
    done

    echo ""

    # Read port from state file
    local port=8080
    if [[ -f "$SERVICE_STATE_FILE" ]]; then
        port=$(grep "^port=" "$SERVICE_STATE_FILE" | cut -d= -f2)
        port="${port:-8080}"

        local started
        started=$(grep "^started=" "$SERVICE_STATE_FILE" | cut -d= -f2)
        if [[ -n "$started" ]]; then
            local uptime=$(($(date +%s) - started))
            echo "Uptime: $(printf '%02d:%02d:%02d' $((uptime / 3600)) $((uptime % 3600 / 60)) $((uptime % 60)))"
        fi
    fi

    # Health check
    if curl -sf "http://localhost:${port}/health" &>/dev/null; then
        echo -e "${COLOR_GREEN}+${COLOR_NC} Health check: PASSED (http://localhost:$port)"
    else
        echo -e "${COLOR_RED}x${COLOR_NC} Health check: FAILED"
    fi
    echo ""
}

# Show service logs
service_logs() {
    local service="${1:-all}"
    check_docker

    case "$service" in
        web)
            docker logs -f rediacc-service-web
            ;;
        rustfs)
            docker logs -f rediacc-service-rustfs
            ;;
        all | "")
            _service_compose logs -f
            ;;
        *)
            log_error "Unknown service: $service"
            log_info "Valid services: web, rustfs, all"
            return 1
            ;;
    esac
}
