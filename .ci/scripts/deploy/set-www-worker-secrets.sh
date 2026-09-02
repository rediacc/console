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
#   ACCOUNT_ED25519_PRIVATE_KEY    ACCOUNT_ED25519_PUBLIC_KEY
#   ACCOUNT_X25519_PRIVATE_KEY     ACCOUNT_X25519_PUBLIC_KEY
#   ACCOUNT_SERVER_API_KEY         ACCOUNT_JWT_SECRET
#   STRIPE_SECRET_KEY              STRIPE_WEBHOOK_SECRET
#   ROOT_EMAIL                     CLOUDFLARE_TURNSTILE_SECRET_KEY
#   AWS_SES_ACCESS_KEY_ID          AWS_SES_SECRET_ACCESS_KEY
#   AWS_SES_REGION                 AWS_SES_FROM   AWS_SES_CONFIGURATION_SET
#   SELLER_NAME                    SELLER_VAT_NUMBER
#   SELLER_REGISTRATION_NUMBER     SELLER_ADDRESS_LINE1
#   SELLER_ADDRESS_LINE2           SELLER_CITY
#   SELLER_POSTAL_CODE             SELLER_COUNTRY   SELLER_EMAIL
#
# ONE NAME EVERYWHERE. The `SECRET_*` / `VAR_*` translation shim is gone: the
# variable this script READS is the key it WRITES, and that key is what the
# Worker's zod schema declares (private/account/src/types/env.ts). There is no
# region indirection at all in this builder -- cd-deploy-worker.yml decides
# which Stripe/SES credentials to hand it (sandbox on edge, live EU on stable)
# and passes them under their own names.
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

# ─── Non-empty guards for values zod will NOT catch ──────────────────────────
# Same reasoning and same shape as set-account-worker-secrets.sh: the Worker
# schema marks these optional() and normalises "" to undefined, so an empty
# value deploys cleanly and silently turns the feature off. `required: true`
# on the GitHub side used to be the guard; a job-start Bitwarden fetch has no
# equivalent, so the guard lives on the deploy path. Stripe is unconditional
# here: cd-deploy-worker.yml feeds the sandbox key on edge and the live key on
# stable, so it is never legitimately empty for www.
_require_nonempty() {
    local name="$1" value="$2"
    if [[ -z "$value" ]]; then
        echo "set-www-worker-secrets.sh: $name is EMPTY for WORKER_NAME=$WORKER_NAME." >&2
        echo "  The Worker's schema accepts an empty value and silently disables the feature it" >&2
        echo "  drives, so this refuses to deploy instead. Check the secret store for that name." >&2
        exit 1
    fi
}
# The six env.ts declares NON-optional are demanded here too. zod DOES catch
# those -- but only inside the deployed Worker, as an EnvConfigError 500 on
# every request afterwards. Catching them at deploy time costs one line each
# and is the difference between a failed deploy and a broken region.
_require_nonempty ACCOUNT_ED25519_PRIVATE_KEY "${ACCOUNT_ED25519_PRIVATE_KEY:-}"
_require_nonempty ACCOUNT_ED25519_PUBLIC_KEY "${ACCOUNT_ED25519_PUBLIC_KEY:-}"
_require_nonempty ACCOUNT_X25519_PRIVATE_KEY "${ACCOUNT_X25519_PRIVATE_KEY:-}"
_require_nonempty ACCOUNT_X25519_PUBLIC_KEY "${ACCOUNT_X25519_PUBLIC_KEY:-}"
_require_nonempty ACCOUNT_SERVER_API_KEY "${ACCOUNT_SERVER_API_KEY:-}"
_require_nonempty ACCOUNT_JWT_SECRET "${ACCOUNT_JWT_SECRET:-}"
_require_nonempty ROOT_EMAIL "${ROOT_EMAIL:-}"
_require_nonempty AWS_SES_ACCESS_KEY_ID "${AWS_SES_ACCESS_KEY_ID:-}"
_require_nonempty AWS_SES_SECRET_ACCESS_KEY "${AWS_SES_SECRET_ACCESS_KEY:-}"
_require_nonempty AWS_SES_REGION "${AWS_SES_REGION:-}"
_require_nonempty CLOUDFLARE_TURNSTILE_SECRET_KEY "${CLOUDFLARE_TURNSTILE_SECRET_KEY:-}"
_require_nonempty STRIPE_SECRET_KEY "${STRIPE_SECRET_KEY:-}"
_require_nonempty STRIPE_WEBHOOK_SECRET "${STRIPE_WEBHOOK_SECRET:-}"

jq -n \
    --arg ed25519_priv "${ACCOUNT_ED25519_PRIVATE_KEY:-}" \
    --arg ed25519_pub "${ACCOUNT_ED25519_PUBLIC_KEY:-}" \
    --arg x25519_priv "${ACCOUNT_X25519_PRIVATE_KEY:-}" \
    --arg x25519_pub "${ACCOUNT_X25519_PUBLIC_KEY:-}" \
    --arg api_key "${ACCOUNT_SERVER_API_KEY:-}" \
    --arg jwt "${ACCOUNT_JWT_SECRET:-}" \
    --arg stripe "${STRIPE_SECRET_KEY:-}" \
    --arg stripe_wh "${STRIPE_WEBHOOK_SECRET:-}" \
    --arg admin "${ROOT_EMAIL:-}" \
    --arg ses_key "${AWS_SES_ACCESS_KEY_ID:-}" \
    --arg ses_secret "${AWS_SES_SECRET_ACCESS_KEY:-}" \
    --arg ses_region "${AWS_SES_REGION:-}" \
    --arg ses_from "${AWS_SES_FROM:-}" \
    --arg ses_cs "${AWS_SES_CONFIGURATION_SET:-}" \
    --arg turnstile "${CLOUDFLARE_TURNSTILE_SECRET_KEY:-}" \
    --arg seller_name "${SELLER_NAME:-}" \
    --arg seller_vat "${SELLER_VAT_NUMBER:-}" \
    --arg seller_reg "${SELLER_REGISTRATION_NUMBER:-}" \
    --arg seller_addr1 "${SELLER_ADDRESS_LINE1:-}" \
    --arg seller_addr2 "${SELLER_ADDRESS_LINE2:-}" \
    --arg seller_city "${SELLER_CITY:-}" \
    --arg seller_postal "${SELLER_POSTAL_CODE:-}" \
    --arg seller_country "${SELLER_COUNTRY:-}" \
    --arg seller_email "${SELLER_EMAIL:-}" \
    '{
        ACCOUNT_ED25519_PRIVATE_KEY: $ed25519_priv,
        ACCOUNT_ED25519_PUBLIC_KEY: $ed25519_pub,
        ACCOUNT_X25519_PRIVATE_KEY: $x25519_priv,
        ACCOUNT_X25519_PUBLIC_KEY: $x25519_pub,
        ACCOUNT_SERVER_API_KEY: $api_key,
        ACCOUNT_JWT_SECRET: $jwt,
        STRIPE_SECRET_KEY: $stripe,
        STRIPE_WEBHOOK_SECRET: $stripe_wh,
        ROOT_EMAIL: $admin,
        AWS_SES_ACCESS_KEY_ID: $ses_key,
        AWS_SES_SECRET_ACCESS_KEY: $ses_secret,
        AWS_SES_REGION: $ses_region,
        AWS_SES_FROM: $ses_from,
        AWS_SES_CONFIGURATION_SET: $ses_cs,
        CLOUDFLARE_TURNSTILE_SECRET_KEY: $turnstile,
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
