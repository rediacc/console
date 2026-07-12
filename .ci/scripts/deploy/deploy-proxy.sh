#!/bin/bash
# Deploy the executor proxy Worker + Container to Cloudflare.
#
# MANUAL ONLY. This is not wired into the release pipeline, and deliberately so:
# the executor is the component that holds customers' config keys in memory and
# is the only thing allowed to open SSH to their machines. It gets a human in the
# loop until it has run in front of real traffic.
#
# CI runs the dry-run path instead (build + `wrangler deploy --dry-run` + a
# docker build), which catches everything except the deploy itself.
#
# Usage:
#   deploy-proxy.sh --region eu
#   deploy-proxy.sh --region eu --dry-run
#
# Requires: CLOUDFLARE_API_TOKEN (scoped, NOT the global key), CLOUDFLARE_ACCOUNT_ID

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

REPO_ROOT="$(get_repo_root)"
WORKER_DIR="$REPO_ROOT/workers/proxy"
REGION="${ARG_REGION:-eu}"
DRY_RUN="${ARG_DRY_RUN:-false}"

: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required (use a scoped token, never the global API key)}"

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

log_step "Deploying the proxy worker and container image (region: $REGION)..."
npx wrangler deploy

log_info "Deployed. The executor still needs its own account token:"
log_info "  npx wrangler secret put EXECUTOR_TOKEN --config workers/proxy/wrangler.toml"
log_info "That token must carry the proxy:exec scope and belong to the Rediacc org."
