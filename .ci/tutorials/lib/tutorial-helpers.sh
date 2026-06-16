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

# Format a display command for typing: when it carries more than two long
# options, each " --opt" moves onto its own indented continuation line so
# viewers see aligned parameters instead of one long wrapped string.
# Quote-aware — never splits inside single- or double-quoted arguments.
# Markers keep the flat one-line command (cards/docs/parity unaffected).
_format_display_cmd() {
    local cmd="$1"
    local seg="" c q=""
    local -a segs=()
    local i
    for ((i = 0; i < ${#cmd}; i++)); do
        c="${cmd:$i:1}"
        if [[ -n "$q" ]]; then
            seg+="$c"
            [[ "$c" == "$q" ]] && q=""
            continue
        fi
        if [[ "$c" == "'" || "$c" == '"' ]]; then
            q="$c"
            seg+="$c"
            continue
        fi
        if [[ "$c" == " " && "${cmd:$((i + 1)):2}" == "--" ]]; then
            segs+=("$seg")
            seg=""
            continue
        fi
        seg+="$c"
    done
    segs+=("$seg")
    local param_count=$((${#segs[@]} - 1))
    if ((param_count <= 2)); then
        printf '%s' "$cmd"
        return
    fi
    local out="${segs[0]}"
    for ((i = 1; i < ${#segs[@]}; i++)); do
        out+=" \\"$'\n'"    ${segs[$i]}"
    done
    printf '%s' "$out"
}

# Internal: clear the screen, reprint the section breadcrumb, emit the
# marker for the DISPLAY command, print the prompt, and simulate typing.
# The marker text feeds the storyboard cards, transcripts, and docs pages,
# so it must always carry the clean command the viewer should copy.
_type_command() {
    local display_cmd="$1"
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

    _emit_marker "$display_cmd"

    # Print prompt
    printf '%b' "$TUTORIAL_PROMPT"

    # Beautify display: replace expanded $HOME with literal ~ so the cast
    # shows portable paths instead of /home/<recordist-username>/...
    if [[ -n "$HOME" ]]; then display_cmd="${display_cmd//$HOME/\~}"; fi
    display_cmd="$(_format_display_cmd "$display_cmd")"

    # Type each character
    for ((i = 0; i < ${#display_cmd}; i++)); do
        printf '%s' "${display_cmd:$i:1}"
        sleep "$delay"
    done

    # Press enter
    printf '\n'
    sleep 0.3
}

# Internal: print the fresh empty prompt that marks "command done, awaiting
# next" — this is what plays under the after-narration freeze in the MP4.
_settle_prompt() {
    printf '%b' "$TUTORIAL_PROMPT"
    sleep 1.5
}

# Simulate typing a command, then execute it. The command MUST succeed —
# a non-zero exit aborts the recording so broken demos can never ship.
#
# Usage: run_cmd "rdc ops check"
#        run_cmd "rdc repo up --name app -m srv" "rdc repo up --name app -m srv --debug"
#
# The optional second argument is the command actually EXECUTED while the
# first is what the viewer sees typed (and what flows into cards/docs).
# Use it only when the on-screen form cannot run verbatim in the recording
# environment; the two must stay semantically identical.
run_cmd() {
    local display_cmd="$1"
    local exec_cmd="${2:-$1}"

    _type_command "$display_cmd"

    # Execute and check exit code (|| captures rc under set -e).
    local rc=0
    eval "$exec_cmd" || rc=$?
    if [[ $rc -ne 0 ]]; then
        echo "FATAL: command failed with exit code $rc: $exec_cmd" >&2
        exit $rc
    fi

    _settle_prompt
}

# Type + run a command that MUST fail (sandbox/isolation demos). The
# denial output is the demo; a command that unexpectedly SUCCEEDS aborts
# the recording — the inverse assertion of run_cmd.
#
# Usage: run_cmd_expect_fail "ls /"
run_cmd_expect_fail() {
    local cmd="$1"

    _type_command "$cmd"

    local rc=0
    eval "$cmd" || rc=$?
    if [[ $rc -eq 0 ]]; then
        echo "FATAL: command unexpectedly succeeded (expected failure): $cmd" >&2
        exit 1
    fi

    _settle_prompt
}

# Type + run a long-running command, let it produce output for a few
# seconds, then deliver Ctrl+C exactly like a human would: print ^C and
# send SIGINT. The command must exit cleanly (0 or 130) on SIGINT.
#
# Usage: run_cmd_interrupt "rdc repo tunnel -m srv -r app" 4
run_cmd_interrupt() {
    local cmd="$1"
    local run_secs="${2:-4}"

    _type_command "$cmd"

    eval "$cmd" &
    local pid=$!
    sleep "$run_secs"

    # Echo the ^C a real terminal would show, then interrupt the job.
    # The background eval is a subshell — signal its children (the real
    # command) first, then the subshell itself.
    printf '^C\n'
    pkill -INT -P "$pid" 2>/dev/null || true
    kill -INT "$pid" 2>/dev/null || true
    local rc=0
    wait "$pid" || rc=$?
    if [[ $rc -ne 0 && $rc -ne 130 ]]; then
        echo "FATAL: interrupted command exited $rc (expected 0/130): $cmd" >&2
        exit $rc
    fi

    _settle_prompt
}

# Mark the end of the on-camera portion: print the completion banner, hold
# the final frame, then silence stdout/stderr so cleanup spinners never
# leak into the cast. Call this INSTEAD of printing the banner manually;
# cleanup commands follow this call.
end_recording() {
    printf '\n\033[1;32m# Tutorial complete!\033[0m\n'
    sleep 2
    exec >/dev/null 2>&1
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
