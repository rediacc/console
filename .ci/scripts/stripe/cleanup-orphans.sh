#!/bin/bash
# Nightly cleanup of orphaned Stripe sandbox resources
#
# Lists all webhook endpoints with pr_number metadata, checks if the PR
# is still open, and deletes endpoints + workers for closed PRs.
#
# Usage: cleanup-orphans.sh
# Env: STRIPE_SANDBOX_SECRET_KEY, CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, GH_TOKEN

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd curl
require_cmd jq
require_cmd gh
require_var STRIPE_SANDBOX_SECRET_KEY
require_var CLOUDFLARE_API_TOKEN
require_var CLOUDFLARE_ACCOUNT_ID
require_var GH_TOKEN

GITHUB_REPO="${GITHUB_REPOSITORY:-rediacc/console}"

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
# MAIN
# =============================================================================

log_step "Scanning for orphaned Stripe sandbox resources..."

endpoints=$(stripe_api GET "/v1/webhook_endpoints?limit=100")
pr_endpoints=$(echo "$endpoints" | jq -c '[.data[] | select(.metadata.pr_number != null)]')
total=$(echo "$pr_endpoints" | jq 'length')

log_info "Found $total PR-associated webhook endpoints"

if [[ "$total" -eq 0 ]]; then
    log_info "No orphaned resources to clean up"
    exit 0
fi

cleaned=0

while IFS= read -r endpoint; do
    endpoint_id=$(echo "$endpoint" | jq -r '.id')
    pr_number=$(echo "$endpoint" | jq -r '.metadata.pr_number')

    # Check if PR is still open
    pr_state=$(gh pr view "$pr_number" --repo "$GITHUB_REPO" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")

    if [[ "$pr_state" == "OPEN" ]]; then
        log_debug "PR #${pr_number} is still open, skipping"
        continue
    fi

    log_step "PR #${pr_number} is ${pr_state}, cleaning up..."

    # Delete webhook endpoint
    stripe_api DELETE "/v1/webhook_endpoints/$endpoint_id" > /dev/null
    log_info "Deleted webhook endpoint: $endpoint_id (PR #${pr_number})"

    # Delete Cloudflare Workers (account-server + www proxy)
    worker_name="account-pr-${pr_number}"
    cf_api DELETE "/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$worker_name" > /dev/null 2>&1 || true
    log_info "Deleted worker: $worker_name"

    www_worker_name="www-pr-${pr_number}"
    cf_api DELETE "/accounts/$CLOUDFLARE_ACCOUNT_ID/workers/scripts/$www_worker_name" > /dev/null 2>&1 || true
    log_info "Deleted worker: $www_worker_name"

    cleaned=$((cleaned + 1))
done < <(echo "$pr_endpoints" | jq -c '.[]')

log_info "Cleaned up $cleaned orphaned PR environments"
