#!/bin/bash
# Push every runtime secret into ONE regional account Worker in a single API call.
#
# WHY `secret bulk` AND NOT `secret put`: each individual `wrangler secret put`
# creates a new Worker version, and on an assets-bound Worker a new version
# disassociates the static assets that were uploaded with the deploy. One bulk
# call sets them all against a single version.
#
# Secrets arrive as ENVIRONMENT VARIABLES, never as arguments — argv is visible
# in process listings and in some log surfaces.
#
# ONE NAME EVERYWHERE. There used to be a translation shim here: the workflow
# handed in `SECRET_ED25519_PRIVATE_KEY` / `VAR_SELLER_NAME` / `STRIPE_KEY_EU`,
# and this script wrote a THIRD spelling (`ED25519_PRIVATE_KEY`) into the
# Worker. Three namespaces for one value is the "what is for what" problem the
# secret-namespace migration exists to end, so the shim is gone: the variable
# this script READS and the key it WRITES are now the same name, and that name
# is the one the Worker's zod schema declares
# (private/account/src/types/env.ts). Adding a secret here means adding exactly
# one name, and `npm run check:ci-worker-secret-names` asserts the two files
# agree — zod v4 STRIPS an unknown key silently, so a disagreement is otherwise
# invisible until the feature it drives quietly stops working.
#
# THE INDIRECTIONS THAT REMAIN, and why each one is not a shim:
#
#   AWS_SES_ACCESS_KEY_ID_<SUFFIX>     -> Worker AWS_SES_ACCESS_KEY_ID
#   AWS_SES_SECRET_ACCESS_KEY_<SUFFIX> -> Worker AWS_SES_SECRET_ACCESS_KEY
#   STRIPE_WEBHOOK_SECRET_<SUFFIX>     -> Worker STRIPE_WEBHOOK_SECRET
#   OBS_OTLP_CREDENTIALS_<SUFFIX>      -> Worker OBS_OTLP_CREDENTIALS
#     These are REGION FAN-INS, not renames. The store holds three genuinely
#     different values; one regional Worker holds one of them, and the deploy
#     job is handed all three so it can pick its own. The suffix is dropped
#     because the Worker has no concept of "the other region's" credential.
#     Resolved by bash indirection off SUFFIX — a find-and-replace CANNOT see
#     these constructed names, so a future rename must edit them by hand.
#
#   STRIPE_SECRET_KEY                  -> Worker STRIPE_SECRET_KEY
#     NO suffix, and this is the 2026-09-02 correction: there is ONE Stripe
#     account (acct_1ONIroAH2UKrsSNm) serving every region, so the three
#     STRIPE_SECRET_KEY_{EU,US,ASIA} secrets held one identical value and the
#     region suffix was a fiction. Only the WEBHOOK secret is genuinely
#     per-region — each endpoint has its own signing secret.
#
# On the edge channel Stripe is deliberately blank: billing is disabled there.
#
# Usage:
#   .ci/scripts/deploy/set-account-worker-secrets.sh
#
# Required env:
#   WORKER_NAME                    Worker to write the secrets to
#   TARGET                         deploy channel: stable | edge
#   SUFFIX                         region suffix for indirection: EU | US | ASIA
#   CLOUDFLARE_API_TOKEN           wrangler auth
#   CLOUDFLARE_ACCOUNT_ID          wrangler auth
#   ACCOUNT_ED25519_PRIVATE_KEY    ACCOUNT_ED25519_PUBLIC_KEY
#   ACCOUNT_X25519_PRIVATE_KEY     ACCOUNT_X25519_PUBLIC_KEY
#   ACCOUNT_SERVER_API_KEY         ACCOUNT_JWT_SECRET
#   ROOT_EMAIL                     CLOUDFLARE_TURNSTILE_SECRET_KEY
#   AWS_SES_REGION                 AWS_SES_FROM   AWS_SES_CONFIGURATION_SET
#   STRIPE_SECRET_KEY              STRIPE_WEBHOOK_SECRET_<SUFFIX>
#   AWS_SES_ACCESS_KEY_ID_<SUFFIX> AWS_SES_SECRET_ACCESS_KEY_<SUFFIX>
#   AWS_SES_ACCESS_KEY_ID_EU       AWS_SES_SECRET_ACCESS_KEY_EU  (ASIA borrows these)
#   OBS_OTLP_CREDENTIALS_<SUFFIX>
#   ACCOUNT_BACKUP_S3_ENDPOINT  ACCOUNT_BACKUP_S3_ACCESS_KEY_ID
#   ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY
#     The chunk-store backup plane's CREDENTIAL and base endpoint. The
#     credential is deliberately not region-suffixed: one R2 credential serves
#     every region. These select the PRESIGN MINTER path;
#     `ACCOUNT_BACKUP_R2_GRANT_PARENT_SECRET` must stay UNSET, since setting
#     it selects the locally-signed-JWT minter that live R2 refused in every
#     tested variant (docs/backup-storage/07-execution-record.md 6.1).
#   BACKUP_BUCKET_STABLE           BACKUP_BUCKET_EDGE       R2_JURISDICTION
#     The backup BUCKET, which IS per region and per channel, and the region's
#     R2 jurisdiction. Both come from regions.json via the deploy matrix, not
#     from a secret: the bucket names are public and already committed in
#     workers/account/wrangler.*.toml as the BACKUP_BUCKET binding.
#
#     This is the fix for a real defect. There used to be ONE global
#     backup-bucket secret against six per-region bindings, so in us/asia the
#     Worker's native binding read and GC'd the correct regional bucket while
#     every presigned PUT URL it minted pointed at whichever single bucket the
#     global secret named. R2_JURISDICTION exists because the EU buckets are
#     jurisdiction-locked and reachable ONLY at the jurisdictional host --
#     a correct bucket name against the default host still fails.
#   SELLER_NAME                    SELLER_VAT_NUMBER
#   SELLER_REGISTRATION_NUMBER     SELLER_ADDRESS_LINE1
#   SELLER_ADDRESS_LINE2           SELLER_CITY
#   SELLER_POSTAL_CODE             SELLER_COUNTRY   SELLER_EMAIL
#
# Run locally (WRITES to Cloudflare — point WORKER_NAME at a scratch Worker):
#   WORKER_NAME=scratch TARGET=edge SUFFIX=EU CLOUDFLARE_API_TOKEN=... \
#     .ci/scripts/deploy/set-account-worker-secrets.sh
#
# Shell options: the workflow block ran under plain `bash -e`; `-uo pipefail`
# are added here. The indirect reads keep an explicit `:-` fallback so an
# unknown SUFFIX still yields an empty value under `-u`, exactly as it did
# before. pipefail only tightens the single `jq | wrangler` pipe, where a jq
# failure previously went unnoticed because wrangler's status won.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd jq
require_cmd npx
: "${WORKER_NAME:?set-account-worker-secrets.sh: WORKER_NAME must be set}"
: "${TARGET:?set-account-worker-secrets.sh: TARGET must be set}"
: "${SUFFIX:?set-account-worker-secrets.sh: SUFFIX must be set}"

# Stripe. The KEY is account-wide (one Stripe account); only the WEBHOOK
# signing secret is per-endpoint, hence per-region.
if [[ "$TARGET" == "stable" ]]; then
    stripe_key="${STRIPE_SECRET_KEY:-}"
    wh_var="STRIPE_WEBHOOK_SECRET_${SUFFIX}"
    stripe_webhook="${!wh_var:-}"
else
    # Edge (beta channel): no Stripe -- billing disabled
    stripe_key=""
    stripe_webhook=""
fi

# SES region fan-in.
ses_key_var="AWS_SES_ACCESS_KEY_ID_${SUFFIX}"
ses_access_key_id="${!ses_key_var:-}"
ses_secret_var="AWS_SES_SECRET_ACCESS_KEY_${SUFFIX}"
ses_secret_access_key="${!ses_secret_var:-}"
# Asia uses EU SES while ap-northeast-1 production access is pending
if [[ "$SUFFIX" == "ASIA" ]]; then
    ses_access_key_id="${AWS_SES_ACCESS_KEY_ID_EU:-}"
    ses_secret_access_key="${AWS_SES_SECRET_ACCESS_KEY_EU:-}"
fi

# Observability credentials fan-in.
otlp_var="OBS_OTLP_CREDENTIALS_${SUFFIX}"
otlp_creds="${!otlp_var:-}"

# Backup plane: the bucket follows the CHANNEL, the endpoint follows the
# region's R2 JURISDICTION. Neither is a secret; see the header.
if [[ "$TARGET" == "stable" ]]; then
    backup_bucket="${BACKUP_BUCKET_STABLE:-}"
else
    backup_bucket="${BACKUP_BUCKET_EDGE:-}"
fi
# Fail loudly rather than shipping a Worker that signs against an empty bucket.
# backup-chunk-store.ts reads `env.ACCOUNT_BACKUP_S3_BUCKET ?? ''`, so an
# empty value does NOT throw there -- it mints presigned URLs against bucket ""
# and every backup upload 404s at runtime. That silent shape is exactly what the
# `required: true` block in cd-deploy-account.yml exists to prevent for the
# secrets, and the bucket needs the same treatment now that it is derived.
if [[ -z "$backup_bucket" ]]; then
    echo "set-account-worker-secrets.sh: no backup bucket for TARGET=$TARGET." >&2
    echo "  Expected BACKUP_BUCKET_STABLE / BACKUP_BUCKET_EDGE from the deploy" >&2
    echo "  matrix (regions.json backupR2/edgeBackupR2). Refusing to deploy a" >&2
    echo "  Worker that would presign against an empty bucket name." >&2
    exit 1
fi
# An EU-jurisdiction bucket lives at <account>.eu.r2.cloudflarestorage.com; the
# default host cannot see it. Insert the jurisdiction label if it is not already
# there, so a secret already carrying the jurisdictional form is left alone.
backup_endpoint="${ACCOUNT_BACKUP_S3_ENDPOINT:-}"
R2_JURISDICTION="${R2_JURISDICTION:-}"
if [[ -n "$R2_JURISDICTION" && "$backup_endpoint" == *".r2.cloudflarestorage.com"* &&
    "$backup_endpoint" != *".${R2_JURISDICTION}.r2.cloudflarestorage.com"* ]]; then
    backup_endpoint="${backup_endpoint/.r2.cloudflarestorage.com/.${R2_JURISDICTION}.r2.cloudflarestorage.com}"
fi

# ─── Non-empty guards for values zod will NOT catch ──────────────────────────
# The Worker schema (private/account/src/types/env.ts) marks these optional()
# and wraps most of them in `preprocess((v) => v === '' ? undefined : v)`, so an
# EMPTY value validates, deploys, and turns the feature off silently: email
# stops with requests still returning 200, Turnstile disables itself, telemetry
# goes dark (the exact OTLP incident that created the `required: true` block in
# cd-deploy-account.yml), backups 503. `required: true` on the GitHub side was
# the guard against that -- and a job-start fetch from Bitwarden has no such
# thing: a correct UUID pointing at an empty value injects "" without complaint
# (verified 2026-09-02). So the guard moves HERE, onto the deploy path, where
# it holds regardless of where the value came from. Same shape as the bucket
# guard above; that one is the precedent.
#
# The NAME passed to each call is the Worker key, which since the shim was
# deleted is also the variable name to go looking for in the secret store.
#
# Stripe is conditional: edge deliberately blanks it (billing disabled), so it
# is demanded only on stable. Everything else is demanded on both channels.
_require_nonempty() {
    local name="$1" value="$2"
    if [[ -z "$value" ]]; then
        echo "set-account-worker-secrets.sh: $name is EMPTY for WORKER_NAME=$WORKER_NAME TARGET=$TARGET SUFFIX=$SUFFIX." >&2
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
_require_nonempty AWS_SES_ACCESS_KEY_ID "$ses_access_key_id"
_require_nonempty AWS_SES_SECRET_ACCESS_KEY "$ses_secret_access_key"
_require_nonempty AWS_SES_REGION "${AWS_SES_REGION:-}"
_require_nonempty CLOUDFLARE_TURNSTILE_SECRET_KEY "${CLOUDFLARE_TURNSTILE_SECRET_KEY:-}"
_require_nonempty OBS_OTLP_CREDENTIALS "$otlp_creds"
_require_nonempty ACCOUNT_BACKUP_S3_ENDPOINT "$backup_endpoint"
_require_nonempty ACCOUNT_BACKUP_S3_ACCESS_KEY_ID "${ACCOUNT_BACKUP_S3_ACCESS_KEY_ID:-}"
_require_nonempty ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY "${ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY:-}"
if [[ "$TARGET" == "stable" ]]; then
    _require_nonempty STRIPE_SECRET_KEY "$stripe_key"
    _require_nonempty STRIPE_WEBHOOK_SECRET "$stripe_webhook"
fi

jq -n \
    --arg ed25519_priv "${ACCOUNT_ED25519_PRIVATE_KEY:-}" \
    --arg ed25519_pub "${ACCOUNT_ED25519_PUBLIC_KEY:-}" \
    --arg x25519_priv "${ACCOUNT_X25519_PRIVATE_KEY:-}" \
    --arg x25519_pub "${ACCOUNT_X25519_PUBLIC_KEY:-}" \
    --arg api_key "${ACCOUNT_SERVER_API_KEY:-}" \
    --arg jwt "${ACCOUNT_JWT_SECRET:-}" \
    --arg stripe "$stripe_key" \
    --arg stripe_wh "$stripe_webhook" \
    --arg admin "${ROOT_EMAIL:-}" \
    --arg ses_key "$ses_access_key_id" \
    --arg ses_secret "$ses_secret_access_key" \
    --arg ses_region "${AWS_SES_REGION:-}" \
    --arg ses_from "${AWS_SES_FROM:-}" \
    --arg ses_cs "${AWS_SES_CONFIGURATION_SET:-}" \
    --arg turnstile "${CLOUDFLARE_TURNSTILE_SECRET_KEY:-}" \
    --arg otlp_creds "$otlp_creds" \
    --arg backup_endpoint "$backup_endpoint" \
    --arg backup_bucket "$backup_bucket" \
    --arg backup_akid "${ACCOUNT_BACKUP_S3_ACCESS_KEY_ID:-}" \
    --arg backup_secret "${ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY:-}" \
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
        OBS_OTLP_CREDENTIALS: $otlp_creds,
        ACCOUNT_BACKUP_S3_ENDPOINT: $backup_endpoint,
        ACCOUNT_BACKUP_S3_BUCKET: $backup_bucket,
        ACCOUNT_BACKUP_S3_ACCESS_KEY_ID: $backup_akid,
        ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY: $backup_secret,
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
