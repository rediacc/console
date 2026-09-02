#!/bin/bash
# Deploy the account worker to bench.rediacc.com.
#
# bench is an internal-only "real Cloudflare D1" environment for the dev team
# to validate changes against actual D1/R2 before promoting to edge or prod.
# It is INTENTIONALLY NOT wired into ci.yml or cd-v2.yml — deploys are local
# only, triggered by you running this script.
#
# Auth (uses scripts/dev/lib/cf-auth.sh — see that file's header for details):
#   CF_GLOBAL_API_KEY + CF_EMAIL  Global API Key (recommended; auto-creates a
#                                 scoped token via cf-auth.sh)
#   CF_MANAGEMENT_TOKEN      Pre-created scoped API token (if you have one)
#   Interactive prompt       Asks for one of the above when neither is set
#   Get your Global API Key: https://dash.cloudflare.com/profile/api-tokens
#
# Note: secret rotation lives in private/account/scripts/rotation/ now,
# orchestrated by `./run.sh rotation rotate <slug>`. This script only handles
# the deploy itself, not credential lifecycle.
#
# Other prerequisites:
#   - private/account/.env populated with signing keys + AWS_SES_*
#   - jq, npx
#
# Usage:
#   ./scripts/dev/deploy-bench.sh
#
# Resources this script touches:
#   D1:     account-db-bench (uuid ac45c2de-053b-404c-bc47-9ad9cbd2bb15)
#   R2:     rediacc-configs-bench
#   Worker: rediacc-account-bench
#   Domain: https://bench.rediacc.com
#
# To wipe the bench environment, see: scripts/dev/reset-bench.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"
source "$SCRIPT_DIR/lib/cf-auth.sh"

# ─── Prereqs ───────────────────────────────────────────────────────────
require_cmd curl
require_cmd jq
require_cmd npx

[[ -f "$ROOT_DIR/private/account/.env" ]] || {
    log_error "private/account/.env not found. Run \`./run.sh account reset\` to generate one."
    exit 1
}

ACCOUNT_ID="fa51e4a18d553c30e1633288e9733d04"
WORKER_DIR="$ROOT_DIR/workers/account"
WORKER_NAME="rediacc-account-bench"
CONFIG="wrangler.bench.toml"
DB_NAME="account-db-bench"
DOMAIN="bench.rediacc.com"
# Bench has its own Turnstile widget (rediacc-console-bench) so rotations of
# the production widget don't block bench deploys. The sitekey is public (it
# ships in HTML). The secret is in .env.bench as CLOUDFLARE_TURNSTILE_SECRET_KEY, managed
# by `./run.sh rotation rotate turnstile-bench`.
TURNSTILE_SITEKEY="0x4AAAAAAC46Rczgin0T1o04"

[[ -f "$WORKER_DIR/$CONFIG" ]] || {
    log_error "$WORKER_DIR/$CONFIG missing"
    exit 1
}

# ─── Cloudflare auth ───────────────────────────────────────────────────
# resolve_cf_auth populates CF_AUTH_HEADERS and (if you started from a Global
# API Key) auto-creates CF_MANAGEMENT_TOKEN, the scoped token wrangler needs.
# We register a trap to self-destruct it on exit so we don't accumulate stale
# tokens in the CF account (every deploy creates a new one).
resolve_cf_auth
trap 'self_destruct_credentials 2>/dev/null || true' EXIT INT TERM

# wrangler reads CLOUDFLARE_API_TOKEN by preference. If we got a management
# token (the common path), use it. If the user provided their own scoped
# token via CF_MANAGEMENT_TOKEN, that's what we forward. Either way wrangler
# never sees the Global API Key directly.
if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
    export CLOUDFLARE_API_TOKEN="$CF_MANAGEMENT_TOKEN"
else
    log_error "resolve_cf_auth did not produce a management token (unexpected)"
    exit 1
fi
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"

# Unset the legacy global-key envs so wrangler only sees CLOUDFLARE_API_TOKEN
# (otherwise it warns "Using CF_API_KEY environment variable. This is
# deprecated."). CF_API_KEY is not ours: it is wrangler's OWN deprecated alias
# for the global key, so clearing it from the ambient shell is defensive
# hygiene, not a second name for CF_GLOBAL_API_KEY.
unset CF_GLOBAL_API_KEY CF_API_KEY CF_EMAIL

# Wait a moment for the freshly-created management token to propagate through
# the Cloudflare API. Without this, the very first wrangler call (D1 migrate)
# can race the token propagation and fail with "Authentication error 10000",
# even though direct curl succeeds and the token has the right policies.
# A few seconds is enough; this only runs once per deploy.
sleep 5

# ─── Step 1: build the account portal SPA ──────────────────────────────
log_step "Building account portal SPA (Turnstile sitekey: $TURNSTILE_SITEKEY)"
cd "$ROOT_DIR/private/account/web"
[[ -d node_modules ]] || npm install
VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITEKEY" \
    VITE_CI_MODE='false' \
    npx vite build --outDir "$WORKER_DIR/dist/account"
log_info "Account portal built → $WORKER_DIR/dist/account"

# ─── Step 2: install worker deps + apply migrations ────────────────────
cd "$WORKER_DIR"
[[ -d node_modules ]] || npm install

log_step "Applying D1 migrations to $DB_NAME (remote)"
npx wrangler d1 migrations apply "$DB_NAME" --remote --config "$CONFIG"
log_info "Migrations applied"

# ─── Step 3: deploy the worker ─────────────────────────────────────────
log_step "Deploying $WORKER_NAME → https://$DOMAIN"
npx wrangler deploy --config "$CONFIG"
log_info "Worker deployed"

# ─── Step 4: rotation preflight + push secrets ─────────────────────────
log_step "Loading private/account/.env (with .env.bench overrides)"

# HOISTED ABOVE THE ROTATION PREFLIGHT on 2026-09-02. It used to sit AFTER it,
# and `rotation check` needs the AWS_IAM_ADMIN_ACCESS_KEY_ID/AWS_IAM_ADMIN_SECRET_ACCESS_KEY and Cloudflare
# credentials that live in this very file. So unless the operator happened to
# have them exported already, the preflight exited 1 with "AWS IAM admin
# credentials are required" and this script reported "rotation drift detected"
# -- a verdict about credentials it had never compared.

# Source the .env in a subshell to populate the variables we care about.
# `set -a` exports everything sourced inside the block.
set +u
set -a
# shellcheck disable=SC1090,SC1091
source "$ROOT_DIR/private/account/.env"
# Layer .env.bench on top so its bench-specific keys (currently the
# dedicated AWS_SES_* for rediacc-ses-bench) override the prod values.
# This file is gitignored and managed by the rotation tool.
if [[ -f "$ROOT_DIR/private/account/.env.bench" ]]; then
    # shellcheck disable=SC1090,SC1091
    source "$ROOT_DIR/private/account/.env.bench"
    log_info "Loaded private/account/.env.bench (bench-specific overrides)"
fi
set +a
set -u

# Drift preflight: refuse to push stale credentials. The rotation tool
# compares manifest entries to live AWS/CF state and exits non-zero on
# any mismatch. Catches the failure mode where bench would ship a dead
# SES key because a rotation ran on another machine without updating
# this clone's manifest. Runs AFTER the .env load above, deliberately.
log_step "Rotation preflight: ./run.sh rotation check --for=bench"
rotation_rc=0
"$ROOT_DIR/run.sh" rotation check --for=bench || rotation_rc=$?
if ((rotation_rc != 0)); then
    # Distinguish a VERDICT from a check that never reached one. Reporting
    # "drift" for a missing credential sends you off to rotate a key that is
    # fine, which is the same shape as the assert-edge-tag-exists.sh bug.
    if [[ -z "${AWS_IAM_ADMIN_ACCESS_KEY_ID:-}${AWS_SES_ADMIN_KEY_ID:-}" ]]; then
        log_error "rotation check could NOT RUN: no AWS IAM admin credentials in the"
        log_error "environment even after loading private/account/.env. This is NOT"
        log_error "drift -- nothing was compared. Add AWS_IAM_ADMIN_ACCESS_KEY_ID + AWS_IAM_ADMIN_SECRET_ACCESS_KEY there."
    else
        log_error "rotation drift detected — refusing to push stale secrets to bench"
        log_error "fix: run \`./run.sh rotation rotate <slug>\` for the credentials that drifted"
    fi
    exit 1
fi

# Required signing keys (fail loud if .env is missing them)
: "${ACCOUNT_ED25519_PRIVATE_KEY:?missing in .env}"
: "${ACCOUNT_ED25519_PUBLIC_KEY:?missing in .env}"
: "${ACCOUNT_X25519_PRIVATE_KEY:?missing in .env}"
: "${ACCOUNT_X25519_PUBLIC_KEY:?missing in .env}"
: "${ACCOUNT_SERVER_API_KEY:?missing in .env}"
: "${ACCOUNT_JWT_SECRET:?missing in .env}"

# Bench reuses the prod EU SES creds in .env. Stripe is disabled (empty
# strings) so the worker boots without billing — same posture as edge.
STRIPE_SECRET_KEY_BENCH=""
STRIPE_WEBHOOK_SECRET_BENCH=""

# The non-empty guard the three CI builders carry, which this one lacked until
# 2026-09-02. The six ACCOUNT_* keys above fail loud through `:?`, but every key
# below reached `jq` with a bare `:-` default, so a `.env` that had been renamed
# out from under this script would push an EMPTY value and say nothing: zod
# normalises '' to undefined and validates happily, Turnstile silently disables
# itself, the backup plane returns null, and email builds a null transport.
# Bench is not production, but it is where those failures are supposed to be
# CAUGHT, and a silent bench is worse than a red one.
_require_nonempty() {
    if [[ -z "${2:-}" ]]; then
        log_error "$1 is EMPTY for bench — check private/account/.env (and .env.bench)"
        exit 1
    fi
}
_require_nonempty ROOT_EMAIL "${ROOT_EMAIL:-}"
_require_nonempty AWS_SES_ACCESS_KEY_ID "${AWS_SES_ACCESS_KEY_ID:-}"
_require_nonempty AWS_SES_SECRET_ACCESS_KEY "${AWS_SES_SECRET_ACCESS_KEY:-}"
_require_nonempty CLOUDFLARE_TURNSTILE_SECRET_KEY "${CLOUDFLARE_TURNSTILE_SECRET_KEY:-}"
_require_nonempty ACCOUNT_BACKUP_S3_ENDPOINT "${ACCOUNT_BACKUP_S3_ENDPOINT:-${CLOUDFLARE_R2_ENDPOINT:-}}"
_require_nonempty ACCOUNT_BACKUP_S3_ACCESS_KEY_ID "${ACCOUNT_BACKUP_S3_ACCESS_KEY_ID:-${CLOUDFLARE_R2_ACCESS_KEY_ID:-}}"
_require_nonempty ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY "${ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY:-${CLOUDFLARE_R2_SECRET_ACCESS_KEY:-}}"
_require_nonempty OBS_OTLP_CREDENTIALS "${OBS_OTLP_CREDENTIALS:-}"

jq -n \
    --arg ed25519_priv "$ACCOUNT_ED25519_PRIVATE_KEY" \
    --arg ed25519_pub "$ACCOUNT_ED25519_PUBLIC_KEY" \
    --arg x25519_priv "$ACCOUNT_X25519_PRIVATE_KEY" \
    --arg x25519_pub "$ACCOUNT_X25519_PUBLIC_KEY" \
    --arg api_key "$ACCOUNT_SERVER_API_KEY" \
    --arg jwt "$ACCOUNT_JWT_SECRET" \
    --arg stripe "$STRIPE_SECRET_KEY_BENCH" \
    --arg stripe_wh "$STRIPE_WEBHOOK_SECRET_BENCH" \
    --arg admin "${ROOT_EMAIL:-}" \
    --arg ses_key "${AWS_SES_ACCESS_KEY_ID:-}" \
    --arg ses_secret "${AWS_SES_SECRET_ACCESS_KEY:-}" \
    --arg ses_region "${AWS_SES_REGION:-eu-central-1}" \
    --arg ses_from "${AWS_SES_FROM:-noreply@notify.rediacc.com}" \
    --arg ses_cs "${AWS_SES_CONFIGURATION_SET:-}" \
    --arg turnstile "${CLOUDFLARE_TURNSTILE_SECRET_KEY:-}" \
    --arg backup_ep "${ACCOUNT_BACKUP_S3_ENDPOINT:-${CLOUDFLARE_R2_ENDPOINT:-}}" \
    --arg backup_bucket "${ACCOUNT_BACKUP_S3_BUCKET:-rediacc-backups-bench}" \
    --arg backup_key "${ACCOUNT_BACKUP_S3_ACCESS_KEY_ID:-${CLOUDFLARE_R2_ACCESS_KEY_ID:-}}" \
    --arg backup_secret "${ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY:-${CLOUDFLARE_R2_SECRET_ACCESS_KEY:-}}" \
    --arg otlp_creds "${OBS_OTLP_CREDENTIALS:-}" \
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
        ACCOUNT_BACKUP_S3_ENDPOINT: $backup_ep,
        ACCOUNT_BACKUP_S3_BUCKET: $backup_bucket,
        ACCOUNT_BACKUP_S3_ACCESS_KEY_ID: $backup_key,
        ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY: $backup_secret,
        OBS_OTLP_CREDENTIALS: $otlp_creds,
        SELLER_NAME: $seller_name,
        SELLER_VAT_NUMBER: $seller_vat,
        SELLER_REGISTRATION_NUMBER: $seller_reg,
        SELLER_ADDRESS_LINE1: $seller_addr1,
        SELLER_ADDRESS_LINE2: $seller_addr2,
        SELLER_CITY: $seller_city,
        SELLER_POSTAL_CODE: $seller_postal,
        SELLER_COUNTRY: $seller_country,
        SELLER_EMAIL: $seller_email
    }' |
    npx wrangler secret bulk --name "$WORKER_NAME"
log_info "Worker secrets pushed"

echo
log_info "bench is live: https://$DOMAIN"
echo "  D1:     $DB_NAME (ac45c2de-053b-404c-bc47-9ad9cbd2bb15)"
echo "  R2:     rediacc-configs-bench"
echo "  Worker: $WORKER_NAME"
echo
echo "Test it:"
echo "  RDC_BENCH=1 ./rdc.sh subscription login"
echo "  RDC_BENCH=1 ./rdc.sh repo create --name my-app -m my-server --size 2G"
