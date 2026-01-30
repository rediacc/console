#!/bin/bash
# Run CLI local mode E2E tests
# Usage: run-cli-local.sh
#
# Builds the CLI and runs only the 'e2e' Playwright project,
# which contains local execution E2E tests.
#
# Prerequisites:
#   - renet binary in PATH
#   - .env file with E2E_VM1_IP, E2E_SSH_USER, E2E_SSH_KEY
#
# Example:
#   .ci/scripts/test/run-cli-local.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

cd "$(get_repo_root)"

CLI_DIR="packages/cli"

# Build CLI (required for cli-bundle.cjs)
log_step "Building CLI..."
if "$SCRIPT_DIR/../build/build-cli.sh"; then
    log_info "CLI build completed"
else
    log_error "CLI build failed"
    exit 1
fi

# Verify renet is available
if ! command -v renet &>/dev/null; then
    log_error "renet not found in PATH"
    exit 1
fi
log_info "renet: $(which renet)"

log_step "Running CLI local mode E2E tests..."
if (cd "$CLI_DIR" && npx playwright test --config tests/playwright.config.ts --project=e2e --workers=1 --reporter=list); then
    log_info "CLI local mode E2E tests passed"
else
    log_error "CLI local mode E2E tests failed"
    exit 1
fi
