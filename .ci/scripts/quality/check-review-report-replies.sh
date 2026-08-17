#!/bin/bash
# Check that the newest automated review REPORT (issue comment) got a reply.
#
# The Claude review pipeline posts on two surfaces:
#   1. Inline code comments (pulls/comments)  -> gated by check-review-comments.sh
#   2. Top-level issue comments               -> gated HERE and by that same script
#
# Issue comments are flat: GitHub has no resolve/reply threading for them, so
# without a gate their findings can be silently ignored.
#
# WHY TWO SCRIPTS READ THE TOP-LEVEL SURFACE, AND WHY THAT IS NOT DUPLICATION.
# One review pass can leave TWO different top-level comments, produced by two
# different code paths and recognised by two different producer constants:
#
#   - The reviewer's own summary, posted with `gh pr comment` because the
#     prompt (review/prompts/initial.md:39) tells it to. Recognised by the
#     ```json:review-findings fence. check-review-comments.sh owns that one.
#   - The pipeline's report wrapper, posted by claude-review-gate.sh
#     --post-report, or the action's own tracking comment. Recognised by the
#     "**Claude finished" header. THIS script owns that one.
#
# Neither key implies the other. On PR #551 the wrapper (5189238220) carried no
# fence at all, and the fence lived only in the reviewer's own summary
# (5189236393). A gate keyed on one is blind to a pass that produced only the
# other, so the two scripts are complementary coverage, not two checks of the
# same thing.
#
# The obligation, though, is ONE: answer this review pass. Both scripts
# therefore apply the SAME reply rule (below), so a single substantive reply
# posted after both comments satisfies both gates. test-review-status.sh drives
# both scripts against one fixture and asserts exactly that, because the moment
# they disagree this stops being coverage and starts being a tax.
#
# THE BUG THIS FILE CARRIED UNTIL 2026-08-05. The report was matched by the
# "**Claude finished" header AND-ed with "carries the findings fence or a
# '### Review' heading". That second clause is a guess about the report's
# WORDING, not a constant any producer emits -- and the producer does not emit
# it: --post-report wraps whatever the model's final text happened to be. On
# #551 that text was a short wrap-up ("Posted the review. Summary of what I
# did:") with neither marker, so this gate found no report and exited 0 while
# an 8141-char verdict sat unanswered. Keyed off the header alone -- which IS a
# producer constant, written verbatim at claude-review-gate.sh:188 -- it fires.
#
# Usage:
#   GH_TOKEN=xxx PR_NUMBER=123 ./check-review-report-replies.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: gh_json is needed so an API failure cannot be mistaken for a PR with no review report
source "$SCRIPT_DIR/../lib/common.sh"

# The report header. A PRODUCER CONSTANT, not a wording guess:
# claude-review-gate.sh:188 writes it verbatim, and the Claude Code action's own
# tracking comment uses the same prefix (comment-logic.ts, quoted at
# claude-review-gate.sh:153). An in-progress comment cannot match it -- the word
# is "finished".
REPORT_PREFIX='**Claude finished'

# Low-effort filter, same philosophy as check-review-comments.sh: a reply must
# say what was done (or why not), not just acknowledge.
LOW_EFFORT_PATTERNS=(
    "acknowledged" "ack" "ok" "okay" "understood" "noted" "done" "fixed"
    "will do" "will fix" "got it" "thanks" "thank you" "ty" "thx" "yes" "no"
    "sure" "agreed" "makes sense" "good point" "right" "correct" "i see"
    "see above" "addressed" "updated" "changed" "applied"
)

# THESE TWO MUST MATCH check-review-comments.sh's variables of the same names.
# That is what makes one reply clear both gates; test-review-status.sh parses
# both files and fails if they drift apart.
SUMMARY_MIN_CHARS=30
SUMMARY_LONGFORM_CHARS=200

# is_low_effort_reply <reply> [min-chars]
is_low_effort_reply() {
    local min_chars="${2:-$SUMMARY_MIN_CHARS}"
    local normalized
    normalized=$(echo "$1" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?]*$//')
    for pattern in "${LOW_EFFORT_PATTERNS[@]}"; do
        [[ "$normalized" == "$pattern" ]] && return 0
    done
    [[ ${#normalized} -lt $min_chars ]] && return 0
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

# FAIL CLOSED. This used to be `gh api ... 2>/dev/null | jq -s 'add // []'`,
# which maps an unreachable API onto the same value as a PR with no report.
# Under `set -o pipefail` that aborted with no explanation rather than passing
# silently, which is safe but unreadable, and it never retried a transient
# blip. gh_json retries twice and names the probe that failed.
if ! COMMENTS=$(gh_json "issue comments for PR #${PR_NUMBER}" -- \
    api "repos/${REPO}/issues/${PR_NUMBER}/comments" --paginate); then
    # A SECOND INSTRUMENT, not a softer verdict: it keeps this gate RUNNABLE
    # while the REST API is degraded, and a gate that cannot run does not judge
    # a merge, it blocks every one of them.
    #
    # Added during the GitHub incident of 2026-08-17 (status page: "Issues is
    # experiencing degraded performance", ~20% error rates site-wide). This
    # endpoint returned 404 for repos/rediacc/{renet,account,elite}/issues/<n>
    # while the public rediacc/console answered 200, which looks exactly like a
    # private-repo permissions property and is NOT one: sampled 8x per repo, the
    # private repo passed ONCE and failed seven times while the public one
    # passed 8/8. One success is the whole proof -- a token that lacked access
    # would have failed all eight. So the split was load, not visibility, and
    # the earlier version of this comment said otherwise. Do not "fix" a token.
    #
    # GraphQL reads the same comment thread and kept answering throughout. It is
    # a different transport for identical data, so it cannot turn a failing PR
    # into a passing one: if BOTH instruments fail we still fail closed below.
    #
    # Two shape notes, both already tolerated by the logic beneath: GraphQL
    # reports the bot as `github-actions` where REST says `github-actions[bot]`
    # (the filter uses contains(), so either matches), and `first: 100` caps a
    # single page -- far above any real PR here, and an under-read can only
    # HIDE a reply, i.e. fail closed, never invent one.
    GQL='query($owner:String!,$name:String!,$number:Int!){repository(owner:$owner,name:$name){pullRequest(number:$number){comments(first:100){nodes{databaseId body createdAt author{login}}}}}}'
    if ! RAW_GQL=$(gh_json "issue comments for PR #${PR_NUMBER} (graphql fallback)" -- \
        api graphql -f query="$GQL" \
        -f owner="${REPO%%/*}" -f name="${REPO##*/}" -F number="${PR_NUMBER}"); then
        echo "" >&2
        echo "Cannot certify that the review report was addressed, because the PR's" >&2
        echo "issue comments could not be fetched by EITHER the REST issues endpoint" >&2
        echo "or the GraphQL fallback. Failing closed rather than reporting a clean PR." >&2
        exit 1
    fi
    COMMENTS=$(echo "$RAW_GQL" | jq -c '[.data.repository.pullRequest.comments.nodes[]
        | {id: .databaseId, body: .body, created_at: .createdAt,
           user: {login: (.author.login // "")}}]')
fi

# Newest finished report: posted by github-actions, carrying the report header.
#
# NOTHING ELSE IS AND-ED ON. Every extra clause is another chance to describe
# the report differently from the way it is produced, which is exactly how this
# gate went blind. Only the NEWEST is gated: each pass supersedes the previous
# report, and re-litigating superseded ones would make a re-reviewed PR
# permanently unmergeable.
REPORT=$(echo "$COMMENTS" | jq -c --arg prefix "$REPORT_PREFIX" '
    [.[] | select(.user.login | contains("github-actions"))
         | select(.body | startswith($prefix))]
    | sort_by(.created_at) | last // empty')

if [[ -z "$REPORT" ]]; then
    echo "No finished review report found - OK"
    exit 0
fi

REPORT_ID=$(echo "$REPORT" | jq -r '.id')
REPORT_AUTHOR=$(echo "$REPORT" | jq -r '.user.login')
REPORT_CREATED=$(echo "$REPORT" | jq -r '.created_at')

# WHAT COUNTS AS A REPLY -- identical to check-review-comments.sh's rule for the
# top-level surface, so one reply clears both gates:
#
#   (a) a DIFFERENT author from the reporter. Load-bearing: the pipeline posts
#       several comments in a row under one identity (on #551 the reviewed-SHA
#       marker landed 4 seconds after this report and is long enough to clear
#       every substance test), so without this the review answers itself and
#       the gate can never fire.
#   (b) posted after it, compared in jq on GitHub's ISO-8601 strings, so bash's
#       locale-dependent `>` is never involved.
#   (c) substantive: past SUMMARY_MIN_CHARS and not a stock acknowledgement.
#   (d) demonstrably about the review: it cites the report id (or its
#       #issuecomment-<id> anchor), or it is long-form.
#
# (d) used to be a hard requirement to cite the id. It is relaxed for the same
# reason its sibling relaxed it: the real answer on #551 (5190623031, 2856
# chars, per-finding) cites no id, and a gate that calls that unaddressed is a
# gate that gets switched off.
REPLY_ID=""
while IFS= read -r candidate; do
    [[ -z "$candidate" ]] && continue
    CAND_BODY=$(echo "$candidate" | jq -r '.body')
    if is_low_effort_reply "$CAND_BODY" "$SUMMARY_MIN_CHARS"; then
        continue
    fi
    if [[ "$CAND_BODY" == *"$REPORT_ID"* ]] || [[ ${#CAND_BODY} -ge $SUMMARY_LONGFORM_CHARS ]]; then
        REPLY_ID=$(echo "$candidate" | jq -r '.id')
        break
    fi
done < <(echo "$COMMENTS" | jq -c --arg author "$REPORT_AUTHOR" --arg ts "$REPORT_CREATED" '
    [ .[]
      | select(.user.login != $author)
      | select(.created_at > $ts)
    ] | sort_by(.created_at) | .[]')

if [[ -n "$REPLY_ID" ]]; then
    echo "Newest review report (comment ${REPORT_ID}) answered by comment ${REPLY_ID} - OK"
    exit 0
fi

echo ""
echo "============================================================"
echo "  Review Report Requires a Reply"
echo "============================================================"
echo ""
echo "The newest automated review report has not been addressed:"
echo ""
echo "  - comment ${REPORT_ID} by @${REPORT_AUTHOR}, posted ${REPORT_CREATED}"
echo "    https://github.com/${REPO}/pull/${PR_NUMBER}#issuecomment-${REPORT_ID}"
echo ""
echo "------------------------------------------------------------"
echo "WHY THIS BLOCKS. This is the pipeline's report for the head it"
echo "reviewed. It is a top-level comment, so it has no thread and"
echo "nothing to resolve: the only evidence anyone read it is a"
echo "later comment answering it. There is none."
echo ""
echo "READ THE REVIEWER'S OWN SUMMARY TOO. The same pass usually"
echo "posts a SEPARATE summary comment carrying the findings, and"
echo "this report can be just a wrap-up. List both before replying:"
echo ""
echo "  gh api repos/${REPO}/issues/${PR_NUMBER}/comments --paginate \\"
echo "    --jq '.[] | select(.user.login | test(\"github-actions\")) | {id, created_at}'"
echo ""
echo "WHAT A SUBSTANTIVE REPLY MUST CONTAIN. Go finding by finding"
echo "and for each one state exactly one of:"
echo "  - fixed: what changed and in which commit"
echo "  - deferred: where it is tracked (issue or worklist id) and why"
echo "  - disagreed: the reason, concretely, not 'out of scope'"
echo "It must be posted by someone other than @${REPORT_AUTHOR} (a"
echo "second comment from the pipeline is not an answer to the"
echo "first), and it must either cite ${REPORT_ID} or run past ${SUMMARY_LONGFORM_CHARS} characters."
echo ""
echo "ONE reply covers this AND check-review-comments.sh's summary"
echo "check, as long as it is posted after both comments."
echo ""
echo "To answer using gh CLI:"
echo ""
echo "  # 1. Read the full report first"
echo "  gh api repos/${REPO}/issues/comments/${REPORT_ID} --jq .body"
echo ""
echo "  # 2. Post the answer as a NEW top-level comment"
echo "  gh api repos/${REPO}/issues/${PR_NUMBER}/comments -X POST \\"
echo "    -f body=\"Re: review report ${REPORT_ID}"
echo ""
echo "  - <finding 1 title>: fixed in <sha> - <what changed>"
echo "  - <finding 2 title>: not changing - <why>"
echo "  - <nit>: deferred to <issue/worklist id>\""
echo ""
echo "  # IMPORTANT: a top-level comment has NO replies endpoint. Both of"
echo "  # these return 404 (verified against the live API):"
echo "  #   repos/${REPO}/issues/${PR_NUMBER}/comments/${REPORT_ID}/replies"
echo "  #   repos/${REPO}/pulls/${PR_NUMBER}/comments/${REPORT_ID}/replies"
echo "  #     (that path is real, but only for INLINE comment ids)"
echo "  # And repos/${REPO}/issues/comments/${REPORT_ID} is GET/PATCH only --"
echo "  # the EDIT endpoint for the report itself. Posting there would"
echo "  # overwrite the review rather than answer it."
echo ""
echo "Or comment directly on GitHub:"
echo "  https://github.com/${REPO}/pull/${PR_NUMBER}#issuecomment-${REPORT_ID}"
echo "------------------------------------------------------------"
exit 1
