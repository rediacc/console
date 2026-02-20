#!/bin/bash
# Setup Stripe sandbox for PR preview environments
#
# Seeds products/prices (idempotent) and creates a per-PR webhook endpoint.
#
# Usage: setup-sandbox.sh --pr-number <N>
# Env: STRIPE_SANDBOX_SECRET_KEY
# Outputs (to $GITHUB_OUTPUT):
#   stripe_webhook_endpoint_id - ID of created webhook endpoint
#   stripe_webhook_secret      - Signing secret for webhook verification

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

if [[ -z "$PR_NUMBER" ]]; then
    log_error "Usage: setup-sandbox.sh --pr-number <N>"
    exit 1
fi

STRIPE_API="https://api.stripe.com"
WORKER_URL="https://account-pr-${PR_NUMBER}.rediacc.workers.dev"
WEBHOOK_URL="${WORKER_URL}/account/api/v1/webhooks/stripe"

# Stripe API helper
stripe_api() {
    local method="$1" endpoint="$2"
    shift 2
    curl -s -X "$method" \
        "${STRIPE_API}${endpoint}" \
        -u "${STRIPE_SANDBOX_SECRET_KEY}:" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        "$@"
}

# =============================================================================
# STEP 1: Seed products/prices (idempotent)
# =============================================================================

log_step "Checking if products exist in sandbox..."

existing_products=$(stripe_api GET "/v1/products?limit=100&active=true")
product_count=$(echo "$existing_products" | jq '[.data[] | select(.metadata.planCode != null)] | length')

if [[ "$product_count" -ge 3 ]]; then
    log_info "Products already seeded ($product_count found), skipping"
else
    log_step "Seeding products and prices..."

    REPO_ROOT="$(get_repo_root)"
    FIXTURES_FILE="$REPO_ROOT/stripe/fixtures/seed.json"
    require_file "$FIXTURES_FILE"

    # Use stripe CLI if available, otherwise seed manually via API
    if command -v stripe &>/dev/null; then
        stripe fixtures "$FIXTURES_FILE" --api-key "$STRIPE_SANDBOX_SECRET_KEY"
    else
        log_step "stripe CLI not available, seeding via API..."

        seed_product() {
            local name="$1" description="$2" plan_code="$3"
            local monthly_amount="$4" annual_amount="$5"
            local monthly_lookup="${6}" annual_lookup="${7}"

            # Create product
            local product
            product=$(stripe_api POST "/v1/products" \
                -d "name=$name" \
                -d "description=$description" \
                -d "metadata[planCode]=$plan_code")
            local product_id
            product_id=$(echo "$product" | jq -r '.id')
            log_debug "Created product: $product_id ($name)"

            # Create monthly price
            stripe_api POST "/v1/prices" \
                -d "product=$product_id" \
                -d "currency=usd" \
                -d "unit_amount=$monthly_amount" \
                -d "recurring[interval]=month" \
                -d "lookup_key=$monthly_lookup" \
                -d "transfer_lookup_key=true" \
                -d "metadata[planCode]=$plan_code" >/dev/null

            # Create annual price
            stripe_api POST "/v1/prices" \
                -d "product=$product_id" \
                -d "currency=usd" \
                -d "unit_amount=$annual_amount" \
                -d "recurring[interval]=year" \
                -d "lookup_key=$annual_lookup" \
                -d "transfer_lookup_key=true" \
                -d "metadata[planCode]=$plan_code" >/dev/null

            log_info "Seeded $name: product=$product_id"
        }

        seed_product "Professional" "For growing teams" "PROFESSIONAL" 34900 349000 "professional_monthly" "professional_annual"
        seed_product "Business" "For organizations" "BUSINESS" 69900 699000 "business_monthly" "business_annual"
        seed_product "Enterprise" "For large organizations" "ENTERPRISE" 210000 2100000 "enterprise_monthly" "enterprise_annual"
    fi

    log_info "Products and prices seeded successfully"
fi

# =============================================================================
# STEP 2: Create per-PR webhook endpoint
# =============================================================================

log_step "Setting up webhook endpoint for PR #${PR_NUMBER}..."

# Delete existing endpoint for this PR (webhook secret only available at creation)
existing_endpoints=$(stripe_api GET "/v1/webhook_endpoints?limit=100")
existing_id=$(echo "$existing_endpoints" | jq -r --arg url "$WEBHOOK_URL" \
    '.data[] | select(.url == $url) | .id' | head -1)

if [[ -n "$existing_id" ]]; then
    log_step "Deleting existing webhook endpoint: $existing_id"
    stripe_api DELETE "/v1/webhook_endpoints/$existing_id" >/dev/null
fi

# Create new webhook endpoint
log_step "Creating webhook endpoint: $WEBHOOK_URL"
webhook_response=$(stripe_api POST "/v1/webhook_endpoints" \
    -d "url=$WEBHOOK_URL" \
    -d "enabled_events[]=customer.subscription.updated" \
    -d "enabled_events[]=customer.subscription.deleted" \
    -d "enabled_events[]=invoice.payment_failed" \
    -d "enabled_events[]=invoice.payment_succeeded" \
    -d "enabled_events[]=checkout.session.completed" \
    -d "metadata[pr_number]=$PR_NUMBER")

webhook_id=$(echo "$webhook_response" | jq -r '.id')
webhook_secret=$(echo "$webhook_response" | jq -r '.secret')

if [[ -z "$webhook_id" || "$webhook_id" == "null" ]]; then
    log_error "Failed to create webhook endpoint"
    echo "$webhook_response" | jq . >&2
    exit 1
fi

log_info "Webhook endpoint created: $webhook_id"

# Output for GitHub Actions
if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "stripe_webhook_endpoint_id=$webhook_id" >>"$GITHUB_OUTPUT"
    echo "stripe_webhook_secret=$webhook_secret" >>"$GITHUB_OUTPUT"
fi
