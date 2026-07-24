#!/bin/bash
# Install npm dependencies with platform-specific handling
# Usage: install-deps.sh [--ignore-scripts]
#
# On Windows, --ignore-scripts is added automatically to avoid native module
# rebuild issues (ssh2 / cpu-features / esbuild). Note the repo .npmrc now sets
# ignore-scripts=true globally, so this flag is belt-and-braces rather than the
# only thing blocking lifecycle scripts.
#
# IMPORTANT: The lockfile (package-lock.json) must contain resolved entries
# for ALL platform-specific optional deps (rollup, lightningcss, esbuild).
# Never regenerate the lockfile by deleting it on a single platform — this
# drops entries for other platforms. Instead, use `npm install <pkg>` to
# update individual packages while preserving cross-platform entries.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
IGNORE_SCRIPTS=false
WANT_ROOT=true
WANT_ACCOUNT=true
for arg in "$@"; do
    case "$arg" in
        --ignore-scripts) IGNORE_SCRIPTS=true ;;
        --skip-account) WANT_ACCOUNT=false ;;
        --account-only) WANT_ROOT=false ;;
    esac
done

# Change to repo root
cd "$(get_repo_root)"

# NOTE: this script used to run `npm cache clean --force` here "to avoid
# corruption issues on CI runners". It was actively harmful. Every caller pairs
# it with actions/setup-node, whose `cache: 'npm'` had just restored a ~396 MB
# ~/.npm cache; cleaning it meant `npm ci` re-downloaded all 1096 packages over
# the network in every job (~10 GB of pointless cache traffic per CI run). An
# isolated A/B put the warm cache at ~1s of the install, so the RESTORE was the
# waste: callers now cache node_modules itself (.github/actions/setup-workspace)
# and this script only runs on a cache miss, where a cold npm cache is strictly
# worse. retry_with_backoff below is what actually handles transient corruption.

if [[ "$WANT_ROOT" == "true" ]]; then
    log_step "Installing npm dependencies..."
fi

# Build npm ci command
NPM_ARGS="ci"

# Windows requires --ignore-scripts to avoid native-module rebuild timeouts
if [[ "$CI_OS" == "windows" ]] || [[ "$IGNORE_SCRIPTS" == "true" ]]; then
    NPM_ARGS="$NPM_ARGS --ignore-scripts"
    log_info "Using --ignore-scripts flag"
fi

# Run npm ci with retry for transient registry/network failures
run_npm_ci() {
    npm $NPM_ARGS
}

if [[ "$WANT_ROOT" == "true" ]]; then
    if retry_with_backoff 3 10 run_npm_ci; then
        log_info "Dependencies installed successfully"
    else
        log_error "Failed to install dependencies after retries"
        exit 1
    fi

    # Verify node_modules exists
    if [[ ! -d "node_modules" ]]; then
        log_error "node_modules directory not created"
        exit 1
    fi
fi

# Install account dependencies if the submodule is available.
#
# All THREE trees, not just the root one. private/account/web and
# private/account/e2e were installed ad hoc by whichever job happened to need
# them (quality-lint installed all three inline so knip could resolve imports),
# which meant the "account deps are installed" precondition meant something
# different in every job. One list here makes the cached account tree canonical.
if [[ "$WANT_ACCOUNT" == "true" && -f "private/account/package.json" ]]; then
    log_step "Installing account dependencies..."
    run_account_ci() { (cd "$1" && npm ci); }
    for account_dir in private/account private/account/web private/account/e2e; do
        [[ -f "$account_dir/package.json" ]] || continue
        if ! retry_with_backoff 3 10 run_account_ci "$account_dir"; then
            log_error "Failed to install dependencies in $account_dir"
            exit 1
        fi
    done
fi

log_info "npm install complete"
