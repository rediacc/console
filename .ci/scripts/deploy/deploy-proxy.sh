#!/bin/bash
# Deploy the executor proxy Worker + Container to Cloudflare.
#
# MANUAL ONLY. This is not wired into the release pipeline, and deliberately so:
# the executor is the component that holds customers' config keys in memory and
# is the only thing allowed to open SSH to their machines. It gets a human in the
# loop until it has run in front of real traffic.
#
# Nothing in CI runs this script. `--dry-run` builds the CLI and compiles the
# Worker with `wrangler deploy --dry-run`, which does NOT build the container
# image. The image is built and booted by check:ci-proxy-image-smoke instead.
#
# A real deploy also builds a release renet (build-renet.sh, at the current
# release version) and stages it in workers/proxy/renet/ for the image, then
# smoke-tests the live Worker: /v1/health must answer 200 and an
# unauthenticated /v1/server-info must answer 401.
#
# Usage:
#   deploy-proxy.sh --region eu
#   deploy-proxy.sh --region eu --dry-run
#
# Requires: CLOUDFLARE_API_TOKEN (scoped, NOT the global key), CLOUDFLARE_ACCOUNT_ID,
# and for a real deploy ACCOUNT_ED25519_PUBLIC_KEY (baked into renet's licence check)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd curl

parse_args "$@"

REPO_ROOT="$(get_repo_root)"
WORKER_DIR="$REPO_ROOT/workers/proxy"
REGION="${ARG_REGION:-eu}"
DRY_RUN="${ARG_DRY_RUN:-false}"

: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required (use a scoped token, never the global API key)}"

if [[ "$DRY_RUN" != "true" && -z "${ACCOUNT_ED25519_PUBLIC_KEY:-}" ]]; then
    log_error "ACCOUNT_ED25519_PUBLIC_KEY is required: the image's renet is uploaded to machines, and without the key it cannot verify a licence"
    exit 1
fi

log_step "Building the CLI bundle the container image ships..."
cd "$REPO_ROOT"
npm run build --workspace @rediacc/shared
npm run build --workspace @rediacc/cli

cd "$WORKER_DIR"

if [[ "$DRY_RUN" == "true" ]]; then
    log_step "Dry run: type-checking and compiling the worker without deploying..."
    npx wrangler deploy --dry-run --outdir /tmp/rediacc-proxy-dry-run
    log_info "Dry run passed. Nothing was deployed."
    exit 0
fi

log_step "Building the renet the container image ships..."
VERSION="$("$REPO_ROOT/.ci/scripts/version/resolve-version.sh" --current)"
"$REPO_ROOT/.ci/scripts/build/build-renet.sh" --version "$VERSION"
cp "$REPO_ROOT/private/bin/renet-linux-amd64" "$WORKER_DIR/renet/renet-linux-amd64"

log_step "Deploying the proxy worker and container image (region: $REGION)..."
npx wrangler deploy

SMOKE_URL="https://$(sed -n 's/.*pattern = "\([^"]*\)".*/\1/p' wrangler.toml | head -n 1)"
log_step "Smoke-testing $SMOKE_URL..."
HEALTH="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$SMOKE_URL/v1/health" || true)"
if [[ "$HEALTH" != "200" ]]; then
    log_error "Smoke test failed: /v1/health answered ${HEALTH:-nothing}, expected 200"
    exit 1
fi
INFO="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 30 "$SMOKE_URL/v1/server-info" || true)"
if [[ "$INFO" != "401" ]]; then
    log_error "Smoke test failed: an unauthenticated /v1/server-info answered ${INFO:-nothing}, expected 401"
    exit 1
fi
log_info "Smoke test passed: /v1/health 200, unauthenticated /v1/server-info 401."

log_info "Deployed. The executor still needs its own account token:"
log_info "  npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml"
log_info "That token must carry the proxy:exec and audit:write scopes and belong to the Rediacc org."
