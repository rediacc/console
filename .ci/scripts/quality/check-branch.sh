#!/bin/bash
# Check that PR branch is up-to-date with base branch and has no conflicts
# If behind but no conflicts, automatically rebase and push (triggers new CI run)
#
# Usage:
#   .ci/scripts/quality/check-branch.sh
#
# Environment variables:
#   GITHUB_BASE_REF - Base branch name (e.g., 'main') - set by GitHub Actions
#   GITHUB_HEAD_REF - PR branch name - set by GitHub Actions
#   GITHUB_EVENT_NAME - GitHub event type (e.g., 'pull_request')
#   PR_AUTHOR - GitHub username of the PR author (optional, falls back to github-actions[bot])
#
# Exit codes:
#   0 - Branch is up-to-date and has no conflicts
#   1 - Branch has conflicts (cannot auto-rebase)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Skip check for non-PR events
if [[ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]]; then
    log_info "Skipping branch check (not a pull request)"
    exit 0
fi

BASE_BRANCH="${GITHUB_BASE_REF:-main}"
HEAD_BRANCH="${GITHUB_HEAD_REF:-}"

log_step "Checking branch status against origin/${BASE_BRANCH}..."

# Fetch the base branch to ensure we have latest
log_info "Fetching origin/${BASE_BRANCH}..."
git fetch origin "${BASE_BRANCH}" --quiet

# Check 1: Is the PR behind the base branch?
BEHIND_COUNT=$(git rev-list --count "HEAD..origin/${BASE_BRANCH}" 2>/dev/null || echo "0")

if [[ "$BEHIND_COUNT" -eq 0 ]]; then
    log_info "Branch is up-to-date with origin/${BASE_BRANCH}"
    exit 0
fi

log_warn "Branch is ${BEHIND_COUNT} commit(s) behind origin/${BASE_BRANCH}"
echo ""
echo "Recent commits on ${BASE_BRANCH} not in this branch:"
git log --oneline "HEAD..origin/${BASE_BRANCH}" | head -5
echo ""

# Check 2: Can we rebase without conflicts?
log_step "Checking if auto-rebase is possible..."

# Configure git identity BEFORE rebase (required for rebase to work)
if [[ -n "${PR_AUTHOR:-}" ]]; then
    git config user.name "$PR_AUTHOR"
    git config user.email "${PR_AUTHOR}@users.noreply.github.com"
else
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
fi

# Try rebase - verbose output helps diagnose issues if it fails
ORIGINAL_HEAD=$(git rev-parse HEAD)
if ! git rebase "origin/${BASE_BRANCH}" 2>&1; then
    # Rebase failed - conflicts detected
    git rebase --abort 2>/dev/null || true
    git checkout "${ORIGINAL_HEAD}" 2>/dev/null || true

    log_error "Cannot auto-rebase: merge conflicts detected"
    echo ""
    log_error "Please resolve conflicts locally:"
    echo "  git fetch origin ${BASE_BRANCH}"
    echo "  git rebase origin/${BASE_BRANCH}"
    echo "  # resolve conflicts"
    echo "  git push --force-with-lease"
    exit 1
fi

log_info "Rebase successful - no conflicts"

# Check if we can push (need HEAD_BRANCH)
if [[ -z "$HEAD_BRANCH" ]]; then
    log_error "Cannot auto-push: GITHUB_HEAD_REF not set"
    log_error "Please rebase manually: git rebase origin/${BASE_BRANCH} && git push --force-with-lease"
    exit 1
fi

log_step "Pushing rebased branch..."

# Push with force-with-lease for safety
if ! git push origin "HEAD:${HEAD_BRANCH}" --force-with-lease; then
    log_error "Failed to push rebased branch"
    log_error "Please rebase manually: git rebase origin/${BASE_BRANCH} && git push --force-with-lease"
    exit 1
fi

log_info "Branch rebased and pushed successfully"
echo ""
echo "=============================================="
echo "AUTO-REBASE COMPLETE"
echo "A new CI run will start automatically."
echo "This run will be cancelled by concurrency group."
echo "=============================================="

# Exit successfully - the concurrency group will cancel this run
# when the new push triggers a new workflow
exit 0
