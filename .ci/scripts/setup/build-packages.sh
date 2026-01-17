#!/bin/bash
# Build shared libraries (npm run build:packages)
# Usage: build-packages.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Change to repo root
cd "$(get_repo_root)"

log_step "Building shared packages..."

# Clean stale TypeScript build cache to prevent module resolution issues
# This is necessary because tsbuildinfo files can cause incremental builds to skip
# emitting files when paths change or when switching between branches
log_debug "Cleaning TypeScript build cache..."
rm -rf packages/shared/dist packages/shared/*.tsbuildinfo
rm -rf packages/shared-desktop/dist packages/shared-desktop/*.tsbuildinfo

if npm run build:packages; then
    log_info "Shared packages built successfully"
else
    log_error "Failed to build shared packages"
    exit 1
fi

# Verify build outputs exist
PACKAGES=("packages/shared/dist" "packages/shared-desktop/dist")
for pkg in "${PACKAGES[@]}"; do
    if [[ -d "$pkg" ]]; then
        log_info "Verified: $pkg exists"
    else
        log_warn "Package directory $pkg not found (may be expected)"
    fi
done
