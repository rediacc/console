#!/bin/bash
# Run license-server CI if available
#
# Usage: .ci/scripts/private/run-license-server.sh [stage]
#   Stages: quality, test, deploy (default: quality)
#
# This is a thin wrapper that checks if the license-server directory exists
# and runs the appropriate npm scripts. Format and lint checks are handled
# by the root biome.json configuration.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

STAGE="${1:-quality}"
REPO_ROOT="$(get_repo_root)"
LICENSE_SERVER_DIR="$REPO_ROOT/private/license-server"

# Check if license-server directory is available
if [[ ! -f "$LICENSE_SERVER_DIR/package.json" ]]; then
    log_warn "License server not available, skipping"
    exit 0
fi

cd "$LICENSE_SERVER_DIR"

case "$STAGE" in
    quality)
        log_step "Running license-server quality checks..."
        # Install deps if not already installed
        if [[ ! -d "node_modules" ]]; then
            npm ci
        fi
        npm run typecheck
        npm run test
        ;;
    test)
        log_step "Running license-server tests..."
        # Install deps if not already installed
        if [[ ! -d "node_modules" ]]; then
            npm ci
        fi
        npm run test
        ;;
    deploy)
        log_step "Deploying license-server to Cloudflare..."
        # Install deps if not already installed
        if [[ ! -d "node_modules" ]]; then
            npm ci
        fi
        npx wrangler deploy
        ;;
    *)
        log_error "Unknown stage: $STAGE"
        exit 1
        ;;
esac
