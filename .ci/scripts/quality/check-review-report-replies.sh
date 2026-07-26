#!/bin/bash
# Check that the newest automated review REPORT (issue comment) got a reply.
#
# The Claude review pipeline posts two kinds of output on a PR:
#   1. Inline code comments (pulls/comments)  -> gated by check-review-comments.sh
#   2. A summary report as an ISSUE comment   -> gated HERE
#
# Issue comments are flat: GitHub has no resolve/reply threading for them, so
# without this gate the report's findings can be silently ignored. A report is
# "addressed" when a LATER issue comment references it by id (the literal
# comment id, or its #issuecomment-<id> anchor) with a substantive body.
#
# Only the NEWEST finished report is gated: each review pass supersedes the
# previous summary, and per-finding accountability is enforced separately by
# the inline-comment gate. In-progress tracking comments ("Claude is
# working...") never match the finished-report signature, so a running review
# cannot trip this gate.
#
# Usage:
#   GH_TOKEN=xxx PR_NUMBER=123 ./check-review-report-replies.sh

set -euo pipefail

# Low-effort filter, same philosophy as check-review-comments.sh: a reply must
# say what was done (or why not), not just acknowledge.
LOW_EFFORT_PATTERNS=(
    "acknowledged" "ack" "ok" "okay" "understood" "noted" "done" "fixed"
    "will do" "will fix" "got it" "thanks" "thank you" "ty" "thx" "yes" "no"
    "sure" "agreed" "makes sense" "good point" "right" "correct" "i see"
    "see above" "addressed" "updated" "changed" "applied"
)

is_low_effort_reply() {
    local normalized
    normalized=$(echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?]*$//')
    for pattern in "${LOW_EFFORT_PATTERNS[@]}"; do
        [[ "$normalized" == "$pattern" ]] && return 0
    done
    # A reply covering a multi-finding report needs more than a sentence
    # fragment; 30 chars is the floor, not the bar.
    [[ ${#normalized} -lt 30 ]] && return 0
    return 1
}

if [[ -z "${GH_TOKEN:-}" ]] && [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "GH_TOKEN or GITHUB_TOKEN is required"
    exit 1
fi

if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "PR_NUMBER not set - skipping review report reply check (not a pull request)"
    exit 0
fi

REPO="${GITHUB_REPOSITORY:-rediacc/console}"

echo "Checking review report replies for PR #${PR_NUMBER}..."

COMMENTS=$(gh api "repos/${REPO}/issues/${PR_NUMBER}/comments" --paginate 2>/dev/null | jq -s 'add // []')

# Newest finished report: posted by github-actions, finished (not the
# in-progress tracking state), carrying the report signature (the findings
# fence or a "### Review" heading -- the prompts mandate the fence).
REPORT=$(echo "$COMMENTS" | jq -r '
    [.[] | select(.user.login | contains("github-actions"))
         | select(.body | startswith("**Claude finished"))
         | select((.body | contains("json:review-findings")) or (.body | contains("### Review")))]
    | sort_by(.created_at) | last // empty')

if [[ -z "$REPORT" ]]; then
    echo "No finished review report found - OK"
    exit 0
fi

REPORT_ID=$(echo "$REPORT" | jq -r '.id')
REPORT_CREATED=$(echo "$REPORT" | jq -r '.created_at')

# Replies: later issue comments that reference the report id. The report
# comment is created when the review STARTS (track_progress updates it in
# place), so any reply necessarily postdates created_at.
REPLIES=$(echo "$COMMENTS" | jq -r --arg id "$REPORT_ID" --arg ts "$REPORT_CREATED" '
    [.[] | select(.id != ($id | tonumber))
         | select(.created_at > $ts)
         | select(.body | contains($id))]')

SUBSTANTIVE=0
while IFS= read -r body; do
    [[ -z "$body" ]] && continue
    if ! is_low_effort_reply "$body"; then
        SUBSTANTIVE=1
        break
    fi
done < <(echo "$REPLIES" | jq -r '.[].body' 2>/dev/null)

if [[ "$SUBSTANTIVE" -eq 1 ]]; then
    echo "Newest review report (comment ${REPORT_ID}) has a substantive reply - OK"
    exit 0
fi

REPLY_COUNT=$(echo "$REPLIES" | jq 'length')
echo ""
echo "============================================================"
echo "  Review Report Requires a Reply"
echo "============================================================"
echo ""
echo "The newest automated review report has not been addressed:"
echo "  https://github.com/${REPO}/pull/${PR_NUMBER}#issuecomment-${REPORT_ID}"
echo ""
if [[ "$REPLY_COUNT" -gt 0 ]]; then
    echo "Comments referencing it exist, but none are substantive."
    echo "Explain per finding what you did or why you disagree."
else
    echo "Post an issue comment that references the report id"
    echo "(${REPORT_ID}) and addresses its findings: what was fixed"
    echo "(with commits), what was deferred and where it is tracked,"
    echo "and what you disagree with and why."
fi
echo ""
echo "To reply using gh CLI:"
echo ""
echo "  gh api repos/${REPO}/issues/${PR_NUMBER}/comments \\"
echo "    -f body=\"Re: review report ${REPORT_ID} -- <per-finding response>\""
echo ""
exit 1
