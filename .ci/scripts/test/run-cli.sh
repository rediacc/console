#!/bin/bash
# Run CLI integration tests
# Usage: run-cli.sh [--filter <pattern>] [--backend <url|preset>]
#
# Options:
#   --filter            Filter tests by pattern
#   --backend           Backend URL or preset (local, sandbox, or custom URL)
#   --skip-health-check Skip backend health validation
#
# Example:
#   .ci/scripts/test/run-cli.sh --filter "auth"
#   .ci/scripts/test/run-cli.sh --backend https://abc123.trycloudflare.com
#   .ci/scripts/test/run-cli.sh --backend sandbox
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
BACKEND="${ARG_BACKEND:-}"
SKIP_HEALTH_CHECK="${ARG_SKIP_HEALTH_CHECK:-false}"

# Handle --backend option
if [[ -n "$BACKEND" ]]; then
    source "$SCRIPT_DIR/../../lib/backend-url.sh"
    BACKEND_URL=$(resolve_backend_url "$BACKEND") || {
        log_error "Invalid backend: $BACKEND (use URL or preset: local, sandbox)"
        exit 1
    }
    log_info "Using backend: $BACKEND_URL"

    # Validate backend is accessible (unless --skip-health-check)
    if [[ "$SKIP_HEALTH_CHECK" != "true" ]]; then
        log_step "Validating backend health..."
        if ! wait_for_backend "$BACKEND_URL" 30; then
            log_error "Backend not accessible: $BACKEND_URL"
            log_info "Use --skip-health-check to proceed anyway"
            exit 1
        fi
        log_info "Backend is healthy"
    fi

    # Export for CLI tests
    CLI_API_URL="$(get_api_url "$BACKEND_URL")"
    export CLI_API_URL
fi

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
