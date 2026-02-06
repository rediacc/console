#!/bin/bash
# CI VM Provisioning Script
# Provisions KVM-based VMs (bridge + workers) for testing
# Self-contained: works in both CI (GitHub Actions) and local dev
#
# Usage:
#   .ci/scripts/infra/ci-provision-start.sh [--force-rebuild]
#
# Environment variables (all have defaults):
#   VM_NET_BASE     - Network base IP (default: 192.168.111)
#   VM_NET_OFFSET   - Network offset (default: 0)
#   VM_BRIDGE       - Bridge VM ID (default: 1)
#   VM_WORKERS      - Worker VM IDs, space-separated (default: "11 12")
#   VM_CEPH_NODES   - Ceph node IDs (default: "" = disabled)
#   VM_OS           - VM OS image (default: ubuntu-24.04)
#   VM_IMAGE_DIR    - Path to VM image directory (default: /tmp/rediacc-vm-image)
#
# Outputs (for GitHub Actions):
#   bridge_ip        - Bridge VM IP address
#   worker_ips       - Worker VM IPs (comma-separated)
#   machine_user     - SSH username
#   machine_password - SSH password

set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Source common utilities
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# DEFAULTS
# =============================================================================
VM_NET_BASE="${VM_NET_BASE:-192.168.111}"
VM_NET_OFFSET="${VM_NET_OFFSET:-0}"
VM_BRIDGE="${VM_BRIDGE:-1}"
VM_WORKERS="${VM_WORKERS:-11 12}"
VM_CEPH_NODES="${VM_CEPH_NODES:-}"
VM_OS="${VM_OS:-ubuntu-24.04}"
VM_IMAGE_DIR="${VM_IMAGE_DIR:-/tmp/rediacc-vm-image}"
PROVISION_STATE_FILE="$CONSOLE_ROOT/.provision-state"

FORCE_REBUILD=false
for arg in "$@"; do
    [[ "$arg" == "--force-rebuild" ]] && FORCE_REBUILD=true
done

echo "Provisioning KVM VMs..."
echo "  Bridge: $VM_BRIDGE"
echo "  Workers: $VM_WORKERS"
echo "  OS: $VM_OS"
echo "  Network: ${VM_NET_BASE}.x (offset: $VM_NET_OFFSET)"

# =============================================================================
# STEP 1: CHECK KVM
# =============================================================================
if [[ ! -e /dev/kvm ]]; then
    log_error "KVM is not available (/dev/kvm not found)"
    log_error "VM provisioning requires hardware virtualization support"
    exit 1
fi
log_info "KVM is available"

# =============================================================================
# STEP 2: BUILD RENET FROM SOURCE (if needed)
# =============================================================================
source "$SCRIPT_DIR/build-renet.sh"
RENET_BIN="$CONSOLE_ROOT/private/renet/bin/renet"
export RENET_BINARY="$RENET_BIN"

# =============================================================================
# STEP 3: CHECK KVM PREREQUISITES
# =============================================================================
MISSING_PREREQS=false
for cmd in virsh virt-install qemu-img; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING_PREREQS=true
        break
    fi
done

if [[ "$MISSING_PREREQS" == "true" ]]; then
    log_step "Installing KVM prerequisites via renet..."
    sudo "$RENET_BIN" ops host setup
    log_info "KVM host setup complete"
else
    log_info "KVM prerequisites already installed"
fi

# =============================================================================
# STEP 4: BUILD VM IMAGE IF NOT CACHED
# =============================================================================
if [[ "$FORCE_REBUILD" == "true" ]] || [[ ! -d "$VM_IMAGE_DIR" ]]; then
    log_step "Building VM image (OS: $VM_OS)..."
    "$CONSOLE_ROOT/.ci/scripts/image/build-vm-image.sh" \
        --output "$VM_IMAGE_DIR" \
        --os "$VM_OS"
    log_info "VM image built at: $VM_IMAGE_DIR"
else
    log_info "Using cached VM image: $VM_IMAGE_DIR"
fi

# =============================================================================
# STEP 5: GENERATE VM PASSWORD
# =============================================================================
export VM_PASSWORD="${VM_PASSWORD:-$(head -c 100 /dev/urandom | tr -dc 'A-Za-z0-9' | head -c 14)}"

# =============================================================================
# STEP 6: PROVISION VMS
# =============================================================================
log_step "Running renet ops up..."

export REDIACC_OPS_DISKS_PATH="$VM_IMAGE_DIR"
export VM_NET_BASE VM_NET_OFFSET VM_BRIDGE VM_WORKERS VM_CEPH_NODES

sudo -E "$RENET_BIN" ops up --force --parallel

# =============================================================================
# STEP 7: CALCULATE IPS AND DISPLAY RESULTS
# =============================================================================
BRIDGE_IP="${VM_NET_BASE}.$((VM_BRIDGE + VM_NET_OFFSET))"

# Build worker IPs list (comma-separated, with offset)
WORKER_IPS=$(for ID in $VM_WORKERS; do echo "${VM_NET_BASE}.$((ID + VM_NET_OFFSET))"; done | paste -sd, -)

echo ""
log_info "VMs provisioned successfully!"
echo "  Bridge IP:  $BRIDGE_IP"
echo "  Worker IPs: $WORKER_IPS"
echo "  User:       $USER"
echo "  Password:   $VM_PASSWORD"

# =============================================================================
# STEP 8: WRITE STATE FILE
# =============================================================================
cat >"$PROVISION_STATE_FILE" <<EOF
bridge_ip=$BRIDGE_IP
worker_ips=$WORKER_IPS
vm_password=$VM_PASSWORD
vm_os=$VM_OS
started=$(date +%s)
EOF
log_info "State written to: $PROVISION_STATE_FILE"

# =============================================================================
# OUTPUT FOR GITHUB ACTIONS
# =============================================================================
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "bridge_ip=$BRIDGE_IP" >>"$GITHUB_OUTPUT"
    echo "worker_ips=$WORKER_IPS" >>"$GITHUB_OUTPUT"
    echo "machine_user=$USER" >>"$GITHUB_OUTPUT"
    echo "machine_password=$VM_PASSWORD" >>"$GITHUB_OUTPUT"
fi
