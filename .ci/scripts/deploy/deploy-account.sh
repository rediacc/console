#!/bin/bash
# Deploy the account Worker to Cloudflare for a specific region
#
# Each region has its own D1 database and R2 bucket, configured in
# region-specific wrangler configs (wrangler.{region}.toml).
#
# Usage:
#   deploy-account.sh --region eu                    # production EU
#   deploy-account.sh --region us                    # production US
#   deploy-account.sh --region asia                  # production ASIA
#   deploy-account.sh --region eu --target edge      # edge EU

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

REPO_ROOT="$(get_repo_root)"
WORKER_DIR="$REPO_ROOT/workers/account"
REGION="${ARG_REGION:?--region is required (eu, us)}"
TARGET="${ARG_TARGET:-production}"

# Resolve wrangler config for this region and target
if [[ "$TARGET" == "edge" ]]; then
    CONFIG="wrangler.edge-${REGION}.toml"
else
    CONFIG="wrangler.${REGION}.toml"
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

# Ensure wrangler is available (installed globally by CD workflow, or locally)
if ! command -v wrangler &>/dev/null && [[ ! -d "node_modules" ]]; then
    npm install
fi

# Read D1 database name from wrangler config
DB_NAME=$(grep 'database_name' "$CONFIG" | head -1 | sed 's/.*= *"\(.*\)"/\1/')
if [[ -z "$DB_NAME" ]]; then
    log_error "Could not read database_name from $CONFIG"
    exit 1
fi

log_step "Deploying account worker: $TARGET $REGION ($CONFIG)"

# Apply migrations (idempotent)
log_step "Applying migrations to $DB_NAME..."
npx wrangler d1 migrations apply "$DB_NAME" --remote --config "$CONFIG"
log_info "Migrations applied to $DB_NAME"

# Deploy
npx wrangler deploy --config "$CONFIG"
log_info "Account worker deployed: $TARGET $REGION"
