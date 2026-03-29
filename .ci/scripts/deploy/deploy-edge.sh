#!/bin/bash
# Deploy the edge Worker to Cloudflare (edge.rediacc.com)
#
# Applies migrations to edge-account-db, then deploys the edge Worker.
# Uses wrangler.edge.toml for edge-specific config (separate D1, domain).
#
# Usage:
#   deploy-edge.sh
#
# Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
WORKER_DIR="$REPO_ROOT/workers/www"

if [[ ! -f "$WORKER_DIR/wrangler.edge.toml" ]]; then
    log_error "Edge worker config not found at $WORKER_DIR/wrangler.edge.toml"
    exit 1
fi

cd "$WORKER_DIR"

require_var CLOUDFLARE_API_TOKEN
require_var CLOUDFLARE_ACCOUNT_ID

CLOUDFLARE_API_TOKEN="$(printf '%s' "$CLOUDFLARE_API_TOKEN" | tr -d '\r\n')"
export CLOUDFLARE_API_TOKEN

# Install deps if not already installed
if [[ ! -d "node_modules" ]]; then
    npm install
fi

log_step "Deploying edge worker (edge.rediacc.com)..."

# Apply migrations to edge D1 (idempotent)
log_step "Applying migrations to edge-account-db..."
npx wrangler d1 migrations apply edge-account-db --remote --config wrangler.edge.toml
log_info "Migrations applied to edge-account-db"

# Deploy edge worker
npx wrangler deploy --config wrangler.edge.toml
log_info "Edge worker deployed"
