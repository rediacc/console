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
        # Windows Git Bash / fallback — Windows format: "TCP  0.0.0.0:port  ...  LISTENING"
        netstat -an 2>/dev/null | grep -qE ":$port\b.*(LISTEN|LISTENING)"
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

# =============================================================================
# DETERMINISTIC BLOCK ALLOCATION (per-worktree)
# =============================================================================
#
# A scan-from-a-base allocator gives a worktree a different port after every
# reboot, which breaks bookmarks and makes "which checkout am I looking at?"
# unanswerable. These two helpers derive a STABLE slot from a key (the
# worktree's absolute path), then fall back through slot-aligned candidates so
# the fallback stays block-aligned instead of colliding with a neighbour's block.

# Derive a stable slot index from an arbitrary key.
# Usage: derive_slot <key> <slot_count>
derive_slot() {
    local key="$1"
    local slots="${2:-100}"
    local digest

    # sha256 of the key; first 8 hex digits are plenty of entropy for <1k slots.
    digest="$(printf '%s' "$key" | _sha256sum_portable | cut -c1-8)"
    echo $((0x$digest % slots))
}

# Portable sha256 (mirrors _sha256sum in local-common.sh, which this file must
# not depend on -- find-port.sh is sourced standalone by
# check-setup-idempotency.sh:129-130, which runs `bash -c "source '$fp'; derive_slot ..."`.
# It is NOT check-account-probes.sh, which this comment used to name: that gate
# sources .ci/lib/account.sh, and account.sh is what pulls find-port.sh in.)
_sha256sum_portable() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum
    else
        shasum -a 256
    fi
}

# Find a free, slot-aligned block of consecutive ports.
# Usage: find_port_block <key> <range_start> <range_end> <block_size>
# Returns: the base port of a free block on stdout, or exit 1.
find_port_block() {
    local key="$1"
    local range_start="${2:-17000}"
    local range_end="${3:-17999}"
    local block="${4:-10}"

    local slots=$(((range_end - range_start + 1) / block))
    [[ "$slots" -lt 1 ]] && return 1

    local preferred_slot
    preferred_slot="$(derive_slot "$key" "$slots")"

    # Try the derived slot first, then every other slot in order. Walking all
    # slots (rather than giving up) means a busy machine still gets a devbox.
    local i slot base port_in_use
    for ((i = 0; i < slots; i++)); do
        slot=$(((preferred_slot + i) % slots))
        base=$((range_start + slot * block))

        port_in_use=false
        local offset
        for ((offset = 0; offset < block; offset++)); do
            if is_port_in_use $((base + offset)); then
                port_in_use=true
                break
            fi
        done

        if [[ "$port_in_use" == false ]]; then
            echo "$base"
            return 0
        fi
    done

    return 1
}
