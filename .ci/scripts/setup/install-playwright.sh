#!/bin/bash
# Install Playwright browsers
# Usage: install-playwright.sh [options]
#
# Installs Playwright browsers with optional system dependencies.
# Supports installing specific browsers or all browsers.
#
# Options:
#   --browsers    Space-separated list of browsers (default: "chromium")
#   --with-deps   Install system dependencies (default: true in CI)
#   --package     Package directory (default: packages/e2e)
#
# Available browsers: chromium, firefox, webkit, msedge
#
# Example:
#   .ci/scripts/setup/install-playwright.sh
#   .ci/scripts/setup/install-playwright.sh --browsers "chromium webkit"
#   .ci/scripts/setup/install-playwright.sh --browsers "chromium firefox webkit" --with-deps

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

BROWSERS="${ARG_BROWSERS:-chromium}"
PACKAGE="${ARG_PACKAGE:-packages/e2e}"

# Default --with-deps to true in CI, false otherwise
if is_ci; then
    WITH_DEPS="${ARG_WITH_DEPS:-true}"
else
    WITH_DEPS="${ARG_WITH_DEPS:-false}"
fi

# Change to repo root
cd "$(get_repo_root)"

# Validate package directory
require_dir "$PACKAGE"

cd "$PACKAGE"

log_step "Installing Playwright browsers: $BROWSERS"

# Build base command
INSTALL_ARGS=()
[[ "$WITH_DEPS" == "true" ]] && INSTALL_ARGS+=("--with-deps")

# Deduplicate browsers
IFS=' ' read -ra BROWSER_ARR <<<"$BROWSERS"
declare -A SEEN_BROWSERS
UNIQUE_BROWSERS=()
for browser in "${BROWSER_ARR[@]}"; do
    if [[ -z "${SEEN_BROWSERS[$browser]:-}" ]]; then
        SEEN_BROWSERS[$browser]=1
        UNIQUE_BROWSERS+=("$browser")
    fi
done

# Install each unique browser
for browser in "${UNIQUE_BROWSERS[@]}"; do
    log_step "Installing $browser..."
    npx playwright install "${INSTALL_ARGS[@]}" "$browser"
done

log_info "Playwright browsers installed: ${UNIQUE_BROWSERS[*]}"
