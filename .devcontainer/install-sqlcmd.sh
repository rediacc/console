#!/bin/bash

# go-sqlcmd installation script — shared with private/elite/scripts/install-sqlcmd.sh
# Keep version in sync with the canonical copy above.
#
# Usage:
#   ./install-sqlcmd.sh [install-dir]
#
# Arguments:
#   install-dir  Optional. Default: /usr/local/bin
#
# Environment:
#   TARGETARCH   Docker build arg (amd64, arm64, s390x). Auto-detected if not set.

set -e

SQLCMD_VERSION="1.9.0"
INSTALL_DIR="${1:-/usr/local/bin}"

# Detect architecture
if [ -n "$TARGETARCH" ]; then
    # Docker build context
    ARCH="$TARGETARCH"
elif command -v dpkg &>/dev/null; then
    # Debian/Ubuntu
    ARCH=$(dpkg --print-architecture)
else
    # Fallback to uname
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64) ARCH="amd64" ;;
        aarch64) ARCH="arm64" ;;
    esac
fi

echo "Installing go-sqlcmd v${SQLCMD_VERSION} for ${ARCH} to ${INSTALL_DIR}"

mkdir -p "$INSTALL_DIR"
wget -qO- "https://github.com/microsoft/go-sqlcmd/releases/download/v${SQLCMD_VERSION}/sqlcmd-linux-${ARCH}.tar.bz2" | tar -xj -C "$INSTALL_DIR"
chmod +x "$INSTALL_DIR/sqlcmd"

echo "Installed: $("$INSTALL_DIR/sqlcmd" --version 2>&1 | head -1)"
