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

# Clean npm cache on CI runners
if [[ "${CI:-false}" == "true" ]]; then
    log_info "Cleaning npm cache (CI environment)"
    npm cache clean --force 2>/dev/null || true
fi

# Build npm install command
# Use `npm install` instead of `npm ci` to properly resolve optional
# platform-specific dependencies (npm/cli#4828). npm ci skips optional
# deps on cross-platform CI runners.
NPM_ARGS="install"

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

# Verify rollup native binding is present (npm/cli#4828 workaround)
ROLLUP_VERSION=$(node -e "try{console.log(require('rollup/package.json').version)}catch{}" 2>/dev/null || true)
if [[ -n "$ROLLUP_VERSION" ]]; then
    ROLLUP_DIR=$(node -e "const p=process.platform,a=process.arch;const m={'linux-x64':'linux-x64-gnu','linux-arm64':'linux-arm64-gnu','darwin-arm64':'darwin-arm64','darwin-x64':'darwin-x64','win32-x64':'win32-x64-msvc'};console.log('@rollup/rollup-'+(m[p+'-'+a]||'unknown'))" 2>/dev/null)
    if [[ ! -d "node_modules/$ROLLUP_DIR" ]]; then
        log_warn "Missing $ROLLUP_DIR — installing via npm pack fallback..."
        mkdir -p "node_modules/$ROLLUP_DIR"
        ROLLUP_TARBALL=$(npm pack "$ROLLUP_DIR@$ROLLUP_VERSION" 2>/dev/null) || true
        if [[ -f "$ROLLUP_TARBALL" ]]; then
            tar xzf "$ROLLUP_TARBALL" -C "node_modules/$ROLLUP_DIR" --strip-components=1
            rm -f "$ROLLUP_TARBALL"
            log_info "Installed $ROLLUP_DIR via tarball fallback"
        else
            log_warn "Could not download $ROLLUP_DIR — build may fail"
        fi
    fi
fi

# Install account dependencies if submodule is available
if [[ -f "private/account/package.json" ]]; then
    log_step "Installing account dependencies..."
    (cd private/account && npm ci)
fi

log_info "npm install complete"
