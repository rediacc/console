#!/bin/bash
# Backend management for local development
# Thin wrappers around CI scripts (.ci/scripts/infra/)
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

# Start backend services (delegates to CI script)
backend_start() {
    check_docker
    "$CI_SCRIPTS_DIR/infra/ci-start.sh" || {
        log_error "Failed to start backend services"
        return 1
    }

    # Save backend state for uptime tracking
    echo "started=$(date +%s)" >"$BACKEND_STATE_FILE"
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
        if ((elapsed % 10 == 0)); then
            log_debug "Waiting... (${elapsed}s / ${timeout}s)"
        fi
    done

    log_error "Backend health check timed out after ${timeout}s"
    log_info "Check logs with: ./run.sh backend logs"
    return 1
}

# Stop backend services (delegates to CI script)
backend_stop() {
    check_docker
    log_step "Stopping backend services"
    "$CI_SCRIPTS_DIR/infra/ci-stop.sh"
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
        all | "")
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
            echo "Uptime: $(printf '%02d:%02d:%02d' $((uptime / 3600)) $((uptime % 3600 / 60)) $((uptime % 60)))"
        fi
    fi
}

# =============================================================================
# VM PROVISIONING
# =============================================================================

# Provision KVM VMs (delegates to CI script)
provision_start() {
    ensure_renet_built
    "$CI_SCRIPTS_DIR/infra/ci-provision-start.sh" "$@" || {
        log_error "Failed to provision VMs"
        return 1
    }
}

# Stop provisioned VMs (delegates to CI script)
provision_stop() {
    "$CI_SCRIPTS_DIR/infra/ci-provision-stop.sh"
    log_info "VMs stopped"
}

# Show VM provision status
provision_status() {
    log_info "VM Provision Status"
    log_info "==================="
    echo ""

    # Check state file
    if [[ -f "$PROVISION_STATE_FILE" ]]; then
        local bridge_ip worker_ips vm_os started
        bridge_ip=$(grep "^bridge_ip=" "$PROVISION_STATE_FILE" | cut -d= -f2)
        worker_ips=$(grep "^worker_ips=" "$PROVISION_STATE_FILE" | cut -d= -f2)
        vm_os=$(grep "^vm_os=" "$PROVISION_STATE_FILE" | cut -d= -f2)
        started=$(grep "^started=" "$PROVISION_STATE_FILE" | cut -d= -f2)

        echo "  OS:         ${vm_os:-unknown}"
        echo "  Bridge IP:  ${bridge_ip:-unknown}"
        echo "  Worker IPs: ${worker_ips:-unknown}"

        if [[ -n "$started" ]]; then
            local uptime=$(($(date +%s) - started))
            echo "  Uptime:     $(printf '%02d:%02d:%02d' $((uptime / 3600)) $((uptime % 3600 / 60)) $((uptime % 60)))"
        fi
        echo ""
    else
        echo "  No provision state file found"
        echo "  Start VMs with: ./run.sh provision start"
        echo ""
    fi

    # Show virsh status if available
    if command -v virsh &>/dev/null; then
        echo "  VM List (virsh):"
        sudo virsh list --all 2>/dev/null | sed 's/^/    /' || echo "    (virsh not available or no VMs)"
        echo ""
    fi
}

# =============================================================================
# BACKEND MANAGEMENT (continued)
# =============================================================================

# Reset backend (stop, remove volumes, fresh start)
backend_reset() {
    check_docker

    log_warn "This will delete all backend data (SQL database, volumes)"

    if ! prompt_continue "Are you sure"; then
        log_info "Reset cancelled"
        return 0
    fi

    log_step "Resetting backend"

    backend_stop

    # Remove any leftover volumes
    docker volume ls -q | grep -E "^(rediacc|ci)" | xargs -r docker volume rm 2>/dev/null || true

    log_info "Backend reset complete"
    log_info "Start fresh with: ./run.sh backend start"
}
