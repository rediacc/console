#!/bin/bash
# Deploy the www Worker to Cloudflare
#
# Handles both production and preview deployments.
# - Production: uses wrangler.toml as-is (Service Binding to account-server)
# - Preview: generates a combined worker config that embeds the account server
#   directly (preview.ts entry), so only a single Worker (pr-N) is needed.
#
# Usage:
#   deploy-www.sh                  # production
#   deploy-www.sh --name pr-379    # preview (combined worker)

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
    # Preview deployment: combined worker with account server embedded.
    # Uses preview.ts entry point which imports the account Hono app directly,
    # eliminating the need for a separate account-pr-N worker.
    log_step "Deploying combined preview worker: $ARG_NAME"

    cat >wrangler.preview.toml <<TOML
name = "$ARG_NAME"
main = "src/preview.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = "./dist"
run_worker_first = ["/account", "/account/*"]

[vars]
S3_BUCKET = "subscriptions"
S3_REGION = "auto"
TOML

    npx wrangler deploy --config wrangler.preview.toml
    rm -f wrangler.preview.toml
else
    # Production deployment: use wrangler.toml as-is
    log_step "Deploying www production worker..."
    npx wrangler deploy
fi
