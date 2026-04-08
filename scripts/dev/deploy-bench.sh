#!/bin/bash
# Deploy the account worker to bench.rediacc.com.
#
# bench is an internal-only "real Cloudflare D1" environment for the dev team
# to validate changes against actual D1/R2 before promoting to edge or prod.
# It is INTENTIONALLY NOT wired into ci.yml or cd-v2.yml — deploys are local
# only, triggered by you running this script.
#
# Auth (uses scripts/dev/lib/cf-auth.sh — see that file's header for details):
#   CF_API_KEY + CF_EMAIL    Global API Key (recommended; auto-creates a
#                            scoped token via cf-auth.sh)
#   CF_MANAGEMENT_TOKEN      Pre-created scoped API token (if you have one)
#   Interactive prompt       Asks for one of the above when neither is set
#   Get your Global API Key: https://dash.cloudflare.com/profile/api-tokens
#
# Note: secret rotation lives in private/account/scripts/rotation/ now,
# orchestrated by `./run.sh rotation rotate <slug>`. This script only handles
# the deploy itself, not credential lifecycle.
#
# Other prerequisites:
#   - private/account/.env populated with signing keys + AWS_SES_* (the SES
#     creds in .env are reused as-is — bench shares the prod EU SES sender so
#     test emails actually go out)
#   - jq, npx
#
# Usage:
#   ./scripts/dev/deploy-bench.sh                    # full deploy
#   ./scripts/dev/deploy-bench.sh --skip-build       # skip SPA rebuild
#   ./scripts/dev/deploy-bench.sh --skip-secrets     # skip secret push
#   ./scripts/dev/deploy-bench.sh --code-only        # = --skip-build --skip-secrets
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

# ─── Argument parsing ──────────────────────────────────────────────────
SKIP_BUILD=false
SKIP_SECRETS=false
for arg in "$@"; do
    case "$arg" in
        --skip-build) SKIP_BUILD=true ;;
        --skip-secrets) SKIP_SECRETS=true ;;
        --code-only)
            SKIP_BUILD=true
            SKIP_SECRETS=true
            ;;
        -h | --help)
            grep '^# ' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            log_error "Unknown argument: $arg"
            log_error "Run with --help for usage."
            exit 2
            ;;
    esac
done

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
# Bench is part of the production Turnstile widget's allowed-domains list
# (rediacc-console, sitekey below). The secret is the same as prod and is
# already in private/account/.env as TURNSTILE_SECRET_KEY — no separate widget
# to manage. The sitekey is public (it ships in HTML) so it's safe to bake in.
# If the prod widget is rotated via `./run.sh rotation rotate turnstile`, the
# rotation tool pushes the new secret to the bench worker as a consumer; the
# sitekey itself never changes on rotation, only the secret.
TURNSTILE_SITEKEY="0x4AAAAAACmA163lgukBNfsB"

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
# deprecated.").
unset CF_API_KEY CF_EMAIL

# Wait a moment for the freshly-created management token to propagate through
# the Cloudflare API. Without this, the very first wrangler call (D1 migrate)
# can race the token propagation and fail with "Authentication error 10000",
# even though direct curl succeeds and the token has the right policies.
# A few seconds is enough; this only runs once per deploy.
sleep 5

# ─── Step 1: build the account portal SPA ──────────────────────────────
if [[ "$SKIP_BUILD" == "false" ]]; then
    log_step "Building account portal SPA (Turnstile sitekey: $TURNSTILE_SITEKEY)"
    cd "$ROOT_DIR/private/account/web"
    [[ -d node_modules ]] || npm install
    # The sitekey must be baked into the bundle at build time — vite inlines
    # import.meta.env.VITE_* values during the build. Without this, the
    # frontend renders the Turnstile widget with an empty sitekey, no token
    # is produced, and the server rejects the request with "Captcha
    # verification required".
    VITE_TURNSTILE_SITE_KEY="$TURNSTILE_SITEKEY" \
        VITE_CI_MODE='false' \
        npx vite build --outDir "$WORKER_DIR/dist/account"
    log_info "Account portal built → $WORKER_DIR/dist/account"
else
    log_step "Skipping SPA build (--skip-build)"
    [[ -d "$WORKER_DIR/dist/account" ]] || {
        log_error "dist/account is missing — run without --skip-build first"
        exit 1
    }
fi

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

# ─── Step 4: push secrets (sourced from private/account/.env + .env.bench) ──
if [[ "$SKIP_SECRETS" == "true" ]]; then
    log_step "Skipping secret push (--skip-secrets)"
else
    # Drift preflight: refuse to push stale credentials. The rotation tool
    # compares manifest entries to live AWS/CF state and exits non-zero on
    # any mismatch. Catches the failure mode where bench would ship a dead
    # SES key because a rotation ran on another machine without updating
    # this clone's manifest.
    log_step "Rotation preflight: ./run.sh rotation check --for=bench"
    if ! "$ROOT_DIR/run.sh" rotation check --for=bench; then
        log_error "rotation drift detected — refusing to push stale secrets to bench"
        log_error "fix: run \`./run.sh rotation rotate <slug>\` for the credentials that drifted"
        exit 1
    fi

    log_step "Pushing worker secrets from private/account/.env (with .env.bench overrides)"

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

    # Required signing keys (fail loud if .env is missing them)
    : "${ED25519_PRIVATE_KEY:?missing in .env}"
    : "${ED25519_PUBLIC_KEY:?missing in .env}"
    : "${X25519_PRIVATE_KEY:?missing in .env}"
    : "${X25519_PUBLIC_KEY:?missing in .env}"
    : "${API_KEY:?missing in .env}"
    : "${JWT_SECRET:?missing in .env}"

    # Bench reuses the prod EU SES creds in .env. Stripe is disabled (empty
    # strings) so the worker boots without billing — same posture as edge.
    SECRET_STRIPE_KEY=""
    SECRET_STRIPE_WEBHOOK=""

    jq -n \
        --arg ed25519_priv "$ED25519_PRIVATE_KEY" \
        --arg ed25519_pub "$ED25519_PUBLIC_KEY" \
        --arg x25519_priv "$X25519_PRIVATE_KEY" \
        --arg x25519_pub "$X25519_PUBLIC_KEY" \
        --arg api_key "$API_KEY" \
        --arg jwt "$JWT_SECRET" \
        --arg stripe "$SECRET_STRIPE_KEY" \
        --arg stripe_wh "$SECRET_STRIPE_WEBHOOK" \
        --arg admin "${ROOT_EMAIL:-}" \
        --arg ses_key "${AWS_SES_ACCESS_KEY_ID:-}" \
        --arg ses_secret "${AWS_SES_SECRET_ACCESS_KEY:-}" \
        --arg ses_region "${AWS_SES_REGION:-eu-central-1}" \
        --arg ses_from "${AWS_SES_FROM:-noreply@notify.rediacc.com}" \
        --arg turnstile "${TURNSTILE_SECRET_KEY:-}" \
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
        }' |
        npx wrangler secret bulk --name "$WORKER_NAME"
    log_info "Worker secrets pushed"
fi

echo
log_info "bench is live: https://$DOMAIN"
echo "  D1:     $DB_NAME (ac45c2de-053b-404c-bc47-9ad9cbd2bb15)"
echo "  R2:     rediacc-configs-bench"
echo "  Worker: $WORKER_NAME"
echo
echo "Test it:"
echo "  RDC_BENCH=1 ./rdc.sh subscription login"
echo "  RDC_BENCH=1 ./rdc.sh repo create --name my-app -m my-server --size 2G"
