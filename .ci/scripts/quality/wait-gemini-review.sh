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
MAX_WAIT="${GEMINI_TIMEOUT:-840}"       # 14 minutes max wait from trigger time
STALE_THRESHOLD="${GEMINI_STALE:-1200}" # 20 minutes - if trigger is older, skip immediately
POLL_INTERVAL="${GEMINI_POLL:-30}"      # Check every 30 seconds
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

# Get all issue comments with timestamps to find the trigger time
COMMENTS_JSON=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq '[.[] | {body: .body, created_at: .created_at}]' 2>/dev/null || echo "[]")

if ! echo "$COMMENTS_JSON" | jq -e ".[] | select(.body | contains(\"$TRIGGER_MARKER\"))" >/dev/null 2>&1; then
    # No trigger for this commit - check if it's because we hit the max
    # MAX_GEMINI_REVIEWS is defined in common.sh
    REVIEW_COUNT=$(echo "$COMMENTS_JSON" | jq '[.[] | select(.body | contains("triggered by CI for commit"))] | length' 2>/dev/null || echo "0")

    if [[ "$REVIEW_COUNT" -ge "$MAX_GEMINI_REVIEWS" ]]; then
        log_info "Max Gemini review triggers reached ($REVIEW_COUNT/$MAX_GEMINI_REVIEWS) - skipping wait"
        exit 0
    fi

    # First commit case - Gemini reviews automatically on PR open
    # But on force-push (1 commit, existing reviews), trigger-gemini-review.sh handles it
    COMMIT_COUNT=$(gh pr view "$PR_NUMBER" --json commits --jq '.commits | length' 2>/dev/null || echo "0")
    EXISTING_GEMINI_REVIEWS=$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/reviews" --paginate \
        --jq "[.[] | select(.user.login == \"${GEMINI_BOT}\")] | length" 2>/dev/null || echo "0")
    if [[ "$COMMIT_COUNT" -le 1 ]] && [[ "$EXISTING_GEMINI_REVIEWS" -eq 0 ]]; then
        log_info "First commit on new PR - Gemini auto-reviews on PR open, checking for existing review..."
        TRIGGER_TIME=""
    elif [[ "$COMMIT_COUNT" -le 1 ]] && [[ "$EXISTING_GEMINI_REVIEWS" -gt 0 ]]; then
        # Force-pushed PR - trigger script should have posted a trigger comment
        # If it didn't (e.g., skipped conditions), don't wait
        log_info "Force-pushed PR (1 commit, $EXISTING_GEMINI_REVIEWS existing reviews) but no trigger found"
        log_info "Skipping wait - trigger was likely skipped"
        exit 0
    else
        # No trigger for this commit - likely skipped due to unresolved threads
        # Don't wait for a review that will never come
        log_info "No review trigger for commit $SHORT_SHA - trigger was likely skipped"
        log_info "Skipping wait (unresolved threads or other skip condition)"
        exit 0
    fi
else
    # Get the timestamp of the trigger comment for this commit
    TRIGGER_TIME=$(echo "$COMMENTS_JSON" | jq -r "[.[] | select(.body | contains(\"$TRIGGER_MARKER\"))] | last | .created_at" 2>/dev/null || echo "")
fi

# Calculate smart timeout based on when the trigger was posted
NOW_EPOCH=$(date +%s)
TIMEOUT="$MAX_WAIT"

if [[ -n "$TRIGGER_TIME" ]]; then
    TRIGGER_EPOCH=$(date -d "$TRIGGER_TIME" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$TRIGGER_TIME" +%s 2>/dev/null || echo "0")

    if [[ "$TRIGGER_EPOCH" -gt 0 ]]; then
        TIME_SINCE_TRIGGER=$((NOW_EPOCH - TRIGGER_EPOCH))

        # If trigger is older than stale threshold (20 mins), Gemini is unresponsive - skip
        if [[ "$TIME_SINCE_TRIGGER" -ge "$STALE_THRESHOLD" ]]; then
            log_info "Trigger was posted ${TIME_SINCE_TRIGGER}s ago (> ${STALE_THRESHOLD}s threshold)"
            log_info "Gemini appears unresponsive - skipping wait"
            exit 0
        fi

        # Calculate remaining wait time instead of waiting full MAX_WAIT
        TIMEOUT=$((MAX_WAIT - TIME_SINCE_TRIGGER))
        if [[ "$TIMEOUT" -lt "$POLL_INTERVAL" ]]; then
            TIMEOUT="$POLL_INTERVAL" # At least one poll
        fi

        log_info "Trigger posted ${TIME_SINCE_TRIGGER}s ago, will wait up to ${TIMEOUT}s more"
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

# Timeout reached - don't block PR, just warn
echo ""
echo "============================================================"
echo "  Gemini Review Gate: TIMEOUT (Proceeding)"
echo "============================================================"
echo ""
echo "Gemini Code Assist did not respond within the wait period."
echo "Proceeding without blocking the PR."
echo ""
echo "Possible causes:"
echo "  1. Gemini is experiencing high load"
echo "  2. Gemini encountered an error processing this PR"
echo ""
echo "You can manually trigger a review later:"
echo "  - Comment '/gemini review' on the PR"
echo ""
echo "PR: https://github.com/${GITHUB_REPOSITORY}/pull/${PR_NUMBER}"
echo "============================================================"
exit 0
