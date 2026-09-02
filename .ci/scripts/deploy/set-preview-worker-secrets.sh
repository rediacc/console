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
#   PR_NUMBER=123 ACCOUNT_...=... .ci/scripts/deploy/set-preview-worker-secrets.sh
#
# Required env:
#   PR_NUMBER                      preview worker is named pr-<PR_NUMBER>
#   CLOUDFLARE_API_TOKEN           wrangler auth
#   CLOUDFLARE_ACCOUNT_ID          wrangler auth
#   ACCOUNT_ED25519_PRIVATE_KEY    ACCOUNT_ED25519_PUBLIC_KEY
#   ACCOUNT_X25519_PRIVATE_KEY     ACCOUNT_X25519_PUBLIC_KEY
#   ACCOUNT_SERVER_API_KEY         ACCOUNT_JWT_SECRET
#   STRIPE_SECRET_KEY              STRIPE_WEBHOOK_SECRET
#   ROOT_EMAIL                     CLOUDFLARE_TURNSTILE_SECRET_KEY
#   AWS_SES_ACCESS_KEY_ID          AWS_SES_SECRET_ACCESS_KEY
#   AWS_SES_REGION                 AWS_SES_FROM   AWS_SES_CONFIGURATION_SET
#
# ONE NAME EVERYWHERE. The `SECRET_*` / `VAR_*` translation shim is gone: the
# variable this script READS is the key it WRITES, and that key is what the
# Worker's zod schema declares (private/account/src/types/env.ts).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd jq
require_cmd npx

: "${PR_NUMBER:?PR_NUMBER is required}"

WORKER="pr-${PR_NUMBER}"

# ─── Non-empty guards, same shape and reasoning as the other two builders ────
# The four optional-but-silent values (SES pair, region, Turnstile) turn their
# feature off without an error when empty; the six ACCOUNT_* ones are
# non-optional in env.ts and would instead make every request on the preview
# 500 with an EnvConfigError. Both failures are far cheaper here.
#
# Stripe is NOT demanded: ci.yml feeds the preview the SANDBOX key, and a
# preview without billing is a legitimate state.
_require_nonempty() {
    local name="$1" value="$2"
    if [[ -z "$value" ]]; then
        echo "set-preview-worker-secrets.sh: $name is EMPTY for WORKER_NAME=$WORKER." >&2
        echo "  The Worker's schema either accepts an empty value and silently disables the" >&2
        echo "  feature, or rejects it on every request; this refuses to deploy instead." >&2
        exit 1
    fi
}
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
        CLOUDFLARE_TURNSTILE_SECRET_KEY: $turnstile
    }' | npx wrangler secret bulk --name "$WORKER"

log_info "Set 15 secrets on $WORKER in one bulk call"
