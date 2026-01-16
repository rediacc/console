#!/bin/bash
# Common utilities for console scripts
# Provides logging, error handling, and helper functions
#
# ⚠️  IMPORTANT: When adding/modifying utility functions:
# ⚠️  1. Update this file (common.sh)
# ⚠️  2. Use the functions in the main 'go' script (console/go) if needed
# ⚠️  3. Document any new utilities

# Source constants if not already loaded
if [[ -z "${CONSOLE_ROOT_DIR:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
    source "$SCRIPT_DIR/config/constants.sh"
fi

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================

# Log with timestamp and level
_log() {
    local level="$1"
    shift
    local message="$*"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    echo -e "${timestamp} [${level}] ${message}" >&2
}

# Log info message (green)
log_info() {
    echo -e "${COLOR_GREEN}✓${COLOR_NC} $*" >&2
}

# Log step message (cyan, bold)
log_step() {
    echo "" >&2
    echo -e "${COLOR_CYAN}▶${COLOR_NC} $*" >&2
}

# Log warning message (yellow)
log_warn() {
    echo -e "${COLOR_YELLOW}⚠${COLOR_NC} $*" >&2
}

# Log error message (red)
log_error() {
    echo -e "${COLOR_RED}✗${COLOR_NC} $*" >&2
}

# Log debug message (only if DEBUG=1)
log_debug() {
    if [[ "${DEBUG:-0}" == "1" ]]; then
        echo -e "${COLOR_BLUE}[DEBUG]${COLOR_NC} $*" >&2
    fi
}

# =============================================================================
# ERROR HANDLING
# =============================================================================

# Exit with error message
die() {
    log_error "$@"
    exit 1
}

# Check if command exists
require_command() {
    local cmd="$1"
    local install_hint="${2:-}"

    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required command not found: $cmd"
        if [[ -n "$install_hint" ]]; then
            log_info "Install with: $install_hint"
        fi
        exit 1
    fi
}

# Check if file exists
require_file() {
    local file="$1"
    local hint="${2:-}"

    if [[ ! -f "$file" ]]; then
        log_error "Required file not found: $file"
        if [[ -n "$hint" ]]; then
            log_info "$hint"
        fi
        exit 1
    fi
}

# Check if directory exists
require_directory() {
    local dir="$1"
    local hint="${2:-}"

    if [[ ! -d "$dir" ]]; then
        log_error "Required directory not found: $dir"
        if [[ -n "$hint" ]]; then
            log_info "$hint"
        fi
        exit 1
    fi
}

# =============================================================================
# USER INTERACTION
# =============================================================================

# Prompt user to continue (y/N)
prompt_continue() {
    local message="${1:-Continue}"
    local response

    read -p "$message? (y/N): " response
    [[ "$response" =~ ^[yY]$ ]]
}

# Prompt user for input with default
prompt_input() {
    local prompt="$1"
    local default="${2:-}"
    local response

    if [[ -n "$default" ]]; then
        read -p "$prompt [$default]: " response
        echo "${response:-$default}"
    else
        read -p "$prompt: " response
        echo "$response"
    fi
}

# =============================================================================
# DOCKER UTILITIES
# =============================================================================

# Check if Docker is running
check_docker() {
    require_command docker "https://docs.docker.com/get-docker/"

    if ! docker info &>/dev/null; then
        log_error "Docker is not running"
        log_info "Start Docker Desktop or Docker daemon"
        exit 1
    fi
}

# Check if container is running
is_container_running() {
    local container="$1"
    docker ps --format "{{.Names}}" 2>/dev/null | grep -q "^${container}$"
}

# Wait for container to be healthy
wait_for_container_health() {
    local container="$1"
    local timeout="${2:-60}"
    local elapsed=0

    while [[ $elapsed -lt $timeout ]]; do
        if docker inspect "$container" &>/dev/null; then
            local status
            status=$(docker inspect -f '{{.State.Status}}' "$container")

            if [[ "$status" == "running" ]]; then
                # Check health if health check is defined
                local health
                health=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "N/A")

                if [[ "$health" == "healthy" ]] || [[ "$health" == "N/A" ]]; then
                    return 0
                fi
            fi
        fi

        sleep 2
        elapsed=$((elapsed + 2))
    done

    return 1
}

# =============================================================================
# FILE UTILITIES
# =============================================================================

# Create directory if it doesn't exist
ensure_directory() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir" || die "Failed to create directory: $dir"
    fi
}

# Backup file if it exists
backup_file() {
    local file="$1"
    if [[ -f "$file" ]]; then
        local backup="${file}.backup.$(date +%Y%m%d_%H%M%S)"
        cp "$file" "$backup"
        log_debug "Backed up $file to $backup"
    fi
}

# =============================================================================
# VERSION COMPARISON
# =============================================================================

# Compare semantic versions (returns 0 if v1 >= v2)
version_gte() {
    local v1="$1"
    local v2="$2"

    # Remove 'v' prefix if present
    v1="${v1#v}"
    v2="${v2#v}"

    # Compare using sort -V
    local highest
    highest=$(printf "%s\n%s" "$v1" "$v2" | sort -V | tail -n1)

    [[ "$highest" == "$v1" ]]
}

# =============================================================================
# ENVIRONMENT UTILITIES
# =============================================================================

# Load environment file
load_env() {
    local env_file="$1"

    if [[ ! -f "$env_file" ]]; then
        log_warn "Environment file not found: $env_file"
        return 1
    fi

    # Export variables from .env file
    set -a
    source "$env_file"
    set +a

    log_debug "Loaded environment from: $env_file"
}

# Generate random password
generate_password() {
    local length="${1:-20}"
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-"$length"
}

# =============================================================================
# PROCESS UTILITIES
# =============================================================================

# Run command with timeout
run_with_timeout() {
    local timeout="$1"
    shift

    timeout "$timeout" "$@"
}

# Kill process by port
kill_port() {
    local port="$1"
    local pid

    pid=$(lsof -ti:"$port" 2>/dev/null || true)
    if [[ -n "$pid" ]]; then
        log_info "Killing process on port $port (PID: $pid)"
        kill -9 "$pid" 2>/dev/null || true
    fi
}

# =============================================================================
# VALIDATION
# =============================================================================

# Validate URL format
is_valid_url() {
    local url="$1"
    [[ "$url" =~ ^https?:// ]]
}

# Validate port number
is_valid_port() {
    local port="$1"
    [[ "$port" =~ ^[0-9]+$ ]] && [[ "$port" -ge 1 ]] && [[ "$port" -le 65535 ]]
}

# Check if port is available
is_port_available() {
    local port="$1"
    ! lsof -i:"$port" &>/dev/null
}
