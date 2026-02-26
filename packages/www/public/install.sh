#!/bin/bash
# Rediacc CLI Installer
#
# Quick install (downloads and runs this script):
#   curl -fsSL https://www.rediacc.com/install.sh | bash
#
# Safer alternative (download first, inspect, then run):
#   curl -fsSL https://www.rediacc.com/install.sh -o install.sh
#   less install.sh  # inspect the script
#   bash install.sh

set -euo pipefail

# Configuration (can be overridden via environment variables)
RELEASES_URL="${REDIACC_RELEASES_URL:-https://releases.rediacc.com}"
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

# Detect C library (musl vs glibc) on Linux
detect_libc() {
  if [ "$(uname -s)" != "Linux" ]; then echo ""; return; fi
  # ldd is linked against the system libc — its --version output identifies it
  if ldd --version 2>&1 | grep -qi musl; then echo "musl"; return; fi
  echo ""
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

  LIBC=$(detect_libc)

  if [ -n "$LIBC" ]; then
    echo "Detected: $PLATFORM-$LIBC ($ARCH)"
  else
    echo "Detected: $PLATFORM ($ARCH)"
  fi

  # Get latest version
  echo "Fetching latest version..."
  LATEST_JSON=$(curl -fsSL -A "Rediacc-Installer/1.0" "${RELEASES_URL}/cli/latest.json") || error "Failed to fetch version information"

  # Extract version - use jq if available, otherwise fall back to grep/sed
  if command -v jq &> /dev/null; then
    VERSION=$(echo "$LATEST_JSON" | jq -r '.version')
  else
    VERSION=$(echo "$LATEST_JSON" | grep -o '"version":"[^"]*"' | sed -E 's/"version":"([^"]+)"/\1/')
  fi

  if [[ -z "$VERSION" ]]; then
    error "Could not determine latest version"
  fi

  echo "Latest version: v$VERSION"

  if [ -n "$LIBC" ]; then
    BINARY_NAME="rdc-${PLATFORM}-${LIBC}-${ARCH}"
  else
    BINARY_NAME="rdc-${PLATFORM}-${ARCH}"
  fi
  DOWNLOAD_URL="${RELEASES_URL}/cli/v${VERSION}/${BINARY_NAME}"
  CHECKSUM_URL="${DOWNLOAD_URL}.sha256"

  # Create directories
  mkdir -p "$INSTALL_DIR" "$VERSIONS_DIR/$VERSION"

  # Download binary
  echo "Downloading rdc v$VERSION..."
  TEMP_FILE=$(mktemp)
  curl -fsSL -A "Rediacc-Installer/1.0" "$DOWNLOAD_URL" -o "$TEMP_FILE" || {
    rm -f "$TEMP_FILE"
    error "Failed to download binary from $DOWNLOAD_URL"
  }

  # Download and verify checksum
  echo "Verifying checksum..."
  EXPECTED_SHA=$(curl -fsSL -A "Rediacc-Installer/1.0" "$CHECKSUM_URL" | awk '{print $1}') || {
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
  # Version directories use semver naming (e.g., "0.4.59"). We sort them by
  # version number (newest first) and delete the oldest ones beyond MAX_VERSIONS.
  if [[ -d "$VERSIONS_DIR" ]]; then
    local version_count=0
    # Use find + sort for cross-platform (Linux/macOS) version sorting
    # -t. -k1,1nr -k2,2nr -k3,3nr sorts by major.minor.patch descending
    while IFS= read -r dir; do
      [[ -z "$dir" ]] && continue
      version_count=$((version_count + 1))
      if [[ $version_count -gt $MAX_VERSIONS ]]; then
        rm -rf "$dir" 2>/dev/null || true
      fi
    done < <(find "$VERSIONS_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | while read -r d; do
      basename "$d"
    done | sort -t. -k1,1nr -k2,2nr -k3,3nr | while read -r v; do
      echo "$VERSIONS_DIR/$v"
    done)
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
