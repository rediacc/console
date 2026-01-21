#!/bin/bash
# Backend management for local development and CI
# Uses console's self-contained docker-compose (.ci/docker/ci/)
#
# Usage:
#   source .ci/lib/elite-backend.sh
#   backend_start
#   backend_health
#   backend_stop

# Source constants and utilities
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../config/constants.sh"
source "$SCRIPT_DIR/../scripts/lib/common.sh"

# =============================================================================
# IMAGE MANAGEMENT
# =============================================================================

# Pull Docker images from GHCR
backend_pull_images() {
    check_docker

    log_step "Pulling Docker images from ghcr.io"

    # Authenticate with GitHub (if GITHUB_TOKEN set)
    if [[ -n "${GITHUB_TOKEN:-}" ]]; then
        log_debug "Authenticating with ghcr.io"
        echo "$GITHUB_TOKEN" | docker login ghcr.io -u "${GITHUB_USER:-$(whoami)}" --password-stdin &>/dev/null || {
            log_warn "GitHub authentication failed, proceeding without auth"
            log_warn "Set GITHUB_TOKEN environment variable for authentication"
        }
    fi

    # Pull images (using ELITE_IMAGE_* for backward compatibility)
    local images=("${DOCKER_REGISTRY}/web:${DOCKER_TAG}" "${DOCKER_REGISTRY}/api:${DOCKER_TAG}" "$ELITE_IMAGE_SQL")
    local image

    for image in "${images[@]}"; do
        log_info "Pulling: $image"
        run_with_timeout "$TIMEOUT_DOCKER_PULL" docker pull --quiet "$image" || {
            log_error "Failed to pull image: $image"
            return 1
        }
    done

    log_info "All images pulled successfully"
}

# =============================================================================
# SERVICE LIFECYCLE
# =============================================================================

# Start backend services
backend_start() {
    check_docker

    log_step "Starting backend services"

    # Source CI environment
    source "$CI_DIR/scripts/infra/ci-env.sh"

    # Prepare mssql directory for SQL Server
    local mssql_dir="$CI_DOCKER_DIR/mssql"
    if [[ -d "$mssql_dir" ]]; then
        rm -rf "$mssql_dir"
    fi
    mkdir -p "$mssql_dir"
    # Set ownership for SQL Server (UID 10001)
    sudo chown -R 10001:10001 "$mssql_dir" 2>/dev/null || chmod -R 777 "$mssql_dir"

    # Start services
    (cd "$CI_DOCKER_DIR" && docker compose -f docker-compose.yml up -d) || {
        log_error "Failed to start backend services"
        return 1
    }

    log_info "Backend services started"

    # Save backend state
    echo "started=$(date +%s)" > "$BACKEND_STATE_FILE"
}

# Wait for backend health check
backend_health() {
    local endpoint="${API_URL_LOCAL}${API_HEALTH_ENDPOINT}"
    local timeout="${API_HEALTH_TIMEOUT}"
    local interval="${API_HEALTH_INTERVAL}"
    local elapsed=0

    log_step "Waiting for backend health check (timeout: ${timeout}s)"

    while [[ $elapsed -lt $timeout ]]; do
        if curl -sf --connect-timeout 2 --max-time 5 "$endpoint" &>/dev/null; then
            log_info "Backend is healthy"
            return 0
        fi

        sleep "$interval"
        elapsed=$((elapsed + interval))

        # Progress indicator
        if (( elapsed % 10 == 0 )); then
            log_debug "Waiting... (${elapsed}s / ${timeout}s)"
        fi
    done

    log_error "Backend health check timed out after ${timeout}s"
    log_info "Check logs with: ./go backend logs"
    return 1
}

# Stop backend services
backend_stop() {
    check_docker

    log_step "Stopping backend services"

    if [[ -d "$CI_DOCKER_DIR" ]]; then
        (cd "$CI_DOCKER_DIR" && docker compose -f docker-compose.yml down --volumes --remove-orphans) || {
            log_warn "Docker compose down failed, forcing container removal"
        }
        # Clean up mssql data
        rm -rf "$CI_DOCKER_DIR/mssql" 2>/dev/null || true
    fi

    # Force remove containers if they still exist
    docker stop "$CI_CONTAINER_WEB" "$CI_CONTAINER_API" "$CI_CONTAINER_SQL" 2>/dev/null || true
    docker rm "$CI_CONTAINER_WEB" "$CI_CONTAINER_API" "$CI_CONTAINER_SQL" 2>/dev/null || true

    # Remove state file
    rm -f "$BACKEND_STATE_FILE"

    log_info "Backend services stopped"
}

# Show service logs
backend_logs() {
    local service="${1:-all}"

    check_docker

    case "$service" in
        api)
            docker logs -f "$CI_CONTAINER_API"
            ;;
        sql)
            docker logs -f "$CI_CONTAINER_SQL"
            ;;
        web)
            docker logs -f "$CI_CONTAINER_WEB"
            ;;
        all|"")
            log_info "Showing logs for all services (Ctrl+C to exit)"
            docker logs -f "$CI_CONTAINER_API" 2>&1 &
            docker logs -f "$CI_CONTAINER_SQL" 2>&1 &
            docker logs -f "$CI_CONTAINER_WEB" 2>&1 &
            wait
            ;;
        *)
            log_error "Unknown service: $service"
            log_info "Valid services: api, sql, web, all"
            return 1
            ;;
    esac
}

# Show service status
backend_status() {
    check_docker

    log_info "Backend Status"
    log_info "=============="
    echo ""

    # Check if containers are running
    local running=0
    local containers=("$CI_CONTAINER_WEB" "$CI_CONTAINER_API" "$CI_CONTAINER_SQL")
    local container

    for container in "${containers[@]}"; do
        if docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
            local status
            status=$(docker inspect -f '{{.State.Status}}' "$container")
            local health
            health=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "N/A")

            echo -e "${COLOR_GREEN}+${COLOR_NC} $container (status: $status, health: $health)"
            running=$((running + 1))
        else
            echo -e "${COLOR_RED}x${COLOR_NC} $container (not running)"
        fi
    done

    echo ""

    # Check health endpoint
    if curl -sf "${API_URL_LOCAL}${API_HEALTH_ENDPOINT}" &>/dev/null; then
        echo -e "${COLOR_GREEN}+${COLOR_NC} API health check: PASSED"
    else
        echo -e "${COLOR_RED}x${COLOR_NC} API health check: FAILED"
    fi

    echo ""

    # Show uptime
    if [[ -f "$BACKEND_STATE_FILE" ]]; then
        local started
        started=$(grep "^started=" "$BACKEND_STATE_FILE" | cut -d= -f2)
        if [[ -n "$started" ]]; then
            local uptime=$(($(date +%s) - started))
            echo "Uptime: $(printf '%02d:%02d:%02d' $((uptime/3600)) $((uptime%3600/60)) $((uptime%60)))"
        fi
    fi
}

# Reset backend (stop, remove volumes, fresh start)
backend_reset() {
    check_docker

    log_warn "This will delete all backend data (SQL database, volumes)"

    if ! prompt_continue "Are you sure"; then
        log_info "Reset cancelled"
        return 0
    fi

    log_step "Resetting backend"

    # Stop services
    backend_stop

    # Remove any leftover volumes
    docker volume ls -q | grep -E "^(rediacc|ci)" | xargs -r docker volume rm 2>/dev/null || true

    log_info "Backend reset complete"
    log_info "Start fresh with: ./go backend start"
}

# =============================================================================
# ALIASES (backward compatibility for existing scripts)
# =============================================================================
elite_start() { backend_start "$@"; }
elite_stop() { backend_stop "$@"; }
elite_health() { backend_health "$@"; }
elite_logs() { backend_logs "$@"; }
elite_status() { backend_status "$@"; }
elite_reset() { backend_reset "$@"; }
elite_pull_images() { backend_pull_images "$@"; }
