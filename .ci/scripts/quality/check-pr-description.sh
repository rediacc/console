#!/bin/bash
# Check that PR description is up-to-date with recent commits
#
# After multiple commits, PR descriptions can become stale and misleading.
# This check ensures the description is updated when:
#   - The PR has 3+ commits AND
#   - The description hasn't been updated in 30+ minutes
#
# Skip label: 'description-current' - add this label to bypass the check
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
MIN_COMMITS=3                    # Minimum commits before requiring update
STALE_THRESHOLD_MINUTES=30       # How old description can be (in minutes)
SKIP_LABEL="description-current"

# Validate environment
require_var PR_NUMBER
require_var GH_TOKEN
require_var GITHUB_REPOSITORY

log_step "Checking PR description freshness..."

# Check for skip label
LABELS=$(gh pr view "$PR_NUMBER" --json labels --jq '.labels[].name' 2>/dev/null || echo "")
if echo "$LABELS" | grep -q "$SKIP_LABEL"; then
    log_info "Skipping description check ('$SKIP_LABEL' label present)"
    exit 0
fi

# Get PR details
PR_DATA=$(gh pr view "$PR_NUMBER" --json commits,createdAt,body,title 2>/dev/null || echo "{}")

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

# Get PR creation time
# Note: GitHub's updatedAt changes on ANY activity (comments, labels, etc.)
# so we use createdAt as the baseline for when description was written.
# If user updates description, they should add 'description-current' label.
PR_CREATED_AT=$(echo "$PR_DATA" | jq -r '.createdAt')

# Convert to epoch for comparison
COMMIT_EPOCH=$(date -d "$LATEST_COMMIT_TIME" +%s 2>/dev/null || \
               date -j -f "%Y-%m-%dT%H:%M:%SZ" "$LATEST_COMMIT_TIME" +%s 2>/dev/null || echo "0")
PR_EPOCH=$(date -d "$PR_CREATED_AT" +%s 2>/dev/null || \
           date -j -f "%Y-%m-%dT%H:%M:%SZ" "$PR_CREATED_AT" +%s 2>/dev/null || echo "0")

if [[ "$COMMIT_EPOCH" == "0" ]] || [[ "$PR_EPOCH" == "0" ]]; then
    log_warn "Could not parse timestamps - skipping check"
    exit 0
fi

# Calculate how much newer the latest commit is vs PR creation
AGE_SECONDS=$((COMMIT_EPOCH - PR_EPOCH))
AGE_MINUTES=$((AGE_SECONDS / 60))
THRESHOLD_SECONDS=$((STALE_THRESHOLD_MINUTES * 60))

log_info "Latest commit: $LATEST_COMMIT_TIME"
log_info "PR created: $PR_CREATED_AT"
log_info "Time since PR creation: ${AGE_MINUTES}m"

# If latest commit is within threshold of PR creation, description is likely still accurate
if [[ "$AGE_SECONDS" -lt "$THRESHOLD_SECONDS" ]]; then
    log_info "Latest commit is within ${STALE_THRESHOLD_MINUTES}m of PR creation - OK"
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
echo "Please update the PR title and description to reflect:"
echo "  - Current scope of changes"
echo "  - Key implementation decisions"
echo "  - Any breaking changes or migration notes"
echo ""
echo "Actions:"
echo "  1. Update PR title/description on GitHub"
echo "  2. Or add '$SKIP_LABEL' label if description is intentionally unchanged"
echo ""
echo "PR: https://github.com/${GITHUB_REPOSITORY}/pull/${PR_NUMBER}"
echo "============================================================"
exit 1
