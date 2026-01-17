#!/bin/bash
# Run CLI integration tests
# Usage: run-cli.sh [--filter <pattern>]
#
# Options:
#   --filter  Filter tests by pattern
#
# ⚠️  IMPORTANT: When modifying this script:
# ⚠️  1. Test the script locally
# ⚠️  2. Update the main 'go' script if needed (console/go)
# ⚠️  3. Verify CI workflow compatibility

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

FILTER="${ARG_FILTER:-}"

# Change to repo root
cd "$(get_repo_root)"

CLI_DIR="packages/cli"

# Build CLI before running tests (required for cli-bundle.cjs)
log_step "Building CLI..."
if "$SCRIPT_DIR/../build/build-cli.sh"; then
    log_info "CLI build completed"
else
    log_error "CLI build failed"
    exit 1
fi

log_step "Running CLI integration tests..."

CMD=("npm" "test")
if [[ -n "$FILTER" ]]; then
    CMD+=("--" "--grep" "$FILTER")
fi

if (cd "$CLI_DIR" && "${CMD[@]}"); then
    log_info "CLI tests passed"
else
    log_error "CLI tests failed"
    exit 1
fi
