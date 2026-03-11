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

compute_hash_for_paths() {
    local root_dir="$1"
    shift

    (
        cd "$root_dir"
        find "$@" -type f -print0 2>/dev/null |
            LC_ALL=C sort -z |
            xargs -0 sha256sum 2>/dev/null |
            sha256sum |
            awk '{print $1}'
    )
}

compute_hash_for_package_dirs() {
    local root_dir="$1"
    shift

    (
        cd "$root_dir"
        find "$@" \
            \( -path '*/dist/*' -o -path '*/node_modules/*' -o -path '*/reports/*' -o -path '*/test-results/*' \) -prune -o \
            \( -name '*.tsbuildinfo' -o -name '.DS_Store' \) -prune -o \
            -type f -print0 2>/dev/null |
            LC_ALL=C sort -z |
            xargs -0 sha256sum 2>/dev/null |
            sha256sum |
            awk '{print $1}'
    )
}

read_stamp_hash() {
    local stamp_file="$1"

    if [[ -f "$stamp_file" ]]; then
        cat "$stamp_file"
    fi
}

write_stamp_hash() {
    local stamp_file="$1"
    local stamp_hash="$2"

    mkdir -p "$(dirname "$stamp_file")"
    printf '%s\n' "$stamp_hash" >"$stamp_file"
}

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
# Uses a hash-based stamp so npm metadata-only mtime changes do not force reinstall
ensure_deps() {
    local node_modules_dir="$LOCAL_ROOT_DIR/node_modules"
    local stamp_file="$LOCAL_ROOT_DIR/.ci/cache/npm-install.stamp"
    local current_hash
    local saved_hash=""

    current_hash="$(
        {
            sha256sum "$LOCAL_ROOT_DIR/package.json"
            sha256sum "$LOCAL_ROOT_DIR/package-lock.json"
            if [[ -f "$LOCAL_ROOT_DIR/.npmrc" ]]; then
                sha256sum "$LOCAL_ROOT_DIR/.npmrc"
            fi
        } | sha256sum | awk '{print $1}'
    )"

    saved_hash="$(read_stamp_hash "$stamp_file")"

    if [[ -d "$node_modules_dir" ]] &&
        [[ -x "$node_modules_dir/.bin/tsx" ]] &&
        [[ -L "$node_modules_dir/@rediacc/cli" ]] &&
        [[ "$saved_hash" == "$current_hash" ]]; then
        log_debug "Dependencies are up-to-date (stamp matched)"
        return 0
    fi

    log_step "Installing dependencies..."
    (cd "$LOCAL_ROOT_DIR" && npm install)
    write_stamp_hash "$stamp_file" "$current_hash"
}

# Ensure shared packages are built
# Required before running tests or building web/CLI
ensure_packages_built() {
    local stamp_file="$LOCAL_ROOT_DIR/.ci/cache/build-packages.stamp"
    local current_hash
    local saved_hash=""

    current_hash="$(
        compute_hash_for_package_dirs "$LOCAL_ROOT_DIR" \
            packages/shared \
            packages/shared-desktop \
            packages/provisioning
    )"

    saved_hash="$(read_stamp_hash "$stamp_file")"

    if [[ -d "$LOCAL_ROOT_DIR/packages/shared/dist" ]] &&
        [[ -d "$LOCAL_ROOT_DIR/packages/shared-desktop/dist" ]] &&
        [[ -d "$LOCAL_ROOT_DIR/packages/provisioning/dist" ]] &&
        [[ "$saved_hash" == "$current_hash" ]]; then
        log_debug "Shared packages are up-to-date (stamp matched)"
        return 0
    fi

    log_step "Building shared packages..."
    "$LOCAL_CI_DIR/scripts/setup/build-packages.sh"
    write_stamp_hash "$stamp_file" "$current_hash"
}

ensure_cli_built() {
    local cli_dist="$LOCAL_ROOT_DIR/packages/cli/dist"
    local cli_entry="$cli_dist/cli-bundle.cjs"
    local stamp_file="$LOCAL_ROOT_DIR/.ci/cache/build-cli.stamp"
    local current_hash
    local saved_hash=""

    current_hash="$(
        compute_hash_for_package_dirs "$LOCAL_ROOT_DIR" \
            packages/cli
    )"

    saved_hash="$(read_stamp_hash "$stamp_file")"

    if [[ -f "$cli_entry" ]] && [[ "$saved_hash" == "$current_hash" ]]; then
        log_debug "CLI build is up-to-date (stamp matched)"
        return 0
    fi

    log_step "Building CLI..."
    (cd "$LOCAL_ROOT_DIR" && npm run build -w @rediacc/cli)
    (cd "$LOCAL_ROOT_DIR" && npm run build:bundle -w @rediacc/cli)

    if [[ ! -f "$cli_entry" ]]; then
        log_error "CLI build failed: entrypoint not found at $cli_entry"
        exit 1
    fi

    write_stamp_hash "$stamp_file" "$current_hash"
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

# Check if Go is installed (required for renet build)
check_go_installed() {
    if ! command -v go &>/dev/null; then
        log_error "Go is not installed (required for building renet)"
        log_info "Install Go from: https://go.dev/dl/"
        exit 1
    fi
    log_debug "Go version: $(go version)"
}

# Ensure renet binary is built and up-to-date
# Builds from Go source with embedded assets (CRIU, rsync)
# Only rebuilds when Go sources are newer than the binary
ensure_renet_built() {
    local renet_dir="$LOCAL_ROOT_DIR/private/renet"
    local renet_bin="$renet_dir/bin/renet"

    if [[ -f "$renet_bin" ]]; then
        local newer_files
        newer_files=$(find "$renet_dir" \
            \( -name "*.go" -o -name "go.mod" -o -name "go.sum" \) \
            -newer "$renet_bin" -type f 2>/dev/null | head -1)

        if [[ -z "$newer_files" ]]; then
            log_debug "Renet binary is up-to-date"
            return 0
        fi
        log_step "Renet sources changed, rebuilding..."
    else
        log_step "Building renet (first time, requires Docker for asset extraction)..."
    fi

    check_go_installed
    (cd "$renet_dir" && ./build.sh dev)

    if [[ ! -f "$renet_bin" ]]; then
        log_error "Renet build failed: binary not found at $renet_bin"
        exit 1
    fi
    log_info "Renet built successfully"
}

# Export for use in subprocesses
export LOCAL_ROOT_DIR
export LOCAL_CI_DIR
export LOCAL_LIB_DIR
