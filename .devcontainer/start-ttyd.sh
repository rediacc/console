#!/usr/bin/env bash
# Start ttyd web terminal with tmux session persistence.
#
# Port: 7681 (default, configurable via TTYD_PORT)
# Each authenticated user gets a persistent tmux session.
# The TTYD_USER env var (set by auth proxy via -H flag) is used as the tmux session name.
#
# THIS FILE IS A SHIPPED PRODUCT INTERFACE, like its sibling start-desktop.sh
# (see that file's header): the hub invokes these by name through a compose
# label, so it must stay self-contained -- no sourcing from .ci/, which the
# Dockerfile build context (.devcontainer/) could not reach anyway.
#
# RUNS IN THE FOREGROUND, deliberately. An earlier header claimed
# `start-ttyd.sh &` was "typical in container entrypoint" while the script
# `exec`s under `set -e`, so it could never background itself. Backgrounding is
# the CALLER's job -- .devcontainer/devbox-autostart.sh already backgrounds and
# logs everything it starts, and the hub's compose command has its own `&`.
#
# Usage:
#   start-ttyd.sh              # foreground
#   start-ttyd.sh &            # background (typical in container entrypoint)
#   setsid start-ttyd.sh &     # detached from parent shell

set -euo pipefail

TTYD_PORT="${TTYD_PORT:-7681}"
TTYD_PID_FILE="${TTYD_PID_FILE:-/tmp/ttyd.pid}"

# Idempotency: skip if already running.
#
# THE PID FILE HAS TO BE WRITTEN FOR THIS TO MEAN ANYTHING. This guard read a
# file that nothing in the repo ever created, so it could never fire: a second
# invocation always fell through and died on "address in use" -- an idempotency
# check that was decoration. The write is below, and it records the pid of the
# process that BECOMES ttyd (`exec` keeps $$), not of a child.
if [ -f "$TTYD_PID_FILE" ] && kill -0 "$(cat "$TTYD_PID_FILE")" 2>/dev/null; then
    echo "[ttyd] Already running (PID $(cat "$TTYD_PID_FILE"))"
    exit 0
fi

echo "[ttyd] Starting on port $TTYD_PORT..."

# A stale file from a killed container would otherwise shadow a live start
# forever, since the guard above only clears when the pid is genuinely gone.
printf '%s\n' "$$" >"$TTYD_PID_FILE"
trap 'rm -f "$TTYD_PID_FILE"' EXIT

# Start ttyd with:
#   -W          Allow writing (not read-only)
#   -p PORT     Listen port
#   -t ...      xterm.js client options
#   tmux ...    Persistent session per user (uses TTYD_USER if set by auth proxy)
#
# `tmux new-session -A` is attach-or-create, and that is the whole point: a
# browser reload re-attaches the SAME session with its scrollback instead of
# opening a fresh shell.
exec ttyd \
    --writable \
    --port "$TTYD_PORT" \
    -t fontSize=14 \
    -t disableLeaveAlert=true \
    bash -c 'SESSION_NAME="${TTYD_USER:-main}"; exec tmux new-session -A -s "$SESSION_NAME"'
