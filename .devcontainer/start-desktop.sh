#!/usr/bin/env bash
# Start XFCE desktop environment accessible via noVNC (HTTP)
#
# Architecture:
#   Xvfb (:99) -> XFCE4 -> x11vnc (:5999) -> websockify+noVNC (:6080)
#
# This script ONLY starts services. All packages must be pre-installed
# in the container image (see Dockerfile).
#
# Idempotent: safe to call multiple times. Skips already-running services.
#
# Usage:
#   start-desktop.sh              # Start with defaults
#   start-desktop.sh --stop       # Stop all desktop services
#   start-desktop.sh --status     # Show service status
#
# Environment variables (all optional):
#   DESKTOP_DISPLAY      - X display number (default: 99)
#   DESKTOP_VNC_PORT     - VNC port (default: 5999)
#   DESKTOP_NOVNC_PORT   - noVNC HTTP port (default: 6080)
#   DESKTOP_RESOLUTION   - Resolution (default: 1600x900)
#   DESKTOP_COLOR_DEPTH  - Color depth (default: 24)

set -uo pipefail

# ============================================================================
# Configuration
# ============================================================================
DISPLAY_NUM="${DESKTOP_DISPLAY:-99}"
VNC_PORT="${DESKTOP_VNC_PORT:-5999}"
NOVNC_PORT="${DESKTOP_NOVNC_PORT:-6080}"
RESOLUTION="${DESKTOP_RESOLUTION:-1600x900}"
COLOR_DEPTH="${DESKTOP_COLOR_DEPTH:-24}"

PIDFILE_DIR="/tmp/desktop-pids"
LOG_DIR="/tmp/desktop-logs"

export DISPLAY=":${DISPLAY_NUM}"

# ============================================================================
# Utility Functions
# ============================================================================
log_info() { echo "[desktop] $*"; }
log_error() { echo "[desktop] ERROR: $*" >&2; }

wait_for_port() {
	local port=$1 timeout=${2:-30} elapsed=0
	while ! nc -z localhost "$port" 2>/dev/null; do
		if [ $elapsed -ge $timeout ]; then return 1; fi
		sleep 1
		elapsed=$((elapsed + 1))
	done
	return 0
}

is_running() {
	local pidfile="$PIDFILE_DIR/$1.pid"
	if [ -f "$pidfile" ]; then
		local pid
		pid=$(cat "$pidfile")
		if kill -0 "$pid" 2>/dev/null; then
			return 0
		fi
		rm -f "$pidfile" # stale pidfile
	fi
	return 1
}

save_pid() {
	echo "$2" >"$PIDFILE_DIR/$1.pid"
}

# ============================================================================
# Service Functions
# ============================================================================

start_xvfb() {
	if is_running xvfb; then
		log_info "Xvfb already running, skipping"
		return 0
	fi
	log_info "Starting Xvfb on display :${DISPLAY_NUM} (${RESOLUTION}x${COLOR_DEPTH})..."
	Xvfb ":${DISPLAY_NUM}" -screen 0 "${RESOLUTION}x${COLOR_DEPTH}" \
		>"$LOG_DIR/xvfb.log" 2>&1 &
	save_pid xvfb $!
	sleep 2
	if ! is_running xvfb; then
		log_error "Failed to start Xvfb"
		cat "$LOG_DIR/xvfb.log" 2>/dev/null || true
		return 1
	fi
	log_info "Xvfb started (PID: $(cat "$PIDFILE_DIR/xvfb.pid"))"
}

start_dbus() {
	if [ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]; then
		log_info "D-Bus session already available, skipping"
		return 0
	fi
	log_info "Starting D-Bus session bus..."
	eval "$(dbus-launch --sh-syntax)"
	export DBUS_SESSION_BUS_ADDRESS
	log_info "D-Bus started: $DBUS_SESSION_BUS_ADDRESS"
}

init_keyring() {
	log_info "Initializing keyring..."
	mkdir -p ~/.local/share/keyrings
	echo -n "" | gnome-keyring-daemon --unlock --components=secrets,pkcs11 \
		2>/dev/null || true
	eval "$(echo -n "" | gnome-keyring-daemon --start \
		--components=secrets,pkcs11 2>/dev/null)" || true
	export GNOME_KEYRING_CONTROL SSH_AUTH_SOCK
}

start_xfce() {
	if is_running xfce; then
		log_info "XFCE already running, skipping"
		return 0
	fi
	log_info "Starting XFCE4 desktop..."
	startxfce4 >"$LOG_DIR/xfce.log" 2>&1 &
	save_pid xfce $!
	sleep 3
	if ! is_running xfce; then
		log_error "Failed to start XFCE"
		cat "$LOG_DIR/xfce.log" 2>/dev/null || true
		return 1
	fi
	log_info "XFCE started (PID: $(cat "$PIDFILE_DIR/xfce.pid"))"
}

start_vnc() {
	if is_running x11vnc; then
		log_info "x11vnc already running, skipping"
		return 0
	fi
	log_info "Starting x11vnc on port ${VNC_PORT}..."
	x11vnc -display ":${DISPLAY_NUM}" \
		-rfbport "${VNC_PORT}" \
		-nopw \
		-forever \
		-shared \
		-bg \
		-o "$LOG_DIR/x11vnc.log"
	# x11vnc with -bg forks itself; find the actual PID
	local vnc_pid
	vnc_pid=$(pgrep -f "x11vnc.*rfbport.*${VNC_PORT}" | head -1) || true
	if [ -n "$vnc_pid" ]; then
		save_pid x11vnc "$vnc_pid"
	fi
	if ! wait_for_port "$VNC_PORT" 10; then
		log_error "x11vnc failed to start"
		cat "$LOG_DIR/x11vnc.log" 2>/dev/null || true
		return 1
	fi
	log_info "x11vnc started on port ${VNC_PORT}"
}

start_novnc() {
	if is_running websockify; then
		log_info "noVNC/websockify already running, skipping"
		return 0
	fi
	log_info "Starting noVNC on port ${NOVNC_PORT}..."
	# Find noVNC web directory (varies by distro)
	local novnc_web="/usr/share/novnc"
	if [ ! -d "$novnc_web" ]; then
		novnc_web="/usr/share/javascript/novnc"
	fi
	if [ ! -d "$novnc_web" ]; then
		log_error "noVNC web directory not found"
		return 1
	fi
	websockify --web="$novnc_web" "$NOVNC_PORT" "localhost:${VNC_PORT}" \
		>"$LOG_DIR/websockify.log" 2>&1 &
	save_pid websockify $!
	if ! wait_for_port "$NOVNC_PORT" 10; then
		log_error "websockify failed to start"
		cat "$LOG_DIR/websockify.log" 2>/dev/null || true
		return 1
	fi
	log_info "noVNC started on port ${NOVNC_PORT}"
}

# ============================================================================
# Stop / Status Functions
# ============================================================================

stop_all() {
	log_info "Stopping desktop services..."
	for svc in websockify x11vnc xfce xvfb; do
		if is_running "$svc"; then
			local pid
			pid=$(cat "$PIDFILE_DIR/$svc.pid")
			log_info "Stopping $svc (PID: $pid)..."
			kill "$pid" 2>/dev/null || true
			rm -f "$PIDFILE_DIR/$svc.pid"
		fi
	done
	log_info "All desktop services stopped"
}

show_status() {
	echo "Desktop Service Status:"
	for svc in xvfb xfce x11vnc websockify; do
		if is_running "$svc"; then
			echo "  $svc: RUNNING (PID: $(cat "$PIDFILE_DIR/$svc.pid"))"
		else
			echo "  $svc: STOPPED"
		fi
	done
}

# ============================================================================
# Main
# ============================================================================

mkdir -p "$PIDFILE_DIR" "$LOG_DIR"

case "${1:-start}" in
--stop | stop)
	stop_all
	exit 0
	;;
--status | status)
	show_status
	exit 0
	;;
start | --start) ;; # fall through to start
*)
	echo "Usage: $0 [start|stop|status]"
	exit 1
	;;
esac

log_info "================================================================"
log_info "Starting XFCE Desktop Environment"
log_info "  Display:    :${DISPLAY_NUM}"
log_info "  Resolution: ${RESOLUTION}x${COLOR_DEPTH}"
log_info "  VNC Port:   ${VNC_PORT} (internal)"
log_info "  noVNC Port: ${NOVNC_PORT} (HTTP)"
log_info "================================================================"

start_xvfb
start_dbus
init_keyring
start_xfce
start_vnc
start_novnc

log_info "================================================================"
log_info "Desktop ready!"
log_info "  noVNC URL: http://localhost:${NOVNC_PORT}/vnc.html"
log_info "  (In Codespaces, use the forwarded port URL instead)"
log_info "================================================================"
