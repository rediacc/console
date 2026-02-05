#!/bin/bash
# Check that PR description is up-to-date with recent commits
#
# After multiple commits, PR descriptions can become stale and misleading.
# This check ensures the description is updated when:
#   - The PR has 3+ commits AND
#   - The latest commit is more than STALE_THRESHOLD_MINUTES newer than
#     the last time the PR body/title was edited
#
# Uses GitHub's GraphQL lastEditedAt field which only changes when the
# PR body or title is actually edited (not on pushes, comments, or labels).
#
# Usage:
#   .ci/scripts/quality/check-pr-description.sh
#
# Environment variables:
#   GH_TOKEN           - GitHub token for API access
#   PR_NUMBER          - Pull request number
#   GITHUB_REPOSITORY  - Repository in owner/repo format

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Configuration
MIN_COMMITS=3              # Minimum commits before requiring update
STALE_THRESHOLD_MINUTES=30 # How old description can be (in minutes)

# Validate environment
require_var PR_NUMBER
require_var GH_TOKEN
require_var GITHUB_REPOSITORY

log_step "Checking PR description freshness..."

# Get PR details (commit count)
PR_DATA=$(gh pr view "$PR_NUMBER" --json commits,body,title 2>/dev/null || echo "{}")

if [[ "$PR_DATA" == "{}" ]]; then
    log_error "Could not fetch PR data"
    exit 1
fi

# Get commit count
COMMIT_COUNT=$(echo "$PR_DATA" | jq '.commits | length')
log_info "PR has $COMMIT_COUNT commit(s)"

# Check if we have enough commits to care
if [[ "$COMMIT_COUNT" -lt "$MIN_COMMITS" ]]; then
    log_info "Less than $MIN_COMMITS commits - skipping description check"
    exit 0
fi

# Get latest commit time
LATEST_COMMIT_TIME=$(gh pr view "$PR_NUMBER" --json commits \
    --jq '.commits | sort_by(.committedDate) | last | .committedDate' 2>/dev/null || echo "")

if [[ -z "$LATEST_COMMIT_TIME" ]]; then
    log_warn "Could not get latest commit time - skipping check"
    exit 0
fi

# Get the time the PR description was last edited using GraphQL.
# lastEditedAt only changes when body/title is edited (not on pushes, comments, labels).
# Falls back to createdAt if the description was never edited after creation.
OWNER="${GITHUB_REPOSITORY%%/*}"
REPO="${GITHUB_REPOSITORY##*/}"

# Use heredoc to safely construct the GraphQL query (avoids bash ! escaping issues)
GRAPHQL_QUERY=$(
    cat <<'GRAPHQL'
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      lastEditedAt
      createdAt
    }
  }
}
GRAPHQL
)

DESCRIPTION_TIME=$(gh api graphql \
    -F owner="$OWNER" -F repo="$REPO" -F number="$PR_NUMBER" \
    -f query="$GRAPHQL_QUERY" 2>/dev/null |
    jq -r '.data.repository.pullRequest | .lastEditedAt // .createdAt')

if [[ -z "$DESCRIPTION_TIME" ]] || [[ "$DESCRIPTION_TIME" == "null" ]]; then
    log_warn "Could not get PR description edit time - skipping check"
    exit 0
fi

# Convert to epoch for comparison
COMMIT_EPOCH=$(date -d "$LATEST_COMMIT_TIME" +%s 2>/dev/null ||
    date -j -f "%Y-%m-%dT%H:%M:%SZ" "$LATEST_COMMIT_TIME" +%s 2>/dev/null || echo "0")
DESC_EPOCH=$(date -d "$DESCRIPTION_TIME" +%s 2>/dev/null ||
    date -j -f "%Y-%m-%dT%H:%M:%SZ" "$DESCRIPTION_TIME" +%s 2>/dev/null || echo "0")

if [[ "$COMMIT_EPOCH" == "0" ]] || [[ "$DESC_EPOCH" == "0" ]]; then
    log_warn "Could not parse timestamps - skipping check"
    exit 0
fi

# Calculate how much newer the latest commit is vs description edit
AGE_SECONDS=$((COMMIT_EPOCH - DESC_EPOCH))
AGE_MINUTES=$((AGE_SECONDS / 60))
THRESHOLD_SECONDS=$((STALE_THRESHOLD_MINUTES * 60))

log_info "Latest commit: $LATEST_COMMIT_TIME"
log_info "Description last edited: $DESCRIPTION_TIME"
log_info "Time since description edit: ${AGE_MINUTES}m"

# If latest commit is within threshold of last description edit, description is likely still accurate
# Negative age means description was edited after the latest commit (always OK)
if [[ "$AGE_SECONDS" -lt "$THRESHOLD_SECONDS" ]]; then
    log_info "Latest commit is within ${STALE_THRESHOLD_MINUTES}m of description edit - OK"
    exit 0
fi

# Description is stale
echo ""
echo "============================================================"
echo "  PR Description May Be Stale"
echo "============================================================"
echo ""
echo "Your PR has $COMMIT_COUNT commits, but the description hasn't"
echo "been updated in ${AGE_MINUTES} minutes (threshold: ${STALE_THRESHOLD_MINUTES}m)."
echo ""
echo "After multiple commits, PR descriptions can become outdated"
echo "and misleading for reviewers."
echo ""
echo "------------------------------------------------------------"
echo "FOR AI SYSTEMS (Claude, Copilot, etc.):"
echo "------------------------------------------------------------"
echo ""
echo "You MUST:"
echo "  1. Run: git log --oneline origin/main..HEAD"
echo "  2. Review ALL commits in the branch"
echo "  3. Update PR title to reflect the CURRENT scope"
echo "  4. Update PR description with:"
echo "     - Summary of ALL changes (not just initial ones)"
echo "     - Any new features added during review"
echo "     - Breaking changes or migration notes"
echo "  5. Use: gh pr edit $PR_NUMBER --title \"new title\" --body \"new body\""
echo ""
echo "------------------------------------------------------------"
echo "FOR HUMANS:"
echo "------------------------------------------------------------"
echo ""
echo "Please update the PR title and description to reflect:"
echo "  - Current scope of changes"
echo "  - Key implementation decisions"
echo "  - Any breaking changes or migration notes"
echo ""
echo "PR: https://github.com/${GITHUB_REPOSITORY}/pull/${PR_NUMBER}"
echo "============================================================"
exit 1
