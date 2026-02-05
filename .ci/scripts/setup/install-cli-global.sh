#!/bin/bash
# Pack and install CLI globally
# Usage: install-cli-global.sh [options]
#
# Creates a tarball of the CLI package and installs it globally.
# Useful for testing CLI integration in CI.
#
# Options:
#   --package-dir   Path to CLI package directory (default: packages/cli)
#
# Example:
#   .ci/scripts/setup/install-cli-global.sh
#   .ci/scripts/setup/install-cli-global.sh --package-dir packages/cli

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

PACKAGE_DIR="${ARG_PACKAGE_DIR:-packages/cli}"

# Change to repo root
cd "$(get_repo_root)"

# Validate package directory
require_dir "$PACKAGE_DIR"

log_step "Installing CLI globally from $PACKAGE_DIR..."

cd "$PACKAGE_DIR"

# Create tarball
log_step "Creating npm package tarball..."
npm pack

# Find the created tarball (name varies by version)
TARBALL=$(ls -1 rediacc-cli-*.tgz 2>/dev/null | head -n 1)

if [[ -z "$TARBALL" ]]; then
    log_error "No tarball found after npm pack"
    exit 1
fi

# Install globally
log_step "Installing $TARBALL globally..."
npm install -g "$TARBALL"

# Cleanup
rm -f "$TARBALL"

log_info "CLI installed globally"

# Verify installation
if command -v rdc &>/dev/null; then
    log_info "CLI available as 'rdc'"
elif command -v rediacc &>/dev/null; then
    log_info "CLI available as 'rediacc'"
else
    log_warn "CLI command not found in PATH (may need to restart shell)"
fi
