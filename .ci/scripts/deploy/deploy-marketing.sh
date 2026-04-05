#!/bin/bash
# Deploy the marketing Worker to Cloudflare
#
# Serves the static marketing site (docs, pricing, downloads).
# No D1 or R2 -- purely static assets with smart 404 redirects
# and a proxy for public account API calls (newsletter, contact).
#
# Usage:
#   deploy-marketing.sh                    # production (www.rediacc.com)
#   deploy-marketing.sh --target edge      # edge (edge.rediacc.com)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

REPO_ROOT="$(get_repo_root)"
WORKER_DIR="$REPO_ROOT/workers/marketing"
TARGET="${ARG_TARGET:-production}"

if [[ "$TARGET" == "edge" ]]; then
    CONFIG="wrangler.edge.toml"
else
    CONFIG="wrangler.toml"
fi

if [[ ! -f "$WORKER_DIR/$CONFIG" ]]; then
    log_error "Wrangler config not found: $WORKER_DIR/$CONFIG"
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

log_step "Deploying marketing worker: $TARGET ($CONFIG)"
npx wrangler deploy --config "$CONFIG"
log_info "Marketing worker deployed: $TARGET"
