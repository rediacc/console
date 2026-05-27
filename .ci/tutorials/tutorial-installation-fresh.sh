#!/bin/bash
# Tutorial 01 (fresh-VM variant): records the *real* curl install on a clean
# ubuntu-24.04 VM. Designed to run inside an `rdc ops` worker via SSH while
# asciinema rec captures the host side of the session.
#
# Self-contained: does NOT source tutorial-helpers.sh, because the VM has no
# rdc on PATH at the start. Inlines the prompt emitter, marker writer, and
# typed-command helper.

# Intentionally NOT set -e: rdc doctor in the currently published SEA may
# exit 1 (warning-only) until the new exit-code policy ships. The cast still
# captures the full output; we just don't want the recorder to abort.
set -u

# Force human-readable table output. Without this, rdc auto-defaults to JSON
# when stdout isn't a TTY (non-interactive SSH) or when an AI ancestor is
# detected. Casts are for human viewers.
export REDIACC_DEFAULT_OUTPUT=table

PROMPT='\033[1;32muser@rediacc\033[0m:\033[1;34m~\033[0m$ '

# Per-character base delay (sec). Real human typing has 70-150 ms variance; we
# pick a base + jitter so the cast doesn't read like a robot.
TYPE_BASE="${TYPE_BASE:-0.075}"
TYPE_JITTER="${TYPE_JITTER:-0.05}"

emit_marker() {
    printf '\033]rediacc-marker:%s\007' "$1"
}

run_cmd() {
    local cmd="$1"
    # Print the prompt FIRST so the marker fires AFTER the prompt is visible
    # on screen. The MP4 renderer's per-marker hold then shows the prompt
    # while narration plays, instead of a blank frame.
    printf '%b' "$PROMPT"
    sleep 0.25
    emit_marker "$cmd"
    for ((i = 0; i < ${#cmd}; i++)); do
        printf '%s' "${cmd:$i:1}"
        # awk does the float random math bash can't.
        sleep "$(awk -v b="$TYPE_BASE" -v j="$TYPE_JITTER" -v seed="$RANDOM$(date +%N)" 'BEGIN{srand(seed); printf "%.3f", b + rand()*j}')"
    done
    printf '\n'
    sleep 0.3
    eval "$cmd" || true
    sleep 1.5
}

# Type a command but never press Enter or execute it. Use for commands whose
# output is noisy/long and we'd rather narrate than display.
type_only_cmd() {
    local cmd="$1"
    printf '%b' "$PROMPT"
    sleep 0.25
    emit_marker "$cmd"
    for ((i = 0; i < ${#cmd}; i++)); do
        printf '%s' "${cmd:$i:1}"
        sleep "$(awk -v b="$TYPE_BASE" -v j="$TYPE_JITTER" -v seed="$RANDOM$(date +%N)" 'BEGIN{srand(seed); printf "%.3f", b + rand()*j}')"
    done
    # Hold the typed command on screen briefly; do NOT press Enter.
    sleep 1.2
}

section() {
    printf '\n\033[1;33m# %s\033[0m\n' "$1"
}

# Use raw ANSI instead of `clear`; clear(1) needs TERM set and tput, neither
# guaranteed in the SSH/stdin-redirect context. \e[2J wipes the buffer, \e[H
# moves cursor home, \e[3J scrolls back history (so any SSH warnings emitted
# before the script started are also gone).
printf '\033[H\033[3J\033[2J'
sleep 0.4

section "Install the CLI"
run_cmd "curl -fsSL https://www.rediacc.com/install.sh | bash"

# After install, the rdc binary lives in ~/.local/share/rediacc/bin per the
# install.sh shim; ensure it's discoverable.
export PATH="$HOME/.local/share/rediacc/bin:$PATH"

sleep 1

section "Confirm rdc is installed"
run_cmd "rdc --version"

sleep 1

section "Verify the install"
type_only_cmd "rdc doctor"

sleep 1

printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
sleep 2
