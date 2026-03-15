#!/bin/bash
# Standalone CLI runner for rdc (development mode)
# Auto-builds renet from Go source and makes it available to the CLI.

set -euo pipefail

# Root directory
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
source "$ROOT_DIR/.ci/lib/elite-backend.sh"
source "$ROOT_DIR/.ci/lib/service.sh"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"

check_node_version

log_step "Preparing CLI development environment"

# Ensure npm dependencies are installed
ensure_deps

# Ensure shared packages are built
ensure_packages_built

# Ensure CLI is built and type-valid
ensure_cli_built

# Ensure renet is built and up-to-date
ensure_renet_built

# Add renet binary directory to PATH so CLI can find it
renet_bin_dir="$ROOT_DIR/private/renet/bin"
export PATH="$renet_bin_dir:$PATH"
export REDIACC_ENVIRONMENT=development
export REDIACC_SUBSCRIPTION_TOKEN_FILE="$ROOT_DIR/.rdc-dev/api-token.json"

log_info "Renet available at: $renet_bin_dir/renet"

# Load account env if available (provides REDIACC_ACCOUNT_SERVER for subscription commands)
account_env="$ROOT_DIR/private/account/.env"
if [[ -f "$account_env" ]]; then
    set -a
    source "$account_env"
    set +a
fi

log_step "Starting CLI (dev mode)"

# Run the compiled CLI bundle, passing through all arguments
node "$ROOT_DIR/packages/cli/dist/cli-bundle.cjs" "$@"
