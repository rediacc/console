#!/bin/bash
# Deploy the www Worker to Cloudflare
#
# Handles both production and preview deployments using the same wrangler.toml
# as the single source of truth. For preview, generates a temporary config
# overriding the worker name and service binding.
#
# Usage:
#   deploy-www.sh                                                   # production
#   deploy-www.sh --name pr-379 --account-service account-pr-379  # preview

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

REPO_ROOT="$(get_repo_root)"
WORKER_DIR="$REPO_ROOT/workers/www"

if [[ ! -f "$WORKER_DIR/wrangler.toml" ]]; then
    log_error "www worker not found at $WORKER_DIR"
    exit 1
fi

cd "$WORKER_DIR"

# Install deps if not already installed
if [[ ! -d "node_modules" ]]; then
    npm install
fi

if [[ -n "${ARG_NAME:-}" ]]; then
    # Preview deployment: generate config from production template
    ACCOUNT_SERVICE="${ARG_ACCOUNT_SERVICE:-account-server}"
    log_step "Deploying www preview worker: $ARG_NAME (account service: $ACCOUNT_SERVICE)"

    sed -e "s/^name = .*/name = \"$ARG_NAME\"/" \
        -e '/^routes = \[/,/^\]/d' \
        -e "s/^service = .*/service = \"$ACCOUNT_SERVICE\"/" \
        wrangler.toml >wrangler.preview.toml

    npx wrangler deploy --config wrangler.preview.toml
    rm -f wrangler.preview.toml
else
    # Production deployment: use wrangler.toml as-is
    log_step "Deploying www production worker..."
    npx wrangler deploy
fi
