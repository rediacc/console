#!/bin/bash
# Build full renet binaries with embedded CRIU/rsync assets
#
# Usage:
#   build-renet.sh --version 1.2.3 --output ./bin
#   build-renet.sh --version 1.2.3 --assets-dir ./assets --output ./bin
#
# Options:
#   --version VERSION    Version to embed in binary (required)
#   --assets-dir DIR     Directory containing CRIU/rsync binaries (default: auto-detect)
#   --output DIR         Output directory for renet binaries (default: private/bin)
#   --skip-embed         Build without embedded assets (lightweight, for testing)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Defaults
VERSION=""
ASSETS_DIR=""
OUTPUT_DIR=""
SKIP_EMBED=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            VERSION="$2"
            shift 2
            ;;
        --assets-dir)
            ASSETS_DIR="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --skip-embed)
            SKIP_EMBED=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 --version VERSION [--assets-dir DIR] [--output DIR] [--skip-embed]"
            echo ""
            echo "Build full renet binaries with embedded CRIU/rsync assets"
            echo ""
            echo "Options:"
            echo "  --version VERSION    Version to embed in binary (required)"
            echo "  --assets-dir DIR     Directory containing CRIU/rsync binaries"
            echo "  --output DIR         Output directory for renet binaries"
            echo "  --skip-embed         Build without embedded assets"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

[[ -z "$VERSION" ]] && {
    log_error "--version is required"
    exit 1
}

REPO_ROOT="$(get_repo_root)"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/private/bin}"
RENET_DIR="$REPO_ROOT/private/renet"

# Convert to absolute path (handles relative paths, symlinks, and ..)
OUTPUT_DIR="$(readlink -f "$OUTPUT_DIR")"

mkdir -p "$OUTPUT_DIR"

log_step "Building renet binaries (release)"
log_info "  Version: $VERSION"
log_info "  Output: $OUTPUT_DIR"

# Embed assets if not skipped
if [[ "$SKIP_EMBED" != "true" ]]; then
    log_step "Staging embedded assets"

    # SINGLE SOURCE OF TRUTH: private/renet/Dockerfile, driven by `build.sh
    # embed_assets`. It acquires AND per-arch-stages every embedded binary —
    # criu/rsync/CSI compiled from source, rclone/k3s/zot downloaded at their
    # pinned versions with sha256 verification — into pkg/embed/assets/<arch>/.
    # It is idempotent (skips assets already staged). Do NOT re-encode asset
    # acquisition or the per-arch gzip layout here; that lives in the Dockerfile,
    # and duplicating it is exactly the drift this consolidation removes.
    (cd "$RENET_DIR" && ./build.sh embed_assets)

    log_info "Embedded assets:"
    ls -la "$RENET_DIR/pkg/embed/assets/amd64" "$RENET_DIR/pkg/embed/assets/arm64"

    # proxy compose + datastore doc for go:embed (documents, not binary assets)
    log_info "Staging proxy/datastore docs..."
    cp "$REPO_ROOT/private/renet/proxy/docker-compose.yml" "$RENET_DIR/pkg/embed/proxy/"
    cp "$REPO_ROOT/private/renet/docs/datastore/README.md" "$RENET_DIR/pkg/embed/datastore/"
else
    log_info "Skipping asset embedding (--skip-embed)"
fi

# Build renet binaries (release mode: stripped)
log_step "Building renet binaries (release)..."

require_cmd go

cd "$RENET_DIR"

# Inject account server public key if available (from ACCOUNT_ED25519_PUBLIC_KEY env var)
KEY_LDFLAGS=""
if [[ -n "${ACCOUNT_ED25519_PUBLIC_KEY:-}" ]]; then
    KEY_LDFLAGS="-X github.com/rediacc/renet/pkg/license/keys.ProductionPublicKey=${ACCOUNT_ED25519_PUBLIC_KEY}"
    log_info "Account server public key injected from environment"
fi

# OTLP credentials are resolved at RUNTIME by the CLI via
# `GET /telemetry/config` (unauthenticated) — NOT baked in at build time.
# Go 1.18+ records `-ldflags` in `.go.buildinfo`, which made baked
# credentials recoverable via `go version -m` or `strings` from any
# built binary (renet#51).

for os in linux darwin; do
    for arch in amd64 arm64; do
        log_info "Building renet-$os-$arch..."
        CGO_ENABLED=0 GOOS=$os GOARCH=$arch go build \
            -ldflags="-s -w -X main.Version=$VERSION $KEY_LDFLAGS" \
            -o "$OUTPUT_DIR/renet-$os-$arch" ./cmd/renet
    done
done

# Windows targets (Hyper-V backend)
for arch in amd64 arm64; do
    log_info "Building renet-windows-$arch..."
    CGO_ENABLED=0 GOOS=windows GOARCH=$arch go build \
        -ldflags="-s -w -X main.Version=$VERSION $KEY_LDFLAGS" \
        -o "$OUTPUT_DIR/renet-windows-$arch.exe" ./cmd/renet
done

# Generate checksums
log_step "Generating checksums..."
cd "$OUTPUT_DIR"
sha256sum renet-* >checksums.sha256

log_info "Renet binaries built successfully:"
ls -la "$OUTPUT_DIR"/renet-*
cat "$OUTPUT_DIR/checksums.sha256"

# Verify release build (no debug info)
log_step "Verifying release builds..."
for os in linux darwin; do
    for arch in amd64 arm64; do
        binary="$OUTPUT_DIR/renet-$os-$arch"
        if ! file "$binary" | grep -q "not stripped"; then
            log_info "renet-$os-$arch: stripped (release build)"
        else
            log_warn "renet-$os-$arch: may contain debug symbols"
        fi
    done
done

# Windows binaries are PE format, file(1) reports differently
for arch in amd64 arm64; do
    binary="$OUTPUT_DIR/renet-windows-$arch.exe"
    if [[ -f "$binary" ]]; then
        log_info "renet-windows-$arch.exe: $(file -b "$binary" | head -c 80)"
    fi
done
