#!/bin/bash
# Rediacc CLI Installer
# Usage: curl -fsSL https://www.rediacc.com/install.sh | bash

set -euo pipefail

# Configuration
REPO="rediacc/console"
INSTALL_DIR="${HOME}/.local/bin"
VERSIONS_DIR="${HOME}/.local/share/rediacc/versions"
MAX_VERSIONS=5

# Colors for output (only if terminal supports it)
if [ -t 1 ]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  NC='\033[0m' # No Color
else
  RED=''
  GREEN=''
  YELLOW=''
  NC=''
fi

error() {
  echo -e "${RED}Error: $1${NC}" >&2
  exit 1
}

warn() {
  echo -e "${YELLOW}$1${NC}"
}

success() {
  echo -e "${GREEN}$1${NC}"
}

# Detect platform
detect_platform() {
  case "$(uname -s)" in
    Linux)  echo "linux" ;;
    Darwin) echo "mac" ;;
    *)      echo "unsupported" ;;
  esac
}

# Detect architecture
detect_arch() {
  case "$(uname -m)" in
    x86_64|amd64)   echo "x64" ;;
    arm64|aarch64)  echo "arm64" ;;
    *)              echo "unsupported" ;;
  esac
}

# Check for required commands
check_requirements() {
  local missing=""
  for cmd in curl; do
    if ! command -v "$cmd" &> /dev/null; then
      missing="$missing $cmd"
    fi
  done

  if [ -n "$missing" ]; then
    error "Missing required commands:$missing"
  fi

  # Check for sha256sum or shasum
  if ! command -v sha256sum &> /dev/null && ! command -v shasum &> /dev/null; then
    error "Missing required command: sha256sum or shasum"
  fi
}

# Calculate SHA256 checksum (cross-platform)
sha256() {
  if command -v sha256sum &> /dev/null; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

# Main installation logic
main() {
  echo "Setting up Rediacc CLI..."
  echo ""

  check_requirements

  PLATFORM=$(detect_platform)
  ARCH=$(detect_arch)

  if [[ "$PLATFORM" == "unsupported" ]]; then
    error "Unsupported platform: $(uname -s). Supported platforms: Linux, macOS"
  fi

  if [[ "$ARCH" == "unsupported" ]]; then
    error "Unsupported architecture: $(uname -m). Supported architectures: x86_64, arm64"
  fi

  echo "Detected: $PLATFORM ($ARCH)"

  # Get latest version from GitHub API
  echo "Fetching latest version..."
  RELEASE_INFO=$(curl -fsSL "https://api.github.com/repos/$REPO/releases/latest") || error "Failed to fetch release information"
  VERSION=$(echo "$RELEASE_INFO" | grep '"tag_name"' | sed -E 's/.*"v([^"]+)".*/\1/')

  if [[ -z "$VERSION" ]]; then
    error "Could not determine latest version"
  fi

  echo "Latest version: v$VERSION"

  BINARY_NAME="rdc-${PLATFORM}-${ARCH}"
  DOWNLOAD_URL="https://github.com/$REPO/releases/download/v${VERSION}/${BINARY_NAME}"
  CHECKSUM_URL="${DOWNLOAD_URL}.sha256"

  # Create directories
  mkdir -p "$INSTALL_DIR" "$VERSIONS_DIR/$VERSION"

  # Download binary
  echo "Downloading rdc v$VERSION..."
  TEMP_FILE=$(mktemp)
  curl -fsSL "$DOWNLOAD_URL" -o "$TEMP_FILE" || {
    rm -f "$TEMP_FILE"
    error "Failed to download binary from $DOWNLOAD_URL"
  }

  # Download and verify checksum
  echo "Verifying checksum..."
  EXPECTED_SHA=$(curl -fsSL "$CHECKSUM_URL" | awk '{print $1}') || {
    rm -f "$TEMP_FILE"
    error "Failed to download checksum from $CHECKSUM_URL"
  }
  ACTUAL_SHA=$(sha256 "$TEMP_FILE")

  if [[ "$EXPECTED_SHA" != "$ACTUAL_SHA" ]]; then
    rm -f "$TEMP_FILE"
    error "Checksum verification failed. Expected: $EXPECTED_SHA, Got: $ACTUAL_SHA"
  fi

  echo "Checksum verified."

  # Install binary
  chmod +x "$TEMP_FILE"
  mv "$TEMP_FILE" "$VERSIONS_DIR/$VERSION/rdc"

  # Create symlink to current version
  ln -sf "$VERSIONS_DIR/$VERSION/rdc" "$INSTALL_DIR/rdc"

  # Cleanup old versions (keep last MAX_VERSIONS)
  if [[ -d "$VERSIONS_DIR" ]]; then
    # shellcheck disable=SC2012
    ls -1dt "$VERSIONS_DIR"/*/ 2>/dev/null | tail -n +$((MAX_VERSIONS + 1)) | xargs -r rm -rf 2>/dev/null || true
  fi

  # Success message
  echo ""
  success "Rediacc CLI successfully installed!"
  echo ""
  echo "  Version:  v$VERSION"
  echo "  Location: $INSTALL_DIR/rdc"
  echo ""
  echo "  Next:   Run 'rdc --help' to get started"
  echo "  Update: Run 'rdc update' to update to the latest version"

  # PATH check
  if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo ""
    warn "Note: $INSTALL_DIR is not in your PATH"
    echo ""
    echo "  Add it by running:"
    echo ""

    # Detect shell and provide appropriate command
    SHELL_NAME=$(basename "$SHELL")
    case "$SHELL_NAME" in
      zsh)
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.zshrc && source ~/.zshrc"
        ;;
      fish)
        echo "  fish_add_path ~/.local/bin"
        ;;
      *)
        echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc && source ~/.bashrc"
        ;;
    esac
  fi

  echo ""
  success "Installation complete!"
}

main "$@"
