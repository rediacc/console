#!/bin/bash
# Run unit tests for all packages
# Usage: run-unit.sh [--coverage]
#
# Runs unit tests for @rediacc/shared, @rediacc/shared-desktop, @rediacc/web, @rediacc/cli
#
# Options:
#   --coverage  Generate coverage report

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
COVERAGE=false
for arg in "$@"; do
    case "$arg" in
        --coverage) COVERAGE=true ;;
    esac
done

# Change to repo root
cd "$(get_repo_root)"

log_step "Running unit tests..."

# Run tests for each package
FAILED=false

log_step "Testing @rediacc/shared..."
if ! npm run test -w @rediacc/shared; then
    log_error "@rediacc/shared tests failed"
    FAILED=true
fi

log_step "Testing @rediacc/shared-desktop..."
if ! npm run test -w @rediacc/shared-desktop; then
    log_error "@rediacc/shared-desktop tests failed"
    FAILED=true
fi

log_step "Testing @rediacc/web..."
if ! npm run test:run -w @rediacc/web; then
    log_error "@rediacc/web tests failed"
    FAILED=true
fi

log_step "Testing @rediacc/cli (unit)..."
if ! npm run test:unit -w @rediacc/cli; then
    log_error "@rediacc/cli unit tests failed"
    FAILED=true
fi

# Generate coverage report if requested
if [[ "$COVERAGE" == "true" ]]; then
    log_step "Generating coverage report..."
    npm run test:coverage || log_warn "Coverage generation failed"
fi

if [[ "$FAILED" == "true" ]]; then
    log_error "Some unit tests failed"
    exit 1
fi

log_info "All unit tests passed"
