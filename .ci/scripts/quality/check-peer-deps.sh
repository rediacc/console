#!/bin/bash
# Check for peer dependency conflicts
# Usage: check-peer-deps.sh
#
# Runs npm ls and checks for invalid peer dependencies.
# Peer dependency conflicts can cause runtime issues and should be resolved.
#
# Example:
#   .ci/scripts/quality/check-peer-deps.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Change to repo root
cd "$(get_repo_root)"

log_step "Checking for peer dependency conflicts..."

# Run npm ls and capture output (it may have non-zero exit on warnings)
NPM_LS_OUTPUT=$(npm ls 2>&1 || true)

if echo "$NPM_LS_OUTPUT" | grep -q "invalid"; then
    log_error "Peer dependency conflicts detected"
    echo ""
    echo "Invalid dependencies:"
    echo "$NPM_LS_OUTPUT" | grep "invalid" || true
    exit 1
fi

log_info "No peer dependency conflicts found"
