#!/bin/bash
# Build json (template catalog)
# Usage: build-json.sh
#
# Builds the template catalog site located in packages/json.
# Output is generated at packages/json/dist/

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Change to repo root
cd "$(get_repo_root)"

log_step "Building json (template catalog)..."

# Run build
if npm run build:json; then
    log_info "json build completed"
else
    log_error "json build failed"
    exit 1
fi

# Verify build output
if [[ ! -d "packages/json/dist" ]]; then
    log_error "json dist directory not created"
    exit 1
fi

if [[ ! -f "packages/json/dist/index.html" ]]; then
    log_error "json index.html not found in dist"
    exit 1
fi

log_info "json build complete: packages/json/dist/"
