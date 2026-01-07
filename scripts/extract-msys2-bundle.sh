#!/bin/bash
#
# extract-msys2-bundle.sh
#
# Downloads and extracts minimal MSYS2 binaries for bundling with Electron app.
# This creates a portable rsync/SSH bundle for Windows without requiring
# system-wide MSYS2 installation.
#
# Required binaries (~15-20MB total):
# - rsync.exe, ssh.exe, ssh-keygen.exe, ssh-agent.exe
# - Core DLLs: msys-2.0.dll, msys-crypto-3.dll, msys-z.dll, etc.
#
# Usage:
#   ./scripts/extract-msys2-bundle.sh [--ci] [--output <dir>]
#
# Options:
#   --ci        Run in CI mode (non-interactive, skip prompts)
#   --output    Output directory (default: packages/desktop/msys2-bundle)
#
# Note: This script is meant to run on Windows (via Git Bash, MSYS2, or WSL)
#       or on Linux for CI cross-compilation. On macOS, it will skip execution.

set -e

# Configuration
MSYS2_VERSION="${MSYS2_VERSION:-20241208}"
MSYS2_MIRROR="https://github.com/msys2/msys2-installer/releases/download"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSOLE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$CONSOLE_ROOT/packages/desktop/msys2-bundle}"
TEMP_DIR="${TEMP_DIR:-$CONSOLE_ROOT/.msys2-temp}"
CI_MODE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions (output to stderr to avoid polluting stdout for return values)
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" >&2
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --ci)
            CI_MODE=true
            shift
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --version)
            MSYS2_VERSION="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--ci] [--output <dir>] [--version <YYYYMMDD>]"
            echo ""
            echo "Options:"
            echo "  --ci        Run in CI mode (non-interactive)"
            echo "  --output    Output directory (default: packages/desktop/msys2-bundle)"
            echo "  --version   MSYS2 version date (default: $MSYS2_VERSION)"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Detect platform
detect_platform() {
    case "$(uname -s)" in
        CYGWIN*|MINGW*|MSYS*)
            echo "windows"
            ;;
        Linux)
            # Check for WSL
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        Darwin)
            echo "macos"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

PLATFORM=$(detect_platform)

# Skip on macOS - not needed for development
if [[ "$PLATFORM" == "macos" ]]; then
    log_info "Skipping MSYS2 bundle extraction on macOS (not needed)"
    exit 0
fi

# Required binaries to extract
BINARIES=(
    "rsync.exe"
    "ssh.exe"
    "ssh-keygen.exe"
    "ssh-agent.exe"
)

# Required DLLs for the binaries
# These are the dependencies for rsync 3.4.1 and openssh
DLLS=(
    "msys-2.0.dll"
    "msys-crypto-3.dll"
    "msys-z.dll"
    "msys-iconv-2.dll"
    "msys-xxhash-0.dll"
    "msys-zstd-1.dll"
    "msys-lz4-1.dll"
    "msys-gcc_s-seh-1.dll"
    "msys-ssl-3.dll"
)

# Clean up function
cleanup() {
    if [[ -d "$TEMP_DIR" ]]; then
        log_info "Cleaning up temporary files..."
        rm -rf "$TEMP_DIR"
    fi
}

# Set up trap for cleanup
trap cleanup EXIT

# Check if tar archive already exists (for caching)
check_cached_archive() {
    local archive_name="msys2-base-x86_64-${MSYS2_VERSION}.tar.xz"
    local cache_dir="$CONSOLE_ROOT/.cache"

    if [[ -f "$cache_dir/$archive_name" ]]; then
        log_info "Using cached MSYS2 archive: $cache_dir/$archive_name"
        echo "$cache_dir/$archive_name"
        return 0
    fi

    return 1
}

# Download MSYS2 base archive
download_msys2() {
    local archive_name="msys2-base-x86_64-${MSYS2_VERSION}.tar.xz"
    # GitHub release tags use hyphenated date format (2024-12-08) while filenames don't (20241208)
    local version_tag="${MSYS2_VERSION:0:4}-${MSYS2_VERSION:4:2}-${MSYS2_VERSION:6:2}"
    local download_url="${MSYS2_MIRROR}/${version_tag}/${archive_name}"
    local cache_dir="$CONSOLE_ROOT/.cache"
    local archive_path="$cache_dir/$archive_name"

    # Check if already cached
    if cached=$(check_cached_archive 2>/dev/null); then
        echo "$cached"
        return 0
    fi

    # Create cache directory
    mkdir -p "$cache_dir"

    log_info "Downloading MSYS2 base archive..."
    log_info "URL: $download_url"

    if command -v curl &>/dev/null; then
        curl -L -o "$archive_path" "$download_url"
    elif command -v wget &>/dev/null; then
        wget -O "$archive_path" "$download_url"
    else
        log_error "Neither curl nor wget found. Cannot download MSYS2."
        exit 1
    fi

    echo "$archive_path"
}

# Extract MSYS2 archive
extract_msys2() {
    local archive_path="$1"

    log_info "Extracting MSYS2 archive..."
    mkdir -p "$TEMP_DIR"

    # Extract the archive
    tar -xf "$archive_path" -C "$TEMP_DIR"

    # Find the extracted directory (should be msys64)
    local msys2_root="$TEMP_DIR/msys64"
    if [[ ! -d "$msys2_root" ]]; then
        log_error "Could not find extracted MSYS2 directory"
        exit 1
    fi

    echo "$msys2_root"
}

# Initialize MSYS2 and install packages (only on Windows/WSL)
initialize_msys2() {
    local msys2_root="$1"

    # On native Windows, we can use the MSYS2 shell to install packages
    if [[ "$PLATFORM" == "windows" ]]; then
        log_info "Initializing MSYS2 and installing packages..."

        # Update the package database and install required packages
        "$msys2_root/usr/bin/bash.exe" -lc "pacman -Syu --noconfirm"
        "$msys2_root/usr/bin/bash.exe" -lc "pacman -S --noconfirm rsync openssh"
    elif [[ "$PLATFORM" == "wsl" ]]; then
        # On WSL, use Windows path and call the bash executable
        local win_msys2_root
        win_msys2_root=$(wslpath -w "$msys2_root")

        log_info "Initializing MSYS2 via WSL..."
        cmd.exe /c "${win_msys2_root}\\usr\\bin\\bash.exe" -lc "pacman -Syu --noconfirm" 2>/dev/null || true
        cmd.exe /c "${win_msys2_root}\\usr\\bin\\bash.exe" -lc "pacman -S --noconfirm rsync openssh" 2>/dev/null || true
    else
        # On Linux CI, we can't run Windows binaries
        # We rely on pre-extracted binaries from a previous Windows run
        log_warn "Cannot initialize MSYS2 on Linux (no Windows binaries available)"
        log_warn "Using binaries from the extracted archive (may not have rsync/ssh)"
    fi
}

# Copy required files to output directory
copy_bundle_files() {
    local msys2_root="$1"
    local bin_src="$msys2_root/usr/bin"

    log_info "Creating bundle directory: $OUTPUT_DIR"
    mkdir -p "$OUTPUT_DIR/usr/bin"
    mkdir -p "$OUTPUT_DIR/etc"

    # Copy binaries
    log_info "Copying binaries..."
    for binary in "${BINARIES[@]}"; do
        if [[ -f "$bin_src/$binary" ]]; then
            cp "$bin_src/$binary" "$OUTPUT_DIR/usr/bin/"
            log_info "  Copied: $binary"
        else
            log_warn "  Missing: $binary"
        fi
    done

    # Copy DLLs
    log_info "Copying DLLs..."
    for dll in "${DLLS[@]}"; do
        if [[ -f "$bin_src/$dll" ]]; then
            cp "$bin_src/$dll" "$OUTPUT_DIR/usr/bin/"
            log_info "  Copied: $dll"
        else
            log_warn "  Missing: $dll"
        fi
    done

    # Copy etc files needed by rsync/ssh
    log_info "Copying configuration files..."
    if [[ -f "$msys2_root/etc/passwd" ]]; then
        cp "$msys2_root/etc/passwd" "$OUTPUT_DIR/etc/"
    fi
    if [[ -f "$msys2_root/etc/group" ]]; then
        cp "$msys2_root/etc/group" "$OUTPUT_DIR/etc/"
    fi

    # Create a version file
    echo "$MSYS2_VERSION" > "$OUTPUT_DIR/VERSION"

    log_info "Bundle created successfully!"
}

# Verify the bundle
verify_bundle() {
    log_info "Verifying bundle..."

    local missing_files=0

    for binary in "${BINARIES[@]}"; do
        if [[ ! -f "$OUTPUT_DIR/usr/bin/$binary" ]]; then
            log_error "Missing binary: $binary"
            missing_files=$((missing_files + 1))
        fi
    done

    for dll in "${DLLS[@]}"; do
        if [[ ! -f "$OUTPUT_DIR/usr/bin/$dll" ]]; then
            log_error "Missing DLL: $dll"
            missing_files=$((missing_files + 1))
        fi
    done

    if [[ $missing_files -gt 0 ]]; then
        log_error "Bundle verification failed: $missing_files files missing"
        return 1
    fi

    # Show bundle size
    local bundle_size
    bundle_size=$(du -sh "$OUTPUT_DIR" | cut -f1)
    log_info "Bundle size: $bundle_size"

    log_info "Bundle verification passed!"
    return 0
}

# Main function
main() {
    log_info "=== MSYS2 Bundle Extraction ==="
    log_info "Platform: $PLATFORM"
    log_info "MSYS2 Version: $MSYS2_VERSION"
    log_info "Output Directory: $OUTPUT_DIR"
    log_info ""

    # Check if bundle already exists
    if [[ -f "$OUTPUT_DIR/VERSION" ]]; then
        existing_version=$(cat "$OUTPUT_DIR/VERSION")
        if [[ "$existing_version" == "$MSYS2_VERSION" ]]; then
            log_info "Bundle already exists with version $MSYS2_VERSION"
            if [[ "$CI_MODE" == "true" ]]; then
                log_info "Using existing bundle (CI mode)"
                verify_bundle
                exit 0
            else
                read -p "Bundle exists. Recreate? [y/N] " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    log_info "Using existing bundle"
                    verify_bundle
                    exit 0
                fi
            fi
        fi
    fi

    # Download MSYS2
    archive_path=$(download_msys2)

    # Extract MSYS2
    msys2_root=$(extract_msys2 "$archive_path")

    # Initialize and install packages (if possible)
    initialize_msys2 "$msys2_root"

    # Copy files to bundle
    copy_bundle_files "$msys2_root"

    # Verify bundle
    if ! verify_bundle; then
        log_error "Bundle creation failed!"
        exit 1
    fi

    log_info ""
    log_info "=== Bundle Created Successfully ==="
    log_info "Location: $OUTPUT_DIR"
}

# Run main function
main "$@"
