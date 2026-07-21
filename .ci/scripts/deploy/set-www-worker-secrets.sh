#!/bin/bash
# Push every runtime secret into the www Worker (stable or edge) in ONE API call.
#
# WHY `secret bulk` AND NOT `secret put`: each individual `wrangler secret put`
# creates a new Worker version, and on an assets-bound Worker a new version
# disassociates the static assets that were uploaded with the deploy. One bulk
# call sets them all against a single version.
#
# Secrets arrive as ENVIRONMENT VARIABLES, never as arguments — argv is visible
# in process listings and in some log surfaces. Which Stripe / SES credentials
# land here is decided by the caller (stable gets the live EU keys, edge gets
# the sandbox ones); this script only marshals what it is handed.
#
# Usage:
#   .ci/scripts/deploy/set-www-worker-secrets.sh
#
# Required env:
#   WORKER_NAME                    Worker to write the secrets to
#   CLOUDFLARE_API_TOKEN           wrangler auth
#   CLOUDFLARE_ACCOUNT_ID          wrangler auth
#   SECRET_ED25519_PRIVATE_KEY     SECRET_ED25519_PUBLIC_KEY
#   SECRET_X25519_PRIVATE_KEY      SECRET_X25519_PUBLIC_KEY
#   SECRET_API_KEY                 SECRET_JWT_SECRET
#   SECRET_STRIPE_KEY              SECRET_STRIPE_WEBHOOK
#   SECRET_ROOT_EMAIL              SECRET_TURNSTILE_KEY
#   SECRET_SES_ACCESS_KEY_ID       SECRET_SES_SECRET_ACCESS_KEY
#   SECRET_SES_REGION              VAR_SES_FROM   VAR_SES_CONFIGURATION_SET
#   VAR_SELLER_NAME                VAR_SELLER_VAT_NUMBER
#   VAR_SELLER_REGISTRATION_NUMBER VAR_SELLER_ADDRESS_LINE1
#   VAR_SELLER_ADDRESS_LINE2       VAR_SELLER_CITY
#   VAR_SELLER_POSTAL_CODE         VAR_SELLER_COUNTRY   VAR_SELLER_EMAIL
#
# Run locally (WRITES to Cloudflare — point WORKER_NAME at a scratch Worker):
#   WORKER_NAME=scratch CLOUDFLARE_API_TOKEN=... \
#     .ci/scripts/deploy/set-www-worker-secrets.sh
#
# Shell options: the workflow block ran under plain `bash -e`; `-uo pipefail`
# are added here. pipefail only tightens the single `jq | wrangler` pipe, where
# a jq failure previously went unnoticed because wrangler's status won.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd jq
require_cmd npx
: "${WORKER_NAME:?set-www-worker-secrets.sh: WORKER_NAME must be set}"

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
    --arg seller_name "${VAR_SELLER_NAME:-}" \
    --arg seller_vat "${VAR_SELLER_VAT_NUMBER:-}" \
    --arg seller_reg "${VAR_SELLER_REGISTRATION_NUMBER:-}" \
    --arg seller_addr1 "${VAR_SELLER_ADDRESS_LINE1:-}" \
    --arg seller_addr2 "${VAR_SELLER_ADDRESS_LINE2:-}" \
    --arg seller_city "${VAR_SELLER_CITY:-}" \
    --arg seller_postal "${VAR_SELLER_POSTAL_CODE:-}" \
    --arg seller_country "${VAR_SELLER_COUNTRY:-}" \
    --arg seller_email "${VAR_SELLER_EMAIL:-}" \
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
        TURNSTILE_SECRET_KEY: $turnstile,
        SELLER_NAME: $seller_name,
        SELLER_VAT_NUMBER: $seller_vat,
        SELLER_REGISTRATION_NUMBER: $seller_reg,
        SELLER_ADDRESS_LINE1: $seller_addr1,
        SELLER_ADDRESS_LINE2: $seller_addr2,
        SELLER_CITY: $seller_city,
        SELLER_POSTAL_CODE: $seller_postal,
        SELLER_COUNTRY: $seller_country,
        SELLER_EMAIL: $seller_email
    }' | npx wrangler secret bulk --name "$WORKER_NAME"
