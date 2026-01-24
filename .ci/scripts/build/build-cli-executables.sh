#!/bin/bash
# Build CLI as a Node.js Single Executable Application (SEA)
# Runs on each native platform/arch runner to produce a self-contained binary.
#
# Usage:
#   build-cli-executables.sh --platform linux --arch x64
#   build-cli-executables.sh --platform mac --arch arm64
#   build-cli-executables.sh --platform win --arch x64
#   build-cli-executables.sh                          # Auto-detect platform/arch
#   build-cli-executables.sh --dry-run                # Preview without building
#
# Options:
#   --platform PLATFORM  Target platform: linux, mac, win (auto-detected if omitted)
#   --arch ARCH          Target architecture: x64, arm64 (auto-detected if omitted)
#   --output DIR         Output directory (default: dist/cli/)
#   --dry-run            Preview without building

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
PLATFORM=""
ARCH=""
OUTPUT_DIR=""
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --platform)
            PLATFORM="$2"
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
        -h|--help)
            echo "Usage: $0 [--platform PLATFORM] [--arch ARCH] [--output DIR] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Auto-detect platform if not specified
if [[ -z "$PLATFORM" ]]; then
    case "$(uname -s)" in
        Linux*)  PLATFORM="linux" ;;
        Darwin*) PLATFORM="mac" ;;
        MINGW*|MSYS*|CYGWIN*) PLATFORM="win" ;;
        *)
            log_error "Cannot detect platform from: $(uname -s)"
            exit 1
            ;;
    esac
    log_info "Auto-detected platform: $PLATFORM"
fi

# Auto-detect architecture if not specified
if [[ -z "$ARCH" ]]; then
    case "$(uname -m)" in
        x86_64|amd64) ARCH="x64" ;;
        aarch64|arm64) ARCH="arm64" ;;
        *)
            log_error "Cannot detect architecture from: $(uname -m)"
            exit 1
            ;;
    esac
    log_info "Auto-detected arch: $ARCH"
fi

# Set output directory
REPO_ROOT="$(get_repo_root)"
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$REPO_ROOT/dist/cli"
fi

# Binary name
BINARY_NAME="rdc-${PLATFORM}-${ARCH}"
if [[ "$PLATFORM" == "win" ]]; then
    BINARY_NAME="${BINARY_NAME}.exe"
fi

CLI_DIR="$REPO_ROOT/packages/cli"
NODE_BIN="$(command -v node)"

log_step "Building CLI SEA executable: $BINARY_NAME"
log_info "  Platform: $PLATFORM"
log_info "  Arch: $ARCH"
log_info "  Node: $NODE_BIN ($(node --version))"
log_info "  Output: $OUTPUT_DIR/$BINARY_NAME"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would build $BINARY_NAME"
    exit 0
fi

# Step 1: Build the CJS bundle
log_step "Building CLI bundle..."
cd "$CLI_DIR"
node bundle.mjs
require_file "$CLI_DIR/dist/cli-bundle.cjs"
log_info "Bundle created: $(wc -c < dist/cli-bundle.cjs) bytes"

# Step 2: Generate SEA blob
log_step "Generating SEA blob..."
node --experimental-sea-config sea-config.json
require_file "$CLI_DIR/dist/sea-prep.blob"
log_info "SEA blob created: $(wc -c < dist/sea-prep.blob) bytes"

# Step 3: Copy node binary
log_step "Copying node binary..."
mkdir -p "$OUTPUT_DIR"
cp "$NODE_BIN" "$OUTPUT_DIR/$BINARY_NAME"
chmod +x "$OUTPUT_DIR/$BINARY_NAME"

# Step 4: Remove existing signature (macOS only, must happen before strip)
if [[ "$PLATFORM" == "mac" ]]; then
    log_step "Removing existing code signature..."
    codesign --remove-signature "$OUTPUT_DIR/$BINARY_NAME"
fi

# Step 5: Strip debug symbols (before injection to avoid corrupting SEA section)
# Note: macOS strip is incompatible with Node.js binaries (__LINKEDIT segment issues)
# so we only strip on Linux where it works reliably.
if [[ "$PLATFORM" == "linux" ]]; then
    log_step "Stripping debug symbols..."
    strip --strip-all "$OUTPUT_DIR/$BINARY_NAME"
    log_info "Stripped binary: $(wc -c < "$OUTPUT_DIR/$BINARY_NAME") bytes"
fi

# Step 6: Inject SEA blob
log_step "Injecting SEA blob into binary..."
POSTJECT_ARGS=(
    "$OUTPUT_DIR/$BINARY_NAME"
    NODE_SEA_BLOB
    "$CLI_DIR/dist/sea-prep.blob"
    --sentinel-fuse NODE_SEA_FUSE_fce680ab2cc467b6e072b8b5df1996b2
)
# macOS requires --macho-segment-name for proper code signing coverage.
# Without it, the injected blob segment isn't covered by the ad-hoc signature,
# causing SIGSEGV on ARM64 where code signing is mandatory.
if [[ "$PLATFORM" == "mac" ]]; then
    POSTJECT_ARGS+=(--macho-segment-name NODE_SEA)
fi
npx postject "${POSTJECT_ARGS[@]}"

# Step 7: Re-sign (macOS only)
if [[ "$PLATFORM" == "mac" ]]; then
    log_step "Re-signing binary..."
    codesign -s - "$OUTPUT_DIR/$BINARY_NAME"
fi

# Verify
log_step "Verifying executable..."
BINARY_SIZE=$(wc -c < "$OUTPUT_DIR/$BINARY_NAME")
log_info "Binary size: $((BINARY_SIZE / 1024 / 1024))MB ($BINARY_SIZE bytes)"

# Generate SHA256 checksum
log_step "Generating SHA256 checksum..."
if command -v sha256sum &>/dev/null; then
    (cd "$OUTPUT_DIR" && sha256sum "$BINARY_NAME" > "${BINARY_NAME}.sha256")
elif command -v shasum &>/dev/null; then
    (cd "$OUTPUT_DIR" && shasum -a 256 "$BINARY_NAME" > "${BINARY_NAME}.sha256")
else
    log_warn "No sha256sum or shasum available - skipping checksum"
fi
if [[ -f "$OUTPUT_DIR/${BINARY_NAME}.sha256" ]]; then
    log_info "Checksum: $(cat "$OUTPUT_DIR/${BINARY_NAME}.sha256")"
fi

# Quick smoke test (skip on cross-platform CI where binary may not run)
if [[ "$PLATFORM" == "$(detect_os | sed 's/macos/mac/; s/windows/win/')" ]] && \
   [[ "$ARCH" == "$(detect_arch)" ]]; then
    log_step "Running smoke test..."
    if "$OUTPUT_DIR/$BINARY_NAME" --version; then
        log_info "Smoke test passed"
    else
        log_warn "Smoke test failed (exit code: $?) - binary may still be valid"
    fi
else
    log_info "Skipping smoke test (cross-platform build)"
fi

log_info "CLI SEA build complete: $OUTPUT_DIR/$BINARY_NAME"
