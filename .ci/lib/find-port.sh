#!/bin/bash
# Find available port for test infrastructure
# Avoids port conflicts when running multiple worktrees or when default port is in use
#
# Usage:
#   source "$SCRIPT_DIR/../../lib/find-port.sh"
#   PORT=$(find_available_port 3000 3999)

# Prevent re-sourcing
[[ -n "${FIND_PORT_LOADED:-}" ]] && return 0
readonly FIND_PORT_LOADED=1

# =============================================================================
# PORT DETECTION
# =============================================================================

# Find an available port in a range
# Usage: find_available_port [start_port] [end_port]
# Returns: Available port number on stdout, exit code 0 on success, 1 if no port found
find_available_port() {
    local start_port="${1:-3000}"
    local end_port="${2:-3999}"

    for port in $(seq "$start_port" "$end_port"); do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
    done

    return 1
}

# Check if a port is in use
# Usage: is_port_in_use 3000
# Returns: 0 if port is in use, 1 if port is free
is_port_in_use() {
    local port="$1"

    # Try ss first (Linux), fall back to lsof (macOS)
    if command -v ss &>/dev/null; then
        ss -tlnH "sport = :$port" 2>/dev/null | grep -q .
    elif command -v lsof &>/dev/null; then
        lsof -iTCP:"$port" -sTCP:LISTEN &>/dev/null
    elif command -v netstat &>/dev/null; then
        # Windows Git Bash / fallback
        netstat -an 2>/dev/null | grep -qE "(LISTEN|LISTENING).*:$port\b"
    else
        # Cannot determine, assume port is free
        return 1
    fi
}

# Find available port with preference for a specific port
# Usage: find_preferred_port 3000 [fallback_start] [fallback_end]
# Returns: The preferred port if free, otherwise first available in range
find_preferred_port() {
    local preferred_port="$1"
    local fallback_start="${2:-$((preferred_port + 1))}"
    local fallback_end="${3:-$((preferred_port + 999))}"

    if ! is_port_in_use "$preferred_port"; then
        echo "$preferred_port"
        return 0
    fi

    find_available_port "$fallback_start" "$fallback_end"
}
