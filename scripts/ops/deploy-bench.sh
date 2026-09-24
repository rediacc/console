#!/bin/bash
# Deploy the account worker to bench.rediacc.com.
#
# bench is an internal-only "real Cloudflare D1" environment for the dev team
# to validate changes against actual D1/R2 before promoting to edge or prod.
# It is INTENTIONALLY NOT wired into ci.yml or cd-v2.yml — deploys are local
# only, triggered by you running this script.
#
# Auth (uses scripts/ops/lib/cf-auth.sh — see that file's header for details):
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
#   - the Bitwarden bootstrap token (~/.config/rediacc/bws-access-token);
#     every credential comes from the `deploy-bench` profile in
#     .ci/config/secret-supply.json, bound by `bws_env exec` below
#   - jq, npx
#
# Usage:
#   ./scripts/ops/deploy-bench.sh
#
# Resources this script touches:
#   D1:     account-db-bench (uuid ac45c2de-053b-404c-bc47-9ad9cbd2bb15)
#   R2:     rediacc-configs-bench
#   Worker: rediacc-account-bench
#   Domain: https://bench.rediacc.com
#
# To wipe the bench environment, see: scripts/ops/reset-bench.sh

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"
source "$SCRIPT_DIR/lib/cf-auth.sh"

# ─── Prereqs ───────────────────────────────────────────────────────────
require_cmd curl
require_cmd jq
require_cmd npx

# Every credential this script pushes comes from Bitwarden, bound into this
# process's environment by re-running it once under the `deploy-bench` profile
# (.ci/config/secret-supply.json `consumers`). Nothing is read from a file. The
# shell wins, so a value already exported is used as-is.
case ",${REDIACC_BWS_PROFILES:-}," in
    *,deploy-bench,*) ;;
    *)
        PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci.core.bws_env \
            exec --profile deploy-bench -- "$SCRIPT_DIR/$(basename "${BASH_SOURCE[0]}")" "$@"
        ;;
esac

ACCOUNT_ID="fa51e4a18d553c30e1633288e9733d04"
WORKER_DIR="$ROOT_DIR/workers/account"
WORKER_NAME="rediacc-account-bench"
CONFIG="wrangler.bench.toml"
DB_NAME="account-db-bench"
DOMAIN="bench.rediacc.com"
# Bench has its own Turnstile widget (rediacc-console-bench) so rotations of
# the production widget don't block bench deploys. The sitekey is public (it
# ships in HTML). The secret is the store entry CLOUDFLARE_TURNSTILE_SECRET_KEY_BENCH,
# bound as CLOUDFLARE_TURNSTILE_SECRET_KEY by the deploy-bench profile.
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

# ─── Step 0: preflight, before the first remote write ─────────────────
bench_preflight() { PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" python3 -m rediacc_ci.ops.bench_preflight "$@"; }
log_step "Preflight: installed dependencies match the lockfiles"
bench_preflight lockfile "$ROOT_DIR" "$ROOT_DIR/private/account" || exit 1
log_step "Preflight: every R2 bucket bound in $CONFIG exists"
(cd "$WORKER_DIR" && bench_preflight buckets "$CONFIG") || exit 1

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
# THE CREDENTIALS ARE ALREADY IN THE ENVIRONMENT, bound by the re-exec at the top
# under the deploy-bench profile, BEFORE the rotation preflight below: `rotation
# check` needs the AWS IAM admin and Cloudflare credentials that profile carries.
# The bench-specific AWS_SES_* and Turnstile secrets are the store's *_BENCH
# entries bound under the unsuffixed names, so bench can never ship the
# production values by a load-order mistake.
# Drift preflight: refuse to push stale credentials. The rotation tool
# compares manifest entries to live AWS/CF state and exits non-zero on
# any mismatch. Catches the failure mode where bench would ship a dead
# SES key because a rotation ran on another machine without updating
# this clone's manifest. Runs AFTER the profile binding above, deliberately.
log_step "Rotation preflight: ./run.sh rotation check --for=bench"
rotation_rc=0
"$ROOT_DIR/run.sh" rotation check --for=bench || rotation_rc=$?
if ((rotation_rc != 0)); then
    # Distinguish a VERDICT from a check that never reached one. Reporting
    # "drift" for a missing credential sends you off to rotate a key that is
    # fine, which is the same shape as the assert-edge-tag-exists.sh bug.
    if [[ -z "${AWS_IAM_ADMIN_ACCESS_KEY_ID:-}${AWS_SES_ADMIN_KEY_ID:-}" ]]; then
        log_error "rotation check could NOT RUN: no AWS IAM admin credentials in the"
        log_error "environment even after the deploy-bench profile. This is NOT drift --"
        log_error "nothing was compared. Check AWS_IAM_ADMIN_ACCESS_KEY_ID in Bitwarden (ci-shared)."
    else
        log_error "rotation drift detected — refusing to push stale secrets to bench"
        log_error "fix: run \`./run.sh rotation rotate <slug>\` for the credentials that drifted"
    fi
    exit 1
fi

# Required signing keys (bench signs with the DEV keypair, ACCOUNT_*_DEV)
: "${ACCOUNT_ED25519_PRIVATE_KEY:?missing from the deploy-bench profile}"
: "${ACCOUNT_ED25519_PUBLIC_KEY:?missing from the deploy-bench profile}"
: "${ACCOUNT_X25519_PRIVATE_KEY:?missing from the deploy-bench profile}"
: "${ACCOUNT_X25519_PUBLIC_KEY:?missing from the deploy-bench profile}"
: "${ACCOUNT_SERVER_API_KEY:?missing from the deploy-bench profile}"
: "${ACCOUNT_JWT_SECRET:?missing from the deploy-bench profile}"

# Stripe is disabled (empty strings) so the worker boots without billing —
# same posture as edge.
STRIPE_SECRET_KEY_BENCH=""
STRIPE_WEBHOOK_SECRET_BENCH=""

# The non-empty guard the three CI builders carry, which this one lacked until
# 2026-09-02. The six ACCOUNT_* keys above fail loud through `:?`, but every key
# below reached `jq` with a bare `:-` default, so a source that had been renamed
# out from under this script would push an EMPTY value and say nothing: zod
# normalises '' to undefined and validates happily, Turnstile silently disables
# itself, the backup plane returns null, and email builds a null transport.
# Bench is not production, but it is where those failures are supposed to be
# CAUGHT, and a silent bench is worse than a red one.
_require_nonempty() {
    if [[ -z "${2:-}" ]]; then
        log_error "$1 is EMPTY for bench — check its entry in Bitwarden (deploy-bench profile, .ci/config/secret-supply.json)"
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
# The bench collector credential is the store entry OBS_OTLP_CREDENTIALS_BENCH,
# bound under this name by the deploy-bench profile.
_require_nonempty OBS_OTLP_CREDENTIALS "${OBS_OTLP_CREDENTIALS:-}"
# The one value the Worker JSON.parses (private/account/src/routes/telemetry.ts):
# anything but {"user": string, "pass": string} serves {otlp: null}, as silently
# as an empty value. Same probe as .ci/scripts/deploy/set-account-worker-secrets.sh;
# stderr is discarded because jq's parse error quotes the (secret) input.
if ! jq -e -n --arg v "${OBS_OTLP_CREDENTIALS}" \
    '$v | fromjson | type == "object" and (.user | type) == "string" and (.pass | type) == "string"' \
    >/dev/null 2>&1; then
    log_error "OBS_OTLP_CREDENTIALS is not a JSON {\"user\",\"pass\"} object for bench — re-mint it with ./run.sh rotation rotate otlp-bench"
    exit 1
fi

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
# `--config bench`, NOT `RDC_BENCH=1`: the wrapper stopped reading that variable and this
# advice had outlived it. Printing a command the tool ignores is worse than printing none,
# because it fails as a no-op that looks like it worked.
echo "  ./rdc.sh --config bench subscription login"
echo "  ./rdc.sh --config bench repo create --name my-app -m my-server --size 2G"
