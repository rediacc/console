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

# Workaround: npm install may skip platform-specific optional deps (npm/cli#4828)
# Detect missing native bindings and install via npm pack fallback.
install_native_fallback() {
    local pkg_name="$1" pkg_version="$2"
    if [[ ! -d "node_modules/$pkg_name" ]]; then
        log_warn "Missing $pkg_name — installing via npm pack..."
        mkdir -p "node_modules/$pkg_name"
        local tarball
        tarball=$(npm pack "${pkg_name}@${pkg_version}" 2>/dev/null) || true
        if [[ -f "$tarball" ]]; then
            tar xzf "$tarball" -C "node_modules/$pkg_name" --strip-components=1
            rm -f "$tarball"
            log_info "Installed $pkg_name"
        else
            log_warn "Could not install $pkg_name"
        fi
    fi
}

PLATFORM_SUFFIX=$(node -e "const m={'linux-x64':'linux-x64-gnu','linux-arm64':'linux-arm64-gnu','darwin-arm64':'darwin-arm64','darwin-x64':'darwin-x64','win32-x64':'win32-x64-msvc'};console.log(m[process.platform+'-'+process.arch]||'')" 2>/dev/null || true)
if [[ -n "$PLATFORM_SUFFIX" ]]; then
    # Rollup
    ROLLUP_V=$(node -e "try{console.log(require('rollup/package.json').version)}catch{}" 2>/dev/null || true)
    [[ -n "$ROLLUP_V" ]] && install_native_fallback "@rollup/rollup-${PLATFORM_SUFFIX}" "$ROLLUP_V"

    # LightningCSS (may not export package.json, read directly)
    LCSS_V=""
    if [[ -f "node_modules/lightningcss/package.json" ]]; then
        LCSS_V=$(node -e "console.log(require('./node_modules/lightningcss/package.json').version)" 2>/dev/null || true)
    fi
    [[ -n "$LCSS_V" ]] && install_native_fallback "lightningcss-${PLATFORM_SUFFIX}" "$LCSS_V"

    # esbuild (uses different suffix: linux-arm64 not linux-arm64-gnu)
    ESBUILD_SUFFIX=$(node -e "console.log(process.platform+'-'+process.arch)" 2>/dev/null || true)
    ESBUILD_V=$(node -e "try{console.log(require('esbuild/package.json').version)}catch{}" 2>/dev/null || true)
    [[ -n "$ESBUILD_V" ]] && install_native_fallback "@esbuild/${ESBUILD_SUFFIX}" "$ESBUILD_V"
fi

# Install account dependencies if submodule is available
if [[ -f "private/account/package.json" ]]; then
    log_step "Installing account dependencies..."
    (cd private/account && npm ci)
fi

log_info "npm install complete"
