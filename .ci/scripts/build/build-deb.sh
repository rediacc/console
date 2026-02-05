#!/bin/bash
# Build .deb package from CLI binary
# Usage:
#   build-deb.sh --binary PATH --version VER --arch {amd64|arm64} [--output DIR] [--dry-run]
#
# Options:
#   --binary PATH   Path to the CLI binary
#   --version VER   Package version (e.g., 0.4.44)
#   --arch ARCH     Target architecture: amd64, arm64
#   --output DIR    Output directory (default: dist/packages)
#   --dry-run       Preview without building

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# Defaults
BINARY=""
VERSION=""
ARCH=""
OUTPUT_DIR=""
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --binary)
            BINARY="$2"
            shift 2
            ;;
        --version)
            VERSION="$2"
            shift 2
            ;;
        --arch)
            ARCH="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --binary PATH --version VER --arch {amd64|arm64} [--output DIR] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$BINARY" ]]; then
    log_error "Missing required argument: --binary"
    exit 1
fi
if [[ -z "$VERSION" ]]; then
    log_error "Missing required argument: --version"
    exit 1
fi
if [[ -z "$ARCH" ]]; then
    log_error "Missing required argument: --arch"
    exit 1
fi

# Validate architecture
if [[ "$ARCH" != "amd64" && "$ARCH" != "arm64" ]]; then
    log_error "Invalid architecture '$ARCH'. Must be 'amd64' or 'arm64'"
    exit 1
fi

# Set output directory
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$(get_repo_root)/dist/packages"
fi

# Package filename
DEB_FILE="${PKG_NAME}_${VERSION}_${ARCH}.deb"

log_step "Building .deb package: $DEB_FILE"
log_info "  Binary: $BINARY"
log_info "  Version: $VERSION"
log_info "  Arch: $ARCH"
log_info "  Output: $OUTPUT_DIR/$DEB_FILE"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would build $DEB_FILE"
    mkdir -p "$OUTPUT_DIR"
    exit 0
fi

# Validate binary exists (after dry-run check — not needed for validation-only runs)
require_file "$BINARY"

# Require dpkg-deb
require_cmd dpkg-deb

# Create staging directory
STAGING_DIR="$(mktemp -d)"
cleanup() { rm -rf "$STAGING_DIR"; }
trap cleanup EXIT

# Create directory structure
mkdir -p "$STAGING_DIR/DEBIAN"
mkdir -p "$STAGING_DIR/usr/local/bin"

# Copy binary
cp "$BINARY" "$STAGING_DIR/usr/local/bin/$PKG_BINARY_NAME"
chmod 755 "$STAGING_DIR/usr/local/bin/$PKG_BINARY_NAME"

# Write control file
cat >"$STAGING_DIR/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: ${PKG_SECTION}
Priority: ${PKG_PRIORITY}
Architecture: ${ARCH}
Maintainer: ${PKG_MAINTAINER}
Homepage: ${PKG_HOMEPAGE}
Description: ${PKG_DESCRIPTION}
EOF

# Build the package
mkdir -p "$OUTPUT_DIR"
dpkg-deb --build --root-owner-group "$STAGING_DIR" "$OUTPUT_DIR/$DEB_FILE"

# Verify
PACKAGE_SIZE=$(wc -c <"$OUTPUT_DIR/$DEB_FILE")
log_info "Package built: $DEB_FILE ($((PACKAGE_SIZE / 1024))KB)"
