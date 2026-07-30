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
# Record-invocation mode (--record-invocation): echo the claude_args the
#   workflow sent, because the action itself never logs them.
#   Env: CLAUDE_ARGS_SENT (optional GITHUB_STEP_SUMMARY)
# Post-report mode (--post-report): post the model's final report as a PR
#   comment on the entry points where the action cannot (see the mode itself).
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA EXECUTION_FILE
# Post-findings mode (--post-findings): turn the report's machine-readable
#   findings block into line-anchored review comments.
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA
# Mark mode (--mark): upsert the marker comment AFTER a successful review.
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA EXECUTION_FILE
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

# Operator directive (2026-07-24): each review pass costs real turns/tokens,
# and a security-critical hook file went through 5 consecutive passes each
# finding one more edge case -- diminishing returns past a point. Cap total
# reviews per PR; further pushes still get CI, just not another review pass.
#
# (2026-07-29) The cap is now SIZED TO THE DIFF: 3 passes up to 10k changed
# lines, 5 up to 50k, 7 above. A flat 3 is right for a small PR and wrong for a
# consolidation, where each pass can only hold so much of the diff at once.
# REVIEW_CAP_TIERS and review_cap_for() live in ../lib/common.sh so this script
# and review-status.sh cannot drift apart about it.

# Newest marker comment's SHA. With `gh api --paginate`, --jq runs PER PAGE,
# so stream matching bodies flat. The marker BODY is multi-line (the SHA line
# plus an "Automated ... cost" line), so extract the SHA from EVERY line first,
# THEN take the last -- `tail -n 1` before the sed grabbed the trailing cost
# line and matched nothing, silently disabling the whole review-dedup (every
# green push re-reviewed). Found by review finding F4.
# Count finished review reports posted on the PR so far (same signature
# check-review-report-replies.sh uses: a github-actions issue comment starting
# with the report header and carrying either the findings fence or the
# "### Review" heading -- an in-progress tracking comment matches neither).
review_report_count() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.user.login | contains(\"github-actions\"))
                  | select(.body | startswith(\"**Claude finished\"))
                  | select((.body | contains(\"json:review-findings\")) or (.body | contains(\"### Review\")))
                  | .id" 2>/dev/null | wc -l || true
}

last_marker_sha() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$MARKER_PREFIX\")) | .body" 2>/dev/null |
        sed -n 's/.*claude-reviewed: \([0-9a-f]\{40\}\).*/\1/p' | tail -n 1 || true
}

last_marker_id() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$MARKER_PREFIX\")) | .id" 2>/dev/null |
        tail -n 1 || true
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

if [[ "${1:-}" == "--record-invocation" ]]; then
    # The action's own log DELIBERATELY hides what it was invoked with:
    # run-claude-sdk.ts destructures `extraArgs` out before printing the SDK
    # options. That is upstream and not ours to change, but the consequence is:
    # anything passed through `claude_args` leaves NO trace that it was applied,
    # and only its firing would ever reveal it.
    #
    # Spike S-2 hit exactly this while settling `--max-budget-usd`, and it is
    # about to matter more. That flag binds, but as a between-turns post-hoc
    # stop rather than a ceiling (measured overshooting a $0.01 cap to $0.234;
    # see docs/ci-overhaul/spike-s1-s2.md), so "was it even on?" has to be
    # answerable from the log rather than from a halt.
    #
    # Deliberately dumb: it echoes what the workflow says it sent. It cannot
    # prove the action forwarded it, and claiming otherwise would be worse than
    # saying nothing. What it does give is the invoked-vs-observed pair needed
    # to tell "the flag was never set" from "the flag was set and ignored".
    printf '%s\n' "${CLAUDE_ARGS_SENT:-(none recorded)}"
    if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
        {
            echo "### Review invocation"
            echo ''
            echo 'claude_args as sent to the action (the action does not log these itself):'
            echo '```'
            printf '%s\n' "${CLAUDE_ARGS_SENT:-(none recorded)}"
            echo '```'
        } >>"$GITHUB_STEP_SUMMARY"
    fi
    exit 0
fi

if [[ "${1:-}" == "--post-report" ]]; then
    # Post the review report when the ACTION could not. track_progress (which
    # makes the action itself post/update the report comment) is rejected by
    # the action for any event outside pull_request/issues/issue_comment/
    # pull_request_review{,_comment} -- so on the workflow_run entry point the
    # action runs in AGENT mode, which creates no tracking comment at all and
    # leaves the report existing only as the model's final text inside the
    # execution file. Post it from here so both entry points end up with one
    # shape of report: the header prefix is the action's own
    # ("**Claude finished ...", src/github/operations/comment-logic.ts), which
    # is the signature review_report_count above, check-review-report-replies.sh,
    # and --post-findings all match on.
    require_var PR_NUMBER
    require_var HEAD_SHA
    report=""
    if [[ -n "${EXECUTION_FILE:-}" && -f "${EXECUTION_FILE:-}" ]]; then
        # Same result-object shape --mark parses for cost; `.result` carries the
        # model's final text (the action's own format-turns.ts reads that field
        # to render the "Final Result" section).
        report=$(jq -r '
            (if type == "array" then [.[] | select(.type == "result")][-1] else . end) as $r
            | select($r != null) | $r.result // empty
        ' "$EXECUTION_FILE" 2>/dev/null) || report=""
    fi
    if [[ -z "$report" ]]; then
        # Fail OPEN, not closed: --mark is the honesty guard and will refuse to
        # stamp the SHA when nothing posted, so the SHA stays retryable.
        log_warn "no final report text in ${EXECUTION_FILE:-<unset>}; nothing to post"
        exit 0
    fi
    # GitHub rejects issue-comment bodies over 65536 chars with a 422, which
    # would fail this step and strand the SHA in a permanent retry loop. Keep
    # the head (verdict + findings prose) AND the tail (the json:review-findings
    # fence --post-findings parses) rather than a plain truncation that would
    # drop the fence.
    if [[ ${#report} -gt 60000 ]]; then
        log_warn "report is ${#report} chars; truncating the middle to fit the comment limit"
        report="${report:0:30000}

_[report truncated: middle omitted to fit GitHub's comment size limit]_

${report: -25000}"
    fi
    gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
        -f body="**Claude finished the automated review of ${HEAD_SHA:0:7}**

---

${report}" >/dev/null
    log_info "Posted review report for ${HEAD_SHA:0:7} (${#report} chars)"
    exit 0
fi

if [[ "${1:-}" == "--post-findings" ]]; then
    # Post line-anchored review comments with severity badges from the
    # machine-readable findings block the reviewer embeds in its report
    # (```json:review-findings fence inside the newest tracking comment).
    # The model's final report text is the ONLY channel proven to escape the
    # action sandbox, so inline posting is done HERE, deterministically, via
    # github_token. Advisory by design: per-comment failures (line not in
    # diff, stale position) are logged and skipped; this mode never fails
    # the job -- the summary report already posted.
    require_var PR_NUMBER
    require_var HEAD_SHA
    # Robust extraction: the report is multi-line and a finding's own `body`
    # may itself embed a ``` fence (a review bot suggesting a code fix), so a
    # first-closing-fence match truncates and silently drops the whole array.
    # Anchor to the LAST ```json:review-findings block in the stream and take
    # its content up to that block's LAST closing fence; an inner fence in a
    # body no longer ends the block early. jq still validates it as an array.
    # (A mid-pagination gh failure degrades to empty -> advisory skip, never
    # an abort that would fail this step and skip the following --mark step.)
    findings_json=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
        --jq ".[] | select(.user.login | contains(\"github-actions\"))
                  | select(.body | contains(\"json:review-findings\")) | .body" 2>/dev/null |
        awk '
            /^[[:space:]]*```json:review-findings[[:space:]]*$/ { capturing = 1; n = 0; last = 0; next }
            capturing {
                buf[++n] = $0
                if ($0 ~ /^[[:space:]]*```[[:space:]]*$/) last = n
            }
            END { if (last > 0) for (i = 1; i < last; i++) print buf[i] }
        ') || findings_json=""
    if [[ -z "$findings_json" ]] || ! jq -e 'type == "array"' <<<"$findings_json" >/dev/null 2>&1; then
        log_info "no parseable review-findings block; skipping inline comments"
        exit 0
    fi
    posted=0
    skipped=0
    while IFS= read -r f; do
        [[ -n "$f" ]] || continue
        path=$(jq -r '.path // empty' <<<"$f")
        fline=$(jq -r '.line // empty' <<<"$f")
        sev=$(jq -r '.severity // "medium" | ascii_upcase' <<<"$f")
        title=$(jq -r '.title // "finding"' <<<"$f")
        fbody=$(jq -r '.body // empty' <<<"$f")
        if [[ -z "$path" || -z "$fline" ]]; then
            skipped=$((skipped + 1))
            continue
        fi
        if gh api -X POST "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/comments" \
            -f commit_id="$HEAD_SHA" -f path="$path" -F line="$fline" -f side=RIGHT \
            -f body="**[${sev}]** — ${title}

${fbody}" >/dev/null 2>&1; then
            posted=$((posted + 1))
        else
            skipped=$((skipped + 1))
            log_warn "inline comment rejected (line not in diff?): $path:$fline"
        fi
    done < <(jq -c '
        sort_by(.severity // "medium"
            | ascii_downcase
            | if . == "critical" then 0 elif . == "high" then 1 elif . == "medium" then 2 else 3 end)
        | .[0:20] | .[]' <<<"$findings_json" 2>/dev/null)
    log_info "inline findings: $posted posted, $skipped skipped (cap 20)"
    exit 0
fi

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
                  | select(.created_at > (now - 3600 | todate)) | .id" 2>/dev/null | wc -l) || recent=0
    inline=$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/comments" --paginate \
        --jq ".[] | select(.user.login | contains(\"github-actions\"))
                  | select(.created_at > (now - 3600 | todate)) | .id" 2>/dev/null | wc -l) || inline=0
    if [[ "${recent:-0}" -eq 0 && "${inline:-0}" -eq 0 ]]; then
        log_error "review step reported success but posted NOTHING in the last hour; refusing to mark ${HEAD_SHA:0:7} (SHA stays retryable)"
        exit 1
    fi
    # Cost transparency (operator request): the action's execution file's
    # result block carries cost/turns/duration/token usage. Best-effort --
    # a missing or unparseable file never blocks marking.
    cost_line=""
    if [[ -n "${EXECUTION_FILE:-}" && -f "${EXECUTION_FILE:-}" ]]; then
        cost_line=$(jq -r '
            (if type == "array" then [.[] | select(.type == "result")][-1] else . end) as $r
            | select($r != null)
            | ($r.usage // {}) as $u
            | "Cost: $\($r.total_cost_usd // 0 | . * 10000 | round / 10000)"
              + " (\(
                  ($r.modelUsage // {}) as $m
                  | if ($m | length) == 0 then "model n/a"
                    else
                      # EVERY model, ordered by output-token share, not `keys|first`.
                      #
                      # `keys | first` reported ONE model chosen by arbitrary key
                      # order. Observed on PR #543: the line read
                      # "(claude-haiku-4-5-20251001)" while the action was invoked
                      # with `--model claude-sonnet-5`, which reads as "the flag was
                      # ignored" when it may only mean haiku sorted first among the
                      # models used. The action legitimately uses a small model for
                      # its own sub-steps, so a single name can never answer "which
                      # model reviewed my code?" -- it can only mislead. Issue #539.
                      [ $m | to_entries[]
                        | { k: .key,
                            out: (.value.outputTokens // .value.output_tokens // 0) } ]
                      | sort_by(-.out)
                      | map(.k + (if .out > 0 then " " + (.out|tostring) + "out" else "" end))
                      | join(", ")
                    end
                ))"
              + " | \($r.num_turns // "?") turns"
              + " | \((($r.duration_ms // 0) / 60000) | floor)m\((($r.duration_ms // 0) / 1000 | floor) % 60)s"
              + "\nTokens: \($u.input_tokens // 0) in / \($u.output_tokens // 0) out"
              + " / \($u.cache_read_input_tokens // 0) cache-read / \($u.cache_creation_input_tokens // 0) cache-write"
        ' "$EXECUTION_FILE" 2>/dev/null) || cost_line=""
    fi
    body="${MARKER_PREFIX} ${HEAD_SHA} -->
Automated Claude review completed for commit ${HEAD_SHA:0:7}.${cost_line:+
$cost_line}"
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
    pull_request | workflow_dispatch)
        # pull_request: ready_for_review (console) or opened (submodules).
        # workflow_dispatch: manual re-review; PR number arrives via input.
        require_var PR_NUMBER
        pr="$PR_NUMBER"
        head_sha="${PR_HEAD_SHA:-}"
        if [[ -z "$head_sha" ]]; then
            head_sha=$(gh pr view "$pr" --repo "$GITHUB_REPOSITORY" \
                --json headRefOid --jq .headRefOid 2>/dev/null) ||
                emit false "$pr" "" "" "cannot resolve PR head"
        fi
        # REQUIRED_CHECK empty = no green gate: the submodule repos have no
        # PR CI of their own (validation lives in console CI), so there is
        # no signal to wait for; marker dedup alone bounds re-review cost.
        if [[ -n "${REQUIRED_CHECK:-}" ]]; then
            conclusion=$(gh api -X GET \
                "repos/${GITHUB_REPOSITORY}/commits/${head_sha}/check-runs" \
                -f check_name="$REQUIRED_CHECK" \
                --jq '[.check_runs[] | select(.conclusion == "success")] | length' 2>/dev/null) ||
                emit false "$pr" "$head_sha" "" "check-runs lookup failed"
            [[ "${conclusion:-0}" -ge 1 ]] ||
                emit false "$pr" "$head_sha" "" "$REQUIRED_CHECK is not green on the current head"
        else
            log_info "no required check configured; green gate skipped"
        fi
        ;;
    *)
        log_error "Unsupported EVENT_NAME: ${EVENT_NAME:-unset}"
        exit 1
        ;;
esac

review_count=$(review_report_count "$pr")
pr_loc=$(pr_diff_loc "$pr")
MAX_REVIEWS_PER_PR=$(review_cap_for "$pr_loc")
if [[ "${review_count:-0}" -ge "$MAX_REVIEWS_PER_PR" ]]; then
    emit false "$pr" "$head_sha" "" \
        "review cap reached ($review_count/$MAX_REVIEWS_PER_PR reports already posted; cap is $MAX_REVIEWS_PER_PR for a ${pr_loc}-line diff)"
fi
log_info "review budget: $review_count/$MAX_REVIEWS_PER_PR used (${pr_loc} changed lines)"

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
