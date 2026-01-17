#!/bin/bash
# Check .npmrc for problematic settings
# Usage: check-npmrc.sh
#
# Validates that .npmrc doesn't contain settings that hide dependency problems:
#   - legacy-peer-deps: Ignores peer dependency conflicts
#   - force: Forces installation despite errors
#
# These settings can mask real dependency issues that should be fixed properly.
#
# Example:
#   .ci/scripts/quality/check-npmrc.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Change to repo root
cd "$(get_repo_root)"

log_step "Checking .npmrc for problematic settings..."

if [[ -f .npmrc ]]; then
    if grep -qiE "legacy-peer-deps|force" .npmrc; then
        log_error ".npmrc contains legacy-peer-deps or force=true"
        log_error "These settings hide dependency problems that should be fixed properly."
        echo ""
        echo "Problematic lines:"
        grep -iE "legacy-peer-deps|force" .npmrc || true
        exit 1
    fi
    log_info ".npmrc is clean"
else
    log_info "No .npmrc file found (this is fine)"
fi
