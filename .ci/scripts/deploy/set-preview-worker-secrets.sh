#!/bin/bash
# Push every runtime secret into the per-PR preview Worker in ONE API call.
#
# WHY `secret bulk` AND NOT `secret put`: each individual `wrangler secret put`
# creates a new Worker version, and on an assets-bound Worker a new version
# disassociates the static assets that were uploaded with the deploy. One bulk
# call sets them all against a single version.
#
# Secrets arrive as ENVIRONMENT VARIABLES, never as arguments — argv is visible
# in process listings and in some log surfaces.
#
# Usage:
#   PR_NUMBER=123 SECRET_...=... .ci/scripts/deploy/set-preview-worker-secrets.sh
#
# Required env:
#   PR_NUMBER                      preview worker is named pr-<PR_NUMBER>
#   CLOUDFLARE_API_TOKEN           wrangler auth
#   CLOUDFLARE_ACCOUNT_ID          wrangler auth
#   SECRET_ED25519_PRIVATE_KEY     SECRET_ED25519_PUBLIC_KEY
#   SECRET_X25519_PRIVATE_KEY      SECRET_X25519_PUBLIC_KEY
#   SECRET_API_KEY                 SECRET_JWT_SECRET
#   SECRET_STRIPE_KEY              SECRET_STRIPE_WEBHOOK
#   SECRET_ROOT_EMAIL              SECRET_TURNSTILE_KEY
#   SECRET_SES_ACCESS_KEY_ID       SECRET_SES_SECRET_ACCESS_KEY
#   SECRET_SES_REGION              VAR_SES_FROM   VAR_SES_CONFIGURATION_SET

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd jq
require_cmd npx

: "${PR_NUMBER:?PR_NUMBER is required}"

WORKER="pr-${PR_NUMBER}"

jq -n \
    --arg ed25519_priv "${SECRET_ED25519_PRIVATE_KEY:-}" \
    --arg ed25519_pub "${SECRET_ED25519_PUBLIC_KEY:-}" \
    --arg x25519_priv "${SECRET_X25519_PRIVATE_KEY:-}" \
    --arg x25519_pub "${SECRET_X25519_PUBLIC_KEY:-}" \
    --arg api_key "${SECRET_API_KEY:-}" \
    --arg jwt "${SECRET_JWT_SECRET:-}" \
    --arg stripe "${SECRET_STRIPE_KEY:-}" \
    --arg stripe_wh "${SECRET_STRIPE_WEBHOOK:-}" \
    --arg admin "${SECRET_ROOT_EMAIL:-}" \
    --arg ses_key "${SECRET_SES_ACCESS_KEY_ID:-}" \
    --arg ses_secret "${SECRET_SES_SECRET_ACCESS_KEY:-}" \
    --arg ses_region "${SECRET_SES_REGION:-}" \
    --arg ses_from "${VAR_SES_FROM:-}" \
    --arg ses_cs "${VAR_SES_CONFIGURATION_SET:-}" \
    --arg turnstile "${SECRET_TURNSTILE_KEY:-}" \
    '{
        ED25519_PRIVATE_KEY: $ed25519_priv,
        ED25519_PUBLIC_KEY: $ed25519_pub,
        X25519_PRIVATE_KEY: $x25519_priv,
        X25519_PUBLIC_KEY: $x25519_pub,
        API_KEY: $api_key,
        JWT_SECRET: $jwt,
        STRIPE_SECRET_KEY: $stripe,
        STRIPE_WEBHOOK_SECRET: $stripe_wh,
        ROOT_EMAIL: $admin,
        AWS_SES_ACCESS_KEY_ID: $ses_key,
        AWS_SES_SECRET_ACCESS_KEY: $ses_secret,
        AWS_SES_REGION: $ses_region,
        AWS_SES_FROM: $ses_from,
        AWS_SES_CONFIGURATION_SET: $ses_cs,
        TURNSTILE_SECRET_KEY: $turnstile
    }' | npx wrangler secret bulk --name "$WORKER"

log_info "Set 15 secrets on $WORKER in one bulk call"
