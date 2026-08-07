#!/bin/bash
# Check for unreplied review comments on pull requests
#
# This script ensures all review comments have been addressed before merging.
# A comment is considered "addressed" if it has at least one SUBSTANTIVE reply.
#
# Low-effort replies like "Acknowledged", "OK", "Understood" etc. are NOT
# considered valid replies - they don't add value to the review process.
#
# TWO SURFACES, because the review speaks on two endpoints:
#
#   1. INLINE review-thread comments -- repos/{REPO}/pulls/{PR}/comments.
#      Threaded: a reply carries in_reply_to_id, so "addressed" is local.
#
#   2. The TOP-LEVEL review summary -- repos/{REPO}/issues/{PR}/comments.
#      This is where the verdict actually lives. The review prompt
#      (.ci/scripts/review/prompts/initial.md, step 5) tells the reviewer to
#      "Finish with ONE summary comment via gh pr comment", carrying the
#      verdict, the severity-ordered defects, the nits, and the coverage map.
#      Only the top-N findings are ever mirrored inline (claude-review-gate.sh
#      --post-findings caps at 20 and silently skips any line not in the diff),
#      so the summary is strictly the larger surface, not a duplicate of it.
#
# THIS GATE READ ONLY SURFACE 1 UNTIL 2026-08-05, and that is exactly the
# repo's recurring class: a check that cannot see the thing it is checking.
# Live proof, PR #551: the reviewer posted issue comment 5189236393
# ("## Review verdict: approve with one correctness finding to fix", 8141
# chars, github-actions[bot]); nobody answered it; this gate reported the PR
# clean and the Review Gate went green. The sibling gate
# check-review-report-replies.sh does read issues/{PR}/comments, but it only
# matches the pipeline's OWN wrapper comment ("**Claude finished ..."), and on
# #551 that wrapper carried neither the findings fence nor a "### Review"
# heading -- so it found no report and exited 0 vacuously too.
#
# Usage:
#   GH_TOKEN=xxx PR_NUMBER=123 ./check-review-comments.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: gh_json and log_error are needed so an API failure cannot be mistaken for a PR with no review comments
source "$SCRIPT_DIR/../lib/common.sh"

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

# is_low_effort_reply <reply> [min-chars]
#
# Returns 0 if low-effort, 1 if substantive. min-chars defaults to 10, the
# floor a single inline thread has always used. A reply to the whole review
# summary answers many findings at once, so that caller passes a higher floor
# (see SUMMARY_MIN_CHARS below).
is_low_effort_reply() {
    local reply="$1"
    local min_chars="${2:-10}"
    # Normalize: lowercase, trim whitespace, remove trailing punctuation
    local normalized
    normalized=$(echo "$reply" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?]*$//')

    # Check against patterns
    for pattern in "${LOW_EFFORT_PATTERNS[@]}"; do
        if [[ "$normalized" == "$pattern" ]]; then
            return 0 # Is low-effort
        fi
    done

    # Also reject replies shorter than the caller's floor
    if [[ ${#normalized} -lt $min_chars ]]; then
        return 0 # Is low-effort
    fi

    return 1 # Is substantive
}

# A reply to the whole summary must clear a higher bar than a one-line inline
# thread. Same floor check-review-report-replies.sh uses for the same reason.
SUMMARY_MIN_CHARS=30

# ...and one that only clears that floor still has to prove it is ABOUT the
# review, which it does one of two ways (see the reply rule below).
SUMMARY_LONGFORM_CHARS=200

# Validate required environment variables (gh CLI prefers GH_TOKEN over GITHUB_TOKEN)
if [[ -z "${GH_TOKEN:-}" ]] && [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "GH_TOKEN or GITHUB_TOKEN is required"
    exit 1
fi

if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "PR_NUMBER not set - skipping review comments check (not a pull request)"
    exit 0
fi

REPO="${GITHUB_REPOSITORY:-rediacc/console}"

echo "Checking review comments for PR #${PR_NUMBER}..."

UNREPLIED=()
LOW_EFFORT_REPLIES=()
ORIGINAL_COUNT=0

# ===========================================================================
# SURFACE 1 -- inline review threads (repos/{REPO}/pulls/{PR}/comments)
# ===========================================================================

# Fetch all review comments.
#
# FAIL CLOSED. This used to be `|| echo "[]"`, so a rate limit, an expired token
# or a network blip produced the same value as a PR with no review comments: the
# gate printed "No review comments found - OK" and exited 0. This is a
# merge-blocking gate, so a probe failure must block the merge, not wave it
# through. gh_json retries twice before giving up.
if ! COMMENTS=$(gh_json "review comments for PR #${PR_NUMBER}" -- \
    api "repos/${REPO}/pulls/${PR_NUMBER}/comments" --paginate); then
    echo "" >&2
    echo "Cannot certify that review comments were addressed, because the comments" >&2
    echo "could not be fetched. Failing closed rather than reporting a clean PR." >&2
    exit 1
fi

if [[ "$COMMENTS" == "[]" ]]; then
    echo "No inline review comments found - OK"
else
    # Get all replies (comments with in_reply_to_id)
    REPLIES=$(echo "$COMMENTS" | jq -r '[.[] | select(.in_reply_to_id != null)]')

    # Get all original comments (no in_reply_to_id) - these need replies
    ORIGINAL_COMMENTS=$(echo "$COMMENTS" | jq -r '[.[] | select(.in_reply_to_id == null)]')
    ORIGINAL_COUNT=$(echo "$ORIGINAL_COMMENTS" | jq 'length')

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
        echo "All ${ORIGINAL_COUNT} inline review comments have been addressed with substantive replies - OK"
    fi
fi

# ===========================================================================
# SURFACE 2 -- the top-level review summary (repos/{REPO}/issues/{PR}/comments)
# ===========================================================================

# Same fail-closed contract as surface 1: an unreadable comment list must not
# be indistinguishable from "the review posted no summary".
if ! ISSUE_COMMENTS=$(gh_json "issue comments for PR #${PR_NUMBER}" -- \
    api "repos/${REPO}/issues/${PR_NUMBER}/comments" --paginate); then
    echo "" >&2
    echo "Cannot certify that the review summary was addressed, because the PR's" >&2
    echo "issue comments could not be fetched. Failing closed." >&2
    exit 1
fi

# IDENTIFYING THE SUMMARY. issues/{PR}/comments carries ALL PR chatter --
# operator notes, watchdog output, deploy-preview links, CI reports. Blocking
# on every unanswered comment would be intolerable and would get this gate
# suppressed within a day, so the summary is picked out STRUCTURALLY, by the
# marker the pipeline already emits:
#
#   author contains "github-actions"  AND  body contains "json:review-findings"
#
# That is not a heuristic invented here -- it is verbatim the selector
# claude-review-gate.sh --post-findings uses to locate the same comment and
# parse its findings array. If the fence name ever drifts, inline posting
# breaks in the same commit, so the two cannot silently disagree.
# (test-review-status.sh asserts the needle still exists in the gate script.)
#
# The verdict heading is a SECOND, weaker key for a review that produced no
# fence (nothing to anchor, or a budget halt mid-report): live shape on #551
# was a body opening "## Review verdict: approve with one correctness finding".
#
# Excluded: bodies starting with "<!--". Those are the pipeline's bookkeeping
# comments -- MARKER_PREFIX ("<!-- claude-reviewed: <sha> -->") and
# ATTEMPT_PREFIX ("<!-- claude-review-attempt: ...") -- which are state, not
# findings, and must never be mistaken for a verdict awaiting an answer.
#
# Only the NEWEST match is gated, matching check-review-report-replies.sh: each
# review pass supersedes the previous summary, and re-litigating superseded
# verdicts would make a re-reviewed PR permanently unmergeable.
SUMMARY=$(echo "$ISSUE_COMMENTS" | jq -c '
    [ .[]
      | select(.user.login | contains("github-actions"))
      | select((.body | startswith("<!--")) | not)
      | select((.body | contains("json:review-findings"))
               or (.body | test("^[[:space:]]*#{1,3}[[:space:]]*Review verdict"; "i")))
    ] | sort_by(.created_at) | last // empty')

SUMMARY_UNADDRESSED=false
if [[ -z "$SUMMARY" ]]; then
    echo "No top-level review summary found - OK"
else
    SUMMARY_ID=$(echo "$SUMMARY" | jq -r '.id')
    SUMMARY_AUTHOR=$(echo "$SUMMARY" | jq -r '.user.login')
    SUMMARY_CREATED=$(echo "$SUMMARY" | jq -r '.created_at')
    # Bash slice rather than `| head -c`: a summary is thousands of characters,
    # and head closing the pipe early would SIGPIPE the upstream under pipefail.
    SUMMARY_HEAD=$(echo "$SUMMARY" | jq -r '.body' | tr '\n' ' ')
    SUMMARY_HEAD="${SUMMARY_HEAD:0:120}"

    # WHAT COUNTS AS A REPLY. A top-level comment has no thread, so there is no
    # in_reply_to_id to look for. A later comment counts as an answer when ALL
    # of these hold:
    #
    #   (a) a DIFFERENT author from the reviewer. This is the load-bearing
    #       clause, not politeness: the pipeline posts several comments in a
    #       row under the same identity, and on #551 the marker comment
    #       (5189238817, 250 chars) landed 14 SECONDS after the summary. With
    #       author ignored, the review would have "replied" to itself on every
    #       PR and this gate could never fire once.
    #   (b) posted AFTER it. Compared in jq, on the ISO-8601 strings GitHub
    #       returns, so bash's locale-dependent `>` is never involved.
    #   (c) substantive, i.e. past SUMMARY_MIN_CHARS and not a stock
    #       acknowledgement.
    #   (d) demonstrably ABOUT the review -- either it cites the summary's id
    #       (or its #issuecomment-<id> anchor), or it is long-form
    #       (SUMMARY_LONGFORM_CHARS+), the shape a genuine per-finding response
    #       takes. Without (d) an unrelated "preview looks good, merging
    #       tomorrow" would clear the gate.
    #
    # (d) deliberately does NOT hard-require the id, unlike
    # check-review-report-replies.sh. The live answer on #551 (5190623031, 2856
    # chars, per-finding) cites no id, and a rule that calls that unaddressed
    # is a rule that would be turned off.
    #
    # Accepted imprecision: another bot with a different login could satisfy
    # (a). Narrowing that further would need an identity allowlist, which buys
    # little -- the same-identity self-reply above is the failure that actually
    # happens.
    while IFS= read -r candidate; do
        [[ -z "$candidate" ]] && continue
        CAND_BODY=$(echo "$candidate" | jq -r '.body')
        if is_low_effort_reply "$CAND_BODY" "$SUMMARY_MIN_CHARS"; then
            continue
        fi
        if [[ "$CAND_BODY" == *"$SUMMARY_ID"* ]] || [[ ${#CAND_BODY} -ge $SUMMARY_LONGFORM_CHARS ]]; then
            SUMMARY_REPLY_ID=$(echo "$candidate" | jq -r '.id')
            break
        fi
    done < <(echo "$ISSUE_COMMENTS" | jq -c --arg author "$SUMMARY_AUTHOR" --arg ts "$SUMMARY_CREATED" '
        [ .[]
          | select(.user.login != $author)
          | select(.created_at > $ts)
        ] | sort_by(.created_at) | .[]')

    if [[ -n "${SUMMARY_REPLY_ID:-}" ]]; then
        echo "Top-level review summary (comment ${SUMMARY_ID}) answered by comment ${SUMMARY_REPLY_ID} - OK"
    else
        SUMMARY_UNADDRESSED=true
    fi
fi

if [[ ${#UNREPLIED[@]} -eq 0 ]] && [[ ${#LOW_EFFORT_REPLIES[@]} -eq 0 ]] &&
    [[ "$SUMMARY_UNADDRESSED" == "false" ]]; then
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
    UNREPLIED_COUNT=$((${#UNREPLIED[@]} / 2))
    echo ""
    echo "UNREPLIED COMMENTS (${UNREPLIED_COUNT}):"
    echo ""
    for line in "${UNREPLIED[@]}"; do
        echo "$line"
    done
fi

if [[ ${#LOW_EFFORT_REPLIES[@]} -gt 0 ]]; then
    HAS_ISSUES=true
    LOW_EFFORT_COUNT=$((${#LOW_EFFORT_REPLIES[@]} / 3))
    echo ""
    echo "LOW-EFFORT REPLIES (${LOW_EFFORT_COUNT}):"
    echo "These replies don't count as addressing the feedback:"
    echo ""
    for line in "${LOW_EFFORT_REPLIES[@]}"; do
        echo "$line"
    done
fi

if [[ ${#UNREPLIED[@]} -gt 0 ]] || [[ ${#LOW_EFFORT_REPLIES[@]} -gt 0 ]]; then
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
    echo "  # List unreplied comments (find the COMMENT_ID you need to reply to)"
    echo "  gh api repos/${REPO}/pulls/${PR_NUMBER}/comments \\"
    echo "    --jq '.[] | select(.in_reply_to_id == null) | {id, path, line, body}'"
    echo ""
    echo "  # Reply to a specific comment (NOTE: PR number is required in the path!)"
    echo "  gh api repos/${REPO}/pulls/${PR_NUMBER}/comments/{COMMENT_ID}/replies \\"
    echo "    -X POST -f body=\"Your substantive reply here\""
    echo ""
    echo "  # IMPORTANT: The endpoint is /pulls/{PR_NUMBER}/comments/{COMMENT_ID}/replies"
    echo "  # NOT /pulls/comments/{COMMENT_ID}/replies (this will return 404)"
    echo ""
    echo "Or reply directly on GitHub:"
    echo "  https://github.com/${REPO}/pull/${PR_NUMBER}"
    echo "------------------------------------------------------------"
fi

if [[ "$SUMMARY_UNADDRESSED" == "true" ]]; then
    HAS_ISSUES=true
    echo ""
    echo "UNANSWERED REVIEW SUMMARY (1):"
    echo ""
    echo "  - comment ${SUMMARY_ID} by @${SUMMARY_AUTHOR}, posted ${SUMMARY_CREATED}"
    echo "    https://github.com/${REPO}/pull/${PR_NUMBER}#issuecomment-${SUMMARY_ID}"
    echo "    \"${SUMMARY_HEAD}...\""
    echo ""
    echo "------------------------------------------------------------"
    echo "WHY THIS BLOCKS. The automated review posts its verdict, its"
    echo "severity-ordered defects, its nits and its coverage map as ONE"
    echo "top-level comment. Only the top findings are mirrored inline"
    echo "(capped at 20, and any whose line is not in the diff is dropped),"
    echo "so resolving the inline threads does NOT address the summary."
    echo "Top-level comments have no thread and nothing to resolve, so the"
    echo "only evidence anyone read it is a later comment answering it."
    echo "There is none."
    echo ""
    echo "WHAT A SUBSTANTIVE REPLY MUST CONTAIN. Go finding by finding, in"
    echo "the summary's own order, and for each one state exactly one of:"
    echo "  - fixed: what changed and in which commit"
    echo "  - deferred: where it is tracked (issue or worklist id) and why"
    echo "  - disagreed: the reason, concretely, not 'out of scope'"
    echo "Answer the nits and the coverage map too: if the summary says an"
    echo "area went unreviewed, say whether that is acceptable and why."
    echo "It must be posted by someone other than @${SUMMARY_AUTHOR} (a"
    echo "second comment from the reviewer is not an answer to the first),"
    echo "and it must either cite ${SUMMARY_ID} or run past ${SUMMARY_LONGFORM_CHARS} characters."
    echo ""
    echo "To answer using gh CLI:"
    echo ""
    echo "  # 1. Read the full summary first - the excerpt above is 120 chars"
    echo "  gh api repos/${REPO}/issues/comments/${SUMMARY_ID} --jq .body"
    echo ""
    echo "  # 2. Post the answer as a NEW top-level comment"
    echo "  gh api repos/${REPO}/issues/${PR_NUMBER}/comments -X POST \\"
    echo "    -f body=\"Re: review summary ${SUMMARY_ID}"
    echo ""
    echo "  - <finding 1 title>: fixed in <sha> - <what changed>"
    echo "  - <finding 2 title>: not changing - <why>"
    echo "  - <nit>: deferred to <issue/worklist id>"
    echo ""
    echo "  Coverage: <the areas the summary flagged as unreviewed, and your call on them>\""
    echo ""
    echo "  # IMPORTANT: a top-level comment has NO replies endpoint. All three"
    echo "  # of these are wrong, and the first two return 404 (verified):"
    echo "  #   repos/${REPO}/issues/${PR_NUMBER}/comments/${SUMMARY_ID}/replies   -> 404"
    echo "  #   repos/${REPO}/pulls/${PR_NUMBER}/comments/${SUMMARY_ID}/replies    -> 404"
    echo "  #     (that path is real, but only for INLINE comment ids;"
    echo "  #      ${SUMMARY_ID} is an ISSUE comment id and is not found there)"
    echo "  #   repos/${REPO}/issues/comments/${SUMMARY_ID}  -> GET/PATCH only. That"
    echo "  #     is the EDIT endpoint for the summary itself; posting there would"
    echo "  #     overwrite the review, not answer it."
    echo ""
    echo "Or comment directly on GitHub:"
    echo "  https://github.com/${REPO}/pull/${PR_NUMBER}#issuecomment-${SUMMARY_ID}"
    echo "------------------------------------------------------------"
fi

if [[ "$HAS_ISSUES" == "true" ]]; then
    exit 1
fi
exit 0
