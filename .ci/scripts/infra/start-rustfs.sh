#!/bin/bash
# Start RustFS S3-compatible storage on bridge VM
# Usage: start-rustfs.sh [options]
#
# Starts RustFS container on the bridge VM and optionally configures
# worker VMs for rclone access.
#
# Options:
#   --configure-workers  Also configure rclone on worker VMs (default: false)
#   --bucket            Create this bucket (default: rediacc-test)
#   --timeout           Timeout in seconds (default: 120)
#
# Prerequisites:
#   - renet binary must be available at RENET_BINARY or /usr/bin/renet
#   - VMs must be running
#
# Example:
#   .ci/scripts/infra/start-rustfs.sh
#   .ci/scripts/infra/start-rustfs.sh --configure-workers
#   .ci/scripts/infra/start-rustfs.sh --configure-workers --bucket my-bucket

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

CONFIGURE_WORKERS="${ARG_CONFIGURE_WORKERS:-false}"
BUCKET="${ARG_BUCKET:-rediacc-test}"
TIMEOUT="${ARG_TIMEOUT:-120}"

# Find renet binary
RENET="${RENET_BINARY:-/usr/bin/renet}"
if [[ ! -x "$RENET" ]]; then
    log_error "renet binary not found at $RENET"
    log_error "Set RENET_BINARY or ensure /usr/bin/renet exists"
    exit 1
fi

require_cmd timeout

log_step "Starting RustFS on bridge VM..."

# Start RustFS using renet ops command
if timeout "$TIMEOUT" "$RENET" ops rustfs start; then
    log_info "RustFS started successfully"
else
    log_error "Failed to start RustFS (timeout: ${TIMEOUT}s)"
    exit 1
fi

# Create bucket if specified
if [[ -n "$BUCKET" ]]; then
    log_step "Creating bucket: $BUCKET"
    if "$RENET" ops rustfs create-bucket "$BUCKET"; then
        log_info "Bucket '$BUCKET' created"
    else
        log_warn "Bucket creation returned non-zero (may already exist)"
    fi
fi

# Configure workers if requested
if [[ "$CONFIGURE_WORKERS" == "true" ]]; then
    log_step "Configuring rclone on worker VMs..."
    if "$RENET" ops rustfs configure-workers; then
        log_info "Workers configured for RustFS access"
    else
        log_error "Failed to configure workers"
        exit 1
    fi
fi

log_info "RustFS setup complete"
