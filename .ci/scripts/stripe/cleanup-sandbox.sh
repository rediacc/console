#!/bin/bash
# Cleanup Stripe sandbox resources for a closed PR
#
# Deletes the per-PR webhook endpoint and Cloudflare Worker.
#
# Usage: cleanup-sandbox.sh --pr-number <N>
# Env: STRIPE_SANDBOX_SECRET_KEY, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

PR_NUMBER="${ARG_PR_NUMBER:-}"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd curl
require_cmd jq
require_var STRIPE_SANDBOX_SECRET_KEY
require_var CLOUDFLARE_API_TOKEN
require_var CLOUDFLARE_ACCOUNT_ID

if [[ -z "$PR_NUMBER" ]]; then
    log_error "Usage: cleanup-sandbox.sh --pr-number <N>"
    exit 1
fi

WORKER_NAME="account-pr-${PR_NUMBER}"
WEBHOOK_URL="https://${WORKER_NAME}.rediacc.workers.dev/account/api/v1/webhooks/stripe"

# Stripe API helper
stripe_api() {
    local method="$1" endpoint="$2"
    shift 2
    curl -s -X "$method" \
        "https://api.stripe.com${endpoint}" \
        -u "${STRIPE_SANDBOX_SECRET_KEY}:" \
        "$@"
}

# Cloudflare API helper
cf_api() {
    local method="$1" endpoint="$2"
    shift 2
    curl -s -X "$method" \
        "https://api.cloudflare.com/client/v4${endpoint}" \
        -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
        -H "Content-Type: application/json" \
        "$@"
}

# =============================================================================
# STEP 1: Delete Stripe webhook endpoint
# =============================================================================

log_step "Cleaning up Stripe webhook for PR #${PR_NUMBER}..."

endpoints=$(stripe_api GET "/v1/webhook_endpoints?limit=100")
endpoint_id=$(echo "$endpoints" | jq -r --arg url "$WEBHOOK_URL" \
    '.data[] | select(.url == $url) | .id' | head -1)

if [[ -n "$endpoint_id" ]]; then
    stripe_api DELETE "/v1/webhook_endpoints/$endpoint_id" > /dev/null
    log_info "Deleted webhook endpoint: $endpoint_id"
else
    log_info "No webhook endpoint found for PR #${PR_NUMBER}"
fi

# =============================================================================
# STEP 2: Delete Cloudflare Worker
# =============================================================================

log_step "Cleaning up Cloudflare Worker: $WORKER_NAME..."

delete_response=$(cf_api DELETE "/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$WORKER_NAME" 2>/dev/null || echo '{"success":false}')
delete_success=$(echo "$delete_response" | jq -r '.success // false')

if [[ "$delete_success" == "true" ]]; then
    log_info "Deleted worker: $WORKER_NAME"
else
    error_msg=$(echo "$delete_response" | jq -r '.errors[0].message // "not found"' 2>/dev/null || echo "not found")
    log_info "Worker $WORKER_NAME not found or already deleted: $error_msg"
fi

log_info "Cleanup complete for PR #${PR_NUMBER}"
