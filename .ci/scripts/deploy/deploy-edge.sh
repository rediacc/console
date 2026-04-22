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

# Apply migrations to edge D1 (idempotent). Skip gracefully if the DB does
# not exist -- edge-account-db is the pre-multi-region monolithic edge DB;
# after the regional rollout (account-db-{eu,us,asia}, edge-account-db-{eu,us,asia})
# the monolithic DB may have been deleted. The marketing worker's /account/api
# handler would 500 at runtime in that case, but the deploy itself should not
# fail. Deferred cleanup tracked separately.
log_step "Applying migrations to edge-account-db (if it exists)..."
if npx wrangler d1 info edge-account-db --config wrangler.edge.toml >/dev/null 2>&1; then
    npx wrangler d1 migrations apply edge-account-db --remote --config wrangler.edge.toml
    log_info "Migrations applied to edge-account-db"
else
    log_warn "edge-account-db not found on this account; skipping migrations (deploy continues)"
fi

# Deploy edge worker
npx wrangler deploy --config wrangler.edge.toml
log_info "Edge worker deployed"
