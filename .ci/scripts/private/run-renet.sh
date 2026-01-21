#!/bin/bash
# Run renet CI if available
#
# Usage: .ci/scripts/private/run-renet.sh [stage]
#   Stages: all, quality, test, build (default: all)
#
# This is a thin wrapper that delegates to the renet submodule's CI script.
# If the submodule is not available, it exits cleanly with a warning.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STAGE="${1:-all}"
REPO_ROOT="$(get_repo_root)"
RENET_DIR="$REPO_ROOT/private/renet"

# Check if renet submodule is available
if [[ ! -f "$RENET_DIR/.ci/ci.sh" ]]; then
    log_warn "Renet submodule not available, skipping"
    exit 0
fi

log_step "Running renet CI (stage: $STAGE)..."
"$RENET_DIR/.ci/ci.sh" "$STAGE"
