#!/bin/bash
# Install npm dependencies with platform-specific handling
# Usage: install-deps.sh [--ignore-scripts]
#
# On Windows, --ignore-scripts is added automatically to avoid
# native module rebuild issues with electron-builder.

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

# Workaround for npm bug with optional dependencies on cross-platform CI
# https://github.com/npm/cli/issues/4828
NPM_ARGS="$NPM_ARGS --include=optional"

# Run npm ci
if npm $NPM_ARGS; then
    log_info "Dependencies installed successfully"
else
    log_error "Failed to install dependencies"
    exit 1
fi

# Verify node_modules exists
if [[ ! -d "node_modules" ]]; then
    log_error "node_modules directory not created"
    exit 1
fi

# Workaround: npm ci may skip platform-specific optional deps (npm/cli#4828)
# Delete package-lock.json temporarily and re-run npm install to force resolution
# of all platform-specific native bindings (@rollup/*, @esbuild/*, lightningcss-*).
log_info "Ensuring platform-specific optional dependencies..."
rm -f package-lock.json
npm install --prefer-offline 2>/dev/null || npm install 2>/dev/null || true
git checkout package-lock.json 2>/dev/null || true

# Install account dependencies if submodule is available
if [[ -f "private/account/package.json" ]]; then
    log_step "Installing account dependencies..."
    (cd private/account && npm ci)
fi

log_info "npm install complete"
