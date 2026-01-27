#!/bin/bash
# Check for unreplied review comments on pull requests
#
# This script ensures all review comments have been addressed before merging.
# A comment is considered "addressed" if it has at least one reply.
#
# Usage:
#   GITHUB_TOKEN=xxx PR_NUMBER=123 ./check-review-comments.sh

set -euo pipefail

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

# Get all comment IDs that are replies (have in_reply_to_id)
REPLY_TO_IDS=$(echo "$COMMENTS" | jq -r '[.[] | select(.in_reply_to_id != null) | .in_reply_to_id] | unique | .[]')

# Get all original comments (no in_reply_to_id) - these need replies
ORIGINAL_COMMENTS=$(echo "$COMMENTS" | jq -r '[.[] | select(.in_reply_to_id == null)]')
ORIGINAL_COUNT=$(echo "$ORIGINAL_COMMENTS" | jq 'length')

if [[ "$ORIGINAL_COUNT" -eq 0 ]]; then
    echo "No review comments requiring replies - OK"
    exit 0
fi

# Check which original comments have no replies
UNREPLIED=()
while IFS= read -r comment; do
    COMMENT_ID=$(echo "$comment" | jq -r '.id')
    COMMENT_PATH=$(echo "$comment" | jq -r '.path')
    COMMENT_LINE=$(echo "$comment" | jq -r '.line // .original_line // "N/A"')
    COMMENT_AUTHOR=$(echo "$comment" | jq -r '.user.login')
    COMMENT_BODY=$(echo "$comment" | jq -r '.body' | head -c 100)

    # Check if this comment ID appears in the reply_to_ids
    if ! echo "$REPLY_TO_IDS" | grep -q "^${COMMENT_ID}$"; then
        UNREPLIED+=("  - ${COMMENT_PATH}:${COMMENT_LINE} by @${COMMENT_AUTHOR}")
        UNREPLIED+=("    \"${COMMENT_BODY}...\"")
    fi
done < <(echo "$ORIGINAL_COMMENTS" | jq -c '.[]')

if [[ ${#UNREPLIED[@]} -eq 0 ]]; then
    echo "All ${ORIGINAL_COUNT} review comments have been addressed - OK"
    exit 0
fi

# Found unreplied comments
UNREPLIED_COUNT=$(( ${#UNREPLIED[@]} / 2 ))
echo ""
echo "============================================================"
echo "  Review Comments Require Attention"
echo "============================================================"
echo ""
echo "Found ${UNREPLIED_COUNT} review comment(s) without replies:"
echo ""
for line in "${UNREPLIED[@]}"; do
    echo "$line"
done
echo ""
echo "------------------------------------------------------------"
echo "Please address all review comments before merging."
echo ""
echo "To reply using gh CLI:"
echo ""
echo "  gh api repos/${REPO}/pulls/${PR_NUMBER}/comments \\"
echo "    --jq '.[] | select(.in_reply_to_id == null) | {id, path, line, body}'"
echo ""
echo "  gh api repos/${REPO}/pulls/comments/{COMMENT_ID}/replies \\"
echo "    -X POST -f body=\"Your reply here\""
echo ""
echo "Or reply directly on GitHub:"
echo "  https://github.com/${REPO}/pull/${PR_NUMBER}"
echo "------------------------------------------------------------"
exit 1
