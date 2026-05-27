#!/bin/bash
# Tutorial recording helpers
# Provides simulated typing, prompt display, and marker emission for asciinema.
#
# Markers are emitted as OSC escape sequences that the post-processor
# (process-cast-markers.mjs) converts into proper asciinema marker events.

set -euo pipefail

# Override the rdc command if TUTORIAL_RDC_CMD is set to a *different* command
# (e.g. a dev wrapper like "npx tsx .../index.ts"). This takes priority even if
# rdc is in PATH, ensuring the correct version is used.
#
# Guard: if TUTORIAL_RDC_CMD is the bare command `rdc`, defining
# rdc() { rdc "$@"; } would shadow the PATH binary and call itself forever —
# bash stack overflow → SIGSEGV (exit 139). In that case fall through to the
# real rdc in PATH (e.g. the bridge VM has /usr/local/bin/rdc).
if [[ -n "${TUTORIAL_RDC_CMD:-}" && "$TUTORIAL_RDC_CMD" != "rdc" ]]; then
    rdc() { $TUTORIAL_RDC_CMD "$@"; }
    export -f rdc
elif ! command -v rdc &>/dev/null; then
    echo "Error: rdc not found. Set TUTORIAL_RDC_CMD to a wrapper command, or put rdc in PATH." >&2
    exit 1
fi

# Machine configuration — update these if your test environment differs.
# The machine name is just a local alias; we use machine-11/machine-12 so it
# lines up with the .11/.12 worker IPs, but it can be any label (prod-db, web-1).
export TUTORIAL_MACHINE_NAME="${TUTORIAL_MACHINE_NAME:-machine-11}"
export TUTORIAL_MACHINE_IP="${TUTORIAL_MACHINE_IP:-192.168.111.11}"
export TUTORIAL_MACHINE_USER="${TUTORIAL_MACHINE_USER:-$USER}"
export TUTORIAL_SSH_KEY="${TUTORIAL_SSH_KEY:-$HOME/.renet/staging/.ssh/id_rsa}"

# Skip machine activation -- tutorial VMs don't have a valid subscription license.
export REDIACC_SKIP_MACHINE_ACTIVATION=1

# Allow `term connect -c` shell redirects during pre-recording setup. The guard
# blocks writes by default to nudge users toward `rdc repo sync upload`, but
# tutorial scripts need to seed marker files inside the repo sandbox to drive
# the cast narrative.
export REDIACC_SKIP_FILE_WRITE_GUARD=1

# Force human-readable table output. Without this, `rdc` auto-defaults to JSON
# whenever an AI agent is detected in the ancestor process chain (e.g.
# CLAUDECODE=1 in the recording shell). Casts are for human viewers.
export REDIACC_DEFAULT_OUTPUT=table

TUTORIAL_PROMPT="\033[1;32muser@rediacc\033[0m:\033[1;34m~\033[0m\$ "
TUTORIAL_CHAR_DELAY="${TUTORIAL_CHAR_DELAY:-0.04}"

# Emit an OSC marker that the post-processor will detect.
_emit_marker() {
    printf '\033]rediacc-marker:%s\007' "$1"
}

# Tracks the most recent section header so run_cmd can reprint it after
# clearing the screen for each new command.
TUTORIAL_CURRENT_SECTION=""

# Simulate typing a command, then execute it.
# Usage: run_cmd "rdc ops check"
run_cmd() {
    local cmd="$1"
    local delay="${2:-$TUTORIAL_CHAR_DELAY}"

    # Clear screen + scrollback before EVERY command so each cast-narrated
    # MP4 scene starts with only its own command on screen (no prior output
    # clutter that would push the typed command off-screen while narration
    # plays).
    printf '\033[H\033[3J\033[2J'

    # Reprint the active section header so the viewer keeps the breadcrumb.
    if [[ -n "$TUTORIAL_CURRENT_SECTION" ]]; then
        printf '\033[1;33m# %s\033[0m\n' "$TUTORIAL_CURRENT_SECTION"
    fi

    _emit_marker "$cmd"

    # Print prompt
    printf '%b' "$TUTORIAL_PROMPT"

    # Beautify display: replace expanded $HOME with literal ~ so the cast
    # shows portable paths instead of /home/<recordist-username>/... The
    # real (expanded) path is preserved for execution.
    local display_cmd="$cmd"
    if [[ -n "$HOME" ]]; then display_cmd="${cmd//$HOME/\~}"; fi

    # Type each character
    for ((i = 0; i < ${#display_cmd}; i++)); do
        printf '%s' "${display_cmd:$i:1}"
        sleep "$delay"
    done

    # Press enter
    printf '\n'
    sleep 0.3

    # Execute and check exit code
    eval "$cmd"
    local rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "FATAL: command failed with exit code $rc: $cmd" >&2
        exit $rc
    fi

    # Print a fresh empty prompt so the cast's last frame captures
    # "command done, awaiting next" — this is what plays under the
    # after-narration freeze in the MP4 renderer.
    printf '%b' "$TUTORIAL_PROMPT"

    # Pause after output settles
    sleep 1.5
}

# Type a command but never press Enter or execute it. Use for commands whose
# output is noisy/dangerous to re-run (e.g. install scripts that fetch binaries)
# but should still appear on screen so the viewer sees what to type.
type_only_cmd() {
    local cmd="$1"
    local delay="${2:-$TUTORIAL_CHAR_DELAY}"

    printf '\033[H\033[3J\033[2J'

    if [[ -n "$TUTORIAL_CURRENT_SECTION" ]]; then
        printf '\033[1;33m# %s\033[0m\n' "$TUTORIAL_CURRENT_SECTION"
    fi

    _emit_marker "$cmd"

    printf '%b' "$TUTORIAL_PROMPT"

    # Beautify display: $HOME → ~ (same as run_cmd).
    local display_cmd="$cmd"
    if [[ -n "$HOME" ]]; then display_cmd="${cmd//$HOME/\~}"; fi

    for ((i = 0; i < ${#display_cmd}; i++)); do
        printf '%s' "${display_cmd:$i:1}"
        sleep "$delay"
    done

    # No newline, no eval. Hold the typed command on screen.
    sleep 1.5
}

# Pause between sections.
pause() {
    sleep "${1:-2}"
}

# Print a visible comment / section header. Records the header in
# TUTORIAL_CURRENT_SECTION so run_cmd reprints it after each per-command clear.
section() {
    printf '\033[H\033[3J\033[2J'
    sleep 0.3
    printf '\033[1;33m# %s\033[0m\n' "$1"
    TUTORIAL_CURRENT_SECTION="$1"
    sleep 1
}

# Clear screen for a fresh start.
clear_screen() {
    printf '\033[2J\033[H'
    sleep 0.5
}
