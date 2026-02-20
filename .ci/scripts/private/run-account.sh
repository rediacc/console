#!/bin/bash
# Run account CI if available
#
# Usage: .ci/scripts/private/run-account.sh [stage]
#   Stages: quality, test, deploy (default: quality)
#
# This is a thin wrapper that checks if the account directory exists
# and runs the appropriate npm scripts. Lint, format, and typecheck are
# handled by root-level quality commands (check:lint, check:format,
# check:types).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STAGE="${1:-quality}"
REPO_ROOT="$(get_repo_root)"
ACCOUNT_DIR="$REPO_ROOT/private/account"

# Check if account directory is available
if [[ ! -f "$ACCOUNT_DIR/package.json" ]]; then
    log_warn "Account server not available, skipping"
    exit 0
fi

cd "$ACCOUNT_DIR"

# Install deps if not already installed (e.g. by install-deps.sh)
if [[ ! -d "node_modules" ]]; then
    npm ci
fi

case "$STAGE" in
    quality | test)
        log_step "Running account tests..."
        npm run test
        ;;
    deploy)
        log_step "Deploying account to Cloudflare..."
        npx wrangler deploy
        ;;
    *)
        log_error "Unknown stage: $STAGE"
        exit 1
        ;;
esac
