#!/bin/bash
# Build desktop application for distribution
# Usage: build-desktop.sh --platform <linux|mac|win> --arch <x64|arm64>
#
# Options:
#   --platform  Target platform: linux, mac, or win
#   --arch      Target architecture: x64 or arm64
#
# Prerequisites:
#   - Web application must be built first
#   - Electron main/preload must be built first
#
# Example:
#   .ci/scripts/build/build-desktop.sh --platform linux --arch x64

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

PLATFORM="${ARG_PLATFORM:-}"
ARCH="${ARG_ARCH:-}"

# Validate required arguments
if [[ -z "$PLATFORM" ]] || [[ -z "$ARCH" ]]; then
    log_error "Usage: build-desktop.sh --platform <linux|mac|win> --arch <x64|arm64>"
    exit 1
fi

# Validate platform
case "$PLATFORM" in
    linux|mac|win) ;;
    *)
        log_error "Invalid platform: $PLATFORM (must be linux, mac, or win)"
        exit 1
        ;;
esac

# Validate architecture
case "$ARCH" in
    x64|arm64) ;;
    *)
        log_error "Invalid architecture: $ARCH (must be x64 or arm64)"
        exit 1
        ;;
esac

# Change to repo root
cd "$(get_repo_root)"

DESKTOP_DIR="packages/desktop"

log_step "Building desktop app for $PLATFORM-$ARCH..."

# Verify prerequisites
if [[ ! -d "packages/web/dist" ]]; then
    log_error "Web app not built. Run build-web.sh first."
    exit 1
fi

if [[ ! -f "$DESKTOP_DIR/out/main/index.js" ]]; then
    log_warn "Electron main not built. Building now..."
    (cd "$DESKTOP_DIR" && npm run build)
fi

# Build Electron main/preload if needed
if [[ ! -f "$DESKTOP_DIR/out/main/index.js" ]] || [[ ! -f "$DESKTOP_DIR/out/preload/index.js" ]]; then
    log_step "Building Electron main/preload..."
    (cd "$DESKTOP_DIR" && npm run build)
fi

# Windows-specific: Ensure externalized modules are available locally.
# On Windows, --ignore-scripts skips the postinstall hook (install-app-deps),
# so hoisted modules aren't linked into the desktop package's node_modules/.
# electron-builder needs them there to include in the packaged app.
if [[ "$PLATFORM" == "win" ]]; then
    # Resolve externalized modules and their transitive dependencies
    "$SCRIPT_DIR/resolve-desktop-externals.sh"

    log_step "Bundling MSYS2 for Windows..."
    (cd "$DESKTOP_DIR" && npm run bundle:msys2) || log_warn "MSYS2 bundling skipped"
fi

# Create distribution package
log_step "Creating distribution package..."

case "$PLATFORM" in
    linux)
        (cd "$DESKTOP_DIR" && npm run dist:linux -- --$ARCH)
        ;;
    mac)
        export CSC_IDENTITY_AUTO_DISCOVERY=false  # Skip code signing in CI
        (cd "$DESKTOP_DIR" && npm run dist:mac -- --$ARCH)
        ;;
    win)
        (cd "$DESKTOP_DIR" && npm run dist:win -- --$ARCH)
        # Rename for consistent platform-suffixed naming
        if [[ -f "dist/desktop/latest.yml" ]]; then
            mv dist/desktop/latest.yml dist/desktop/latest-win.yml
        fi
        ;;
esac

# Verify output
if [[ -d "dist/desktop" ]]; then
    log_info "Desktop build complete"
    ls -lah dist/desktop/
else
    log_error "Desktop build output not found"
    exit 1
fi

log_info "Desktop build complete: dist/desktop/"
