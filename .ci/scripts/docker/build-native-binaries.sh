#!/bin/bash
# Build native binaries for renet embedded assets (CRIU, rsync, rclone)
# Builds natively for the current architecture to avoid QEMU emulation issues
#
# Usage:
#   build-native-binaries.sh --output /path/to/output                    # Build CRIU + rsync for current arch
#   build-native-binaries.sh --output /path --cross-rsync                # Also cross-compile rsync
#   build-native-binaries.sh --output /path --criu-only                  # Build CRIU only
#   build-native-binaries.sh --dry-run --output /path                    # Preview without building
#
# Options:
#   --output DIR      Output directory for binaries (required)
#   --cross-rsync     Cross-compile rsync for opposite architecture (amd64 only)
#   --criu-only       Build only CRIU (for arm64 native runner)
#   --dry-run         Preview without building
#
# Environment variables:
#   DRY_RUN=true     Preview mode
#   CRIU_VERSION     CRIU version to build (default: 4.2)
#   RSYNC_VERSION    rsync version to build (default: 3.4.1)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Configuration
DRY_RUN="${DRY_RUN:-false}"
OUTPUT_DIR=""
CROSS_RSYNC=false
CRIU_ONLY=false
CRIU_VERSION="${CRIU_VERSION:-4.2}"
RSYNC_VERSION="${RSYNC_VERSION:-3.4.1}"
RCLONE_VERSION="${RCLONE_VERSION:-1.69.1}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --cross-rsync)
            CROSS_RSYNC=true
            shift
            ;;
        --criu-only)
            CRIU_ONLY=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --output DIR [--cross-rsync] [--criu-only] [--dry-run]"
            echo ""
            echo "Build native binaries for renet embedded assets"
            echo ""
            echo "Options:"
            echo "  --output DIR      Output directory for binaries (required)"
            echo "  --cross-rsync     Cross-compile rsync for opposite architecture"
            echo "  --criu-only       Build only CRIU (for arm64 native runner)"
            echo "  --dry-run         Preview without building"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Validate required arguments
if [[ -z "$OUTPUT_DIR" ]]; then
    log_error "--output is required"
    exit 1
fi

# Convert OUTPUT_DIR to absolute path (critical: we cd into temp dirs during build)
if [[ "$OUTPUT_DIR" != /* ]]; then
    OUTPUT_DIR="$(pwd)/$OUTPUT_DIR"
fi

# Detect architecture
ARCH=$(detect_arch)
case "$ARCH" in
    x64)
        ARCH_SUFFIX="amd64"
        OTHER_ARCH="arm64"
        ;;
    arm64)
        ARCH_SUFFIX="arm64"
        OTHER_ARCH="amd64"
        ;;
    *)
        log_error "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

log_step "Building native binaries for $ARCH_SUFFIX"
log_info "  CRIU version: $CRIU_VERSION"
log_info "  rsync version: $RSYNC_VERSION"
log_info "  rclone version: $RCLONE_VERSION"
log_info "  Output: $OUTPUT_DIR"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would build:"
    log_info "  - criu-linux-$ARCH_SUFFIX (native)"
    [[ "$CRIU_ONLY" != "true" ]] && log_info "  - rsync-linux-$ARCH_SUFFIX (native)"
    [[ "$CROSS_RSYNC" == "true" ]] && log_info "  - rsync-linux-$OTHER_ARCH (cross-compile)"
    [[ "$CRIU_ONLY" != "true" ]] && log_info "  - rclone-linux-$ARCH_SUFFIX (download)"
    [[ "$CRIU_ONLY" != "true" ]] && log_info "  - rclone-linux-$OTHER_ARCH (download)"
    exit 0
fi

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Build CRIU natively
build_criu() {
    local arch_suffix="$1"
    local output_file="$OUTPUT_DIR/criu-linux-$arch_suffix"

    if [[ -f "$output_file" ]]; then
        log_info "CRIU already exists: $output_file"
        return 0
    fi

    log_step "Building CRIU $CRIU_VERSION for $arch_suffix..."

    local build_dir
    build_dir=$(mktemp -d)
    # We intentionally expand $build_dir now to capture the temp directory path
    # shellcheck disable=SC2064
    trap "rm -rf '$build_dir'" EXIT

    cd "$build_dir"

    # Install build dependencies
    log_info "Installing CRIU build dependencies..."
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        sudo apt-get update -qq
        sudo apt-get install -y -qq \
            build-essential pkg-config \
            libprotobuf-dev libprotobuf-c-dev protobuf-c-compiler protobuf-compiler \
            python3-protobuf libcap-dev libnl-3-dev libnet1-dev \
            libaio-dev python3-yaml curl uuid-dev
    else
        log_error "Only apt-based systems are supported for CRIU builds"
        exit 1
    fi

    # Download and build CRIU
    log_info "Downloading CRIU source..."
    retry_with_backoff 3 5 curl -fsSL -o "criu-${CRIU_VERSION}.tar.gz" \
        "https://github.com/checkpoint-restore/criu/archive/v${CRIU_VERSION}/criu-${CRIU_VERSION}.tar.gz"
    tar -xzf "criu-${CRIU_VERSION}.tar.gz"

    cd "criu-${CRIU_VERSION}"
    log_info "Compiling CRIU (this may take a few minutes)..."
    make -j"$(nproc)"

    cp criu/criu "$output_file"
    chmod +x "$output_file"

    log_info "Built CRIU: $output_file"
}

# Build rsync natively
build_rsync() {
    local arch_suffix="$1"
    local output_file="$OUTPUT_DIR/rsync-linux-$arch_suffix"

    if [[ -f "$output_file" ]]; then
        log_info "rsync already exists: $output_file"
        return 0
    fi

    log_step "Building rsync $RSYNC_VERSION for $arch_suffix..."

    local build_dir
    build_dir=$(mktemp -d)
    # We intentionally expand $build_dir now to capture the temp directory path
    # shellcheck disable=SC2064
    trap "rm -rf '$build_dir'" EXIT

    cd "$build_dir"

    # Install build dependencies
    log_info "Installing rsync build dependencies..."
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        sudo apt-get update -qq
        sudo apt-get install -y -qq \
            build-essential curl patch pkg-config \
            libpopt-dev libacl1-dev libattr1-dev \
            liblz4-dev libxxhash-dev libzstd-dev \
            libssl-dev zlib1g-dev
    else
        log_error "Only apt-based systems are supported for rsync builds"
        exit 1
    fi

    # Download rsync source
    log_info "Downloading rsync source..."
    retry_with_backoff 3 5 curl -fsSL -o "rsync-${RSYNC_VERSION}.tar.gz" \
        "https://download.samba.org/pub/rsync/rsync-${RSYNC_VERSION}.tar.gz"
    tar -xzf "rsync-${RSYNC_VERSION}.tar.gz"
    retry_with_backoff 3 5 curl -fsSL -o security_fix.patch \
        "https://www.linuxfromscratch.org/patches/blfs/svn/rsync-3.4.1-security_fix-1.patch"

    cd "rsync-${RSYNC_VERSION}"
    patch -Np1 -i ../security_fix.patch

    log_info "Compiling rsync (static)..."
    ./configure --disable-md2man CFLAGS="-static" LDFLAGS="-static"
    make -j"$(nproc)"

    cp rsync "$output_file"
    chmod +x "$output_file"

    log_info "Built rsync: $output_file"
}

# Cross-compile rsync for arm64 (from amd64 host)
build_rsync_cross() {
    local arch_suffix="$1"
    local output_file="$OUTPUT_DIR/rsync-linux-$arch_suffix"

    if [[ -f "$output_file" ]]; then
        log_info "rsync already exists: $output_file"
        return 0
    fi

    log_step "Cross-compiling rsync $RSYNC_VERSION for $arch_suffix..."

    local build_dir
    build_dir=$(mktemp -d)
    # We intentionally expand $build_dir now to capture the temp directory path
    # shellcheck disable=SC2064
    trap "rm -rf '$build_dir'" EXIT

    cd "$build_dir"

    # Install cross-compiler and arm64 libraries
    log_info "Installing cross-compilation dependencies..."
    if command -v apt-get &>/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        sudo dpkg --add-architecture arm64

        # Configure apt sources for multi-arch support
        # The default sources only serve amd64, so we need to:
        # 1. Constrain default sources to amd64 only
        # 2. Add ports.ubuntu.com for arm64 packages
        log_info "Configuring apt sources for multi-arch..."

        # Convert default sources to amd64-only (handles both sources.list and .sources format)
        if [[ -f /etc/apt/sources.list ]] && [[ -s /etc/apt/sources.list ]]; then
            # Traditional sources.list format - add [arch=amd64] constraint
            sudo sed -i 's/^deb \([^[]\)/deb [arch=amd64] \1/g' /etc/apt/sources.list
            sudo sed -i 's/^deb-src \([^[]\)/deb-src [arch=amd64] \1/g' /etc/apt/sources.list
        fi

        # Handle DEB822 format (.sources files) used in newer Ubuntu
        for sources_file in /etc/apt/sources.list.d/*.sources; do
            if [[ -f "$sources_file" ]]; then
                # Add Architectures: amd64 if not already present
                if ! grep -q "^Architectures:" "$sources_file"; then
                    sudo sed -i '/^Types:/a Architectures: amd64' "$sources_file"
                fi
            fi
        done

        # Add arm64 sources from ports.ubuntu.com
        sudo bash -c 'cat > /etc/apt/sources.list.d/arm64-ports.list << EOF
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports noble main restricted universe multiverse
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports noble-updates main restricted universe multiverse
deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports noble-security main restricted universe multiverse
EOF'

        sudo apt-get update -qq
        sudo apt-get install -y -qq \
            build-essential curl patch pkg-config \
            gcc-aarch64-linux-gnu \
            libpopt-dev:arm64 libacl1-dev:arm64 libattr1-dev:arm64 \
            liblz4-dev:arm64 libxxhash-dev:arm64 libzstd-dev:arm64 \
            libssl-dev:arm64 zlib1g-dev:arm64
    else
        log_error "Only apt-based systems are supported for cross-compilation"
        exit 1
    fi

    # Download rsync source
    log_info "Downloading rsync source..."
    retry_with_backoff 3 5 curl -fsSL -o "rsync-${RSYNC_VERSION}.tar.gz" \
        "https://download.samba.org/pub/rsync/rsync-${RSYNC_VERSION}.tar.gz"
    tar -xzf "rsync-${RSYNC_VERSION}.tar.gz"
    retry_with_backoff 3 5 curl -fsSL -o security_fix.patch \
        "https://www.linuxfromscratch.org/patches/blfs/svn/rsync-3.4.1-security_fix-1.patch"

    cd "rsync-${RSYNC_VERSION}"
    patch -Np1 -i ../security_fix.patch

    log_info "Cross-compiling rsync for arm64..."
    # Force deterministic cross-compilation: QEMU on CI runners makes arm64
    # binaries executable, so autoconf detects "cross compiling... no" and runs
    # sizeof test programs under emulation. These probes are flaky (wrong results
    # under load), leaving SIZEOF_SHORT undefined and breaking uint16 typedefs.
    # Solution: set cross_compiling=yes + explicit ac_cv_sizeof_* cache vars
    # for the arm64 LP64 ABI (mathematically certain values).
    ./configure \
        --host=aarch64-linux-gnu \
        CC=aarch64-linux-gnu-gcc \
        --disable-md2man \
        CFLAGS="-static" LDFLAGS="-static" \
        cross_compiling=yes \
        ac_cv_sizeof_short=2 \
        ac_cv_sizeof_int=4 \
        ac_cv_sizeof_long=8 \
        ac_cv_sizeof_long_long=8 \
        ac_cv_sizeof_off_t=8 \
        rsync_cv_HAVE_GETTIMEOFDAY_TZ=yes \
        ac_cv_have_C99_vsnprintf=yes \
        ac_cv_func_utime_null=yes

    # Verify SIZEOF macros are correctly set in config.h
    if ! grep -q 'SIZEOF_SHORT 2' config.h; then
        log_error "SIZEOF_SHORT not correctly detected in config.h"
        grep SIZEOF config.h || true
        exit 1
    fi

    # Pre-create rounding.h: cross-compilation can't run the test program.
    # 8-byte alignment is correct for all 64-bit architectures.
    echo '#define ROUNDING 8' >rounding.h

    make -j"$(nproc)"

    cp rsync "$output_file"
    chmod +x "$output_file"

    log_info "Cross-compiled rsync: $output_file"
}

# Download pre-built rclone binary
download_rclone() {
    local arch_suffix="$1"
    local output_file="$OUTPUT_DIR/rclone-linux-$arch_suffix"

    if [[ -f "$output_file" ]]; then
        log_info "rclone already exists: $output_file"
        return 0
    fi

    log_step "Downloading rclone $RCLONE_VERSION for $arch_suffix..."

    local rclone_arch="$arch_suffix"
    local download_url="https://downloads.rclone.org/v${RCLONE_VERSION}/rclone-v${RCLONE_VERSION}-linux-${rclone_arch}.zip"

    local tmp_dir
    tmp_dir=$(mktemp -d)

    retry_with_backoff 3 5 curl -fsSL -o "$tmp_dir/rclone.zip" "$download_url"
    unzip -q "$tmp_dir/rclone.zip" -d "$tmp_dir"
    cp "$tmp_dir/rclone-v${RCLONE_VERSION}-linux-${rclone_arch}/rclone" "$output_file"
    chmod +x "$output_file"
    rm -rf "$tmp_dir"

    log_info "Downloaded rclone: $output_file"
}

# Main logic
main() {
    # Always build CRIU for current architecture
    build_criu "$ARCH_SUFFIX"

    if [[ "$CRIU_ONLY" != "true" ]]; then
        # Build rsync for current architecture
        build_rsync "$ARCH_SUFFIX"

        # Cross-compile rsync for other architecture if requested
        if [[ "$CROSS_RSYNC" == "true" ]]; then
            if [[ "$ARCH_SUFFIX" == "amd64" ]]; then
                build_rsync_cross "$OTHER_ARCH"
            else
                log_warn "Cross-compilation only supported from amd64 host"
            fi
        fi

        # Download pre-built rclone for both architectures
        download_rclone "$ARCH_SUFFIX"
        download_rclone "$OTHER_ARCH"
    fi

    # Summary
    echo ""
    log_info "Build complete. Output files:"
    ls -la "$OUTPUT_DIR"/*.* 2>/dev/null || log_warn "No output files found"
}

main "$@"
