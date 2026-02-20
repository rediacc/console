#!/bin/bash
# Deploy per-PR account server worker to Cloudflare
#
# Usage: deploy-account-server-preview.sh --pr-number <N> --webhook-secret <secret>
# Env: STRIPE_SANDBOX_SECRET_KEY, CLOUDFLARE_API_TOKEN,
#      S3_ENDPOINT, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY,
#      ED25519_PRIVATE_KEY, ED25519_PUBLIC_KEY, ACCOUNT_SERVER_API_KEY

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

PR_NUMBER="${ARG_PR_NUMBER:-}"
WEBHOOK_SECRET="${ARG_WEBHOOK_SECRET:-}"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd npx
require_var STRIPE_SANDBOX_SECRET_KEY
require_var CLOUDFLARE_API_TOKEN
require_var S3_ENDPOINT
require_var S3_ACCESS_KEY_ID
require_var S3_SECRET_ACCESS_KEY
require_var ED25519_PRIVATE_KEY
require_var ED25519_PUBLIC_KEY
require_var ACCOUNT_SERVER_API_KEY

if [[ -z "$PR_NUMBER" || -z "$WEBHOOK_SECRET" ]]; then
    log_error "Usage: deploy-account-server-preview.sh --pr-number <N> --webhook-secret <secret>"
    exit 1
fi

WORKER_NAME="account-pr-${PR_NUMBER}"
REPO_ROOT="$(get_repo_root)"
ACCOUNT_DIR="$REPO_ROOT/private/account"

require_dir "$ACCOUNT_DIR"

# =============================================================================
# DEPLOY WORKER
# =============================================================================

log_step "Deploying $WORKER_NAME to Cloudflare Workers..."

cd "$ACCOUNT_DIR"

# Deploy with custom worker name (no custom domain for preview)
npx wrangler deploy \
    --name "$WORKER_NAME" \
    --var "S3_BUCKET:licenses-preview" \
    --var "S3_REGION:auto"

log_info "Worker deployed: https://${WORKER_NAME}.rediacc.workers.dev"

# =============================================================================
# SET SECRETS
# =============================================================================

log_step "Setting worker secrets..."

set_secret() {
    local name="$1" value="$2"
    echo "$value" | npx wrangler secret put "$name" --name "$WORKER_NAME" 2>/dev/null
    log_debug "Set secret: $name"
}

set_secret "STRIPE_SECRET_KEY" "$STRIPE_SANDBOX_SECRET_KEY"
set_secret "STRIPE_WEBHOOK_SECRET" "$WEBHOOK_SECRET"
set_secret "S3_ENDPOINT" "$S3_ENDPOINT"
set_secret "S3_ACCESS_KEY_ID" "$S3_ACCESS_KEY_ID"
set_secret "S3_SECRET_ACCESS_KEY" "$S3_SECRET_ACCESS_KEY"
set_secret "ED25519_PRIVATE_KEY" "$ED25519_PRIVATE_KEY"
set_secret "ED25519_PUBLIC_KEY" "$ED25519_PUBLIC_KEY"
set_secret "API_KEY" "$ACCOUNT_SERVER_API_KEY"

log_info "All secrets configured for $WORKER_NAME"

# Output for GitHub Actions
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "account_server_url=https://${WORKER_NAME}.rediacc.workers.dev" >>"$GITHUB_OUTPUT"
fi
