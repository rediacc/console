#!/bin/bash
# Run renet build verification
#
# Usage: .ci/scripts/private/renet-build.sh [--cross-compile]
#
# Options:
#   --cross-compile    Enable cross-compilation for linux/amd64 and linux/arm64
#
# This wrapper delegates to the renet submodule's build script.
# If the submodule is not available, it exits cleanly with a warning.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

CROSS_COMPILE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --cross-compile)
            CROSS_COMPILE=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

REPO_ROOT="$(get_repo_root)"
RENET_DIR="$REPO_ROOT/private/renet"

# Check if renet submodule is available
if [[ ! -f "$RENET_DIR/.ci/ci.sh" ]]; then
    log_warn "Renet submodule not available, skipping"
    exit 0
fi

log_step "Running renet build verification..."

# Export CROSS_COMPILE for the build script
export CROSS_COMPILE

"$RENET_DIR/.ci/ci.sh" build

select_binary_dir() {
    local monorepo_bin="$REPO_ROOT/private/bin"
    local submodule_bin="$RENET_DIR/bin"

    if [[ -f "$monorepo_bin/renet-linux-amd64" && -f "$monorepo_bin/renet-linux-arm64" ]]; then
        echo "$monorepo_bin"
        return 0
    fi

    if [[ -f "$submodule_bin/renet-linux-amd64" && -f "$submodule_bin/renet-linux-arm64" ]]; then
        echo "$submodule_bin"
        return 0
    fi

    echo "$monorepo_bin"
}

# Verify cross-compiled binaries exist
if [[ "$CROSS_COMPILE" == "true" ]]; then
    log_step "Verifying cross-compiled binaries..."

    BINARY_DIR="$(select_binary_dir)"

    if [[ -f "$BINARY_DIR/renet-linux-amd64" ]]; then
        log_info "linux/amd64: OK ($(du -h "$BINARY_DIR/renet-linux-amd64" | cut -f1))"
    else
        log_error "linux/amd64 binary not found at $BINARY_DIR/renet-linux-amd64"
        exit 1
    fi

    if [[ -f "$BINARY_DIR/renet-linux-arm64" ]]; then
        log_info "linux/arm64: OK ($(du -h "$BINARY_DIR/renet-linux-arm64" | cut -f1))"
    else
        log_error "linux/arm64 binary not found at $BINARY_DIR/renet-linux-arm64"
        exit 1
    fi
fi

log_info "Build verification completed"
