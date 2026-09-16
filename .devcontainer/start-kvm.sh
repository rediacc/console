#!/usr/bin/env bash
# Start KVM/libvirt stack for local VM provisioning
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

# Does the HOST have KVM? Answered from /proc, which is namespaced but NOT
# filtered by the device cgroup, so a container started WITHOUT `--device
# /dev/kvm` still sees the module here. That is the whole point: it is the one
# signal available inside the container that distinguishes the two cases below.
host_has_kvm() {
	[ -d /sys/module/kvm ] || grep -qE '^(kvm_intel|kvm_amd|kvm)\b' /proc/modules 2>/dev/null
}

check_kvm() {
	if [ ! -e /dev/kvm ]; then
		# TWO VERY DIFFERENT SITUATIONS USED TO PRINT THE SAME REASSURING LINE,
		# and that is why the devbox went a long time with no KVM at all while
		# saying everything was fine:
		#
		#   (a) the machine genuinely has no nested virtualisation -- skipping
		#       is correct, and this script should exit 0;
		#   (b) the machine HAS KVM and the container was started without
		#       `--device /dev/kvm` -- a misconfiguration, and calling that
		#       "normal" is a lie that costs the reader the actual answer.
		#
		# The old code returned 1 for both and the caller exited 0 for both.
		if host_has_kvm; then
			log_error "The kernel HAS KVM but this container was not given /dev/kvm."
			log_error "This is a MISCONFIGURATION, not a machine without virtualisation."
			log_error "The container needs, at creation time:"
			log_error "    --device /dev/kvm"
			log_error "    --group-add \$(stat -c '%g' /dev/kvm)   # the HOST gid, derived"
			log_error "    --cap-add NET_ADMIN"
			log_error "    --security-opt systempaths=unconfined"
			log_error "Recreate it: ./run.sh devbox remove && ./run.sh devbox up"
			return 2
		fi
		log_info "KVM not available (/dev/kvm not found), skipping"
		log_info "This machine has no nested virtualization; that is expected here."
		return 1
	fi
	# NOT `chmod 0666` any more. `--device` reproduces the HOST's owning gid
	# inside the container -- measured here as 991 against an image `kvm` group of
	# 105 -- so the Dockerfile's `usermod -aG kvm vscode` grants nothing on the
	# bound node, and the old fix made the device world-writable at runtime to
	# work around it. The creation-time `--group-add <host gid>` in
	# .ci/lib/devbox.sh grants exactly the access the host already models, needs
	# no sudo, and widens no permissions. If the device is still unwritable the
	# gid was not passed, so SAY THAT rather than papering over it.
	if [ ! -w /dev/kvm ]; then
		log_error "/dev/kvm exists but is not writable by $(id -un)."
		log_error "The container was given the device but not the host's kvm group."
		log_error "Add at creation time: --group-add \$(stat -c '%g' /dev/kvm)"
		log_error "Recreate it: ./run.sh devbox remove && ./run.sh devbox up"
		return 2
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
	# LIBVIRT'S PER-DOMAIN MOUNT NAMESPACE CANNOT WORK IN THIS CONTAINER, and it
	# is on by default. Measured 2026-09-07: with /dev/kvm and /dev/net/tun both
	# bound, libvirtd running and the default network ACTIVE,
	# `./rdc.sh ops up --basic` still died inside virt-install with
	#
	#   ERROR Kernel does not provide mount namespace: Permission denied
	#
	# libvirt's qemu driver puts each domain in its own mount namespace so it can
	# build a private /dev for the guest. That needs unshare(CLONE_NEWNS), which
	# docker's default seccomp and capability set do not give an unprivileged
	# container. qemu.conf ships the setting COMMENTED OUT (`#namespaces =
	# [ "mount" ]`), and a commented-out line is not "off": it is the default
	# spelled out, so the feature was on and nothing in the file said so.
	#
	# Turning it off is the documented way to run libvirt inside a container. It
	# costs the guest a private /dev, which this fleet does not rely on: the VMs
	# get their disks and NIC through virt-install as before.
	#
	# Written at RUNTIME rather than baked into the image because the setting is
	# a property of running inside a container, which is the same reason the
	# /proc/sys remount below lives here. Idempotent, and it appends only when
	# no uncommented `namespaces` line is already present.
	if ! sudo grep -qE '^[[:space:]]*namespaces[[:space:]]*=' /etc/libvirt/qemu.conf; then
		log_info "Disabling libvirt per-domain mount namespaces (container)"
		printf '\n# Set by start-kvm.sh: a container cannot unshare a mount namespace.\nnamespaces = []\n' |
			sudo tee -a /etc/libvirt/qemu.conf >/dev/null
	fi

	# CGROUPS: libvirt cannot build a cgroup hierarchy for a domain in here, and
	# the two failures it produces look different but are one cause. First
	# /sys/fs/cgroup is mounted read-only by docker, so creating the machine
	# cgroup fails outright:
	#
	#   Failed to create v2 cgroup '/sys/fs/cgroup/machine/': Read-only file system
	#
	# Remounting it read-write (this container has SYS_ADMIN) gets past that and
	# straight into the second, which is cgroup v2 delegation: a nested cgroup
	# cannot be populated from inside an undelegated subtree, so libvirt creates
	# the parent and then cannot use the child:
	#
	#   unable to open '/sys/fs/cgroup/machine/qemu-2-rediacc1.libvirt-qemu/'
	#
	# So the remount is not the fix, it is one layer of the same wall. Telling
	# libvirt not to place qemu in cgroups at all clears both and needs NO extra
	# privilege, which is why this is the setting written rather than the mount.
	# The cost is that the fleet's VMs are not cgroup-limited inside the devbox;
	# they are already bounded by the container's own limits.
	if ! sudo grep -qE '^[[:space:]]*cgroup_controllers[[:space:]]*=' /etc/libvirt/qemu.conf; then
		log_info "Disabling libvirt cgroup placement (container)"
		printf '\n# Set by start-kvm.sh: cgroup v2 delegation does not reach into a container.\ncgroup_controllers = []\n' |
			sudo tee -a /etc/libvirt/qemu.conf >/dev/null
	fi

	# THE QEMU ACCOUNT NEEDS THE HOST'S KVM GROUP, not the image's. This is the
	# same host-versus-image gid mismatch that .ci/lib/devbox.sh solves for the
	# CONTAINER USER by deriving the gid and passing --group-add, and it has to be
	# solved a second time here because qemu does not run as that user: libvirtd
	# drops each domain to `libvirt-qemu`, which the image put in its own `kvm`
	# group (gid 105) while the bound device carries the HOST's gid. Measured
	# here: /dev/kvm is gid 991, libvirt-qemu is in 105, and virt-install died
	# with
	#
	#   Could not access KVM kernel module: Permission denied
	#   qemu-system-x86_64: -accel kvm: failed to initialize kvm: Permission denied
	#
	# after every other layer had been cleared. The old `sudo chmod 0666
	# /dev/kvm` hid this by making the device world-writable; deriving the group
	# is the same trick devbox.sh already plays, and it widens nothing beyond
	# what the host already models.
	kvm_gid="$(stat -c '%g' /dev/kvm 2>/dev/null || true)"
	if [ -n "$kvm_gid" ] && id libvirt-qemu >/dev/null 2>&1; then
		if ! id -G libvirt-qemu 2>/dev/null | tr ' ' '\n' | grep -qx "$kvm_gid"; then
			log_info "Adding libvirt-qemu to the host kvm group (gid $kvm_gid)"
			getent group "$kvm_gid" >/dev/null 2>&1 ||
				sudo groupadd -g "$kvm_gid" kvm-host
			sudo usermod -aG "$kvm_gid" libvirt-qemu
		fi
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
	# /proc/sys IS READ-ONLY UNDER DOCKER, and libvirt must write a per-bridge
	# sysctl to start a NAT network. Without this remount `virsh net-start` fails
	# with
	#   cannot write to '/proc/sys/net/ipv6/conf/virbr0/disable_ipv6'
	#   on bridge 'virbr0': Read-only file system
	# which is the error the old `2>/dev/null` on the next line threw away.
	#
	# The container is given --cap-add SYS_ADMIN for exactly this (see
	# .ci/lib/devbox.sh, which records why that was chosen over
	# --security-opt systempaths=unconfined: the latter also flips
	# /proc/sysrq-trigger and core_pattern to writable). NOT FATAL if it fails:
	# a devbox created before this change has no SYS_ADMIN, and the network start
	# below then reports the real reason loudly rather than dying here.
	if ! mountpoint -q /proc/sys || ! sudo mount -o remount,rw /proc/sys 2>/dev/null; then
		log_warn "Could not remount /proc/sys read-write."
		log_warn "If the network start below fails on a read-only file system, this"
		log_warn "container predates --cap-add SYS_ADMIN. Recreate it:"
		log_warn "    ./run.sh devbox remove && ./run.sh devbox up"
	fi

	log_info "Starting default network..."
	# STDERR IS KEPT. It used to go to /dev/null, and the warning below then
	# guessed at a cause ("dnsmasq may be unavailable") that was wrong: the real
	# message, recovered only by removing this redirect, was
	#   cannot write to '/proc/sys/net/ipv6/conf/virbr0/disable_ipv6'
	#   on bridge 'virbr0': Read-only file system
	# which is docker mounting /proc/sys ro and is fixed at CREATION time with
	# --security-opt systempaths=unconfined, not by anything dnsmasq does. A
	# guessed cause sent every reader in the wrong direction.
	net_err="$(sudo virsh net-start default 2>&1)" || true
	# Autostart only; its stderr is noise when the network is already started.
	sudo virsh net-autostart default >/dev/null 2>&1 || true
	sleep 1
	if net_is_active; then
		log_info "Default network active (192.168.122.0/24)"
	else
		log_error "The libvirt default network did NOT start. virsh said:"
		printf '%s\n' "$net_err" | sed 's/^/[kvm]   /' >&2
		log_error "VM provisioning through the default NAT network will not work."
		log_error "If that names a read-only /proc/sys, the container needs"
		log_error "    --cap-add NET_ADMIN --security-opt systempaths=unconfined"
		log_error "Recreate it: ./run.sh devbox remove && ./run.sh devbox up"
		return 1
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
# THE CALLER MUST NOT FLATTEN THESE BACK TOGETHER. check_kvm returns 1 for a
# machine that genuinely has no KVM (skip quietly, exit 0 -- a devbox on such a
# host must still come up cleanly) and 2 for a container that was misconfigured
# on a KVM-capable kernel. The old code exited 0 for both, which is how a
# devbox with no KVM at all reported success for months.
# `|| kvm_rc=$?` and NOT a bare call: this script runs under `set -euo pipefail`
# (line 21), so a bare `check_kvm` returning non-zero aborts here and every line
# below becomes unreachable. Caught by running it -- the misconfigured case
# exited 2 when it should exit 1, and, far worse, the genuinely-no-KVM case
# would have exited 1 where it must exit 0, breaking every devbox on a machine
# without nested virtualisation.
kvm_rc=0
check_kvm || kvm_rc=$?
if [ "$kvm_rc" -eq 2 ]; then
	exit 1
elif [ "$kvm_rc" -ne 0 ]; then
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
