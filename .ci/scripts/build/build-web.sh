#!/bin/bash
# Build web application
# Usage: build-web.sh [--type DEBUG|RELEASE] [--analyze]
#
# Options:
#   --type     Build type: DEBUG or RELEASE (default: RELEASE)
#   --analyze  Analyze bundle size after build
#
# Environment variables:
#   VITE_APP_VERSION  Version to embed in build (default: git SHA)
#   VITE_BASE_PATH    Base path for routing (default: /)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

BUILD_TYPE="${ARG_TYPE:-RELEASE}"
ANALYZE="${ARG_ANALYZE:-false}"

# Validate build type
case "$BUILD_TYPE" in
    DEBUG | RELEASE) ;;
    *)
        log_error "Invalid build type: $BUILD_TYPE (must be DEBUG or RELEASE)"
        exit 1
        ;;
esac

# Change to repo root
cd "$(get_repo_root)"

log_step "Building web application ($BUILD_TYPE)..."

# Set build environment
export REDIACC_BUILD_TYPE="$BUILD_TYPE"
export VITE_APP_VERSION="${VITE_APP_VERSION:-$(git rev-parse --short HEAD 2>/dev/null || echo 'dev')}"
export VITE_BASE_PATH="${VITE_BASE_PATH:-/}"
export NODE_ENV="production"

# Run build
if npm run build:web; then
    log_info "Web build completed"
else
    log_error "Web build failed"
    exit 1
fi

# Verify build output
if [[ ! -d "packages/web/dist" ]]; then
    log_error "dist directory not created"
    exit 1
fi

if [[ ! -f "packages/web/dist/index.html" ]]; then
    log_error "index.html not found in dist"
    exit 1
fi

log_info "Build output verified"

# Bundle size analysis
if [[ "$ANALYZE" == "true" ]] || [[ "$BUILD_TYPE" == "RELEASE" ]]; then
    log_step "Analyzing bundle size..."

    # Total size (cross-platform: use -sk for kilobytes, works on both GNU and BSD)
    TOTAL_SIZE_KB=$(du -sk packages/web/dist/ | cut -f1)
    TOTAL_SIZE=$((TOTAL_SIZE_KB * 1024))
    TOTAL_SIZE_MB=$(awk "BEGIN {printf \"%.2f\", $TOTAL_SIZE_KB / 1024}")

    log_info "Total bundle size: ${TOTAL_SIZE_MB}MB"

    # Check size limit (10MB)
    MAX_SIZE=$((10 * 1024 * 1024))
    if [[ $TOTAL_SIZE -gt $MAX_SIZE ]]; then
        log_warn "Bundle size exceeds 10MB limit"
    fi

    # List JS bundles
    if [[ -d "packages/web/dist/assets/js" ]]; then
        log_step "JS bundles:"
        du -h packages/web/dist/assets/js/*.js | sort -h
    fi
fi

log_info "Web build complete: packages/web/dist/"
