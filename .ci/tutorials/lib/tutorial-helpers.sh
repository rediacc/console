#!/bin/bash
# Tutorial recording helpers
# Provides simulated typing, prompt display, and marker emission for asciinema.
#
# Markers are emitted as OSC escape sequences that the post-processor
# (process-cast-markers.mjs) converts into proper asciinema marker events.

set -euo pipefail

# Override the rdc command if TUTORIAL_RDC_CMD is set (e.g. dev wrapper).
# This takes priority even if rdc is in PATH, ensuring the correct version is used.
if [[ -n "${TUTORIAL_RDC_CMD:-}" ]]; then
    rdc() { $TUTORIAL_RDC_CMD "$@"; }
    export -f rdc
elif ! command -v rdc &>/dev/null; then
    echo "Error: rdc not found. Set TUTORIAL_RDC_CMD to the path of your rdc wrapper." >&2
    exit 1
fi

# Machine configuration — update these if your test environment differs.
export TUTORIAL_MACHINE_NAME="${TUTORIAL_MACHINE_NAME:-worker-vm}"
export TUTORIAL_MACHINE_IP="${TUTORIAL_MACHINE_IP:-192.168.111.11}"
export TUTORIAL_MACHINE_USER="${TUTORIAL_MACHINE_USER:-$USER}"
export TUTORIAL_SSH_KEY="${TUTORIAL_SSH_KEY:-$HOME/.renet/staging/.ssh/id_rsa}"

TUTORIAL_PROMPT="\033[1;32muser@rediacc\033[0m:\033[1;34m~\033[0m\$ "
TUTORIAL_CHAR_DELAY="${TUTORIAL_CHAR_DELAY:-0.04}"

# Emit an OSC marker that the post-processor will detect.
_emit_marker() {
    printf '\033]rediacc-marker:%s\007' "$1"
}

# Simulate typing a command, then execute it.
# Usage: run_cmd "rdc ops check"
run_cmd() {
    local cmd="$1"
    local delay="${2:-$TUTORIAL_CHAR_DELAY}"

    _emit_marker "$cmd"

    # Print prompt
    printf '%b' "$TUTORIAL_PROMPT"

    # Type each character
    for ((i = 0; i < ${#cmd}; i++)); do
        printf '%s' "${cmd:$i:1}"
        sleep "$delay"
    done

    # Press enter
    printf '\n'
    sleep 0.3

    # Execute
    eval "$cmd"

    # Pause after output settles
    sleep 1.5
}

# Pause between sections.
pause() {
    sleep "${1:-2}"
}

# Print a visible comment / section header.
section() {
    printf '\n\033[1;33m# %s\033[0m\n' "$1"
    sleep 1
}

# Clear screen for a fresh start.
clear_screen() {
    printf '\033[2J\033[H'
    sleep 0.5
}
