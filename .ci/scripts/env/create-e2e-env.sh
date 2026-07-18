#!/bin/bash
# Create E2E test environment file
# Usage: create-e2e-env.sh --output <path> [options]
#
# Generates a .env file for E2E integration tests with VM network configuration.
#
# Options:
#   --output        Output .env file path (required)
#   --vm-net-base   VM network base (default: 192.168.111)
#   --vm-net-offset VM network offset (default: 0)
#   --vm-control    Control-node VM ID (default: 1); --vm-bridge is a kept alias
#   --vm-workers    Worker VM IDs, space-separated (default: "11 12")
#   --vm-ceph-nodes Ceph node VM IDs, space-separated (default: "21 22 23" if --ceph)
#   --ceph          Enable Ceph mode (no workers, only Ceph nodes)
#   --vm-ram-worker Per-role RAM (MB) for worker VMs (default: renet VMRAM fallback)
#   --vm-ram-ceph   Per-role RAM (MB) for Ceph nodes (default: renet VMRAM fallback)
#   --ceph-osd-memory-target  osd_memory_target in bytes for the Ceph test profile
#   --timeout       Bridge timeout in ms (default: BRIDGE_TIMEOUT env or 120000)
#   --renet-path    Path to renet binary (default: RENET_BINARY env or source build)
#   --vm-image      OS image name (default: VM_IMAGE env or "ubuntu-24.04")
#   --vm-net        libvirt network name (renet VM_NET); a second group uses renet12
#   --docker-registry  In-VM registry endpoint; empty = renet derives it from the bridge IP
#   --k8s           Write K8S_MODE=1 (arm the kube/cluster suites)
#
# The combined workers+Ceph topology must pass explicit --vm-workers AND
# --vm-ceph-nodes (do NOT use --ceph, which zeroes VM_WORKERS).
#
# Example:
#   .ci/scripts/env/create-e2e-env.sh --output packages/e2e-tests/.env
#   .ci/scripts/env/create-e2e-env.sh --output .env --vm-workers "11 12 13"
#   .ci/scripts/env/create-e2e-env.sh --ceph --output packages/e2e-tests/.env
#   .ci/scripts/env/create-e2e-env.sh --output .env --vm-workers "11 12" \
#     --vm-ceph-nodes "21 22 23" --vm-ram-worker 2560 --vm-ram-ceph 2560 \
#     --ceph-osd-memory-target 1717986918

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

OUTPUT="${ARG_OUTPUT:-}"
VM_NET_BASE="${ARG_VM_NET_BASE:-192.168.111}"
VM_NET_OFFSET="${ARG_VM_NET_OFFSET:-0}"
# VM_CONTROL is the canonical name for the control node (VM 1); --vm-bridge stays
# as an accepted alias. renet reads both env vars (VM_CONTROL winning).
VM_BRIDGE="${ARG_VM_CONTROL:-${ARG_VM_BRIDGE:-1}}"
TIMEOUT="${ARG_TIMEOUT:-${BRIDGE_TIMEOUT:-120000}}"
RENET_PATH="${ARG_RENET_PATH:-${RENET_BINARY:-$(get_repo_root)/private/renet/bin/renet}}"

# libvirt network name for this group (renet VM_NET). Empty = renet's default
# (renet11). A second concurrent group passes --vm-net renet12.
VM_NET_NAME="${ARG_VM_NET:-}"
# In-VM registry endpoint (renet DOCKER_REGISTRY). Empty = renet derives it from
# the group's bridge IP (the wave-8 opsconfig fix), which is what a second group
# wants (192.168.112.5:5000 follows VM_NET_BASE/VM_BRIDGE automatically).
DOCKER_REGISTRY_VALUE="${ARG_DOCKER_REGISTRY:-}"
# K8s mode arms the kube/cluster suites (K8S_MODE=1). The k8s CI legs also set it
# as a job env; --k8s writes it into the .env so a local run needs no extra flag.
K8S_TOGGLE="${ARG_K8S:-false}"

# Handle Ceph mode
# Note: PROVISION_CEPH_CLUSTER is now inferred from VM_CEPH_NODES (if set, Ceph provisioning is enabled)
CEPH_MODE="${ARG_CEPH:-false}"
if [[ "$CEPH_MODE" == "true" ]]; then
    VM_WORKERS=""
    VM_CEPH_NODES="${ARG_VM_CEPH_NODES:-21 22 23}"
else
    VM_WORKERS="${ARG_VM_WORKERS:-11 12}"
    VM_CEPH_NODES="${ARG_VM_CEPH_NODES:-}"
fi

# VM image (e.g., "ubuntu-24.04", "debian-13")
VM_IMAGE_VALUE="${ARG_VM_IMAGE:-${VM_IMAGE:-ubuntu-24.04}}"

# Per-role RAM and Ceph OSD memory target (empty = renet defaults).
VM_RAM_WORKER="${ARG_VM_RAM_WORKER:-${VM_RAM_WORKER:-}}"
VM_RAM_CEPH="${ARG_VM_RAM_CEPH:-${VM_RAM_CEPH:-}}"
CEPH_OSD_MEMORY_TARGET="${ARG_CEPH_OSD_MEMORY_TARGET:-${CEPH_OSD_MEMORY_TARGET:-}}"

# Provision Ceph exactly when Ceph nodes are configured. Written EXPLICITLY
# rather than left to renet's VM_CEPH_NODES inference: renet's opsconfig.Load
# also sources a parent-directory .env (cwd/../.env), so a stray
# PROVISION_CEPH_CLUSTER=false there would otherwise silently disable Ceph. This
# value flows through the harness .env into process.env, which godotenv.Load
# will not override.
if [[ -n "$VM_CEPH_NODES" ]]; then
    PROVISION_CEPH_CLUSTER="true"
else
    PROVISION_CEPH_CLUSTER="false"
fi

# Validate required arguments
if [[ -z "$OUTPUT" ]]; then
    log_error "Usage: create-e2e-env.sh --output <path> [options]"
    exit 1
fi

# Fail fast if the requested topology cannot fit a 16 GB runner. The bridge is
# fixed at 1024 MB by the kvm driver; workers/Ceph use their per-role RAM,
# falling back to renet VMRAM (4096) when unset. Budget ceiling is 14.5 GB so
# the host keeps headroom for QEMU/host overhead.
assert_ram_budget() {
    local worker_ram="${VM_RAM_WORKER:-4096}"
    local ceph_ram="${VM_RAM_CEPH:-4096}"
    local bridge_ram=1024
    local ceiling_mb=14848 # 14.5 GB

    local worker_count=0 ceph_count=0
    # shellcheck disable=SC2086
    [[ -n "$VM_WORKERS" ]] && worker_count=$(echo $VM_WORKERS | wc -w)
    # shellcheck disable=SC2086
    [[ -n "$VM_CEPH_NODES" ]] && ceph_count=$(echo $VM_CEPH_NODES | wc -w)

    local total=$((bridge_ram + worker_count * worker_ram + ceph_count * ceph_ram))
    log_info "VM RAM budget: bridge ${bridge_ram} + ${worker_count}x${worker_ram} (worker) + ${ceph_count}x${ceph_ram} (ceph) = ${total} MB"
    if [[ "$total" -gt "$ceiling_mb" ]]; then
        log_error "Requested VM RAM ${total} MB exceeds the ${ceiling_mb} MB (14.5 GB) budget for a 16 GB runner."
        log_error "Lower --vm-ram-worker/--vm-ram-ceph or reduce node counts."
        exit 1
    fi
}
assert_ram_budget

# Create output directory if needed
OUTPUT_DIR="$(dirname "$OUTPUT")"
mkdir -p "$OUTPUT_DIR"

log_step "Creating E2E test environment: $OUTPUT"

cat >"$OUTPUT" <<EOF
# E2E Test Environment
# Generated by .ci/scripts/env/create-e2e-env.sh
# Note: PROVISION_CEPH_CLUSTER is inferred from VM_CEPH_NODES (if set, Ceph provisioning is enabled)
# Note: Renet auto-detects data directory via CI env var (uses \$RUNNER_TEMP/renet in CI)

VM_NET_BASE=$VM_NET_BASE
VM_NET_OFFSET=$VM_NET_OFFSET
VM_CONTROL=$VM_BRIDGE
VM_BRIDGE=$VM_BRIDGE
VM_WORKERS=$VM_WORKERS
VM_CEPH_NODES=$VM_CEPH_NODES
VM_IMAGE=$VM_IMAGE_VALUE
CEPH_MODE=$CEPH_MODE
VM_RAM_WORKER=$VM_RAM_WORKER
VM_RAM_CEPH=$VM_RAM_CEPH
CEPH_OSD_MEMORY_TARGET=$CEPH_OSD_MEMORY_TARGET
PROVISION_CEPH_CLUSTER=$PROVISION_CEPH_CLUSTER
BRIDGE_TIMEOUT=$TIMEOUT
RENET_BINARY_PATH=$RENET_PATH
CI=${CI:-true}
NODE_ENV=test
EOF

# Optional per-group extras. VM_NET / DOCKER_REGISTRY are only written when the
# caller pins them, so a default single group keeps renet's built-in derivation.
if [[ -n "$VM_NET_NAME" ]]; then
    echo "VM_NET=$VM_NET_NAME" >>"$OUTPUT"
fi
if [[ -n "$DOCKER_REGISTRY_VALUE" ]]; then
    echo "DOCKER_REGISTRY=$DOCKER_REGISTRY_VALUE" >>"$OUTPUT"
fi
if [[ "$K8S_TOGGLE" == "true" ]]; then
    echo "K8S_MODE=1" >>"$OUTPUT"
fi

log_info "Created E2E test environment: $OUTPUT"

# Display contents for debugging
if [[ "${DEBUG:-false}" == "true" ]]; then
    echo ""
    echo "Contents:"
    cat "$OUTPUT"
fi
