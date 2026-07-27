#!/bin/bash
# Install the packages desktop-ctl.sh needs. INSTALL ONLY -- starts nothing.
#
# The install/start split is the whole point. The deleted
# .ci/scripts/infra/ci-desktop.sh welded 420 lines of apt-install and service
# startup into one path with no stop verb, so a caller that already had the
# packages (the devcontainer, whose image bakes them in) could not reuse any of
# it. Separating them means the devcontainer installs at IMAGE BUILD time and
# CI installs at RUN time, while both start services the same way.
#
# ONE DESKTOP ENVIRONMENT, NOT THREE. The old script offered xfce, gnome
# (Flashback+Metacity) and mate, which meant three start paths, three log files
# and three failure modes -- and only xfce was ever exercised, because that is
# what the devcontainer image bakes. Untested options are not features.
#
# Usage: install-vnc-desktop.sh [--extras vscode,chromium]
# Exit:  0 ok, 1 install failed, 3 unsupported platform.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

parse_args "$@"
EXTRAS="${ARG_EXTRAS:-}"

if ! command -v apt-get >/dev/null 2>&1; then
    log_error "this installer is apt-only (Debian/Ubuntu runners)"
    exit 3
fi

# Explicit list rather than a metapackage: a metapackage's contents change
# between releases, and a desktop that silently gained or lost a component is
# exactly the kind of drift that wastes an afternoon.
PACKAGES=(
    xvfb           # the X server everything renders into
    x11vnc         # exports that X display over VNC on loopback
    novnc          # the browser-side VNC client (static assets)
    websockify     # bridges noVNC's WebSocket to x11vnc's TCP
    xfce4          # the desktop itself
    xfce4-terminal # xfce4 alone ships no terminal
    dbus-x11       # dbus-launch, needed by xfce
    gnome-keyring  # secret storage; xfce apps block without it
    libsecret-1-0  # keyring client library
)

log_step "installing desktop packages (${#PACKAGES[@]} packages)..."
export DEBIAN_FRONTEND=noninteractive

if ! sudo apt-get update -qq; then
    log_error "apt-get update failed"
    exit 1
fi

if ! sudo apt-get install -y -qq --no-install-recommends "${PACKAGES[@]}"; then
    log_error "apt-get install failed"
    exit 1
fi
log_info "desktop packages installed"

# --extras are genuinely optional. They are what makes the box useful for
# looking at a UI, but a desktop without them still comes up, so a failure here
# warns rather than fails: losing the whole debug session because an editor
# would not install is the wrong trade.
case ",$EXTRAS," in
    *,chromium,*)
        log_step "installing chromium..."
        sudo apt-get install -y -qq --no-install-recommends chromium-browser ||
            sudo apt-get install -y -qq --no-install-recommends chromium ||
            log_warn "chromium install failed; continuing without a browser"
        ;;
esac

case ",$EXTRAS," in
    *,vscode,*)
        log_step "installing VS Code..."
        if ! command -v code >/dev/null 2>&1; then
            # Keyring + signed apt repo rather than the `curl | apt-key add`
            # pattern the old script used (apt-key is deprecated and installs a
            # key trusted for EVERY repo on the machine).
            if curl -fsSL --max-time 60 https://packages.microsoft.com/keys/microsoft.asc |
                sudo gpg --dearmor -o /usr/share/keyrings/microsoft-archive-keyring.gpg 2>/dev/null; then
                echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft-archive-keyring.gpg] https://packages.microsoft.com/repos/code stable main" |
                    sudo tee /etc/apt/sources.list.d/vscode.list >/dev/null
                sudo apt-get update -qq && sudo apt-get install -y -qq code ||
                    log_warn "VS Code install failed; continuing without it"
            else
                log_warn "could not fetch the Microsoft signing key; skipping VS Code"
            fi
        else
            log_info "VS Code already present"
        fi
        ;;
esac

log_info "desktop install complete; start it with desktop-ctl.sh start"
