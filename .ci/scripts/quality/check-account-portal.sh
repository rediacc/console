#!/bin/bash
# Check that the account portal frontend compiles and builds correctly
#
# Usage:
#   .ci/scripts/quality/check-account-portal.sh
#
# Exit codes:
#   0 - All checks pass
#   1 - Check failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
WEB_DIR="$REPO_ROOT/private/account/web"
ACCOUNT_DIR="$REPO_ROOT/private/account"

cd "$REPO_ROOT"

# Phase 1: Check that frontend dependencies are installed
log_step "Checking frontend dependencies..."
if [[ ! -d "$WEB_DIR/node_modules" ]]; then
    log_step "Installing frontend dependencies..."
    cd "$WEB_DIR" && npm ci --ignore-scripts
    cd "$REPO_ROOT"
fi

# Phase 2: TypeScript typecheck (frontend)
log_step "Typechecking account portal frontend..."
cd "$WEB_DIR"
if ! npx tsc --noEmit; then
    log_error "Frontend typecheck failed!"
    exit 1
fi
log_info "Frontend typecheck passed"

# Phase 3: TypeScript typecheck (backend)
log_step "Typechecking account portal backend..."
cd "$ACCOUNT_DIR"
if ! npx tsc --noEmit; then
    log_error "Backend typecheck failed!"
    exit 1
fi
log_info "Backend typecheck passed"

# Phase 4: Lint (if biome is available)
log_step "Linting account portal frontend..."
cd "$REPO_ROOT"
if ! npx biome check private/account/web/src/; then
    log_warn "Frontend lint issues found (non-blocking)"
fi

# Phase 5: Build frontend
log_step "Building account portal frontend..."
cd "$WEB_DIR"
if ! npx vite build; then
    log_error "Frontend build failed!"
    exit 1
fi
log_info "Frontend build succeeded"

# Phase 6: Verify output exists
OUTPUT_FILE="$REPO_ROOT/workers/www/dist/account/index.html"
if [[ ! -f "$OUTPUT_FILE" ]]; then
    log_error "Expected build output not found: $OUTPUT_FILE"
    exit 1
fi
log_info "Build output verified: $OUTPUT_FILE"

exit 0
