#!/bin/bash
# Run Account Portal E2E tests with Playwright
#
# Starts infrastructure (RustFS + backend API), installs Playwright browsers,
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
    if [[ "$SKIP_SETUP" != "true" ]]; then
        log_info "Stopping RustFS..."
        cd "$ACCOUNT_DIR" && npm run test:teardown 2>/dev/null || true
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
    log_step "Starting RustFS (S3-compatible storage)..."
    cd "$ACCOUNT_DIR"
    if ! timeout 120 npm run test:setup; then
        log_error "RustFS failed to start within 120 seconds"
        exit 1
    fi
    cd "$REPO_ROOT"

    log_step "Creating S3 bucket 'e2e-account'..."
    cd "$ACCOUNT_DIR"
    node --input-type=module -e "
import { S3Client, CreateBucketCommand, HeadBucketCommand } from '@aws-sdk/client-s3';
const s3 = new S3Client({
  endpoint: 'http://localhost:9100', region: 'us-east-1', forcePathStyle: true,
  credentials: { accessKeyId: 'testadmin', secretAccessKey: 'testadmin' }
});
try { await s3.send(new HeadBucketCommand({ Bucket: 'e2e-account' })); }
catch { await s3.send(new CreateBucketCommand({ Bucket: 'e2e-account' })); }
console.log('Bucket e2e-account ready');
"
    cd "$REPO_ROOT"

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
            ((LISTEN_ELAPSED++))
        done

        if [[ -n "$STRIPE_LISTEN_WEBHOOK_SECRET" ]]; then
            log_info "stripe listen ready (webhook secret captured)"
        else
            log_warn "stripe listen did not output secret within ${LISTEN_TIMEOUT}s, Stripe e2e tests will be skipped"
            kill "$STRIPE_LISTEN_PID" 2>/dev/null || true
            STRIPE_LISTEN_PID=""
        fi
    fi

    log_step "Starting backend API on port $ACCOUNT_API_PORT..."
    cd "$ACCOUNT_DIR"
    ED25519_PRIVATE_KEY="${ED25519_PRIVATE_KEY:?ED25519_PRIVATE_KEY must be set}" \
        ED25519_PUBLIC_KEY="${ED25519_PUBLIC_KEY:?ED25519_PUBLIC_KEY must be set}" \
        API_KEY="${API_KEY:?API_KEY must be set}" \
        JWT_SECRET="${JWT_SECRET:?JWT_SECRET must be set}" \
        ADMIN_EMAIL="${ADMIN_EMAIL:?ADMIN_EMAIL must be set}" \
        S3_ENDPOINT="http://localhost:9100" \
        S3_BUCKET="e2e-account" \
        S3_ACCESS_KEY_ID="testadmin" \
        S3_SECRET_ACCESS_KEY="testadmin" \
        STRIPE_WEBHOOK_SECRET="${STRIPE_LISTEN_WEBHOOK_SECRET:-}" \
        STRIPE_SANDBOX_WEBHOOK_SECRET="${STRIPE_SANDBOX_WEBHOOK_SECRET:-}" \
        STRIPE_SANDBOX_SECRET_KEY="${STRIPE_SANDBOX_SECRET_KEY:-}" \
        PORT="$ACCOUNT_API_PORT" \
        npx tsx src/entry/node.ts &
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

if VITE_API_URL="http://localhost:${ACCOUNT_API_PORT}" "${CMD[@]}"; then
    log_info "Account Portal E2E tests passed"
else
    log_error "Account Portal E2E tests failed"
    exit 1
fi
