#!/bin/bash
# Deploy the www Worker to Cloudflare
#
# Handles both production and preview deployments.
# Both use the same index.ts entry point which embeds the account server directly.
# - Production: uses wrangler.toml as-is
# - Preview: generates wrangler.preview.toml with different name and preview S3 bucket
#
# Usage:
#   deploy-www.sh                  # production
#   deploy-www.sh --name pr-379    # preview

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
    log_step "Deploying preview worker: $ARG_NAME"

    cat >wrangler.preview.toml <<TOML
name = "$ARG_NAME"
main = "src/index.ts"
compatibility_date = "2025-01-01"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = "./dist"
run_worker_first = ["/account", "/account/*"]

[vars]
S3_BUCKET = "subscriptions-preview"
S3_REGION = "auto"
TOML

    npx wrangler deploy --config wrangler.preview.toml
    rm -f wrangler.preview.toml
else
    # Production deployment: use wrangler.toml as-is
    log_step "Deploying www production worker..."
    npx wrangler deploy
fi
