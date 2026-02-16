#!/bin/bash
# Trigger Gemini Code Assist review on new commits
#
# Gemini automatically reviews when a PR is first opened, but does NOT review
# subsequent commits. This script triggers a re-review on new commits.
#
# Skips if:
# - This is the first commit (Gemini reviews automatically)
# - PR has 'no-gemini-review' label
# - Gemini already reviewed the latest commit (unless PR description was updated)
# - Maximum review triggers reached (see MAX_GEMINI_REVIEWS in common.sh)
# - Unresolved review threads exist (must address previous comments first)
# - Changed LOC since last review is less than MIN_LOC_FOR_REVIEW (100 lines)
#
# Re-triggers when:
# - PR description was updated after the last review trigger (scope change)
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

OWNER="${GITHUB_REPOSITORY%%/*}"
REPO="${GITHUB_REPOSITORY##*/}"

log_step "Checking if Gemini review should be triggered..."

# Check if commit message indicates this is a review fix
# Skip triggering new review when developer is addressing previous feedback
COMMIT_MSG=$(git log -1 --pretty=%B 2>/dev/null || echo "")
if echo "$COMMIT_MSG" | grep -qiE "(address|fix|per|apply|resolve).*(review|comment|feedback|suggestion)"; then
    log_info "Commit addresses review feedback - skipping new review trigger"
    echo ""
    echo "------------------------------------------------------------"
    echo "Detected review-fix commit. Skipping new Gemini review."
    echo "Resolve existing threads in GitHub UI to pass the review gate."
    echo "------------------------------------------------------------"
    exit 0
fi

# Check for skip label
LABELS=$(gh pr view "$PR_NUMBER" --json labels --jq '.labels[].name' 2>/dev/null || echo "")
if echo "$LABELS" | grep -q "no-gemini-review"; then
    log_info "Skipping Gemini review (no-gemini-review label present)"
    exit 0
fi

# Check commit count - skip if first commit (Gemini reviews automatically on PR open)
# However, force-pushed PRs may have 1 commit but already have reviews from Gemini.
# In that case, Gemini won't auto-review the new SHA, so we must trigger explicitly.
COMMIT_COUNT=$(gh pr view "$PR_NUMBER" --json commits --jq '.commits | length' 2>/dev/null || echo "0")
if [[ "$COMMIT_COUNT" -le 1 ]]; then
    # Check if Gemini has already reviewed this PR (indicates force-push, not a new PR)
    GEMINI_BOT="gemini-code-assist[bot]"
    EXISTING_REVIEWS=$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/reviews" --paginate \
        --jq "[.[] | select(.user.login == \"${GEMINI_BOT}\")] | length" 2>/dev/null || echo "0")
    if [[ "$EXISTING_REVIEWS" -eq 0 ]]; then
        log_info "First commit on new PR - Gemini will review automatically"
        exit 0
    fi
    log_info "Force-pushed PR detected (1 commit but $EXISTING_REVIEWS existing Gemini reviews) - triggering review"
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

# Check for existing review triggers
# - Skip if we already triggered a review for this specific commit
# - Skip if we've reached the maximum number of review triggers (3)
log_step "Checking for existing review triggers..."

ALL_COMMENTS=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
    --jq '.[].body' 2>/dev/null || echo "")

# Check if this specific commit was already reviewed
TRIGGER_MARKER="triggered by CI for commit ${SHORT_SHA}"
DESCRIPTION_UPDATED=false
if echo "$ALL_COMMENTS" | grep -q "$TRIGGER_MARKER"; then
    # A PR description update can change the review scope without new commits.
    # If the description was edited after the last review trigger, re-request review.
    LAST_TRIGGER_TIME=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
        --jq "[.[] | select(.body | contains(\"$TRIGGER_MARKER\")) | .created_at] | last" 2>/dev/null || echo "")

    DESC_EDIT_TIME=$(gh api graphql \
        -F owner="$OWNER" -F repo="$REPO" -F number="$PR_NUMBER" \
        -f query='query($owner: String!, $repo: String!, $number: Int!) { repository(owner: $owner, name: $repo) { pullRequest(number: $number) { lastEditedAt } } }' \
        --jq '.data.repository.pullRequest.lastEditedAt' 2>/dev/null || echo "")

    if [[ -n "$LAST_TRIGGER_TIME" ]] && [[ -n "$DESC_EDIT_TIME" ]] && [[ "$DESC_EDIT_TIME" != "null" ]]; then
        TRIGGER_EPOCH=$(date -d "$LAST_TRIGGER_TIME" +%s 2>/dev/null || echo "0")
        DESC_EPOCH=$(date -d "$DESC_EDIT_TIME" +%s 2>/dev/null || echo "0")

        if [[ "$DESC_EPOCH" -gt "$TRIGGER_EPOCH" ]]; then
            log_info "PR description updated since last review - re-requesting Gemini review"
            DESCRIPTION_UPDATED=true
        fi
    fi

    if [[ "$DESCRIPTION_UPDATED" != "true" ]]; then
        log_info "Review already triggered for commit $SHORT_SHA"
        exit 0
    fi
fi

# Limit review triggers per PR to avoid spam (constant defined in common.sh)
REVIEW_COUNT=$(echo "$ALL_COMMENTS" | grep -c "triggered by CI for commit" || echo "0")
if [[ "$REVIEW_COUNT" -ge "$MAX_GEMINI_REVIEWS" ]]; then
    log_info "Maximum review triggers reached ($MAX_GEMINI_REVIEWS) - skipping"
    exit 0
fi

log_info "Review triggers: $REVIEW_COUNT/$MAX_GEMINI_REVIEWS"

# Check if there are enough changes since the last review to warrant a new one
# Skip if changed LOC (added + removed) is less than 100 lines
# Bypass when description was updated (scope change doesn't require code changes)
MIN_LOC_FOR_REVIEW="${MIN_LOC_FOR_REVIEW:-100}"

if [[ "$DESCRIPTION_UPDATED" == "true" ]]; then
    log_info "Skipping LOC check - PR description update indicates scope change"
else

    log_step "Checking LOC changes since last review..."

    # Get all comments with their body to find the last trigger
    COMMENTS_WITH_SHA=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
        --jq '[.[] | select(.body | contains("triggered by CI for commit")) | .body]' 2>/dev/null || echo "[]")

    # Extract the SHA from the last trigger comment
    LAST_REVIEWED_SHA=$(echo "$COMMENTS_WITH_SHA" | jq -r 'last | capture("triggered by CI for commit (?<sha>[a-f0-9]+)") | .sha // empty' 2>/dev/null || echo "")

    if [[ -n "$LAST_REVIEWED_SHA" ]]; then
        # Calculate diff between last reviewed commit and current HEAD
        # Use git diff --shortstat to get a summary
        DIFF_STAT=$(git diff --shortstat "${LAST_REVIEWED_SHA}..HEAD" 2>/dev/null || echo "")

        if [[ -n "$DIFF_STAT" ]]; then
            # Extract insertions and deletions from shortstat output
            # Format: " X files changed, Y insertions(+), Z deletions(-)"
            INSERTIONS=$(echo "$DIFF_STAT" | grep -oE '[0-9]+ insertion' | grep -oE '[0-9]+' || echo "0")
            DELETIONS=$(echo "$DIFF_STAT" | grep -oE '[0-9]+ deletion' | grep -oE '[0-9]+' || echo "0")
            TOTAL_LOC=$((${INSERTIONS:-0} + ${DELETIONS:-0}))

            log_info "Changes since last review ($LAST_REVIEWED_SHA): +${INSERTIONS:-0}/-${DELETIONS:-0} = $TOTAL_LOC lines"

            if [[ "$TOTAL_LOC" -lt "$MIN_LOC_FOR_REVIEW" ]]; then
                log_info "Changed LOC ($TOTAL_LOC) < minimum threshold ($MIN_LOC_FOR_REVIEW)"
                log_info "Skipping review trigger - not enough changes since last review"
                echo ""
                echo "------------------------------------------------------------"
                echo "Skipping Gemini review: only $TOTAL_LOC lines changed."
                echo "Minimum threshold is $MIN_LOC_FOR_REVIEW lines."
                echo "------------------------------------------------------------"
                exit 0
            fi
        else
            log_info "No diff found or empty commit - skipping review trigger"
            exit 0
        fi
    else
        log_info "No previous review trigger found - this will be the first triggered review"
    fi

fi # end DESCRIPTION_UPDATED else block

# Check for unresolved review threads before triggering new review
# Don't ask Gemini to review again until previous comments are addressed
log_step "Checking for unresolved review threads..."

THREAD_QUERY='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          isOutdated
        }
      }
    }
  }
}'

THREAD_RESULT=$(gh api graphql \
    -f query="$THREAD_QUERY" \
    -f owner="$OWNER" \
    -f repo="$REPO" \
    -F pr="$PR_NUMBER" 2>/dev/null || echo '{}')

# Count unresolved threads (excluding outdated ones)
UNRESOLVED_COUNT=$(echo "$THREAD_RESULT" | jq '[
    .data.repository.pullRequest.reviewThreads.nodes[]
    | select(.isResolved == false and .isOutdated == false)
] | length' 2>/dev/null || echo "0")

if [[ "$UNRESOLVED_COUNT" -gt 0 ]]; then
    log_info "Found $UNRESOLVED_COUNT unresolved review thread(s)"
    log_info "Skipping new review until previous comments are addressed"
    echo ""
    echo "------------------------------------------------------------"
    echo "Previous review comments must be resolved before requesting"
    echo "a new Gemini review. Please:"
    echo "  1. Address the feedback in unresolved threads"
    echo "  2. Resolve each thread in the GitHub UI"
    echo "  3. Push a new commit to trigger another review"
    echo "------------------------------------------------------------"
    exit 0
fi

log_info "No unresolved threads - proceeding with review trigger"

# Trigger Gemini review
log_step "Triggering Gemini review for commit $SHORT_SHA..."

if [[ "$DESCRIPTION_UPDATED" == "true" ]]; then
    COMMENT_BODY="/gemini review

<!-- triggered by CI for commit ${SHORT_SHA} (description updated) -->"
else
    COMMENT_BODY="/gemini review

<!-- triggered by CI for commit ${SHORT_SHA} -->"
fi

if gh pr comment "$PR_NUMBER" --body "$COMMENT_BODY"; then
    log_info "Gemini review triggered successfully"
    echo ""
    echo "Gemini Code Assist will post a review shortly."
else
    log_warn "Failed to post comment - Gemini review not triggered"
    # Don't fail the job - this is not critical
    exit 0
fi
