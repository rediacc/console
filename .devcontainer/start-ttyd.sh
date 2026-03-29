#!/usr/bin/env bash
# Start ttyd web terminal with tmux session persistence.
#
# Port: 7681 (default, configurable via TTYD_PORT)
# Each authenticated user gets a persistent tmux session.
# The TTYD_USER env var (set by auth proxy via -H flag) is used as the tmux session name.
#
# Usage:
#   start-ttyd.sh              # foreground
#   start-ttyd.sh &            # background (typical in container entrypoint)
#   setsid start-ttyd.sh &     # detached from parent shell

set -euo pipefail

TTYD_PORT="${TTYD_PORT:-7681}"
TTYD_PID_FILE="/tmp/ttyd.pid"

# Idempotency: skip if already running.
if [ -f "$TTYD_PID_FILE" ] && kill -0 "$(cat "$TTYD_PID_FILE")" 2>/dev/null; then
    echo "[ttyd] Already running (PID $(cat "$TTYD_PID_FILE"))"
    exit 0
fi

echo "[ttyd] Starting on port $TTYD_PORT..."

# Start ttyd with:
#   -W          Allow writing (not read-only)
#   -p PORT     Listen port
#   -t ...      xterm.js client options
#   tmux ...    Persistent session per user (uses TTYD_USER if set by auth proxy)
exec ttyd \
    --writable \
    --port "$TTYD_PORT" \
    -t fontSize=14 \
    -t disableLeaveAlert=true \
    bash -c 'SESSION_NAME="${TTYD_USER:-main}"; exec tmux new-session -A -s "$SESSION_NAME"'
