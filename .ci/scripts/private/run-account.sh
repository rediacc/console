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

# A missing submodule must not read as "tests passed". `check:ci-account-server`
# is a gate in ci-quality.yml, and a silent exit 0 there means the account suite
# never ran while the job reported green.
if [[ ! -f "$ACCOUNT_DIR/package.json" ]]; then
    if [[ "${CI:-}" == "true" ]]; then
        log_error "Account server not available at $ACCOUNT_DIR (submodule not checked out)."
        log_error "CI=true: failing rather than reporting success for tests that never ran."
        log_error "Check out the submodule, or drop this gate from the job that needs it."
        exit 1
    fi
    log_warn "Account server not available at $ACCOUNT_DIR, skipping."
    log_warn "CI is not 'true', so absence is a soft skip here; in CI it is a hard failure."
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
        # This stage used to run `npx wrangler deploy` from private/account with
        # no --config, which picks up that directory's root wrangler.toml. That
        # file is local-dev only: its worker name and D1 id are live nowhere, so
        # the deploy would have published an orphan worker. Nothing invokes this
        # stage, so refusing breaks no caller.
        log_error "This stage cannot deploy the account server."
        log_error "Production and edge are the seven configs under workers/account/:"
        log_error "  wrangler.{eu,us,asia}.toml, wrangler.edge-{eu,us,asia}.toml, wrangler.bench.toml"
        log_error "Deploy through the script that resolves them:"
        log_error "  .ci/scripts/deploy/deploy-account.sh --region <eu|us|asia> [--target edge]"
        exit 1
        ;;
    *)
        log_error "Unknown stage: $STAGE"
        exit 1
        ;;
esac
