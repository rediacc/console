#!/bin/bash
# Wait for Gemini Code Assist to post its review
#
# This script polls PR comments until Gemini's review is found or times out.
# It ensures CI doesn't pass before Gemini has a chance to review the code.
#
# Skips if:
# - PR has 'no-gemini-review' label
# - First commit on PR (Gemini auto-reviews)
# - PR is from a bot
#
# Usage:
#   .ci/scripts/quality/wait-gemini-review.sh
#
# Environment variables:
#   GH_TOKEN           - GitHub token for API access
#   PR_NUMBER          - Pull request number
#   GITHUB_REPOSITORY  - Repository in owner/repo format

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Configuration
TIMEOUT="${GEMINI_TIMEOUT:-600}"      # 10 minutes max wait
POLL_INTERVAL="${GEMINI_POLL:-30}"    # Check every 30 seconds
GEMINI_BOT="gemini-code-assist[bot]"

# Validate environment
require_var PR_NUMBER
require_var GH_TOKEN
require_var GITHUB_REPOSITORY

log_step "Waiting for Gemini Code Assist review..."

# Check for skip label
LABELS=$(gh pr view "$PR_NUMBER" --json labels --jq '.labels[].name' 2>/dev/null || echo "")
if echo "$LABELS" | grep -q "no-gemini-review"; then
    log_info "Skipping Gemini wait (no-gemini-review label present)"
    exit 0
fi

# Check commit count - skip if first commit (Gemini reviews automatically)
COMMIT_COUNT=$(gh pr view "$PR_NUMBER" --json commits --jq '.commits | length' 2>/dev/null || echo "0")
if [[ "$COMMIT_COUNT" -le 1 ]]; then
    log_info "First commit - Gemini will review automatically (no wait needed)"
    exit 0
fi

# Get latest commit SHA
LATEST_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid --jq '.headRefOid' 2>/dev/null || echo "")
if [[ -z "$LATEST_SHA" ]]; then
    log_error "Could not get latest commit SHA"
    exit 1
fi

SHORT_SHA="${LATEST_SHA:0:7}"
log_info "Waiting for Gemini review on commit $SHORT_SHA..."
log_info "Timeout: ${TIMEOUT}s, Poll interval: ${POLL_INTERVAL}s"

# Function to check if Gemini has reviewed
check_gemini_review() {
    # Get all comments from Gemini bot
    local gemini_comments
    gemini_comments=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
        --jq "[.[] | select(.user.login == \"${GEMINI_BOT}\")] | last" 2>/dev/null || echo "null")

    if [[ "$gemini_comments" == "null" ]] || [[ -z "$gemini_comments" ]]; then
        return 1
    fi

    # Check if the comment mentions the current commit SHA
    # Gemini includes the commit SHA in its review summary
    local comment_body
    comment_body=$(echo "$gemini_comments" | jq -r '.body // ""')

    if echo "$comment_body" | grep -qi "$SHORT_SHA"; then
        log_info "Found Gemini review for commit $SHORT_SHA"
        return 0
    fi

    # Also check if the review was posted recently (within last 5 minutes of this script starting)
    # This handles cases where Gemini's review format changes
    local comment_time
    comment_time=$(echo "$gemini_comments" | jq -r '.created_at // ""')

    if [[ -n "$comment_time" ]]; then
        # Parse ISO 8601 timestamp
        local comment_epoch
        comment_epoch=$(date -d "$comment_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$comment_time" +%s 2>/dev/null || echo "0")
        local now_epoch
        now_epoch=$(date +%s)
        local age=$((now_epoch - comment_epoch))

        # If Gemini posted within the last 10 minutes, assume it's for this commit
        if [[ $age -lt 600 ]]; then
            log_info "Found recent Gemini review (${age}s ago)"
            return 0
        fi
    fi

    return 1
}

# Progress callback for polling
log_poll_progress() {
    local elapsed="$1"
    local timeout="$2"
    # $3 is interval_num, unused
    local remaining=$((timeout - elapsed))

    log_step "[${elapsed}s/${timeout}s] Waiting for Gemini review... (${remaining}s remaining)"
}

# Poll for Gemini review
if poll_with_watchdog "$TIMEOUT" "$POLL_INTERVAL" check_gemini_review log_poll_progress; then
    echo ""
    echo "============================================================"
    echo "  Gemini Review Gate: PASSED"
    echo "============================================================"
    echo ""
    echo "Gemini Code Assist has reviewed this PR."
    exit 0
fi

# Timeout reached - fail with instructions
echo ""
echo "============================================================"
echo "  Gemini Review Gate: TIMEOUT"
echo "============================================================"
echo ""
echo "Gemini Code Assist did not post a review within ${TIMEOUT}s."
echo ""
echo "Possible causes:"
echo "  1. Gemini is experiencing high load"
echo "  2. The review was not triggered"
echo "  3. Gemini encountered an error"
echo ""
echo "Actions you can take:"
echo "  - Wait and re-run this job"
echo "  - Manually trigger: comment '/gemini review' on the PR"
echo "  - Add 'no-gemini-review' label to skip this check"
echo ""
echo "PR: https://github.com/${GITHUB_REPOSITORY}/pull/${PR_NUMBER}"
echo "============================================================"
exit 1
