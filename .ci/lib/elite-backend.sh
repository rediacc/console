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

# Auto-start backend (idempotent, safe for postStartCommand)
# Skips gracefully if Docker unavailable or backend already healthy.
# Never returns non-zero so it doesn't block devcontainer startup.
backend_auto() {
    if ! command -v docker &>/dev/null || ! docker info &>/dev/null; then
        log_info "Docker not available, skipping backend auto-start"
        return 0
    fi

    # Idempotency: skip if already healthy
    if curl -sf --connect-timeout 2 --max-time 5 "${API_URL_LOCAL}${API_HEALTH_ENDPOINT}" &>/dev/null; then
        log_info "Backend already healthy, skipping auto-start"
        return 0
    fi

    log_step "Auto-starting backend services..."

    # In Codespaces, ci-start.sh skips 'docker compose build' and expects
    # pre-pulled images. Pull them now (web, api, sql from GHCR).
    # license-server has no GHCR image — compose builds it from source.
    if [[ -n "${CODESPACES:-}" || -n "${GITHUB_ACTIONS:-}" ]]; then
        backend_pull_images || {
            log_warn "Image pull failed, will try compose up anyway"
        }
    fi

    backend_start || {
        log_warn "Backend auto-start failed, continuing without backend"
        return 0
    }

    log_info "Backend auto-start complete"
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
        while IFS='=' read -r key value; do
            case "$key" in
                bridge_ip) bridge_ip="$value" ;;
                worker_ips) worker_ips="$value" ;;
                vm_os) vm_os="$value" ;;
                started) started="$value" ;;
            esac
        done <"$PROVISION_STATE_FILE"

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

# Auto-provision VMs (idempotent, safe for postStartCommand)
# Skips gracefully if KVM unavailable or VMs already running.
# Never returns non-zero so it doesn't block devcontainer startup.
provision_auto() {
    # Graceful skip if KVM unavailable
    if [[ ! -e /dev/kvm ]]; then
        log_info "KVM not available, skipping VM provisioning"
        return 0
    fi

    # Graceful skip if libvirtd not running
    if ! pgrep -x libvirtd >/dev/null 2>&1; then
        log_warn "libvirtd not running (was start-kvm.sh called first?)"
        return 0
    fi

    # Idempotency: skip if VMs are already running
    if sudo virsh list --all 2>/dev/null | grep -q "running"; then
        log_info "VMs already running, skipping provisioning"
        provision_post_setup
        return 0
    fi

    # Delegate to existing provisioning
    provision_start "$@" || {
        log_warn "VM provisioning failed, continuing without VMs"
        return 0
    }

    provision_post_setup
}

# Post-provision setup: fix SSH keys, configure SSH, write .vm-info
provision_post_setup() {
    provision_fix_ssh_keys
    provision_setup_ssh_config
    provision_write_vm_info
}

# Fix root-owned SSH keys created by sudo renet ops up
provision_fix_ssh_keys() {
    local renet_dir="$HOME/.renet"
    if [[ -d "$renet_dir" ]]; then
        sudo chown -R "$(id -u):$(id -g)" "$renet_dir"
        log_info "SSH key permissions fixed"
    fi
}

# Configure ~/.ssh/config for passwordless SSH to VMs
provision_setup_ssh_config() {
    local ssh_config="$HOME/.ssh/config"
    local marker="# Rediacc VMs (auto-generated)"

    mkdir -p "$(dirname "$ssh_config")"

    if [[ -f "$ssh_config" ]] && grep -q "$marker" "$ssh_config"; then
        return 0
    fi

    cat >>"$ssh_config" <<-EOF

	$marker
	Host 192.168.111.*
	    User vscode
	    IdentityFile ~/.renet/staging/.ssh/id_rsa
	    StrictHostKeyChecking no
	    UserKnownHostsFile /dev/null
	    LogLevel ERROR
	EOF
    chmod 600 "$ssh_config"
    log_info "SSH config updated for VM access"
}

# Generate .vm-info developer info file from .provision-state
provision_write_vm_info() {
    if [[ ! -f "$PROVISION_STATE_FILE" ]]; then
        return 0
    fi

    local bridge_ip worker_ips vm_password vm_os started
    while IFS='=' read -r key value; do
        case "$key" in
            bridge_ip) bridge_ip="$value" ;;
            worker_ips) worker_ips="$value" ;;
            vm_password) vm_password="$value" ;;
            vm_os) vm_os="$value" ;;
            started) started="$value" ;;
        esac
    done <"$PROVISION_STATE_FILE"

    local ssh_cmds="  ssh $bridge_ip     # Bridge"
    local i=1
    IFS=',' read -ra workers <<<"$worker_ips"
    for ip in "${workers[@]}"; do
        ssh_cmds+=$'\n'"  ssh $ip    # Worker $i"
        i=$((i + 1))
    done

    local ts
    ts=$(date -d "@$started" '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null || echo "unknown")

    cat >"$CONSOLE_ROOT_DIR/.vm-info" <<-EOF
	=== Rediacc VM Environment ===
	Provisioned: $ts

	Bridge VM:    $bridge_ip
	Worker VMs:   $(echo "$worker_ips" | sed 's/,/, /g')
	VM OS:        $vm_os
	SSH User:     vscode
	SSH Password: $vm_password

	SSH Commands:
	$ssh_cmds

	SSH Key (auto-configured in ~/.ssh/config):
	  ~/.renet/staging/.ssh/id_rsa

	Quick Commands:
	  ./run.sh provision status   # Check VM status
	  ./run.sh provision stop     # Destroy VMs
	  ./run.sh provision start    # Re-provision VMs
	  sudo virsh list --all       # List all VMs
	EOF
    log_info "VM info written to .vm-info"
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
