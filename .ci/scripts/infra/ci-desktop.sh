#!/bin/bash
# CI Desktop Environment Setup Script
# Installs and starts a desktop environment accessible via browser
#
# Supported environments:
#   - none  (default): No desktop environment
#   - xfce:  Lightweight, fast startup (~300MB)
#   - gnome: GNOME Flashback with Metacity (~400MB) - classic GNOME experience
#   - mate:  GNOME 2 fork, stable (~350MB)
#
# Note: Full GNOME Shell requires compositing/3D which Xvfb doesn't support.
#       We use GNOME Flashback instead, which works perfectly with VNC.
#
# Architecture:
#   Runner: Xvfb + [Desktop Environment] + x11vnc + websockify + noVNC
#   Access: http://localhost:6080/vnc.html → VNC → Desktop
#
# This runs on the GitHub Actions runner (Ubuntu), not in a container.
#
# Usage:
#   ./ci-desktop.sh              # Normal mode (cleanup on exit)
#   ./ci-desktop.sh --keep-running  # CI mode (no cleanup trap)

set -e

# Parse arguments
KEEP_RUNNING=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --keep-running)
            KEEP_RUNNING=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Source common utilities if available
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/../lib/common.sh" ]]; then
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/../lib/common.sh"
fi

# Cleanup function for graceful shutdown
cleanup() {
    "${SCRIPT_DIR}/ci-desktop-cleanup.sh"
}

# Only set trap if not in keep-running mode
if [[ "$KEEP_RUNNING" != "true" ]]; then
    trap cleanup EXIT
fi

# Helper function to wait for a port to be ready
wait_for_port() {
    local port=$1
    local timeout=${2:-30}
    local elapsed=0

    while ! nc -z localhost "$port" 2>/dev/null; do
        if [ $elapsed -ge $timeout ]; then
            return 1
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 0
}

# ============================================================================
# Desktop Environment Installation Functions
# ============================================================================

install_base_packages() {
    echo "Installing base packages..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        xvfb \
        x11vnc \
        novnc \
        websockify \
        dbus-x11 \
        netcat-openbsd \
        gnome-keyring \
        libsecret-1-0
    echo "Base packages installed"
}

install_xfce() {
    echo "Installing Xfce desktop environment..."
    sudo apt-get install -y -qq \
        xfce4 \
        xfce4-terminal
    echo "Xfce installed"
}

install_gnome() {
    echo "Installing GNOME Flashback desktop environment..."
    # GNOME Shell requires compositing/3D which Xvfb doesn't support
    # GNOME Flashback uses Metacity (non-compositing WM) - works with VNC/Xvfb
    # See: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=776746
    sudo apt-get install -y -qq \
        gnome-session-flashback \
        gnome-terminal \
        gnome-control-center \
        metacity \
        gnome-panel \
        adwaita-icon-theme \
        nautilus
    echo "GNOME Flashback installed"
    echo "Using GNOME Flashback (Metacity) for VNC compatibility"
}

install_mate() {
    echo "Installing MATE desktop environment..."
    sudo apt-get install -y -qq \
        mate-desktop-environment-core \
        mate-terminal
    echo "MATE installed"
}

# ============================================================================
# Desktop Environment Start Functions
# ============================================================================

start_xfce() {
    echo "Starting Xfce4 desktop..."
    startxfce4 &
    DE_PID=$!
    sleep 3

    if ! kill -0 $DE_PID 2>/dev/null; then
        echo "ERROR: Failed to start Xfce desktop session"
        exit 1
    fi
    echo "Xfce4 desktop started (PID: $DE_PID)"
}

start_gnome() {
    echo "Starting GNOME Flashback (Metacity) desktop..."
    # Use gnome-flashback-metacity session which doesn't require compositing
    # This works with Xvfb unlike full GNOME Shell which needs 3D/EGL
    export XDG_SESSION_TYPE=x11
    export XDG_CURRENT_DESKTOP="GNOME-Flashback:GNOME"
    export XDG_MENU_PREFIX="gnome-flashback-"

    gnome-session --session=gnome-flashback-metacity 2>/tmp/gnome-session.log &
    DE_PID=$!
    sleep 4

    if ! kill -0 $DE_PID 2>/dev/null; then
        echo "ERROR: Failed to start GNOME Flashback session"
        echo "Session log:"
        cat /tmp/gnome-session.log 2>/dev/null || true
        exit 1
    fi
    echo "GNOME Flashback desktop started (PID: $DE_PID)"
}

start_mate() {
    echo "Starting MATE desktop..."
    mate-session &
    DE_PID=$!
    sleep 3

    if ! kill -0 $DE_PID 2>/dev/null; then
        echo "ERROR: Failed to start MATE desktop session"
        exit 1
    fi
    echo "MATE desktop started (PID: $DE_PID)"
}

# ============================================================================
# Common Setup Functions
# ============================================================================

install_nodejs() {
    echo "Installing Node.js 24.x..."
    curl -fsSL https://deb.nodesource.com/setup_24.x | sudo -E bash -
    sudo apt-get install -y -qq nodejs
    echo "Node.js $(node -v) installed"
}

install_vscode() {
    echo "Installing VS Code..."
    sudo apt-get install -y -qq wget gpg
    wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor >/tmp/packages.microsoft.gpg
    sudo install -D -o root -g root -m 644 /tmp/packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
    echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | sudo tee /etc/apt/sources.list.d/vscode.list >/dev/null
    rm -f /tmp/packages.microsoft.gpg
    sudo apt-get update -qq
    sudo apt-get install -y -qq code
    echo "VS Code installed"

    echo "Installing VS Code extensions..."
    code --install-extension ms-vscode-remote.remote-ssh
    echo "VS Code Remote SSH extension installed"
}

install_rediacc_desktop() {
    echo "Installing Rediacc Console Desktop..."

    # Get middleware URL from environment or use default
    local base_url="${MIDDLEWARE_URL:-http://localhost}"

    # Fetch cli-packages.json once and reuse
    local cli_packages
    cli_packages=$(curl -sf "${base_url}/cli-packages.json") || true

    # Check if desktop packages are available
    if ! echo "$cli_packages" | jq -e '.packages.desktop' >/dev/null 2>&1; then
        echo "Desktop packages not embedded in this distribution"
        echo "Skipping Rediacc Desktop installation"
        return 0
    fi

    # Get AppImage filename from cached response
    local appimage_info
    appimage_info=$(echo "$cli_packages" | jq -r '.packages.desktop.platforms["linux-x64"].appimage // empty')
    if [ -z "$appimage_info" ]; then
        echo "No Linux x64 AppImage available"
        return 0
    fi

    local filename
    filename=$(echo "$appimage_info" | jq -r '.filename')
    local download_url="${base_url}/desktop/${filename}"

    # Install AppImage
    local install_dir="/opt/rediacc-console"
    sudo mkdir -p "$install_dir"

    echo "  Downloading ${filename}..."
    if ! sudo curl -sf "$download_url" -o "${install_dir}/rediacc-console.AppImage"; then
        echo "WARNING: Failed to download Rediacc Desktop AppImage"
        return 0
    fi

    sudo chmod +x "${install_dir}/rediacc-console.AppImage"

    # Create desktop shortcut
    mkdir -p ~/Desktop
    cat >~/Desktop/rediacc-console-app.desktop <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Rediacc Console (Desktop)
Comment=Rediacc Console Desktop Application
Exec=${install_dir}/rediacc-console.AppImage --no-sandbox %U
Icon=rediacc-console
Terminal=false
Categories=Development;
MimeType=x-scheme-handler/rediacc;
EOF
    chmod +x ~/Desktop/rediacc-console-app.desktop
    gio set ~/Desktop/rediacc-console-app.desktop metadata::trusted true 2>/dev/null || true

    echo "Rediacc Desktop installed at ${install_dir}/"
}

configure_chromium() {
    echo "Configuring Chromium policies..."
    sudo mkdir -p /etc/chromium/policies/managed
    sudo tee /etc/chromium/policies/managed/no-first-run.json >/dev/null <<'EOF'
{
    "BrowserSignin": 0,
    "SyncDisabled": true,
    "MetricsReportingEnabled": false,
    "DefaultBrowserSettingEnabled": false,
    "PromotionalTabsEnabled": false,
    "CommandLineFlagSecurityWarningsEnabled": false
}
EOF

    # Also set user-level first run flag
    mkdir -p ~/.config/chromium
    touch ~/.config/chromium/First\ Run
    echo "Chromium configured"
}

create_desktop_shortcut() {
    echo "Creating desktop shortcut..."
    mkdir -p ~/Desktop
    cat >~/Desktop/rediacc-console.desktop <<'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Rediacc Console
Comment=Open Rediacc Console in Chromium
Exec=chromium-browser --no-sandbox http://localhost/console
Icon=chromium-browser
Terminal=false
Categories=Network;WebBrowser;
EOF
    chmod +x ~/Desktop/rediacc-console.desktop

    # Mark desktop file as trusted (skip "untrusted" prompt)
    gio set ~/Desktop/rediacc-console.desktop metadata::trusted true 2>/dev/null || true
    echo "Desktop shortcut created"
}

start_xvfb() {
    echo "Starting virtual display :${DISPLAY_NUM}..."
    Xvfb :${DISPLAY_NUM} -screen 0 ${RESOLUTION}x${COLOR_DEPTH} &
    XVFB_PID=$!
    sleep 2

    if ! kill -0 $XVFB_PID 2>/dev/null; then
        echo "ERROR: Failed to start Xvfb"
        exit 1
    fi
    echo "Virtual display started (PID: $XVFB_PID)"

    export DISPLAY=:${DISPLAY_NUM}
}

start_dbus() {
    echo "Starting D-Bus session..."
    eval "$(dbus-launch --sh-syntax)"
    export DBUS_SESSION_BUS_ADDRESS
}

init_keyring() {
    echo "Initializing keyring with empty password..."
    mkdir -p ~/.local/share/keyrings
    echo -n "" | gnome-keyring-daemon --unlock --components=secrets,pkcs11 2>/dev/null || true
    eval "$(echo -n "" | gnome-keyring-daemon --start --components=secrets,pkcs11 2>/dev/null)" || true
    export GNOME_KEYRING_CONTROL
    export SSH_AUTH_SOCK
}

start_vnc() {
    echo "Starting VNC server on port ${VNC_PORT}..."
    x11vnc -display :${DISPLAY_NUM} \
        -rfbport ${VNC_PORT} \
        -nopw \
        -forever \
        -shared \
        -bg \
        -o /tmp/x11vnc.log

    echo "  Waiting for VNC server to be ready..."
    if ! wait_for_port ${VNC_PORT} 10; then
        echo "ERROR: Failed to start VNC server"
        cat /tmp/x11vnc.log 2>/dev/null || true
        exit 1
    fi
    echo "VNC server started on port ${VNC_PORT}"
}

start_novnc() {
    echo "Starting noVNC on port ${NOVNC_PORT}..."

    # Find noVNC web directory (varies by distro)
    NOVNC_WEB="/usr/share/novnc"
    if [ ! -d "$NOVNC_WEB" ]; then
        NOVNC_WEB="/usr/share/javascript/novnc"
    fi

    websockify --web=${NOVNC_WEB} ${NOVNC_PORT} localhost:${VNC_PORT} &
    WEBSOCKIFY_PID=$!

    echo "  Waiting for noVNC to be ready..."
    if ! wait_for_port ${NOVNC_PORT} 10; then
        echo "ERROR: Failed to start noVNC/websockify"
        exit 1
    fi
    echo "noVNC started on port ${NOVNC_PORT}"
}

# ============================================================================
# Main Script
# ============================================================================

# Configuration (can be overridden by environment variables)
DESKTOP_ENVIRONMENT="${DESKTOP_ENVIRONMENT:-none}"
DISPLAY_NUM="${DESKTOP_DISPLAY:-99}"
VNC_PORT="${DESKTOP_VNC_PORT:-5999}"
NOVNC_PORT="${DESKTOP_NOVNC_PORT:-6080}"
RESOLUTION="${DESKTOP_RESOLUTION:-1600x900}"
COLOR_DEPTH="${DESKTOP_COLOR_DEPTH:-24}"

# Validate desktop environment
case "$DESKTOP_ENVIRONMENT" in
    xfce | gnome | mate) ;;
    *)
        echo "ERROR: Unknown desktop environment: $DESKTOP_ENVIRONMENT"
        echo "   Supported: xfce, gnome, mate"
        exit 1
        ;;
esac

echo "================================================================"
echo "Setting up Desktop Environment"
echo "================================================================"
echo ""
echo "Configuration:"
echo "  Environment: ${DESKTOP_ENVIRONMENT}"
echo "  Display: :${DISPLAY_NUM}"
echo "  Resolution: ${RESOLUTION}x${COLOR_DEPTH}"
echo "  VNC Port: ${VNC_PORT}"
echo "  noVNC Port: ${NOVNC_PORT}"
echo "  Keep Running: ${KEEP_RUNNING}"
echo ""

# Create directories
mkdir -p ~/.vnc
mkdir -p /tmp/.X11-unix

# Install packages
install_base_packages

case "$DESKTOP_ENVIRONMENT" in
    xfce)
        install_xfce
        ;;
    gnome)
        install_gnome
        ;;
    mate)
        install_mate
        ;;
esac

install_nodejs
install_vscode
configure_chromium
create_desktop_shortcut
install_rediacc_desktop

# Start display and session infrastructure
start_xvfb
start_dbus
init_keyring

# Start desktop environment
case "$DESKTOP_ENVIRONMENT" in
    xfce)
        start_xfce
        ;;
    gnome)
        start_gnome
        ;;
    mate)
        start_mate
        ;;
esac

# Start VNC stack
start_vnc
start_novnc

# Save PIDs for cleanup
cat >/tmp/desktop-pids.txt <<EOF
XVFB_PID=$XVFB_PID
DE_PID=$DE_PID
WEBSOCKIFY_PID=$WEBSOCKIFY_PID
EOF

echo ""
echo "================================================================"
echo "Desktop environment ready!"
echo ""
echo "Environment: ${DESKTOP_ENVIRONMENT}"
echo "Direct access (local): http://localhost:${NOVNC_PORT}/vnc.html"
echo "================================================================"

# Output for GitHub Actions
if [ -n "$GITHUB_OUTPUT" ]; then
    echo "desktop-port=${NOVNC_PORT}" >>$GITHUB_OUTPUT
    echo "desktop-url=http://localhost:${NOVNC_PORT}/vnc.html" >>$GITHUB_OUTPUT
    echo "desktop-environment=${DESKTOP_ENVIRONMENT}" >>$GITHUB_OUTPUT
fi

# If keep-running mode, clear the trap (already not set, but be explicit)
if [[ "$KEEP_RUNNING" == "true" ]]; then
    echo "Keep-running mode enabled - desktop processes will persist"
fi
