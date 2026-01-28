#!/bin/bash
# Local development utilities for console ./run.sh script
# This file bridges console development with CI infrastructure
#
# Usage: source "$ROOT_DIR/.ci/lib/local-common.sh"

# Prevent multiple sourcing
[[ -n "${LOCAL_COMMON_LOADED:-}" ]] && return 0
LOCAL_COMMON_LOADED=1

# =============================================================================
# SETUP
# =============================================================================

# Get directories
LOCAL_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_CI_DIR="$(cd "$LOCAL_LIB_DIR/.." && pwd)"
LOCAL_ROOT_DIR="$(cd "$LOCAL_CI_DIR/.." && pwd)"

# Source CI common library for logging, validation, etc.
source "$LOCAL_CI_DIR/scripts/lib/common.sh"

# =============================================================================
# CONSOLE-SPECIFIC HELPERS
# =============================================================================

# Check if middleware API is available
# Returns: 0 if available, 1 otherwise
check_middleware() {
    local api_url="${VITE_API_URL:-http://localhost:7322/api}"
    local health_endpoint="${api_url}/health"

    log_debug "Checking middleware availability at: $health_endpoint"

    if curl -s -f --connect-timeout 2 --max-time 5 "$health_endpoint" &>/dev/null; then
        log_debug "Middleware is available"
        return 0
    else
        log_debug "Middleware is not available"
        return 1
    fi
}

# Smart dependency installation (only if needed)
# Checks if node_modules is up-to-date before running npm install
ensure_deps() {
    if [[ ! -d "$LOCAL_ROOT_DIR/node_modules" ]] || \
       [[ "$LOCAL_ROOT_DIR/package-lock.json" -nt "$LOCAL_ROOT_DIR/node_modules" ]]; then
        log_step "Installing dependencies..."
        (cd "$LOCAL_ROOT_DIR" && npm install)
    else
        log_debug "Dependencies are up-to-date"
    fi
}

# Ensure shared packages are built
# Required before running tests or building web/CLI
ensure_packages_built() {
    local shared_dist="$LOCAL_ROOT_DIR/packages/shared/dist"
    local shared_src="$LOCAL_ROOT_DIR/packages/shared/src"

    # Check if shared package needs rebuilding
    if [[ ! -d "$shared_dist" ]] || \
       [[ "$shared_src" -nt "$shared_dist" ]]; then
        log_step "Building shared packages..."
        "$LOCAL_CI_DIR/scripts/setup/build-packages.sh"
    else
        log_debug "Shared packages are up-to-date"
    fi
}

# Prompt user to continue with a yes/no question
# Usage: prompt_continue "Message" || exit 1
# Returns: 0 if user confirmed (y/Y), 1 otherwise
prompt_continue() {
    local message="${1:-Continue?}"
    local response

    read -p "$message (y/N): " response
    [[ "$response" =~ ^[yY]$ ]]
}

# Open browser on different platforms
# Usage: open_browser "http://localhost:3000"
open_browser() {
    local url="$1"

    case "$CI_OS" in
        macos)
            open "$url" 2>/dev/null || true
            ;;
        linux)
            if command -v xdg-open &>/dev/null; then
                xdg-open "$url" 2>/dev/null || true
            fi
            ;;
        windows)
            start "$url" 2>/dev/null || true
            ;;
    esac
}

# Check if a specific package.json script exists
# Usage: has_npm_script "lint" && npm run lint
has_npm_script() {
    local script_name="$1"
    grep -q "\"$script_name\":" "$LOCAL_ROOT_DIR/package.json"
}

# Run npm script with error handling
# Usage: run_npm_script "build:web" "Building web application"
run_npm_script() {
    local script_name="$1"
    local description="${2:-Running npm script: $script_name}"

    log_step "$description"
    (cd "$LOCAL_ROOT_DIR" && npm run "$script_name")
}

# Check Node.js version meets minimum requirement
# Usage: check_node_version "18.0.0"
check_node_version() {
    local min_version="${1:-18.0.0}"
    local current_version

    if ! command -v node &>/dev/null; then
        log_error "Node.js is not installed"
        return 1
    fi

    current_version=$(node -v | cut -d'v' -f2)

    if ! printf '%s\n' "$min_version" "$current_version" | sort -V -C; then
        log_error "Node.js version $current_version is too old (minimum: $min_version)"
        return 1
    fi

    log_debug "Node.js version: $current_version"
    return 0
}

# Export for use in subprocesses
export LOCAL_ROOT_DIR
export LOCAL_CI_DIR
export LOCAL_LIB_DIR
