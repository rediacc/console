#!/bin/bash
# Install VS Code based on detected operating system
# Usage: install-vscode.sh [--check]
#
# Options:
#   --check   Only verify VS Code is installed, don't install

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
CHECK_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=true ;;
    esac
done

# Check if VS Code is already installed
if command -v code &>/dev/null; then
    log_info "VS Code is already installed"
    code --version
    exit 0
fi

if [[ "$CHECK_ONLY" == "true" ]]; then
    log_error "VS Code is not installed"
    exit 1
fi

log_step "Installing VS Code for $CI_OS..."

case "$CI_OS" in
    linux)
        log_step "Installing VS Code via apt..."
        sudo apt-get update -qq

        # Add Microsoft GPG key
        wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor >/tmp/packages.microsoft.gpg
        sudo install -D -o root -g root -m 644 /tmp/packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg

        # Add VS Code repository
        echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" |
            sudo tee /etc/apt/sources.list.d/vscode.list >/dev/null

        # Install VS Code
        sudo apt-get update -qq
        sudo apt-get install -y code

        # Cleanup
        rm -f /tmp/packages.microsoft.gpg
        ;;

    macos)
        log_step "Installing VS Code via Homebrew..."
        if ! command -v brew &>/dev/null; then
            log_error "Homebrew is not installed"
            exit 1
        fi
        brew install --cask visual-studio-code
        ;;

    windows)
        log_step "Installing VS Code via Chocolatey..."
        if ! command -v choco &>/dev/null; then
            log_error "Chocolatey is not installed"
            exit 1
        fi
        choco install vscode -y

        # Refresh PATH to include VS Code
        if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
            # On GitHub Actions, we need to manually add to PATH
            export PATH="$PATH:/c/Program Files/Microsoft VS Code/bin"
        fi
        ;;

    *)
        log_error "Unsupported operating system: $CI_OS"
        exit 1
        ;;
esac

# Verify installation
if command -v code &>/dev/null; then
    log_info "VS Code installed successfully"
    code --version
else
    log_error "VS Code installation failed - 'code' command not found"
    exit 1
fi
