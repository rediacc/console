#!/bin/bash
# Setup virtual display (Xvfb) for Linux GUI tests
# Usage: setup-display.sh
#
# This script is only needed on Linux for Electron/GUI tests.
# It installs X11 dependencies and starts Xvfb.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Only run on Linux
if [[ "$CI_OS" != "linux" ]]; then
    log_info "Display setup not needed on $CI_OS"
    exit 0
fi

log_step "Setting up virtual display (Xvfb)..."

# Install X11 dependencies
log_step "Installing X11 dependencies..."
sudo apt-get update -qq
sudo apt-get install -y \
    xvfb \
    libgtk-3-0 \
    libnotify4 \
    libnss3 \
    libxss1 \
    libxtst6 \
    xdg-utils \
    libatspi2.0-0 \
    libsecret-1-0

# Start Xvfb
log_step "Starting Xvfb..."
Xvfb :99 -screen 0 1920x1080x24 &
XVFB_PID=$!

# Wait for Xvfb to start
sleep 2

# Verify Xvfb is running
if kill -0 $XVFB_PID 2>/dev/null; then
    log_info "Xvfb started successfully (PID: $XVFB_PID)"
else
    log_error "Failed to start Xvfb"
    exit 1
fi

# Export DISPLAY
export DISPLAY=:99

# If running in GitHub Actions, append to GITHUB_ENV
if [[ -n "${GITHUB_ENV:-}" ]]; then
    echo "DISPLAY=:99" >> "$GITHUB_ENV"
    log_info "Added DISPLAY=:99 to GITHUB_ENV"
fi

log_info "Virtual display setup complete (DISPLAY=:99)"
