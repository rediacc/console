#!/bin/bash
# Backend URL management for test infrastructure
# Provides URL resolution and validation for external backends
#
# Usage:
#   source "$SCRIPT_DIR/../../lib/backend-url.sh"
#   BACKEND_URL=$(resolve_backend_url "sandbox")
#   wait_for_backend "$BACKEND_URL" 30

# Prevent re-sourcing
[[ -n "${BACKEND_URL_LOADED:-}" ]] && return 0
readonly BACKEND_URL_LOADED=1

# =============================================================================
# BACKEND PRESETS
# =============================================================================

# Associative array for backend presets
declare -A BACKEND_PRESETS=(
    ["local"]="http://localhost:7322"
    ["sandbox"]="https://sandbox.rediacc.com"
)

# =============================================================================
# URL RESOLUTION
# =============================================================================

# Resolve preset name to URL or validate URL format
# Usage: resolve_backend_url "sandbox" OR resolve_backend_url "https://xxx.trycloudflare.com"
# Returns: URL string on stdout, exit code 0 on success, 1 on failure
resolve_backend_url() {
    local input="$1"

    # Check if it's a preset
    if [[ -n "${BACKEND_PRESETS[$input]:-}" ]]; then
        echo "${BACKEND_PRESETS[$input]}"
        return 0
    fi

    # Check if it's a valid URL
    if [[ "$input" =~ ^https?:// ]]; then
        echo "$input"
        return 0
    fi

    # Invalid input
    return 1
}

# List available presets
# Usage: list_backend_presets
list_backend_presets() {
    echo "Available presets:"
    for preset in "${!BACKEND_PRESETS[@]}"; do
        echo "  $preset -> ${BACKEND_PRESETS[$preset]}"
    done
}

# =============================================================================
# HEALTH VALIDATION
# =============================================================================

# Check if backend is accessible (single check)
# Usage: validate_backend_url "http://localhost:7322" [timeout_seconds]
# Returns: 0 if healthy, 1 if not
validate_backend_url() {
    local url="$1"
    local timeout="${2:-10}"

    # Try the health endpoint
    curl -sf --connect-timeout "$timeout" --max-time "$((timeout * 2))" "${url}/api/health" &>/dev/null
}

# Wait for backend with retries
# Usage: wait_for_backend "http://localhost:7322" [timeout_seconds]
# Returns: 0 if healthy within timeout, 1 if timeout exceeded
wait_for_backend() {
    local url="$1"
    local timeout="${2:-30}"
    local interval=2
    local elapsed=0

    while [[ $elapsed -lt $timeout ]]; do
        if validate_backend_url "$url" 5; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    return 1
}

# =============================================================================
# URL UTILITIES
# =============================================================================

# Get API URL from base URL (appends /api if needed)
# Usage: get_api_url "http://localhost:7322"
# Returns: "http://localhost:7322/api"
get_api_url() {
    local base_url="$1"

    # Remove trailing slash if present
    base_url="${base_url%/}"

    # Check if /api is already in the URL
    if [[ "$base_url" =~ /api$ ]]; then
        echo "$base_url"
    else
        echo "${base_url}/api"
    fi
}
