#!/bin/bash
# Build www (Astro marketing site)
# Usage: build-www.sh
#
# Builds the Astro marketing site located in packages/www.
# Output is generated at packages/www/dist/

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Change to repo root
cd "$(get_repo_root)"

log_step "Building www (Astro)..."

# Run build
if npm run build:www; then
    log_info "www build completed"
else
    log_error "www build failed"
    exit 1
fi

# Verify build output
require_dir "packages/www/dist" "www build output"
require_file "packages/www/dist/index.html" "www index.html"

log_info "www build complete: packages/www/dist/"
