#!/bin/bash
# Run middleware CI if available
#
# Usage: .ci/scripts/private/run-middleware.sh [stage]
#   Stages: all, quality, test, build (default: all)
#
# This is a thin wrapper that delegates to the middleware submodule's CI script.
# If the submodule is not available, it exits cleanly with a warning.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STAGE="${1:-all}"
REPO_ROOT="$(get_repo_root)"
MIDDLEWARE_DIR="$REPO_ROOT/private/middleware"

# Check if middleware submodule is available
if [[ ! -f "$MIDDLEWARE_DIR/.ci/ci.sh" ]]; then
    log_warn "Middleware submodule not available, skipping"
    exit 0
fi

# For test stage, setup environment defaults
if [[ "$STAGE" == "test" || "$STAGE" == "all" ]]; then
    source "$SCRIPT_DIR/../env/create-middleware-env.sh"
fi

log_step "Running middleware CI (stage: $STAGE)..."
"$MIDDLEWARE_DIR/.ci/ci.sh" "$STAGE"
