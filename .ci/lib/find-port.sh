#!/bin/bash
# Find available port for test infrastructure
# Avoids port conflicts when running multiple worktrees or when default port is in use
#
# Usage:
#   source "$SCRIPT_DIR/../../lib/find-port.sh"
#   PORT=$(find_available_port 3000 3999)
#
# THIS FILE IS A DELEGATING SHIM. The implementation lives in
# .ci/rediacc_ci/core/ports.py, which carries the reasoning that used to be
# here: why the slot is DERIVED rather than scanned, why the digest is sha256
# truncated to 8 hex digits and must never change, and why the probe still
# shells out to ss / lsof / netstat instead of binding a socket. Read that
# module before changing anything in here.
#
# The function names, their argument order, their stdout and their exit codes
# are unchanged, because .ci/lib/devbox.sh, .ci/lib/account.sh and
# .ci/lib/service.sh source this file and
# .ci/scripts/quality/check-setup-idempotency.sh sources it standalone to run
# `derive_slot` in a subshell.

# Prevent re-sourcing
[[ -n "${FIND_PORT_LOADED:-}" ]] && return 0

# ---------------------------------------------------------------------------
# Locating the package, and why this fails LOUDLY rather than falling back
# ---------------------------------------------------------------------------
#
# There is deliberately no bash fallback implementation. A fallback is a second
# implementation, a second implementation drifts, and the thing that would
# drift here decides which port a bookmarked URL resolves to. If the
# interpreter or the package cannot be found, this file returns non-zero from
# `source` WITHOUT defining any function, so a caller gets
# `derive_slot: command not found` -- which names the problem -- instead of a
# plausible wrong number.
#
# That fail-closed choice is the opposite of the one inside is_port_in_use,
# where "no probing tool at all" deliberately assumes the port is FREE. The
# difference: there, docker's own bind is the backstop and refusing would make
# the devbox unstartable; here, there is no backstop.
#
# REDIACC_CI_ROOT is the package's single environment override (see
# .ci/rediacc_ci/paths.py). It is honoured here so a planted-defect control can
# point the shim at a MUTATED COPY of the package and prove the delegation is
# real -- which is exactly what check-setup-idempotency.sh's control C does.
_find_port_root="${REDIACC_CI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
if [[ ! -d "$_find_port_root/.ci/rediacc_ci/core" ]]; then
    echo "find-port.sh: cannot find rediacc_ci under '$_find_port_root/.ci' (set REDIACC_CI_ROOT)" >&2
    unset _find_port_root
    return 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "find-port.sh: python3 is required; the port logic lives in rediacc_ci.core.ports" >&2
    unset _find_port_root
    return 1
fi
readonly FIND_PORT_LOADED=1
readonly FIND_PORT_CI_DIR="$_find_port_root/.ci"
unset _find_port_root

# One place that builds the interpreter invocation, so the PYTHONPATH is set
# identically for every verb. PYTHONPATH rather than `cd`: every caller below
# may be running from an arbitrary directory (test-age-check.sh's sibling
# harness cds into git fixtures before calling), and changing directory would
# change what the probe and the git commands see.
_find_port_py() {
    PYTHONPATH="$FIND_PORT_CI_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m rediacc_ci.core.ports "$@"
}

# =============================================================================
# PORT DETECTION
# =============================================================================

# Find an available port in a range
# Usage: find_available_port [start_port] [end_port]
# Returns: Available port number on stdout, exit code 0 on success, 1 if no port found
find_available_port() {
    _find_port_py find-available-port "${1:-3000}" "${2:-3999}"
}

# Check if a port is in use
# Usage: is_port_in_use 3000
# Returns: 0 if port is in use, 1 if port is free
#
# The probe order (ss on Linux, lsof on macOS, netstat under Windows Git Bash,
# then "assume free") is preserved in rediacc_ci.core.ports.is_port_in_use.
is_port_in_use() {
    _find_port_py is-port-in-use "$1"
}

# Find available port with preference for a specific port
# Usage: find_preferred_port 3000 [fallback_start] [fallback_end]
# Returns: The preferred port if free, otherwise first available in range
find_preferred_port() {
    local preferred_port="$1"
    _find_port_py find-preferred-port "$preferred_port" \
        "${2:-$((preferred_port + 1))}" "${3:-$((preferred_port + 999))}"
}

# Find the first base with <count> CONSECUTIVE free ports.
# Usage: find_consecutive_free_ports <count> [start] [end]
# Returns: the base port on stdout, or exit 1.
#
# Added by the W7 phase 1 port, and it is a fix rather than a feature. The one
# caller that needs three consecutive ports (account_allocate_ports) used to
# loop in bash over a 1000-port range calling is_port_in_use up to three times
# per candidate. That cost 5.7 ms a probe while the probe was bash and 66 ms
# once it delegated to Python -- about 17 seconds of worst case turning into
# about 200. One verb doing the whole scan in one interpreter removes the cost
# rather than trading correctness for it.
#
# The window is asymmetric on purpose and matches the bash it replaces: the
# BASE ranges over [start, end], while the ports CHECKED are base..base+count-1
# and may run past end.
find_consecutive_free_ports() {
    _find_port_py find-consecutive-free "$1" "${2:-3000}" "${3:-3999}"
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
    _find_port_py derive-slot "$1" "${2:-100}"
}

# Find a free, slot-aligned block of consecutive ports.
# Usage: find_port_block <key> <range_start> <range_end> <block_size>
# Returns: the base port of a free block on stdout, or exit 1.
#
# Delegated as ONE call rather than as a bash loop over is_port_in_use: the
# search probes up to (range/block) x block ports, and one interpreter per
# probe would turn milliseconds into tens of seconds.
find_port_block() {
    _find_port_py find-port-block "$1" "${2:-17000}" "${3:-17999}" "${4:-10}"
}
