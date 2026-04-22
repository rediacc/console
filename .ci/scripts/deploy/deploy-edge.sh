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

# Apply migrations to edge D1 (idempotent). Skip gracefully only when the DB
# genuinely does not exist (CF API 7404) -- edge-account-db is the pre-
# multi-region monolithic edge DB; after the regional rollout
# (account-db-{eu,us,asia}, edge-account-db-{eu,us,asia}) the monolithic DB
# may have been deleted. Auth/network errors still fail the deploy so they
# are not silently swallowed.
log_step "Checking edge-account-db existence..."
D1_INFO_STDERR="$(mktemp)"
trap 'rm -f "$D1_INFO_STDERR"' EXIT
if npx wrangler d1 info edge-account-db --config wrangler.edge.toml >/dev/null 2>"$D1_INFO_STDERR"; then
    log_step "Applying migrations to edge-account-db..."
    npx wrangler d1 migrations apply edge-account-db --remote --config wrangler.edge.toml
    log_info "Migrations applied to edge-account-db"
elif grep -qE 'code:[[:space:]]*7404|could not be found|Couldn.t find a DB' "$D1_INFO_STDERR"; then
    log_warn "edge-account-db not found on this account (7404); skipping migrations (deploy continues)"
    log_warn "Follow-up: recreate the DB or remove the binding from workers/www/wrangler.edge.toml"
else
    log_error "wrangler d1 info failed for a non-404 reason; aborting to avoid silent deploy on auth/network error:"
    cat "$D1_INFO_STDERR" >&2
    exit 1
fi

# Deploy edge worker
npx wrangler deploy --config wrangler.edge.toml
log_info "Edge worker deployed"
