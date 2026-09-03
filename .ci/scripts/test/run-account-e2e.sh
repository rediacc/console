#!/bin/bash
# Run Account Portal E2E tests with Playwright
#
# Starts infrastructure (backend API with SQLite), installs Playwright browsers,
# runs E2E tests, and cleans up. Portable across CI platforms.
#
# Usage: run-account-e2e.sh [options]
#
# Options:
#   --projects    Space-separated browser projects (default: "chromium")
#   --grep        Filter tests by tag (e.g., "@auth", "@admin", "@portal")
#   --skip-setup  Skip infrastructure startup (use when already running)
#   --workers     Playwright worker count (default: 1)
#
# Examples:
#   .ci/scripts/test/run-account-e2e.sh
#   .ci/scripts/test/run-account-e2e.sh --projects "chromium firefox"
#   .ci/scripts/test/run-account-e2e.sh --grep @auth
#   .ci/scripts/test/run-account-e2e.sh --skip-setup
#
# Environment variables:
#   ACCOUNT_API_PORT   Backend API port (default: 3001)
#   E2E_PORT           Vite dev server port (default: 5173)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

PROJECTS="${ARG_PROJECTS:-chromium}"
GREP="${ARG_GREP:-}"
SKIP_SETUP="${ARG_SKIP_SETUP:-false}"
WORKERS="${ARG_WORKERS:-1}"
ACCOUNT_API_PORT="${ACCOUNT_API_PORT:-3001}"
E2E_PORT="${E2E_PORT:-5173}"

REPO_ROOT="$(get_repo_root)"
ACCOUNT_DIR="$REPO_ROOT/private/account"
E2E_DIR="$ACCOUNT_DIR/e2e"

# Check if account submodule is available
if [[ ! -f "$ACCOUNT_DIR/package.json" ]]; then
    log_warn "Account submodule not available, skipping E2E tests"
    exit 0
fi

if [[ ! -d "$E2E_DIR" ]]; then
    log_warn "Account E2E directory not found, skipping"
    exit 0
fi

# Track background processes for cleanup
BACKEND_PID=""
STRIPE_LISTEN_PID=""

cleanup() {
    log_step "Cleaning up..."
    if [[ -n "$STRIPE_LISTEN_PID" ]] && kill -0 "$STRIPE_LISTEN_PID" 2>/dev/null; then
        log_info "Stopping stripe listen (PID $STRIPE_LISTEN_PID)"
        kill "$STRIPE_LISTEN_PID" 2>/dev/null || true
        wait "$STRIPE_LISTEN_PID" 2>/dev/null || true
    fi
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        log_info "Stopping backend API (PID $BACKEND_PID)"
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
    fi
    if [[ "$SKIP_SETUP" != "true" ]] && [[ -f "$ACCOUNT_DIR/e2e-account.db" ]]; then
        log_info "Removing E2E database..."
        rm -f "$ACCOUNT_DIR/e2e-account.db" "$ACCOUNT_DIR/e2e-account.db-wal" "$ACCOUNT_DIR/e2e-account.db-shm" 2>/dev/null || true
    fi
    log_info "Cleanup complete"
}
trap cleanup EXIT

cd "$REPO_ROOT"

# Phase 1: Install dependencies
log_step "Installing account dependencies..."
if [[ ! -d "$ACCOUNT_DIR/node_modules" ]]; then
    cd "$ACCOUNT_DIR" && npm ci
    cd "$REPO_ROOT"
fi
if [[ ! -d "$ACCOUNT_DIR/web/node_modules" ]]; then
    cd "$ACCOUNT_DIR/web" && npm ci
    cd "$REPO_ROOT"
fi
if [[ ! -d "$E2E_DIR/node_modules" ]]; then
    cd "$E2E_DIR" && npm ci
    cd "$REPO_ROOT"
fi

# Phase 2: Start infrastructure (unless --skip-setup)
if [[ "$SKIP_SETUP" != "true" ]]; then
    # Phase 2.5: Start stripe listen for real Stripe e2e tests (optional)
    STRIPE_LISTEN_WEBHOOK_SECRET=""
    if [[ -n "${STRIPE_SANDBOX_SECRET_KEY:-}" ]] && command -v stripe &>/dev/null; then
        log_step "Syncing Stripe products/prices to sandbox..."
        cd "$ACCOUNT_DIR"
        STRIPE_SECRET_KEY="$STRIPE_SANDBOX_SECRET_KEY" npx tsx scripts/stripe-sync.ts 2>&1 || true
        cd "$REPO_ROOT"

        log_step "Starting stripe listen for real Stripe webhook forwarding..."
        STRIPE_LISTEN_LOG=$(mktemp)
        stripe listen \
            --api-key "$STRIPE_SANDBOX_SECRET_KEY" \
            --forward-to "http://localhost:${ACCOUNT_API_PORT}/account/api/v1/webhooks/stripe" \
            >"$STRIPE_LISTEN_LOG" 2>&1 &
        STRIPE_LISTEN_PID=$!

        LISTEN_TIMEOUT=30
        LISTEN_ELAPSED=0
        while [[ $LISTEN_ELAPSED -lt $LISTEN_TIMEOUT ]]; do
            if STRIPE_LISTEN_WEBHOOK_SECRET=$(grep -oP 'whsec_\S+' "$STRIPE_LISTEN_LOG" 2>/dev/null); then
                break
            fi
            sleep 1
            LISTEN_ELAPSED=$((LISTEN_ELAPSED + 1))
        done

        if [[ -n "$STRIPE_LISTEN_WEBHOOK_SECRET" ]]; then
            log_info "stripe listen ready (webhook secret captured)"
        else
            log_warn "stripe listen did not output secret within ${LISTEN_TIMEOUT}s, Stripe e2e tests will be skipped"
            kill "$STRIPE_LISTEN_PID" 2>/dev/null || true
            STRIPE_LISTEN_PID=""
        fi
    fi

    # Generate X25519 keys if not provided (CI uses throwaway keys)
    if [[ -z "${ACCOUNT_X25519_PRIVATE_KEY:-}" ]]; then
        X25519_KEYS=$(node -e "
            const crypto = require('crypto');
            const { privateKey, publicKey } = crypto.generateKeyPairSync('x25519');
            console.log(JSON.stringify({
                private: privateKey.export({type:'pkcs8',format:'der'}).toString('base64'),
                public: publicKey.export({type:'spki',format:'der'}).toString('base64')
            }));
        ")
        ACCOUNT_X25519_PRIVATE_KEY=$(echo "$X25519_KEYS" | jq -r '.private')
        ACCOUNT_X25519_PUBLIC_KEY=$(echo "$X25519_KEYS" | jq -r '.public')
    fi

    log_step "Starting backend API on port $ACCOUNT_API_PORT..."
    cd "$ACCOUNT_DIR"
    ACCOUNT_ENV=(
        "ACCOUNT_ED25519_PRIVATE_KEY=${ACCOUNT_ED25519_PRIVATE_KEY:?ACCOUNT_ED25519_PRIVATE_KEY must be set}"
        "ACCOUNT_ED25519_PUBLIC_KEY=${ACCOUNT_ED25519_PUBLIC_KEY:?ACCOUNT_ED25519_PUBLIC_KEY must be set}"
        "ACCOUNT_X25519_PRIVATE_KEY=${ACCOUNT_X25519_PRIVATE_KEY}"
        "ACCOUNT_X25519_PUBLIC_KEY=${ACCOUNT_X25519_PUBLIC_KEY}"
        "ACCOUNT_SERVER_API_KEY=${ACCOUNT_SERVER_API_KEY:?ACCOUNT_SERVER_API_KEY must be set}"
        "ACCOUNT_JWT_SECRET=${ACCOUNT_JWT_SECRET:?ACCOUNT_JWT_SECRET must be set}"
        "ROOT_EMAIL=${ROOT_EMAIL:?ROOT_EMAIL must be set}"
        "DATABASE_PATH=e2e-account.db"
        "PUBLIC_SITE_URL=http://localhost:$E2E_PORT"
        # WebAuthn/passkey ceremonies (20-03/20-08/27-console): the server's
        # setup-requirements report includes webauthnConfigured, and the
        # config-setup Continue button stays disabled without it. The origin
        # must equal the BROWSER origin (the Vite e2e port) or the ceremony's
        # origin check fails. Mirrors the dev .env (RP_ID localhost).
        "WEBAUTHN_RP_ID=localhost"
        "WEBAUTHN_RP_NAME=Rediacc"
        "WEBAUTHN_ORIGIN=http://localhost:$E2E_PORT"
        "PORT=$ACCOUNT_API_PORT"
        # E2E runs node.ts with ENVIRONMENT=production (for billing coverage), so
        # TEST_MODE is the only opener for the /test/* seed + email-capture routes
        # the Playwright suite depends on. Deployed Workers never set this.
        "TEST_MODE=true"
    )
    if [[ -n "${STRIPE_LISTEN_WEBHOOK_SECRET:-}" ]]; then
        ACCOUNT_ENV+=("STRIPE_WEBHOOK_SECRET=$STRIPE_LISTEN_WEBHOOK_SECRET")
    fi
    # The server verifies against the same fixture the signer above uses. It is passed
    # as STRIPE_SANDBOX_WEBHOOK_SECRET because that is the env var app.ts:530 reads into
    # envConfig.sandboxWebhookSecret; the NAME is a runtime slot, the VALUE is a fixture.
    ACCOUNT_ENV+=("STRIPE_SANDBOX_WEBHOOK_SECRET=${STRIPE_E2E_WEBHOOK_SECRET:-whsec_e2e_test_webhook_secret_for_simulation_only}")
    if [[ -n "${STRIPE_SANDBOX_SECRET_KEY:-}" ]]; then
        ACCOUNT_ENV+=("STRIPE_SANDBOX_SECRET_KEY=$STRIPE_SANDBOX_SECRET_KEY")
    fi
    env "${ACCOUNT_ENV[@]}" npx tsx src/entry/node.ts &
    BACKEND_PID=$!
    cd "$REPO_ROOT"

    # Brief pause then verify process didn't crash immediately
    sleep 2
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        log_error "Backend API process exited immediately (PID $BACKEND_PID)"
        exit 1
    fi

    log_step "Waiting for backend API..."
    if ! retry_with_backoff 6 2 curl -sf --max-time 5 "http://localhost:${ACCOUNT_API_PORT}/health" >/dev/null; then
        log_error "Backend API failed to start on port $ACCOUNT_API_PORT"
        exit 1
    fi
    log_info "Backend API is healthy"
fi

# Phase 3: Install Playwright browsers
log_step "Installing Playwright browsers: $PROJECTS"
cd "$E2E_DIR"
IFS=' ' read -ra PROJECT_ARR <<<"$PROJECTS"
for browser in "${PROJECT_ARR[@]}"; do
    npx playwright install "$browser"
    if is_ci; then
        npx playwright install-deps "$browser" 2>/dev/null || true
    fi
done

# Phase 4: Run E2E tests
log_step "Running Account Portal E2E tests..."

CMD=(npx playwright test)
for project in "${PROJECT_ARR[@]}"; do
    CMD+=("--project=$project")
done
CMD+=("--workers=$WORKERS" "--timeout=60000")
if [[ -n "$GREP" ]]; then
    CMD+=("--grep" "$GREP")
fi

# THE SIGNER USES THE FIXTURE, not a stored credential, and the distinction is the
# whole point. These tests SIGN a simulated webhook and the server VERIFIES it, so both
# sides need the same string and nothing talks to Stripe. Feeding them a real secret made
# the pair self-consistent and therefore untestable: a STRIPE_SANDBOX_WEBHOOK_SECRET that
# expired 24 hours after it was minted passed exactly as well as a fresh one, which is why
# green runs here were never evidence that the stored value was current.
#
# STRIPE_E2E_WEBHOOK_SECRET is the fixture built for this (.ci/lib/account.sh:240,298),
# and .ci/lib/account.sh:828 already wires the local path to it. This line was the one
# place that disagreed.
if VITE_API_URL="http://localhost:${ACCOUNT_API_PORT}" \
    E2E_WEBHOOK_SECRET="${STRIPE_E2E_WEBHOOK_SECRET:-whsec_e2e_test_webhook_secret_for_simulation_only}" \
    "${CMD[@]}"; then
    log_info "Account Portal E2E tests passed"
else
    log_error "Account Portal E2E tests failed"
    exit 1
fi
