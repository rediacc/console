#!/bin/bash
# Bring the devbox's HTTP services up with the container, not by hand.
#
# WHY THIS EXISTS. The entrypoint started openvscode-server and nothing else, so
# `./run.sh devbox status` reported two of its three routes as
# "no backend yet -- ./run.sh account dev (INSIDE the devbox)". That hint is
# accurate and it is also the wrong shape of answer: the whole point of one
# container per worktree behind one proxy is that the worktree's URLs work. A
# URL that requires a human to first open a terminal, find the devbox, and type
# a command is a URL that is broken for everyone who did not read the status
# output.
#
# WHAT IT DOES NOT DO. It never fails the container. A devbox whose VS Code
# works and whose account server did not come up is far better than a devbox
# that refuses to start because `npm install` had not been run yet -- and that
# is a real state on a fresh worktree. Every failure here is logged and
# swallowed; the status probe remains the place that tells the truth about what
# is actually serving.
#
# OPT OUT with DEVBOX_AUTOSTART=0 -- for a devbox you want quiet, or when
# debugging a service by hand and a second copy would fight over ports.
#
# The services bind 0.0.0.0 via REDIACC_DEV_BIND, which devbox.sh already sets
# in the container env. Without that they would listen on 127.0.0.1 inside the
# netns and Traefik would answer 502 while the process looked healthy.

set -u

WORKSPACE="${DEVBOX_WORKSPACE:?DEVBOX_WORKSPACE is required}"
LOG_DIR="${DEVBOX_AUTOSTART_LOG_DIR:-/tmp/devbox-autostart}"
mkdir -p "$LOG_DIR" 2>/dev/null || true

log() { echo "[devbox-autostart] $*"; }

if [ "${DEVBOX_AUTOSTART:-1}" = "0" ]; then
    log "disabled by DEVBOX_AUTOSTART=0; start services yourself with ./run.sh account dev|db"
    exit 0
fi

if [ ! -x "$WORKSPACE/run.sh" ]; then
    log "no executable run.sh at $WORKSPACE; nothing to start"
    exit 0
fi

cd "$WORKSPACE" || {
    log "could not enter $WORKSPACE; nothing to start"
    exit 0
}

# start <name> <subcommand...> -- background, logged, never fatal.
start() {
    local name="$1"
    shift
    local logf="$LOG_DIR/$name.log"

    # Do not stack a second copy on top of a service somebody already started;
    # two servers racing for one port is a worse failure than not starting.
    if pgrep -f "run.sh $*" >/dev/null 2>&1; then
        log "$name already running; leaving it alone"
        return 0
    fi

    log "starting $name (log: $logf)"
    (
        cd "$WORKSPACE" || exit 0
        exec ./run.sh "$@"
    ) >"$logf" 2>&1 &
    log "$name pid $!"
}

start account-dev account dev
start account-db account db

# The browser terminal. NOT routed through start(), which is run.sh-shaped
# (`pgrep -f "run.sh $*"`, `exec ./run.sh "$@"`) and ttyd is not a run.sh
# subcommand -- bending it would cost more than the six lines below.
#
# ttyd and tmux have been in the image since the beginning
# (.devcontainer/Dockerfile) and nothing ever started them, so the terminal
# route was dead on every local path while being live in the shipped hub
# product. This is the line that makes <worktree>-term.<domain> answer.
#
# DEVBOX_TERM_PORT is passed in by .ci/lib/devbox.sh (base + DEVBOX_OFFSET_TERM)
# and forwarded through setpriv by devbox-entrypoint.sh. Its absence is not an
# error: a container created before that env var existed simply has no terminal.
if [ -n "${DEVBOX_TERM_PORT:-}" ] && command -v ttyd >/dev/null 2>&1; then
    if pgrep -x ttyd >/dev/null 2>&1; then
        log "ttyd already running; leaving it alone"
    else
        log "starting ttyd on :$DEVBOX_TERM_PORT (log: $LOG_DIR/ttyd.log)"
        TTYD_PORT="$DEVBOX_TERM_PORT" setsid /usr/local/bin/start-ttyd.sh \
            >"$LOG_DIR/ttyd.log" 2>&1 &
        log "ttyd pid $!"
    fi
fi

# THE BASH PROFILER'S SUPERVISOR, built where the devbox actually looks for it.
#
# bash_env.sh probes two explicit paths for bashcov-sup and skips SILENTLY when
# neither exists. Measured 2026-09-03: /usr/local/bin/bashcov-sup does not exist in
# the running devbox and $HOME/.local/share/rediacc/bin does not either, so every
# bash inside the container was unprofiled while the host was fully covered -- and
# nothing said so. The Dockerfile does build it; the running image simply predates
# that line, which is the same "pinned but absent" shape bws had.
#
# So it is built here too, from the same source of truth, on every start. Cheap:
# the -nt test makes it a no-op once built. Failure is logged and never fatal --
# an autostart that dies over a profiler would cost the container.
_sup_src="/home/developer/console/.devcontainer/bashcov-sup.c"
[ -f "$_sup_src" ] || _sup_src="$(ls -1 /home/*/console/.devcontainer/bashcov-sup.c 2>/dev/null | head -1)"
_sup_bin="$HOME/.local/share/rediacc/bin/bashcov-sup"
if [ -n "${_sup_src:-}" ] && [ -f "$_sup_src" ]; then
    if [ -x "$_sup_bin" ] && [ ! "$_sup_src" -nt "$_sup_bin" ]; then
        log "bashcov-sup already current at $_sup_bin"
    elif command -v gcc >/dev/null 2>&1; then
        mkdir -p "$(dirname "$_sup_bin")"
        if gcc -O2 -Wall -o "$_sup_bin" "$_sup_src" && "$_sup_bin" -- true; then
            log "built bashcov-sup -> $_sup_bin"
        else
            log "bashcov-sup build FAILED; bash profiling stays off in this container"
            rm -f "$_sup_bin"
        fi
    else
        log "gcc missing; bashcov-sup not built, bash profiling stays off"
    fi
fi

log "autostart dispatched; ./run.sh devbox status PROBES what is actually serving"
