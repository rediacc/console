#!/bin/bash
# Trigger Gemini Code Assist review on new commits
#
# Gemini automatically reviews when a PR is first opened, but does NOT review
# subsequent commits. This script triggers a re-review on new commits.
#
# Skips if:
# - This is the first commit (Gemini reviews automatically)
# - PR has 'no-gemini-review' label
# - Gemini already reviewed the latest commit
#
# Usage:
#   .ci/scripts/quality/trigger-gemini-review.sh
#
# Environment variables:
#   GH_TOKEN   - GitHub token for API access
#   PR_NUMBER  - Pull request number
#   GITHUB_REPOSITORY - Repository in owner/repo format

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Validate environment
if [[ -z "${PR_NUMBER:-}" ]]; then
    log_error "PR_NUMBER not set"
    exit 1
fi

if [[ -z "${GH_TOKEN:-}" ]]; then
    log_error "GH_TOKEN not set"
    exit 1
fi

log_step "Checking if Gemini review should be triggered..."

# Check for skip label
LABELS=$(gh pr view "$PR_NUMBER" --json labels --jq '.labels[].name' 2>/dev/null || echo "")
if echo "$LABELS" | grep -q "no-gemini-review"; then
    log_info "Skipping Gemini review (no-gemini-review label present)"
    exit 0
fi

# Check commit count - skip if first commit (Gemini reviews automatically)
COMMIT_COUNT=$(gh pr view "$PR_NUMBER" --json commits --jq '.commits | length' 2>/dev/null || echo "0")
if [[ "$COMMIT_COUNT" -le 1 ]]; then
    log_info "First commit - Gemini will review automatically"
    exit 0
fi

log_info "PR has $COMMIT_COUNT commits"

# Get latest commit SHA
LATEST_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid --jq '.headRefOid' 2>/dev/null || echo "")
if [[ -z "$LATEST_SHA" ]]; then
    log_warn "Could not get latest commit SHA - skipping"
    exit 0
fi

SHORT_SHA="${LATEST_SHA:0:7}"
log_info "Latest commit: $SHORT_SHA"

# Check if Gemini already reviewed this commit
# Gemini's review comments typically include the commit SHA
log_step "Checking for existing Gemini review..."

GEMINI_COMMENTS=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq '[.[] | select(.user.login == "gemini-code-assist[bot]")] | length' 2>/dev/null || echo "0")

if [[ "$GEMINI_COMMENTS" -gt 0 ]]; then
    # Check if the latest Gemini comment mentions the current commit
    LATEST_GEMINI_BODY=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
        --jq '[.[] | select(.user.login == "gemini-code-assist[bot]")] | last | .body // ""' 2>/dev/null || echo "")

    if echo "$LATEST_GEMINI_BODY" | grep -qi "$SHORT_SHA"; then
        log_info "Gemini already reviewed commit $SHORT_SHA"
        exit 0
    fi
fi

# Trigger Gemini review
log_step "Triggering Gemini review for commit $SHORT_SHA..."

if gh pr comment "$PR_NUMBER" --body "/gemini review"; then
    log_info "Gemini review triggered successfully"
    echo ""
    echo "Gemini Code Assist will post a review shortly."
else
    log_warn "Failed to post comment - Gemini review not triggered"
    # Don't fail the job - this is not critical
    exit 0
fi
