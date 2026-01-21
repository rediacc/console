#!/bin/bash
# Run renet integration tests
#
# Usage: .ci/scripts/private/renet-integration.sh [--no-cleanup]
#
# Options:
#   --no-cleanup    Skip cleanup after tests (useful for debugging)
#
# This wrapper runs the full integration test suite for renet, which includes:
# - Docker isolated network tests
# - Checkpoint/restore tests (if CRIU available)
# - Proxy and router tests
# - Datastore tests
#
# Requires: Docker, Python 3, root access (for full test coverage)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

NO_CLEANUP=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-cleanup)
            NO_CLEANUP="--no-cleanup"
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
if [[ ! -f "$RENET_DIR/scripts/ci-test.sh" ]]; then
    log_warn "Renet submodule not available, skipping"
    exit 0
fi

log_step "Running renet integration tests..."

# Run integration tests
"$RENET_DIR/scripts/ci-test.sh" $NO_CLEANUP

# Copy test results to expected location if they exist
if [[ -f "$RENET_DIR/test-results.xml" ]]; then
    log_info "Integration test results available at: $RENET_DIR/test-results.xml"
fi

log_info "Integration tests completed"
