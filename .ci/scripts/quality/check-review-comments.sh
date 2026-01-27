#!/bin/bash
# Check for unreplied review comments on pull requests
#
# This script ensures all review comments have been addressed before merging.
# A comment is considered "addressed" if it has at least one SUBSTANTIVE reply.
#
# Low-effort replies like "Acknowledged", "OK", "Understood" etc. are NOT
# considered valid replies - they don't add value to the review process.
#
# Usage:
#   GITHUB_TOKEN=xxx PR_NUMBER=123 ./check-review-comments.sh

set -euo pipefail

# Patterns for low-effort replies that don't count as real responses
# These are case-insensitive and match the entire reply (with optional punctuation)
LOW_EFFORT_PATTERNS=(
    "acknowledged"
    "ack"
    "ok"
    "okay"
    "understood"
    "noted"
    "done"
    "fixed"
    "will do"
    "will fix"
    "got it"
    "thanks"
    "thank you"
    "ty"
    "thx"
    "yes"
    "no"
    "sure"
    "agreed"
    "makes sense"
    "good point"
    "right"
    "correct"
    "i see"
    "see above"
    "addressed"
    "updated"
    "changed"
    "applied"
)

# Check if a reply is low-effort (returns 0 if low-effort, 1 if substantive)
is_low_effort_reply() {
    local reply="$1"
    # Normalize: lowercase, trim whitespace, remove trailing punctuation
    local normalized
    normalized=$(echo "$reply" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?]*$//')

    # Check against patterns
    for pattern in "${LOW_EFFORT_PATTERNS[@]}"; do
        if [[ "$normalized" == "$pattern" ]]; then
            return 0  # Is low-effort
        fi
    done

    # Also reject very short replies (less than 10 chars after normalization)
    if [[ ${#normalized} -lt 10 ]]; then
        return 0  # Is low-effort
    fi

    return 1  # Is substantive
}

# Validate required environment variables
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "GITHUB_TOKEN is required"
    exit 1
fi

if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "PR_NUMBER not set - skipping review comments check (not a pull request)"
    exit 0
fi

REPO="${GITHUB_REPOSITORY:-rediacc/console}"

echo "Checking review comments for PR #${PR_NUMBER}..."

# Fetch all review comments
COMMENTS=$(gh api "repos/${REPO}/pulls/${PR_NUMBER}/comments" --paginate 2>/dev/null || echo "[]")

if [[ "$COMMENTS" == "[]" ]]; then
    echo "No review comments found - OK"
    exit 0
fi

# Get all replies (comments with in_reply_to_id)
REPLIES=$(echo "$COMMENTS" | jq -r '[.[] | select(.in_reply_to_id != null)]')

# Get all original comments (no in_reply_to_id) - these need replies
ORIGINAL_COMMENTS=$(echo "$COMMENTS" | jq -r '[.[] | select(.in_reply_to_id == null)]')
ORIGINAL_COUNT=$(echo "$ORIGINAL_COMMENTS" | jq 'length')

if [[ "$ORIGINAL_COUNT" -eq 0 ]]; then
    echo "No review comments requiring replies - OK"
    exit 0
fi

# Build a map of original comment IDs to their substantive reply status
declare -A HAS_SUBSTANTIVE_REPLY

# Check each reply to see if it's substantive
while IFS= read -r reply; do
    [[ -z "$reply" ]] && continue
    REPLY_TO_ID=$(echo "$reply" | jq -r '.in_reply_to_id')
    REPLY_BODY=$(echo "$reply" | jq -r '.body')

    # Check if this reply is substantive
    if ! is_low_effort_reply "$REPLY_BODY"; then
        HAS_SUBSTANTIVE_REPLY[$REPLY_TO_ID]=1
    fi
done < <(echo "$REPLIES" | jq -c '.[]')

# Check which original comments have no substantive replies
UNREPLIED=()
LOW_EFFORT_REPLIES=()
while IFS= read -r comment; do
    [[ -z "$comment" ]] && continue
    COMMENT_ID=$(echo "$comment" | jq -r '.id')
    COMMENT_PATH=$(echo "$comment" | jq -r '.path')
    COMMENT_LINE=$(echo "$comment" | jq -r '.line // .original_line // "N/A"')
    COMMENT_AUTHOR=$(echo "$comment" | jq -r '.user.login')
    COMMENT_BODY=$(echo "$comment" | jq -r '.body' | head -c 100)

    # Check if this comment has a substantive reply
    if [[ -z "${HAS_SUBSTANTIVE_REPLY[$COMMENT_ID]:-}" ]]; then
        # Check if it has any reply at all (to distinguish unreplied vs low-effort)
        HAS_ANY_REPLY=$(echo "$REPLIES" | jq -r "[.[] | select(.in_reply_to_id == $COMMENT_ID)] | length")
        if [[ "$HAS_ANY_REPLY" -gt 0 ]]; then
            LOW_EFFORT_REPLIES+=("  - ${COMMENT_PATH}:${COMMENT_LINE} by @${COMMENT_AUTHOR}")
            LOW_EFFORT_REPLIES+=("    \"${COMMENT_BODY}...\"")
            LOW_EFFORT_REPLIES+=("    (Reply was low-effort - please provide a substantive response)")
        else
            UNREPLIED+=("  - ${COMMENT_PATH}:${COMMENT_LINE} by @${COMMENT_AUTHOR}")
            UNREPLIED+=("    \"${COMMENT_BODY}...\"")
        fi
    fi
done < <(echo "$ORIGINAL_COMMENTS" | jq -c '.[]')

if [[ ${#UNREPLIED[@]} -eq 0 ]] && [[ ${#LOW_EFFORT_REPLIES[@]} -eq 0 ]]; then
    echo "All ${ORIGINAL_COUNT} review comments have been addressed with substantive replies - OK"
    exit 0
fi

# Found issues
HAS_ISSUES=false
echo ""
echo "============================================================"
echo "  Review Comments Require Attention"
echo "============================================================"

if [[ ${#UNREPLIED[@]} -gt 0 ]]; then
    HAS_ISSUES=true
    UNREPLIED_COUNT=$(( ${#UNREPLIED[@]} / 2 ))
    echo ""
    echo "UNREPLIED COMMENTS (${UNREPLIED_COUNT}):"
    echo ""
    for line in "${UNREPLIED[@]}"; do
        echo "$line"
    done
fi

if [[ ${#LOW_EFFORT_REPLIES[@]} -gt 0 ]]; then
    HAS_ISSUES=true
    LOW_EFFORT_COUNT=$(( ${#LOW_EFFORT_REPLIES[@]} / 3 ))
    echo ""
    echo "LOW-EFFORT REPLIES (${LOW_EFFORT_COUNT}):"
    echo "These replies don't count as addressing the feedback:"
    echo ""
    for line in "${LOW_EFFORT_REPLIES[@]}"; do
        echo "$line"
    done
fi

echo ""
echo "------------------------------------------------------------"
echo "Please address all review comments with SUBSTANTIVE replies."
echo ""
echo "Low-effort replies like 'Acknowledged', 'OK', 'Done', 'Fixed'"
echo "etc. are NOT accepted. Explain what you did or why you"
echo "disagree with the feedback."
echo ""
echo "Examples of good replies:"
echo "  - 'Fixed by adding null check in validateInput()'"
echo "  - 'Refactored to use the existing helper as suggested'"
echo "  - 'Keeping as-is because X needs to happen before Y due to...'"
echo ""
echo "To reply using gh CLI:"
echo ""
echo "  gh api repos/${REPO}/pulls/${PR_NUMBER}/comments \\"
echo "    --jq '.[] | select(.in_reply_to_id == null) | {id, path, line, body}'"
echo ""
echo "  gh api repos/${REPO}/pulls/comments/{COMMENT_ID}/replies \\"
echo "    -X POST -f body=\"Your substantive reply here\""
echo ""
echo "Or reply directly on GitHub:"
echo "  https://github.com/${REPO}/pull/${PR_NUMBER}"
echo "------------------------------------------------------------"

if [[ "$HAS_ISSUES" == "true" ]]; then
    exit 1
fi
exit 0
