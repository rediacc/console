#!/bin/bash
# Start / stop / status for the noVNC browser desktop.
#
#   Xvfb (:99) -> XFCE4 -> x11vnc (:5999) -> websockify + noVNC (:6080)
#
# This is the CI debug box's copy, ported from .devcontainer/start-desktop.sh.
#
# ⚠️  THE TWO FILES ARE DELIBERATELY NOT UNIFIED, and the plan to make the
# devcontainer one a shim was ABANDONED after checking what calls it.
# .devcontainer/start-desktop.sh is installed at /usr/local/bin/start-desktop.sh
# and is a SHIPPED PRODUCT INTERFACE: the hub feature invokes it by name as a
# container entry command and as CRIU checkpoint hooks, documented across 13
# locales in packages/www/src/content/docs/*/hub.md. Hub users run
# ghcr.io/<org>/devcontainer:latest WITHOUT this repository mounted, so a shim
# execing a workspace path would break every one of them.
# Unifying via the image is separately blocked: the devcontainer image's docker
# build context is .devcontainer/, so its Dockerfile cannot COPY from .ci/.
#
# So: two copies, each self-contained, with a pointer in both headers. Prefer
# fixing the devcontainer copy FIRST -- that is the one customers run.
#
# WHY THE DEVCONTAINER ONE WON AND THE CI ONE LOST
# The deleted .ci/scripts/infra/ci-desktop.sh (420 lines) and the live
# .devcontainer/start-desktop.sh (277 lines) had drifted into two incompatible
# implementations of the same stack, with two incompatible PID conventions:
# a flat KEY=PID file at /tmp/desktop-pids.txt read by a separate 24-line
# cleanup script, versus a per-service pidfile directory. Either cleanup
# silently no-ops against the other's state, which is exactly how a "stopped"
# desktop keeps running.
#
# The devcontainer version is strictly better on every axis that matters for
# reliable teardown -- per-service pidfiles with stale-pid reclamation,
# idempotent is_running guards on every start, real stop/status verbs, a
# wait-for-port before declaring success, and the setsid re-exec below -- so it
# is the one that survived. What the CI version had that this lacks is package
# INSTALLATION, which is now a separate concern in install-vnc-desktop.sh.
#
# THIS SCRIPT ONLY STARTS THINGS. Packages must already be present:
# the devcontainer bakes them into its image; CI runs install-vnc-desktop.sh.
#
# THREE FIXES APPLIED IN THE PORT, all forced by moving under .ci/ where the
# gates actually run (.github/actions/** and .devcontainer/** are in no lint
# corpus, which is why the originals could carry these):
#   1. `seq 1 10` is BANNED by .ci/scripts/security/check-commands.sh -> for ((...))
#   2. `nc -z` assumed netcat exists -> bp_wait_for_port uses bash /dev/tcp
#   3. `pkill -f "dbus-daemon.*session"` pattern-killed processes it never
#      started -> the D-Bus PID is now captured and killed by PID
#
# Usage: desktop-ctl.sh [start|stop|status] [--resolution WxH] [--display N]

set -euo pipefail

# Re-exec in a new session so the desktop survives the calling shell exiting.
# Without this, SIGHUP goes to the shared process group and kills XFCE, x11vnc
# and websockify, while only Xvfb (which handles SIGHUP itself) survives --
# leaving a "running" desktop with nothing on it. Carried over verbatim from
# .devcontainer/start-desktop.sh:29-37, where it was learned the hard way.
if [[ "${_BP_DESKTOP_SETSID:-}" != "1" ]]; then
    export _BP_DESKTOP_SETSID=1
    exec setsid --wait "$0" "$@"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

VERB="start"
case "${1:-start}" in
    start | --start)
        VERB="start"
        shift || true
        ;;
    stop | --stop)
        VERB="stop"
        shift || true
        ;;
    status | --status)
        VERB="status"
        shift || true
        ;;
    --*) ;;
    *)
        log_error "usage: desktop-ctl.sh [start|stop|status] [--resolution WxH] [--display N]"
        exit 4
        ;;
esac

parse_args "$@"

DISPLAY_NUM="${ARG_DISPLAY:-${DESKTOP_DISPLAY:-99}}"
VNC_PORT="${ARG_VNC_PORT:-${DESKTOP_VNC_PORT:-5999}}"
NOVNC_PORT="${ARG_NOVNC_PORT:-${DESKTOP_NOVNC_PORT:-6080}}"
RESOLUTION="${ARG_RESOLUTION:-${DESKTOP_RESOLUTION:-1600x900}}"
COLOR_DEPTH="${ARG_COLOR_DEPTH:-${DESKTOP_COLOR_DEPTH:-24}}"

STATE_DIR="$(bp_state_dir)"
PIDFILE_DIR="$STATE_DIR/desktop-pids"
LOG_DIR="$STATE_DIR/desktop-logs"

export DISPLAY=":${DISPLAY_NUM}"

is_running() {
    local pidfile="$PIDFILE_DIR/$1.pid" pid
    if [[ -f "$pidfile" ]]; then
        pid="$(cat "$pidfile" 2>/dev/null || true)"
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        rm -f "$pidfile" # stale pidfile, reclaim it
    fi
    return 1
}

save_pid() {
    mkdir -p "$PIDFILE_DIR"
    echo "$2" >"$PIDFILE_DIR/$1.pid"
}

# =============================================================================
# SERVICES
# =============================================================================

start_xvfb() {
    if is_running xvfb; then
        log_info "Xvfb already running, skipping"
        return 0
    fi
    log_step "starting Xvfb on :${DISPLAY_NUM} (${RESOLUTION}x${COLOR_DEPTH})..."
    Xvfb ":${DISPLAY_NUM}" -screen 0 "${RESOLUTION}x${COLOR_DEPTH}" \
        >"$LOG_DIR/xvfb.log" 2>&1 &
    save_pid xvfb $!

    # Wait up to 5s for the X socket. `for ((...))` not `seq`: seq is banned in
    # .ci/** by check-commands.sh.
    local i
    for ((i = 0; i < 10; i++)); do
        [[ -e "/tmp/.X11-unix/X${DISPLAY_NUM}" ]] && break
        sleep 0.5
    done

    if ! is_running xvfb; then
        log_error "failed to start Xvfb"
        cat "$LOG_DIR/xvfb.log" >&2 2>/dev/null || true
        return 1
    fi
    log_info "Xvfb started (pid $(cat "$PIDFILE_DIR/xvfb.pid"))"
}

start_dbus() {
    if [[ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
        log_info "D-Bus session already available, skipping"
        return 0
    fi
    log_step "starting D-Bus session bus..."
    eval "$(dbus-launch --sh-syntax)"
    export DBUS_SESSION_BUS_ADDRESS
    # Capture the PID so stop_all can kill it BY PID. The original pkill'd
    # "dbus-daemon.*session", which reaches any other session's bus too.
    if [[ -n "${DBUS_SESSION_BUS_PID:-}" ]]; then
        save_pid dbus "$DBUS_SESSION_BUS_PID"
    fi
    log_info "D-Bus started: ${DBUS_SESSION_BUS_ADDRESS}"
}

init_keyring() {
    log_step "initializing keyring..."
    mkdir -p ~/.local/share/keyrings
    echo -n "" | gnome-keyring-daemon --unlock --components=secrets,pkcs11 \
        2>/dev/null || true
    local out
    out="$(echo -n "" | gnome-keyring-daemon --start --components=secrets,pkcs11 2>/dev/null || true)"
    [[ -n "$out" ]] && eval "$out" || true
    export GNOME_KEYRING_CONTROL SSH_AUTH_SOCK
    if [[ -n "${GNOME_KEYRING_PID:-}" ]]; then
        save_pid keyring "$GNOME_KEYRING_PID"
    fi
}

start_xfce() {
    if is_running xfce; then
        log_info "XFCE already running, skipping"
        return 0
    fi
    log_step "starting XFCE4..."
    startxfce4 >"$LOG_DIR/xfce.log" 2>&1 &
    save_pid xfce $!
    sleep 3
    if ! is_running xfce; then
        log_error "failed to start XFCE"
        cat "$LOG_DIR/xfce.log" >&2 2>/dev/null || true
        return 1
    fi
    log_info "XFCE started (pid $(cat "$PIDFILE_DIR/xfce.pid"))"
}

start_vnc() {
    if is_running x11vnc; then
        log_info "x11vnc already running, skipping"
        return 0
    fi
    log_step "starting x11vnc on ${VNC_PORT}..."
    # -nopw is safe ONLY because this listens on loopback and reaches the
    # outside world exclusively through the tunnel, which carries its own
    # authentication (Cloudflare Access in named mode). Do not expose this port.
    x11vnc -display ":${DISPLAY_NUM}" \
        -rfbport "${VNC_PORT}" \
        -localhost \
        -nopw \
        -forever \
        -shared \
        -bg \
        -o "$LOG_DIR/x11vnc.log"

    # x11vnc -bg forks, so $! is the wrapper, not the daemon. pgrep is scoped to
    # our exact rfbport so it cannot match another session's x11vnc.
    local vnc_pid
    vnc_pid="$(pgrep -f "x11vnc.*rfbport.*${VNC_PORT}" | head -1 || true)"
    [[ -n "$vnc_pid" ]] && save_pid x11vnc "$vnc_pid"

    if ! bp_wait_for_port "$VNC_PORT" 10; then
        log_error "x11vnc failed to start"
        cat "$LOG_DIR/x11vnc.log" >&2 2>/dev/null || true
        return 1
    fi
    log_info "x11vnc listening on ${VNC_PORT}"
}

start_novnc() {
    if is_running websockify; then
        log_info "noVNC/websockify already running, skipping"
        return 0
    fi
    log_step "starting noVNC on ${NOVNC_PORT}..."
    # The web root moved between distro versions; both paths are real.
    local novnc_web="/usr/share/novnc"
    [[ -d "$novnc_web" ]] || novnc_web="/usr/share/javascript/novnc"
    if [[ ! -d "$novnc_web" ]]; then
        log_error "noVNC web directory not found (looked in /usr/share/novnc and /usr/share/javascript/novnc)"
        log_error "run install-vnc-desktop.sh first"
        return 1
    fi

    websockify --web="$novnc_web" "$NOVNC_PORT" "localhost:${VNC_PORT}" \
        >"$LOG_DIR/websockify.log" 2>&1 &
    save_pid websockify $!

    if ! bp_wait_for_port "$NOVNC_PORT" 10; then
        log_error "websockify failed to start"
        cat "$LOG_DIR/websockify.log" >&2 2>/dev/null || true
        return 1
    fi
    log_info "noVNC listening on ${NOVNC_PORT}"
}

# =============================================================================
# STOP / STATUS
# =============================================================================

# Reverse dependency order. Every kill is BY RECORDED PID -- no pattern kills.
readonly DESKTOP_SERVICES="websockify x11vnc xfce keyring dbus xvfb"

stop_all() {
    log_step "stopping desktop services..."
    local svc pid stopped=0
    for svc in $DESKTOP_SERVICES; do
        if is_running "$svc"; then
            pid="$(cat "$PIDFILE_DIR/$svc.pid")"
            kill "$pid" 2>/dev/null || true
            rm -f "$PIDFILE_DIR/$svc.pid"
            log_info "stopped $svc (pid $pid)"
            stopped=$((stopped + 1))
        fi
    done
    if [[ $stopped -eq 0 ]]; then
        log_info "no desktop services were running"
    fi
}

show_status() {
    local svc
    echo "Desktop service status:"
    for svc in xvfb xfce x11vnc websockify dbus keyring; do
        if is_running "$svc"; then
            echo "  $svc: RUNNING (pid $(cat "$PIDFILE_DIR/$svc.pid"))"
        else
            echo "  $svc: STOPPED"
        fi
    done
}

# =============================================================================
mkdir -p "$PIDFILE_DIR" "$LOG_DIR"

case "$VERB" in
    stop)
        stop_all
        exit 0
        ;;
    status)
        show_status
        exit 0
        ;;
esac

log_step "starting desktop: display :${DISPLAY_NUM}, ${RESOLUTION}x${COLOR_DEPTH}, noVNC on ${NOVNC_PORT}"

start_xvfb
start_dbus
init_keyring
start_xfce
start_vnc
start_novnc

log_info "desktop ready at http://localhost:${NOVNC_PORT}/vnc.html"
bp_set_output "desktop-port" "$NOVNC_PORT"
bp_set_output "desktop-url" "http://localhost:${NOVNC_PORT}/vnc.html"
