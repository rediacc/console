#!/bin/bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-peer-deps is now registered to the Python port's entry point,
# .ci/scripts/quality/check_peer_deps.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs "...check_peer_deps.py" but its header derives "...check-peer-deps.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

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

if grep -q "invalid" <<<"$NPM_LS_OUTPUT"; then
    log_error "Peer dependency conflicts detected"
    echo ""
    echo "Invalid dependencies:"
    echo "$NPM_LS_OUTPUT" | grep "invalid" || true
    exit 1
fi

log_info "No peer dependency conflicts found"
