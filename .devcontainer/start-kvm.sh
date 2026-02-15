#!/usr/bin/env bash
# Start KVM/libvirt stack for local VM provisioning (Standalone Run)
#
# Architecture:
#   /dev/kvm -> virtlogd -> libvirtd -> default NAT network (192.168.122.0/24)
#
# This script ONLY starts services. All packages must be pre-installed
# in the container image (see Dockerfile).
#
# Idempotent: safe to call multiple times. Skips already-running services.
# Graceful: exits 0 with a message if /dev/kvm is not available.
#
# Usage:
#   start-kvm.sh              # Start with defaults
#   start-kvm.sh --stop       # Stop all KVM services
#   start-kvm.sh --status     # Show service status
#
# The renet ops tool expects: virsh, virt-install, qemu-img, cloud-localds,
# jq, ssh, and a running libvirtd.

set -euo pipefail

# ============================================================================
# Session isolation
# ============================================================================
# Re-exec in a new session so that KVM services survive when the calling
# shell exits (e.g., devcontainer postStartCommand). Without this, SIGHUP is
# sent to the shared process group, killing libvirtd / virtlogd.
if [ "${_KVM_SETSID:-}" != "1" ]; then
	export _KVM_SETSID=1
	exec setsid --wait "$0" "$@"
fi

# ============================================================================
# Configuration
# ============================================================================
LOG_DIR="/tmp/kvm-logs"

# ============================================================================
# Utility Functions
# ============================================================================
log_info() { echo "[kvm] $*"; }
log_warn() { echo "[kvm] WARN: $*" >&2; }
log_error() { echo "[kvm] ERROR: $*" >&2; }

# Note: Unlike start-desktop.sh, we use pgrep instead of PID files because
# virtlogd/libvirtd run as root and kill -0 can't check them from vscode user.
daemon_is_running() {
	pgrep -x "$1" >/dev/null 2>&1
}

daemon_pid() {
	pgrep -x "$1" 2>/dev/null | head -1
}

wait_for_socket() {
	local socket=$1 timeout=${2:-30} elapsed=0
	while [ ! -S "$socket" ]; do
		if [ $elapsed -ge $timeout ]; then return 1; fi
		sleep 1
		elapsed=$((elapsed + 1))
	done
	return 0
}

# ============================================================================
# Service Functions
# ============================================================================

check_kvm() {
	if [ ! -e /dev/kvm ]; then
		log_info "KVM not available (/dev/kvm not found), skipping"
		log_info "This is normal on machines without nested virtualization"
		return 1
	fi
	# Fix permissions if needed (Codespaces sometimes resets them)
	if [ ! -w /dev/kvm ]; then
		log_info "Fixing /dev/kvm permissions..."
		sudo chmod 0666 /dev/kvm
	fi
	return 0
}

start_virtlogd() {
	if daemon_is_running virtlogd; then
		log_info "virtlogd already running (PID: $(daemon_pid virtlogd)), skipping"
		return 0
	fi
	log_info "Starting virtlogd..."
	sudo virtlogd --daemon
	sleep 1
	if daemon_is_running virtlogd; then
		log_info "virtlogd started (PID: $(daemon_pid virtlogd))"
	else
		log_error "Failed to start virtlogd"
		return 1
	fi
}

start_libvirtd() {
	if daemon_is_running libvirtd; then
		log_info "libvirtd already running (PID: $(daemon_pid libvirtd)), skipping"
		return 0
	fi
	log_info "Starting libvirtd..."
	sudo libvirtd --daemon
	# Wait for the libvirt socket
	if ! wait_for_socket /run/libvirt/libvirt-sock 15; then
		log_error "libvirtd failed to start (socket not found)"
		return 1
	fi
	if daemon_is_running libvirtd; then
		log_info "libvirtd started (PID: $(daemon_pid libvirtd))"
	else
		log_error "Failed to start libvirtd"
		return 1
	fi
}

net_is_active() {
	sudo virsh net-list --name 2>/dev/null | grep -q "^default$"
}

start_default_network() {
	# Check if default network is already active
	if net_is_active; then
		log_info "Default network already active, skipping"
		return 0
	fi
	# Define default network if it doesn't exist
	if ! sudo virsh net-info default >/dev/null 2>&1; then
		log_info "Defining default network..."
		sudo virsh net-define /usr/share/libvirt/networks/default.xml 2>/dev/null || true
	fi
	log_info "Starting default network..."
	sudo virsh net-start default 2>/dev/null || true
	# Enable autostart
	sudo virsh net-autostart default 2>/dev/null || true
	sleep 1
	if net_is_active; then
		log_info "Default network active (192.168.122.0/24)"
	else
		log_warn "Could not start default network (dnsmasq may be unavailable)"
		log_warn "VM provisioning may still work with custom networks"
	fi
}

# ============================================================================
# Stop / Status Functions
# ============================================================================

stop_all() {
	log_info "Stopping KVM services..."
	# Stop default network
	sudo virsh net-destroy default 2>/dev/null || true
	# Stop daemons
	for svc in libvirtd virtlogd; do
		if daemon_is_running "$svc"; then
			local pid
			pid=$(daemon_pid "$svc")
			log_info "Stopping $svc (PID: $pid)..."
			sudo kill "$pid" 2>/dev/null || true
		fi
	done
	log_info "All KVM services stopped"
}

show_status() {
	echo "KVM Service Status:"
	if [ ! -e /dev/kvm ]; then
		echo "  /dev/kvm: NOT AVAILABLE"
	else
		echo "  /dev/kvm: AVAILABLE"
	fi
	for svc in virtlogd libvirtd; do
		if daemon_is_running "$svc"; then
			echo "  $svc: RUNNING (PID: $(daemon_pid "$svc"))"
		else
			echo "  $svc: STOPPED"
		fi
	done
	# Show network status if libvirtd is running
	if daemon_is_running libvirtd; then
		if net_is_active; then
			echo "  default network: ACTIVE"
		else
			echo "  default network: INACTIVE"
		fi
	fi
}

# ============================================================================
# Main
# ============================================================================

mkdir -p "$LOG_DIR"

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

# Early exit if KVM is not available (not an error)
if ! check_kvm; then
	exit 0
fi

log_info "================================================================"
log_info "Starting KVM/libvirt Stack"
log_info "================================================================"

start_virtlogd
start_libvirtd
start_default_network

log_info "================================================================"
log_info "KVM ready!"
log_info "  Use 'virsh' to manage VMs"
log_info "  Use 'renet ops' for full provisioning"
log_info "================================================================"
