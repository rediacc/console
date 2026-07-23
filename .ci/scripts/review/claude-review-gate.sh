#!/bin/bash
# Gate for the automated Claude PR review (claude-review.yml), prompt assembly,
# and the reviewed-SHA marker upsert.
#
# INVARIANT (operator ruling 2026-07-22): a review fires ONLY for an open,
# non-draft, same-repo PR whose CURRENT head SHA has green CI at decision
# time, that is not already marked reviewed, and whose delta since the last
# reviewed SHA is not submodule pointer bumps only. A red push after a review
# gets no re-review until a later push completes green.
#
# Gate mode (default):
#   Env: GH_TOKEN GITHUB_REPOSITORY GITHUB_OUTPUT EVENT_NAME
#        workflow_run:  WR_EVENT WR_CONCLUSION WR_HEAD_BRANCH WR_HEAD_SHA
#        pull_request:  PR_NUMBER PR_HEAD_SHA
#   Emits to $GITHUB_OUTPUT: go, pr_number, head_sha, last_reviewed_sha,
#   and (when go=true) a heredoc `prompt` assembled from prompts/initial.md
#   or prompts/followup.md.
# Mark mode (--mark): upsert the marker comment AFTER a successful review.
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA
#
# Local dry-run (read-only):
#   GH_TOKEN=$(gh auth token) GITHUB_REPOSITORY=rediacc/console \
#   EVENT_NAME=pull_request PR_NUMBER=531 PR_HEAD_SHA=<sha> \
#   GITHUB_OUTPUT=/dev/stdout .ci/scripts/review/claude-review-gate.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd jq

MARKER_PREFIX='<!-- claude-reviewed:'

# Newest marker comment's SHA. With `gh api --paginate`, --jq runs PER PAGE,
# so stream matching bodies flat and let the caller take the last line.
last_marker_sha() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$MARKER_PREFIX\")) | .body" 2>/dev/null |
        tail -n 1 | sed -n 's/.*claude-reviewed: \([0-9a-f]\{40\}\).*/\1/p'
}

last_marker_id() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$MARKER_PREFIX\")) | .id" 2>/dev/null |
        tail -n 1
}

# emit <go> <pr> <head_sha> <last_sha> <reason>  -- terminal.
emit() {
    {
        echo "go=$1"
        echo "pr_number=$2"
        echo "head_sha=$3"
        echo "last_reviewed_sha=$4"
    } >>"$GITHUB_OUTPUT"
    log_info "go=$1 pr=${2:-?} head=${3:-?} last=${4:-<none>} -- $5"
    exit 0
}

# Turn budget scaled to diff size. Turns are the lesser wall (context is the
# real one -- the prompt's breadth-first rule handles that); this keeps a
# 100K-line consolidation from starving at a budget sized for a 500-line fix.
# The first live review burned 30 turns on READING a 90-file diff and posted
# nothing.
emit_review_turns() {
    local changed
    changed=$(gh pr view "$1" --repo "$GITHUB_REPOSITORY" \
        --json additions,deletions --jq '.additions + .deletions' 2>/dev/null) || changed=0
    local turns=50
    if [[ "${changed:-0}" -ge 30000 ]]; then
        turns=140
    elif [[ "${changed:-0}" -ge 5000 ]]; then
        turns=80
    fi
    echo "review_turns=$turns" >>"$GITHUB_OUTPUT"
    log_info "diff size ${changed:-0} lines -> review_turns=$turns"
}

# emit_prompt <template>  -- substitutes the {{...}} placeholders.
emit_prompt() {
    {
        echo "prompt<<CLAUDE_REVIEW_PROMPT_EOF"
        sed -e "s|{{REPO}}|${GITHUB_REPOSITORY}|g" \
            -e "s|{{PR_NUMBER}}|${pr}|g" \
            -e "s|{{HEAD_SHA}}|${head_sha}|g" \
            -e "s|{{LAST_REVIEWED_SHA}}|${last_sha}|g" \
            "$1"
        echo "CLAUDE_REVIEW_PROMPT_EOF"
    } >>"$GITHUB_OUTPUT"
}

if [[ "${1:-}" == "--mark" ]]; then
    require_var PR_NUMBER
    require_var HEAD_SHA
    # A marker is a CLAIM that a review happened. Step success alone proved
    # false once: the reviewer "succeeded" with 36 permission denials and
    # posted nothing, and the marker then suppressed the retry. Only mark if
    # a NON-marker comment or an inline review comment landed recently.
    # --paginate + stream-count: without it GitHub returns the OLDEST page
    # only, so on a >100-comment PR a just-posted review is invisible and
    # this guard would refuse to mark forever (found by the automated review
    # itself, PR #531 first pass). Per-page --jq emits matches as lines;
    # wc -l totals across pages -- same pattern as last_marker_sha above.
    recent=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$MARKER_PREFIX\") | not)
                  | select(.user.login | contains(\"github-actions\"))
                  | select(.created_at > (now - 3600 | todate)) | .id" 2>/dev/null | wc -l)
    inline=$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/comments" --paginate \
        --jq ".[] | select(.user.login | contains(\"github-actions\"))
                  | select(.created_at > (now - 3600 | todate)) | .id" 2>/dev/null | wc -l)
    if [[ "${recent:-0}" -eq 0 && "${inline:-0}" -eq 0 ]]; then
        log_error "review step reported success but posted NOTHING in the last hour; refusing to mark ${HEAD_SHA:0:7} (SHA stays retryable)"
        exit 1
    fi
    body="${MARKER_PREFIX} ${HEAD_SHA} -->
Automated Claude review completed for commit ${HEAD_SHA:0:7}."
    comment_id=$(last_marker_id "$PR_NUMBER")
    if [[ -n "$comment_id" ]]; then
        gh api -X PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${comment_id}" \
            -f body="$body" >/dev/null
        log_info "Updated marker comment $comment_id -> ${HEAD_SHA:0:7}"
    else
        gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
            -f body="$body" >/dev/null
        log_info "Created marker comment for ${HEAD_SHA:0:7}"
    fi
    exit 0
fi

require_var GITHUB_OUTPUT
log_step "Deciding whether a Claude review should run (event: ${EVENT_NAME:-unset})"

pr=""
head_sha=""
last_sha=""

case "${EVENT_NAME:-}" in
    workflow_run)
        [[ "${WR_EVENT:-}" == "pull_request" ]] || emit false "" "" "" "CI run was not a PR run"
        [[ "${WR_CONCLUSION:-}" == "success" ]] || emit false "" "" "" "CI run not green"
        # workflow_run.pull_requests[] is unreliable; resolve via the branch
        # and pin to the run's SHA. headRefOid == WR_HEAD_SHA is the "current
        # head is green RIGHT NOW" invariant: a superseded push fails it, so a
        # late-finishing green run for an old commit never reviews stale code.
        pr_json=$(gh pr list --repo "$GITHUB_REPOSITORY" --head "${WR_HEAD_BRANCH:-}" \
            --state open --json number,headRefOid,isDraft \
            --jq "[.[] | select(.headRefOid == \"${WR_HEAD_SHA:-}\")] | first // empty")
        [[ -n "$pr_json" ]] || emit false "" "" "" "no open PR currently at this head SHA"
        pr=$(jq -r '.number' <<<"$pr_json")
        [[ "$(jq -r '.isDraft' <<<"$pr_json")" == "false" ]] ||
            emit false "$pr" "" "" "PR is a draft"
        head_sha="${WR_HEAD_SHA}"
        ;;
    pull_request) # ready_for_review
        require_var PR_NUMBER
        require_var PR_HEAD_SHA
        pr="$PR_NUMBER"
        head_sha="$PR_HEAD_SHA"
        conclusion=$(gh api -X GET \
            "repos/${GITHUB_REPOSITORY}/commits/${head_sha}/check-runs" \
            -f check_name='CI Complete' \
            --jq '[.check_runs[] | select(.conclusion == "success")] | length' 2>/dev/null) ||
            emit false "$pr" "$head_sha" "" "check-runs lookup failed"
        [[ "${conclusion:-0}" -ge 1 ]] ||
            emit false "$pr" "$head_sha" "" "CI Complete is not green on the current head"
        ;;
    *)
        log_error "Unsupported EVENT_NAME: ${EVENT_NAME:-unset}"
        exit 1
        ;;
esac

last_sha=$(last_marker_sha "$pr")
if [[ -n "$last_sha" ]]; then
    [[ "$last_sha" != "$head_sha" ]] ||
        emit false "$pr" "$head_sha" "$last_sha" "head already reviewed"
    # Delta since the last ACTUALLY reviewed SHA (markers never advance on
    # skips). The compare API needs no local history; on failure we fail OPEN
    # into an incremental review rather than silently skipping. files[] caps
    # at 300 entries, which cannot mask an all-gitlink diff (those have at
    # most <submodule count> files).
    files_json=$(gh api "repos/${GITHUB_REPOSITORY}/compare/${last_sha}...${head_sha}" \
        --jq '[.files[]?.filename]' 2>/dev/null) || files_json=""
    if [[ -n "$files_json" ]]; then
        if [[ "$(jq 'length' <<<"$files_json")" -eq 0 ]]; then
            emit false "$pr" "$head_sha" "$last_sha" "empty diff since last reviewed SHA"
        fi
        submodule_paths=$(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null |
            awk '{print $2}' || true)
        non_gitlink=$(jq -r '.[]' <<<"$files_json" |
            grep -Fxv -f <(printf '%s\n' "$submodule_paths") || true)
        [[ -n "$non_gitlink" ]] ||
            emit false "$pr" "$head_sha" "$last_sha" "only submodule pointer bumps since ${last_sha:0:7}"
    else
        log_warn "compare ${last_sha:0:7}...${head_sha:0:7} failed -- reviewing anyway (incremental)"
    fi
    emit_review_turns "$pr"
    emit_prompt "$SCRIPT_DIR/prompts/followup.md"
    emit true "$pr" "$head_sha" "$last_sha" "follow-up review: delta since ${last_sha:0:7}"
fi

emit_review_turns "$pr"
emit_prompt "$SCRIPT_DIR/prompts/initial.md"
emit true "$pr" "$head_sha" "" "initial review: full PR diff"
