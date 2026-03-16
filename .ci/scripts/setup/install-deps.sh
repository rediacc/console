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

# Clean npm cache and stale node_modules to avoid corruption on CI runners
if [[ "${CI:-false}" == "true" ]]; then
    log_info "Cleaning npm cache (CI environment)"
    npm cache clean --force 2>/dev/null || true
    # Remove stale node_modules that may have wrong platform binaries
    rm -rf node_modules 2>/dev/null || true
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
# Explicitly install the native bindings for the current platform.
NATIVE_PKGS=""
case "${CI_OS}-${CI_ARCH:-x64}" in
    linux-x64) NATIVE_PKGS="@rollup/rollup-linux-x64-gnu @esbuild/linux-x64 lightningcss-linux-x64-gnu" ;;
    linux-arm64) NATIVE_PKGS="@rollup/rollup-linux-arm64-gnu @esbuild/linux-arm64 lightningcss-linux-arm64-gnu" ;;
    macos-arm64) NATIVE_PKGS="@rollup/rollup-darwin-arm64 @esbuild/darwin-arm64 lightningcss-darwin-arm64" ;;
    macos-x64) NATIVE_PKGS="@rollup/rollup-darwin-x64 @esbuild/darwin-x64 lightningcss-darwin-x64" ;;
    windows-*) NATIVE_PKGS="@rollup/rollup-win32-x64-msvc @esbuild/win32-x64" ;;
esac
if [[ -n "$NATIVE_PKGS" ]]; then
    log_info "Installing native bindings: $NATIVE_PKGS"
    for pkg in $NATIVE_PKGS; do
        if [[ ! -d "node_modules/$pkg" ]]; then
            npm install "$pkg" --no-save --ignore-scripts 2>/dev/null || true
        fi
    done
fi

# Install account dependencies if submodule is available
if [[ -f "private/account/package.json" ]]; then
    log_step "Installing account dependencies..."
    (cd private/account && npm ci)
fi

log_info "npm install complete"
