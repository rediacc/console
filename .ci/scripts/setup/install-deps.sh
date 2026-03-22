#!/bin/bash
# Install npm dependencies with platform-specific handling
# Usage: install-deps.sh [--ignore-scripts]
#
# On Windows, --ignore-scripts is added automatically to avoid
# native module rebuild issues with electron-builder.
#
# IMPORTANT: The lockfile (package-lock.json) must contain resolved entries
# for ALL platform-specific optional deps (rollup, lightningcss, esbuild).
# Never regenerate the lockfile by deleting it on a single platform — this
# drops entries for other platforms. Instead, use `npm install <pkg>` to
# update individual packages while preserving cross-platform entries.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
IGNORE_SCRIPTS=false
for arg in "$@"; do
    case "$arg" in
        --ignore-scripts) IGNORE_SCRIPTS=true ;;
    esac
done

# Change to repo root
cd "$(get_repo_root)"

log_step "Installing npm dependencies..."

# Clean npm cache to avoid corruption issues on CI runners
if [[ "${CI:-false}" == "true" ]]; then
    log_info "Cleaning npm cache (CI environment)"
    npm cache clean --force 2>/dev/null || true
fi

# Build npm ci command
NPM_ARGS="ci"

# Windows requires --ignore-scripts to avoid electron-builder install-app-deps timeout
if [[ "$CI_OS" == "windows" ]] || [[ "$IGNORE_SCRIPTS" == "true" ]]; then
    NPM_ARGS="$NPM_ARGS --ignore-scripts"
    log_info "Using --ignore-scripts flag"
fi

# Run npm ci with retry for network failures (Electron downloads can 504)
run_npm_ci() {
    npm $NPM_ARGS
}

if retry_with_backoff 3 10 run_npm_ci; then
    log_info "Dependencies installed successfully"
else
    log_error "Failed to install dependencies after retries"
    exit 1
fi

# Verify node_modules exists
if [[ ! -d "node_modules" ]]; then
    log_error "node_modules directory not created"
    exit 1
fi

# Install account dependencies if submodule is available
if [[ -f "private/account/package.json" ]]; then
    log_step "Installing account dependencies..."
    run_account_ci() { (cd private/account && npm ci); }
    retry_with_backoff 3 10 run_account_ci
fi

log_info "npm install complete"
