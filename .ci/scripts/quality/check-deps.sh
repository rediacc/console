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
#   PR_AUTHOR - GitHub username of the PR author (optional, falls back to github-actions[bot])
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
# Scope to PR-only commits to avoid false positives from squash merges on the base branch
BASE_REF="${GITHUB_BASE_REF:-main}"
RECENT_AUTOFIX=$(git log --oneline -5 "origin/${BASE_REF}..HEAD" --grep="auto-upgrade dependencies" 2>/dev/null | head -1 || true)
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
CONSOLE_CHANGED=false
SUBMODULE_DIRS_CHANGED=()

# Check parent repo files (workspace packages)
if ! git diff --quiet package.json package-lock.json packages/*/package.json 2>/dev/null; then
    CONSOLE_CHANGED=true
fi

# Check submodule directories for changes
# git diff on submodule paths from parent can't see file-level changes inside submodules,
# so we check inside each submodule directly
for dir in private/*/; do
    dir="${dir%/}" # Remove trailing slash
    # Only process git submodules that have a package.json
    if [[ ! -f "$dir/.git" ]] && [[ ! -d "$dir/.git" ]]; then
        continue
    fi
    if [[ ! -f "$dir/package.json" ]]; then
        continue
    fi
    # Check for package file changes inside the submodule
    if (cd "$dir" && ! git diff --quiet -- package.json package-lock.json 2>/dev/null); then
        SUBMODULE_DIRS_CHANGED+=("$dir")
    fi
done

if [[ "$CONSOLE_CHANGED" == "false" ]] && [[ ${#SUBMODULE_DIRS_CHANGED[@]} -eq 0 ]]; then
    log_info "No upgradable dependencies found (all may be blocked)"
    exit 0
fi

log_step "Committing fix..."

# Configure git author
if [[ -n "${PR_AUTHOR:-}" ]]; then
    git config user.name "$PR_AUTHOR"
    git config user.email "${PR_AUTHOR}@users.noreply.github.com"
else
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
fi

# Handle submodule commits first — must commit inside each submodule,
# push to its remote, then stage the pointer update in the parent
for dir in "${SUBMODULE_DIRS_CHANGED[@]}"; do
    submodule_name=$(basename "$dir")
    log_info "Committing dependency upgrades in $submodule_name..."
    (
        cd "$dir"
        if [[ -n "${PR_AUTHOR:-}" ]]; then
            git config user.name "$PR_AUTHOR"
            git config user.email "${PR_AUTHOR}@users.noreply.github.com"
        else
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
        fi
        git add package.json
        [[ -f package-lock.json ]] && git add package-lock.json
        git commit -m "$(
            cat <<'SUBMSG'
chore(deps): auto-upgrade dependencies

Automatically upgraded by CI.
SUBMSG
        )"
        # Push to submodule remote so the commit is resolvable by future checkouts
        if ! git push origin HEAD:main 2>/dev/null; then
            # main has advanced — push to a dedicated branch instead
            DEPS_BRANCH="ci/deps-upgrade-from-${GITHUB_HEAD_REF}"
            log_info "main diverged, pushing $submodule_name to branch $DEPS_BRANCH..."
            git push origin "HEAD:refs/heads/$DEPS_BRANCH" --force
        fi
        log_info "Pushed $submodule_name submodule to remote"
    )
    # Stage the submodule pointer update in parent
    git add "$dir"
done

# Stage parent repo files
if [[ "$CONSOLE_CHANGED" == "true" ]]; then
    git add package.json package-lock.json packages/*/package.json
fi

git commit -m "$(
    cat <<'EOF'
chore(deps): auto-upgrade dependencies

Automatically upgraded by CI.
EOF
)"
git push origin "HEAD:${GITHUB_HEAD_REF}"

log_info "Dependencies fixed and committed"
exit 0
