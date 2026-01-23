#!/bin/bash
# Check that all dependencies are up-to-date
# With integrated autofix for PRs
#
# Usage:
#   .ci/scripts/quality/check-deps.sh
#
# Environment variables:
#   GITHUB_EVENT_NAME - GitHub event type (e.g., 'pull_request')
#   GITHUB_HEAD_REF - PR branch name (set by GitHub Actions)
#
# Exit codes:
#   0 - Dependencies are up-to-date (or auto-fixed on PR)
#   1 - Outdated dependencies found (and could not auto-fix)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Phase 1: Check
log_step "Checking dependency versions..."
if npx tsx "$REPO_ROOT/scripts/check-deps.ts"; then
    log_info "Dependencies are up-to-date"
    exit 0
fi

# Check failed - can we fix?
log_warn "Outdated dependencies detected"

# Phase 2: Check if fixable context (PR only)
if [[ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]] || [[ -z "${GITHUB_HEAD_REF:-}" ]]; then
    log_error "Cannot auto-fix outside PR context"
    log_error "Run: npm run check:deps -- --upgrade"
    exit 1
fi

# Check for recent autofix commits to prevent loops (specific to deps)
RECENT_AUTOFIX=$(git log --oneline -5 --author="github-actions\[bot\]" --grep="auto-upgrade dependencies" 2>/dev/null | head -1 || true)
if [[ -n "$RECENT_AUTOFIX" ]]; then
    log_error "Recent deps autofix commit detected, cannot auto-fix again: $RECENT_AUTOFIX"
    log_error "Please manually fix dependency issues"
    exit 1
fi

# Phase 3: Attempt fix
log_step "Attempting auto-fix..."
if ! npx tsx "$REPO_ROOT/scripts/check-deps.ts" --upgrade; then
    log_error "Auto-upgrade failed (npm install error)"
    exit 1
fi

# Phase 4: Commit if changes were made
# Check all package files that might have changed
if git diff --quiet package.json package-lock.json packages/*/package.json 2>/dev/null; then
    # No changes - upgrade completed without modifying files
    # This can happen if all outdated packages are in the blocklist
    log_info "No upgradable dependencies found (all may be blocked)"
    exit 0
fi

log_step "Committing fix..."
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
git add package.json package-lock.json packages/*/package.json
git commit -m "$(cat <<'EOF'
chore(deps): auto-upgrade dependencies

Automatically upgraded by CI.
EOF
)"
git push origin "HEAD:${GITHUB_HEAD_REF}"

log_info "Dependencies fixed and committed"
exit 0
