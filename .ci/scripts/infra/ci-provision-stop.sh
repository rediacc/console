#!/bin/bash
# CI VM Teardown Script
# Destroys all provisioned KVM VMs and cleans up state
#
# Usage:
#   .ci/scripts/infra/ci-provision-stop.sh

set -e

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

echo "Stopping provisioned VMs..."

# =============================================================================
# FIND RENET BINARY
# =============================================================================
RENET_BIN="$CONSOLE_ROOT/private/renet/bin/renet"

if [[ ! -f "$RENET_BIN" ]]; then
    echo "  Warning: renet binary not found at $RENET_BIN"
    echo "  Build with: ./run.sh build renet"
    echo "  VMs may still be running — check with: virsh list --all"
else
    echo "  Using renet: $RENET_BIN"
    sudo -E "$RENET_BIN" ops down || echo "  Warning: renet ops down returned non-zero"
fi

# =============================================================================
# CLEANUP STATE FILE
# =============================================================================
PROVISION_STATE_FILE="$CONSOLE_ROOT/.provision-state"
rm -f "$PROVISION_STATE_FILE" 2>/dev/null || true

echo "All VMs stopped"
