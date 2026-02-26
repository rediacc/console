#!/bin/bash
# Build CLI as a musl-linked SEA binary using Docker (node:22-alpine)
# Produces a binary that runs on Alpine Linux and other musl-based distros.
#
# Usage:
#   build-cli-musl.sh --arch x64
#   build-cli-musl.sh --arch arm64 --output dist/cli/
#
# Options:
#   --arch ARCH      Target architecture: x64, arm64
#   --output DIR     Output directory (default: dist/cli/)
#   --dry-run        Preview without building

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
ARCH=""
OUTPUT_DIR=""
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
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
            echo "Usage: $0 --arch ARCH [--output DIR] [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$ARCH" ]]; then
    log_error "Missing required argument: --arch"
    exit 1
fi

REPO_ROOT="$(get_repo_root)"
if [[ -z "$OUTPUT_DIR" ]]; then
    OUTPUT_DIR="$REPO_ROOT/dist/cli"
fi

BINARY_NAME="rdc-linux-musl-${ARCH}"

log_step "Building musl-linked CLI SEA executable: $BINARY_NAME"
log_info "  Arch: $ARCH"
log_info "  Output: $OUTPUT_DIR/$BINARY_NAME"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "[DRY-RUN] Would build $BINARY_NAME"
    exit 0
fi

require_cmd docker

# Select Docker platform for cross-arch builds
DOCKER_PLATFORM=""
case "$ARCH" in
    x64) DOCKER_PLATFORM="linux/amd64" ;;
    arm64) DOCKER_PLATFORM="linux/arm64" ;;
    *)
        log_error "Invalid architecture '$ARCH'. Must be x64 or arm64"
        exit 1
        ;;
esac

# Build inside Alpine container
# The repo root is mounted at /workspace. The build script runs inside the
# container using the musl-linked Node.js binary, producing a musl SEA binary.
log_step "Running build inside node:22-alpine container..."

docker run --rm \
    --platform "$DOCKER_PLATFORM" \
    -v "$REPO_ROOT:/workspace" \
    -w /workspace \
    -e CI="${CI:-}" \
    node:22-alpine sh -c '
set -e

echo "→ Installing build dependencies..."
apk add --no-cache python3 make g++ binutils bash jq

echo "→ Installing npm dependencies..."
npm ci --ignore-scripts
# Rebuild native addons for musl
npm rebuild

echo "→ Building shared packages..."
cd packages/shared && npx tsc -p tsconfig.json && cd /workspace
cd packages/shared-desktop && npx tsc -p tsconfig.json && cd /workspace
cd packages/provisioning && npx tsc -p tsconfig.json && cd /workspace

echo "→ Building CLI bundle and SEA binary..."
.ci/scripts/build/build-cli-executables.sh --platform linux --arch '"$ARCH"'
'

# The Docker build produces dist/cli/rdc-linux-$ARCH (musl-linked)
DOCKER_OUTPUT="$REPO_ROOT/dist/cli/rdc-linux-${ARCH}"

if [[ ! -f "$DOCKER_OUTPUT" ]]; then
    log_error "Docker build produced no output: $DOCKER_OUTPUT"
    exit 1
fi

# Fix ownership of Docker-created files (container runs as root)
sudo chown -R "$(id -u):$(id -g)" "$REPO_ROOT/dist/cli/" 2>/dev/null || true

# Rename to musl variant
mkdir -p "$OUTPUT_DIR"
mv "$DOCKER_OUTPUT" "$OUTPUT_DIR/$BINARY_NAME"

# Move checksum if present, otherwise generate
if [[ -f "${DOCKER_OUTPUT}.sha256" ]]; then
    # Update filename inside checksum file
    sed "s/rdc-linux-${ARCH}/${BINARY_NAME}/" "${DOCKER_OUTPUT}.sha256" >"$OUTPUT_DIR/${BINARY_NAME}.sha256"
    rm -f "${DOCKER_OUTPUT}.sha256"
else
    if command -v sha256sum &>/dev/null; then
        (cd "$OUTPUT_DIR" && sha256sum "$BINARY_NAME" >"${BINARY_NAME}.sha256")
    elif command -v shasum &>/dev/null; then
        (cd "$OUTPUT_DIR" && shasum -a 256 "$BINARY_NAME" >"${BINARY_NAME}.sha256")
    fi
fi

BINARY_SIZE=$(wc -c <"$OUTPUT_DIR/$BINARY_NAME")
log_info "Musl binary: $OUTPUT_DIR/$BINARY_NAME ($((BINARY_SIZE / 1024 / 1024))MB)"

if [[ -f "$OUTPUT_DIR/${BINARY_NAME}.sha256" ]]; then
    log_info "Checksum: $(cat "$OUTPUT_DIR/${BINARY_NAME}.sha256")"
fi

log_info "CLI musl build complete: $OUTPUT_DIR/$BINARY_NAME"
