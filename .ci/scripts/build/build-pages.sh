#!/bin/bash
# Assemble GitHub Pages deployment package
# Usage: build-pages.sh [--output DIR]
#
# Assembles www, web (console), and json builds into a single directory
# suitable for GitHub Pages deployment.
#
# Options:
#   --output DIR   Output directory (default: dist)
#
# Prerequisites:
#   - packages/www/dist/ must exist (built www)
#   - packages/web/dist/ must exist (built web with VITE_BASE_PATH=/console/)
#   - packages/json/dist/ must exist (built json)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

OUTPUT_DIR="${ARG_OUTPUT:-dist}"

# Change to repo root
cd "$(get_repo_root)"

log_step "Assembling pages package..."

# Verify required builds exist
if [[ ! -d "packages/www/dist" ]]; then
    log_error "www build not found at packages/www/dist/"
    log_error "Run 'npm run build:www' first"
    exit 1
fi

if [[ ! -d "packages/web/dist" ]]; then
    log_error "web build not found at packages/web/dist/"
    log_error "Run 'npm run build:web' with VITE_BASE_PATH=/console/ first"
    exit 1
fi

if [[ ! -d "packages/json/dist" ]]; then
    log_error "json build not found at packages/json/dist/"
    log_error "Run 'npm run build:json' first"
    exit 1
fi

# Prepare output directory
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy www to root (marketing site)
log_step "Copying www to root..."
cp -r packages/www/dist/* "$OUTPUT_DIR/"
log_info "Copied www to $OUTPUT_DIR/"

# Copy web to /console/ subpath
log_step "Copying web to /console/..."
mkdir -p "$OUTPUT_DIR/console"
cp -r packages/web/dist/* "$OUTPUT_DIR/console/"
log_info "Copied web to $OUTPUT_DIR/console/"

# Copy json to /json/ subpath
log_step "Copying json to /json/..."
mkdir -p "$OUTPUT_DIR/json"
cp -r packages/json/dist/* "$OUTPUT_DIR/json/"
log_info "Copied json to $OUTPUT_DIR/json/"

# Copy CLI manifest to /cli/ subpath (if generated)
if [[ -f "dist/cli-manifest/manifest.json" ]]; then
    log_step "Copying CLI manifest to /cli/..."
    mkdir -p "$OUTPUT_DIR/cli"
    cp dist/cli-manifest/manifest.json "$OUTPUT_DIR/cli/manifest.json"
    log_info "Copied CLI manifest to $OUTPUT_DIR/cli/"
fi

# Note: apt/ and rpm/ directories are added by build-pkg-repo.sh
# directly into the output directory after this script runs

# Add CNAME for custom domain
log_step "Adding CNAME..."
echo "www.rediacc.com" > "$OUTPUT_DIR/CNAME"

# Add .nojekyll to prevent Jekyll processing
log_step "Adding .nojekyll..."
touch "$OUTPUT_DIR/.nojekyll"

# Display summary
log_info "Pages package ready at $OUTPUT_DIR/"
log_info "  - Root:     www.rediacc.com (marketing site)"
log_info "  - /console: www.rediacc.com/console/ (web app)"
log_info "  - /json:    www.rediacc.com/json/ (template catalog)"
log_info "  - /cli:     www.rediacc.com/cli/ (CLI update manifest)"
log_info "  - /apt:     www.rediacc.com/apt/ (APT repository)"
log_info "  - /rpm:     www.rediacc.com/rpm/ (RPM repository)"
