#!/bin/bash
# Standalone CLI runner for rdc (development mode)
# Auto-builds renet from Go source and makes it available to the CLI.

set -euo pipefail

# Root directory
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

# Auto-install: ensure `rdc` is globally available, pointing to this worktree
mkdir -p ~/.local/bin
ln -sf "$ROOT_DIR/rdc.sh" ~/.local/bin/rdc

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

# Regenerate skill reference if CLI has changed
ref_file="$ROOT_DIR/.claude/skills/rdc/reference.md"
cli_dist="$ROOT_DIR/packages/cli/dist/cli-bundle.cjs"
if [[ ! -f "$ref_file" ]] || [[ "$cli_dist" -nt "$ref_file" ]]; then
    log_step "Regenerating skill reference"
    ref_tmp="$(mktemp)"
    if node "$cli_dist" agent generate-reference > "$ref_tmp" 2>/dev/null && grep -q "^#" "$ref_tmp"; then
        mv "$ref_tmp" "$ref_file"
    else
        rm -f "$ref_tmp"
        log_warn "Skill reference generation failed (keeping existing)"
    fi
fi

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
