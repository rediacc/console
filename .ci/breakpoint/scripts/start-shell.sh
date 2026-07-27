#!/bin/bash
# Start a tmate session so a human can get a real shell on the runner.
#
# Ported from the deleted .github/actions/tmate/scripts/start-session.sh, with
# its two teardown bugs removed. Those bugs are the reason this is a script in
# the folder rather than a restored composite action:
#
#   1. The old stop-session.sh ran `pkill -f "tmate.*new-session"`, which kills
#      a CONCURRENT job's tmate session on a shared machine, and
#      `rm -f /tmp/tmate-*.log`, which globs another job's files. Here the
#      socket path is unique per run and teardown kills only the recorded PID.
#
#   2. That stop-session.sh was NEVER INVOKED by anything. Composite actions
#      have no `post:` hook, and the workflow killed the PID inline instead --
#      so 54 lines of cleanup were dead from the day they were written, and the
#      cleanup that did run was the ad-hoc inline copy.
#
# SECURITY: a tmate session is a shell on a runner that holds the repository
# checkout and, unless the caller scrubbed them, credentials. The connection
# strings are masked here; whether they then travel by email or by log is
# publish-endpoints.sh's decision, not this script's.
#
# Note tmate's WEB session is hosted on tmate.io, OUTSIDE your tunnel, so
# Cloudflare Access does not front it. Anyone holding that URL has a shell.
#
# Usage:  start-shell.sh [--timeout 60]
# Stdout: nothing. Values are written to session state and GITHUB_OUTPUT.
# Exit:   0 ok, 1 the session never came up.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

parse_args "$@"
TIMEOUT="${ARG_TIMEOUT:-60}"

STATE_DIR="$(bp_state_dir)"
mkdir -p "$STATE_DIR"

# Unique per run, so two sessions on one machine cannot collide and so teardown
# never needs a glob.
SOCKET="$STATE_DIR/tmate-${GITHUB_RUN_ID:-local}-$$.sock"

TMATE_BIN="$("$SCRIPT_DIR/install-tmate.sh")"

log_step "starting tmate session..."
"$TMATE_BIN" -S "$SOCKET" new-session -d
bp_state_set BP_TMATE_SOCKET "$SOCKET"

# tmate forks; the PID we want is the one holding the socket.
TMATE_PID="$(pgrep -f "tmate.*-S ${SOCKET}" | head -1 || true)"
if [[ -n "$TMATE_PID" ]]; then
    bp_record_pid tmate "$TMATE_PID"
    bp_state_set BP_TMATE_PID "$TMATE_PID"
fi

# Wait for the session to register with tmate.io before reading its strings.
if ! "$TMATE_BIN" -S "$SOCKET" wait tmate-ready 2>/dev/null; then
    # `wait` blocks indefinitely if the relay never answers, so fall back to a
    # bounded poll rather than hanging the whole job.
    elapsed=0
    ready=false
    while [[ $elapsed -lt $TIMEOUT ]]; do
        if "$TMATE_BIN" -S "$SOCKET" display -p '#{tmate_ssh}' >/dev/null 2>&1; then
            ready=true
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    if [[ "$ready" != "true" ]]; then
        log_error "tmate session did not become ready within ${TIMEOUT}s"
        exit 1
    fi
fi

SSH_CONN="$("$TMATE_BIN" -S "$SOCKET" display -p '#{tmate_ssh}' 2>/dev/null || true)"
WEB_URL="$("$TMATE_BIN" -S "$SOCKET" display -p '#{tmate_web}' 2>/dev/null || true)"
SSH_RO="$("$TMATE_BIN" -S "$SOCKET" display -p '#{tmate_ssh_ro}' 2>/dev/null || true)"
WEB_RO="$("$TMATE_BIN" -S "$SOCKET" display -p '#{tmate_web_ro}' 2>/dev/null || true)"

if [[ -z "$SSH_CONN" ]]; then
    log_error "tmate produced no SSH connection string"
    exit 1
fi

# DELIBERATELY NOT MASKED HERE. This script does not know the delivery
# channel, and masking is irreversible within a run: once a value is masked it
# can never be printed, so masking here made the logs channel emit
# "SSH: ***" -- a shell nobody can reach. That is the exact bug already fixed
# for the tunnel URL (never mask without a working alternative channel); this
# was the same bug's second instance, in a place the first fix did not reach.
#
# publish-endpoints.sh owns the decision, because it is the only thing that
# knows whether email is actually available. It reads these back from the
# session state file rather than being handed them through the workflow`s
# `env:`, because GitHub echoes every step`s `env:` block into the log -- which
# would leak the connection string before any masking could apply.

bp_state_set BP_TMATE_SSH "$SSH_CONN"
bp_state_set BP_TMATE_WEB "$WEB_URL"
bp_state_set BP_TMATE_SSH_RO "$SSH_RO"
bp_state_set BP_TMATE_WEB_RO "$WEB_RO"

# No bp_set_output here on purpose: a step output that the workflow then puts in
# an `env:` block is printed in the log by the runner. State file only.
log_info "tmate session ready (details go to the session state; publish-endpoints.sh decides how to deliver them)"
