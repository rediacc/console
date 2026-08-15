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

# Phase 3b: TypeScript typecheck (e2e). NOTHING checked this until 2026-08-15,
# and the cost was a TS2352 sitting on a branch unseen: the backup wave made
# `kind` part of BackupDestinationSchema while an e2e fixture still built a
# destination without one. Playwright TRANSPILES without typechecking, so the
# suite ran green over a type error, and the schema's own `.default('storage')`
# meant runtime was fine too. Two layers of "works anyway" is exactly how a
# type error becomes invisible.
#
# It lives here rather than in a new gate key because this script is already
# the place a reader looks for "does the account package typecheck", and a
# third phase costs nothing next to the two above it.
log_step "Typechecking account e2e suite..."
cd "$ACCOUNT_DIR"
if ! npx tsc --noEmit -p e2e/tsconfig.json; then
    log_error "e2e typecheck failed!"
    exit 1
fi
log_info "e2e typecheck passed"

# Phase 4: Lint (if biome is available)
log_step "Linting account portal frontend..."
cd "$REPO_ROOT"
if ! npx biome check private/account/web/src/; then
    log_warn "Frontend lint issues found (non-blocking)"
fi

# Phase 5: Generate onboarding content from canonical www tutorials
log_step "Generating account onboarding content..."
cd "$REPO_ROOT"
if ! npm run build:account-onboarding; then
    log_error "Account onboarding content generation failed!"
    exit 1
fi
log_info "Account onboarding content generated"

# Phase 6: Build frontend
log_step "Building account portal frontend..."
cd "$WEB_DIR"
if ! npx vite build; then
    log_error "Frontend build failed!"
    exit 1
fi
log_info "Frontend build succeeded"

# Phase 7: Verify output exists
OUTPUT_FILE="$REPO_ROOT/workers/account/dist/account/index.html"
if [[ ! -f "$OUTPUT_FILE" ]]; then
    log_error "Expected build output not found: $OUTPUT_FILE"
    exit 1
fi
log_info "Build output verified: $OUTPUT_FILE"

exit 0
