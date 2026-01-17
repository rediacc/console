#!/bin/bash
# Build CLI and create bundle
# Usage: build-cli.sh [--bundle] [--verify]
#
# Options:
#   --bundle  Also create single-file bundle (default: true)
#   --verify  Verify build output (default: true)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
BUNDLE="${ARG_BUNDLE:-true}"
VERIFY="${ARG_VERIFY:-true}"

for arg in "$@"; do
    case "$arg" in
        --no-bundle) BUNDLE=false ;;
        --no-verify) VERIFY=false ;;
        --bundle) BUNDLE=true ;;
        --verify) VERIFY=true ;;
    esac
done

# Change to repo root
cd "$(get_repo_root)"

log_step "Building CLI..."

# Build CLI workspace
if npm run build:cli; then
    log_info "CLI build completed"
else
    log_error "CLI build failed"
    exit 1
fi

# Create bundle if requested
if [[ "$BUNDLE" == "true" ]]; then
    log_step "Creating CLI bundle..."
    if npm run build:bundle -w @rediacc/cli; then
        log_info "CLI bundle created"
    else
        log_error "CLI bundle failed"
        exit 1
    fi
fi

# Verify build output
if [[ "$VERIFY" == "true" ]]; then
    log_step "Verifying CLI build output..."

    if [[ ! -d "packages/cli/dist" ]]; then
        log_error "CLI dist directory not created"
        exit 1
    fi

    if [[ ! -f "packages/cli/dist/index.js" ]]; then
        log_error "CLI index.js not found in dist"
        exit 1
    fi

    log_info "CLI build output verified"
    ls -lah packages/cli/dist/
fi

log_info "CLI build complete: packages/cli/dist/"
