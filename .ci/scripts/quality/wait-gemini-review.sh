#!/bin/bash
# Wait for Gemini Code Assist to post its review
#
# This script polls PR comments until Gemini's review is found or times out.
# It ensures CI doesn't pass before Gemini has a chance to review the code.
#
# For first commits, Gemini auto-reviews when the PR is opened.
# For subsequent commits, trigger-gemini-review.sh triggers the review.
# This script waits for Gemini's response in both cases.
#
# Skips if:
# - PR has 'no-gemini-review' label
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

# Get latest commit SHA
LATEST_SHA=$(gh pr view "$PR_NUMBER" --json headRefOid --jq '.headRefOid' 2>/dev/null || echo "")
if [[ -z "$LATEST_SHA" ]]; then
    log_error "Could not get latest commit SHA"
    exit 1
fi

SHORT_SHA="${LATEST_SHA:0:7}"

# Check if a review trigger was actually posted for this commit
# If not (e.g., hit max review limit), skip waiting
TRIGGER_MARKER="triggered by CI for commit ${SHORT_SHA}"
ALL_COMMENTS=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq '.[].body' 2>/dev/null || echo "")

if ! echo "$ALL_COMMENTS" | grep -q "$TRIGGER_MARKER"; then
    # No trigger for this commit - check if it's because we hit the max
    # MAX_GEMINI_REVIEWS is defined in common.sh
    REVIEW_COUNT=$(echo "$ALL_COMMENTS" | grep -c "triggered by CI for commit" || echo "0")

    if [[ "$REVIEW_COUNT" -ge "$MAX_GEMINI_REVIEWS" ]]; then
        log_info "Max Gemini review triggers reached ($REVIEW_COUNT/$MAX_GEMINI_REVIEWS) - skipping wait"
        exit 0
    fi

    # First commit case - Gemini reviews automatically on PR open
    COMMIT_COUNT=$(gh pr view "$PR_NUMBER" --json commits --jq '.commits | length' 2>/dev/null || echo "0")
    if [[ "$COMMIT_COUNT" -le 1 ]]; then
        log_info "First commit - Gemini auto-reviews on PR open, checking for existing review..."
    else
        # No trigger for this commit - likely skipped due to unresolved threads
        # Don't wait for a review that will never come
        log_info "No review trigger for commit $SHORT_SHA - trigger was likely skipped"
        log_info "Skipping wait (unresolved threads or other skip condition)"
        exit 0
    fi
fi

log_info "Waiting for Gemini review on commit $SHORT_SHA..."
log_info "Timeout: ${TIMEOUT}s, Poll interval: ${POLL_INTERVAL}s"

# Function to check if Gemini has reviewed
check_gemini_review() {
    # Check PR reviews first (Gemini posts reviews, not just comments)
    # Use --paginate to get all reviews (default only returns first page)
    local gemini_review
    gemini_review=$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/reviews" --paginate \
        --jq "[.[] | select(.user.login == \"${GEMINI_BOT}\")] | last" 2>/dev/null || echo "null")

    if [[ "$gemini_review" != "null" ]] && [[ -n "$gemini_review" ]]; then
        local review_body review_time
        review_body=$(echo "$gemini_review" | jq -r '.body // ""')
        review_time=$(echo "$gemini_review" | jq -r '.submitted_at // ""')

        # Check if review mentions the current commit SHA
        if echo "$review_body" | grep -qi "$SHORT_SHA"; then
            log_info "Found Gemini review for commit $SHORT_SHA"
            return 0
        fi

        # Check if review was posted recently (within last 10 minutes)
        if [[ -n "$review_time" ]]; then
            local review_epoch now_epoch age
            review_epoch=$(date -d "$review_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$review_time" +%s 2>/dev/null || echo "0")
            now_epoch=$(date +%s)
            age=$((now_epoch - review_epoch))

            if [[ $age -lt 600 ]]; then
                log_info "Found recent Gemini review (${age}s ago)"
                return 0
            fi
        fi
    fi

    # Also check issue comments (fallback for older review style)
    local gemini_comments
    gemini_comments=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
        --jq "[.[] | select(.user.login == \"${GEMINI_BOT}\")] | last" 2>/dev/null || echo "null")

    if [[ "$gemini_comments" != "null" ]] && [[ -n "$gemini_comments" ]]; then
        local comment_body comment_time
        comment_body=$(echo "$gemini_comments" | jq -r '.body // ""')

        if echo "$comment_body" | grep -qi "$SHORT_SHA"; then
            log_info "Found Gemini comment for commit $SHORT_SHA"
            return 0
        fi

        comment_time=$(echo "$gemini_comments" | jq -r '.created_at // ""')
        if [[ -n "$comment_time" ]]; then
            local comment_epoch now_epoch age
            comment_epoch=$(date -d "$comment_time" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$comment_time" +%s 2>/dev/null || echo "0")
            now_epoch=$(date +%s)
            age=$((now_epoch - comment_epoch))

            if [[ $age -lt 600 ]]; then
                log_info "Found recent Gemini comment (${age}s ago)"
                return 0
            fi
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
