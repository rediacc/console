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
# Post-report mode (--post-report): post the model's final report as a PR
#   comment on the entry points where the action cannot (see the mode itself).
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA EXECUTION_FILE
# Post-findings mode (--post-findings): turn the report's machine-readable
#   findings block into line-anchored review comments.
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA
# Apply-labels mode (--apply-labels): label the PR from the SAME review pass,
#   using a second machine-readable fence in the same report plus a mechanical
#   floor derived from the changed paths. Advisory end to end.
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA EXECUTION_FILE
# Mark mode (--mark): upsert the marker comment after a review.
#   Env: GH_TOKEN GITHUB_REPOSITORY PR_NUMBER HEAD_SHA EXECUTION_FILE
#        REVIEW_OUTCOME (the review step's outcome; anything other than
#        "success" records a SPENT ATTEMPT instead of marking the SHA reviewed).
#   A spent attempt consumes review budget without claiming the code was read,
#   so a pass that burned its turns and posted nothing cannot be repeated for
#   free on every later green push.
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
# Deliberately a DIFFERENT prefix from MARKER_PREFIX. A spent attempt consumes
# review budget but must never satisfy `last_marker_sha`, or a review that read
# nothing would suppress a later real one for the same SHA.
ATTEMPT_PREFIX='<!-- claude-review-attempt:'
# The label ledger (--apply-labels). A THIRD distinct prefix, for the same
# reason the second one exists: it must be invisible to last_marker_sha, to
# review_report_count (which keys on "**Claude finished"), and to the
# spent-attempt counter, or a bookkeeping comment would look like a review.
LEDGER_PREFIX='<!-- claude-labels:'

# THE HARD WHITELIST for --apply-labels. This is the security boundary of that
# arm, not a tidiness rule: adding a label the repo does not carry CREATES it,
# so an unfiltered hallucinated name would appear on the repo AND fail
# check:ci-label-inventory for everyone until someone deleted it by hand. Model
# output reaches the labels API only through add_desired(), which refuses
# anything not listed here.
#
# `bump-major` is DELIBERATELY ABSENT (operator ruling): a wrong minor is
# cosmetic, a wrong major is a statement to every consumer of the version
# stream. The model may RECOMMEND one in its report; applying it stays a human
# act, and its absence here means no code path in this arm can reach it.
MANAGED_LABELS=(bug enhancement documentation ci bump-minor bump-none)

# Created on demand immediately before its first use, the nightly-red pattern
# (see the CREATE_ON_DEMAND allowlist in ../quality/check-label-inventory.sh).
# The colour and description are asserted equal to .github/labels.yml by
# test-review-labels.sh, since this file cannot read labels.yml: the post-review
# steps run from a staged copy of .ci alone.
# "<name>|<color>|<description>", one row per label. A TABLE rather than the
# three scalars this used to be: bump-none arrived needing exactly the same
# treatment as `ci`, and a second set of scalars would have been the copy that
# drifts. Each row is asserted equal to .github/labels.yml by
# test-review-labels.sh, since this file cannot read labels.yml itself: the
# post-review steps run from a staged copy of .ci alone.
CREATE_ON_DEMAND_LABELS=(
    "ci|FEF2C0|Build system, CI workflows, or .ci tooling (applied by the automated review)"
    "bump-none|C5DEF5|No user-facing change: merging skips the release (review-applied; removed on release-worthy pushes)"
)

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
# review_report_count() lives in ../lib/common.sh beside review_cap_for(), for
# the reason stated there: this file counts the numerator and review-status.sh
# reports the fraction, and two copies of the numerator drifted once already.

# Spent review passes are counted by review_spent_attempt_count() in
# ../lib/common.sh, beside review_report_count() and review_cap_for(). The local
# copy that used to live here is gone deliberately: review-status.sh could not
# see it, summed a smaller numerator, and its deadlock guard stopped firing.

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
    # DENSITY, not rungs. Measured on this wave, same day, same reviewer, both landing in
    # the old 50-turn tier:
    #
    #   PR #552  2270 lines / 39 files  -> completed, full report   (22.0 turns/KLOC)
    #   PR #553  2802 lines / 36 files  -> error_max_turns, nothing (17.8 turns/KLOC)
    #
    # File count does not discriminate: 39 files passed where 36 failed. Lines do.
    #
    # Rungs were the wrong shape and my first fix proved it -- moving the boundary from 5000
    # to 2000 left a 2000..29999 tier whose TOP edge got 2.6 turns/KLOC, a wider version of
    # the same hole. Any wide tier starves at its top, so the budget now scales continuously
    # and the worst case is the same everywhere.
    #
    # TURNS_PER_KLOC is set above the measured survivor (22.0) rather than at it, because
    # one survival is not a floor. MAX_TURNS is a real cost ceiling, so above
    # MAX_TURNS/TURNS_PER_KLOC*1000 lines (~5600) density necessarily decays -- there the
    # budget is simply the maximum, and breadth-first reading in the prompt is what carries
    # it. check-review-turn-capacity.sh enforces exactly that split.
    local per_kloc=25 max_turns=140 min_turns=50
    local kloc=$(((${changed:-0} + 999) / 1000))
    local turns=$((kloc * per_kloc))
    [[ "$turns" -lt "$min_turns" ]] && turns="$min_turns"
    [[ "$turns" -gt "$max_turns" ]] && turns="$max_turns"
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

if [[ "${1:-}" == "--apply-labels" ]]; then
    # Label the PR from the review pass that just ran. Two inputs, in this
    # order of trust:
    #
    #   1. A MECHANICAL FLOOR derived from the changed paths alone. It needs no
    #      model output at all, so it still lands when the review starved and
    #      posted nothing -- which is why the workflow runs this step under
    #      always(), like --mark.
    #   2. The model's verdict, carried in a ```json:pr-labels fence at the end
    #      of the same report --post-report posts. That report text is the only
    #      channel proven to escape the action sandbox, and it is already being
    #      produced: this costs ZERO extra invocations, zero extra turns, and
    #      nothing in review_spend_total.
    #
    # ADVISORY END TO END. Every failure below logs and exits 0. A label is
    # never worth failing the review job or blocking a merge over.
    require_var PR_NUMBER
    require_var HEAD_SHA

    desired=""

    is_managed() {
        local want="$1" l
        for l in "${MANAGED_LABELS[@]}"; do
            if [[ "$l" == "$want" ]]; then
                return 0
            fi
        done
        return 1
    }

    add_desired() {
        if ! is_managed "$1"; then
            log_warn "refusing to apply '$1': not in the managed label set"
            return 0
        fi
        case $'\n'"$desired" in
            *$'\n'"$1"$'\n'*) return 0 ;;
        esac
        desired="${desired}${1}"$'\n'
    }

    # --- 1. the mechanical floor ------------------------------------------
    changed=$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}/files" --paginate \
        --jq '.[].filename' 2>/dev/null </dev/null) || changed=""
    if [[ -z "$changed" ]]; then
        log_warn "could not read the changed-file list for PR ${PR_NUMBER}; skipping the mechanical labels"
    else
        # ALL-FILES rules, conservative by construction: one stray source file
        # and the label does not apply. "This diff is entirely docs" and "this
        # diff is entirely CI plumbing" are facts about the file list, so they
        # need no model to see them and no model can talk them out of them.
        #
        # NOT routed through scope-map.cjs, which was the obvious reuse and is
        # the wrong tool: classify() answers "which CI jobs must run", and
        # .github/ and .ci/ paths yield full-CI REASONS there rather than
        # modules, so its output does not map onto PR kinds at all.
        # `^agent/` is the tracked agent working-notes root (session STATE.md,
        # agent/RULES.md, agent/PLAN-*.md, the /handoff program suites under
        # agent/programs/<slug>/). It is named EXPLICITLY rather than left to the
        # trailing `\.md$` alternative, which is the shape it arrived in: while
        # every file under that tree happened to end in .md the docs label landed
        # by accident, and the first checklist sidecar, fixture or script under
        # agent/ would have silently turned a notes-only PR into an unlabelled
        # one. The tree ships nothing and is a zero-job module in
        # .ci/scripts/ci/scope-map.cjs, so "entirely agent notes" is a
        # documentation PR by the same reasoning `^docs/` already is.
        if ! grep -qvE '(^docs/|^agent/|^packages/www/src/content/docs/|^CLAUDE\.md$|^LICENSE$|\.md$)' <<<"$changed"; then
            add_desired documentation
        fi
        if ! grep -qvE '(^\.github/|^\.ci/|^scripts/ci-runner/)' <<<"$changed"; then
            add_desired ci
        fi
    fi

    # --- 2. the model's verdict -------------------------------------------
    verdict=""
    if [[ -n "${EXECUTION_FILE:-}" && -f "${EXECUTION_FILE:-}" ]]; then
        # Same result-object shape --post-report and --mark parse.
        report=$(jq -r '
            (if type == "array" then [.[] | select(.type == "result")][-1] else . end) as $r
            | select($r != null) | $r.result // empty
        ' "$EXECUTION_FILE" 2>/dev/null) || report=""
        # LAST fence wins, same reasoning as --post-findings: a report may quote
        # the required format before emitting its real one.
        verdict=$(awk '
            /^[[:space:]]*```json:pr-labels[[:space:]]*$/ { capturing = 1; n = 0; next }
            capturing && /^[[:space:]]*```[[:space:]]*$/ { capturing = 0; next }
            capturing { buf[++n] = $0 }
            END { for (i = 1; i <= n; i++) print buf[i] }
        ' <<<"$report") || verdict=""
    fi

    # FALLBACK: the fence may live only in the POSTED COMMENT. Observed on the
    # feature's first live run (#559, run 31267699743): the model posts its
    # summary itself via `gh pr comment` and put the fence THERE, while its
    # final result text back to the harness did not repeat it -- so the
    # extraction above logged "no json:pr-labels block" beside a PR whose
    # verdict comment plainly carried one. The result text stays the primary
    # source (it wins when both exist); the newest fence-bearing comment is
    # the fallback. Trust model: PR comments already carry the reviewed-SHA
    # markers this pipeline acts on, the whitelist hard-filters every label,
    # and bump-major is never applied automatically, so a forged fence cannot
    # do more than a forged marker could.
    if [[ -z "$verdict" ]]; then
        comment_report=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
            --jq '.[] | select(.body | contains("```json:pr-labels")) | .body' 2>/dev/null | tail -c 65536) || comment_report=""
        if [[ -n "$comment_report" ]]; then
            verdict=$(awk '
                /^[[:space:]]*```json:pr-labels[[:space:]]*$/ { capturing = 1; n = 0; next }
                capturing && /^[[:space:]]*```[[:space:]]*$/ { capturing = 0; next }
                capturing { buf[++n] = $0 }
                END { for (i = 1; i <= n; i++) print buf[i] }
            ' <<<"$comment_report") || verdict=""
            [[ -n "$verdict" ]] && log_info "json:pr-labels fence found in the posted report comment (absent from the result text)"
        fi
    fi

    if [[ -z "$verdict" ]]; then
        log_info "no json:pr-labels block in the report; mechanical labels only"
    elif ! jq -e '
        type == "object"
        and ((.bump // "patch") as $b | ["none", "patch", "minor", "major"] | index($b) != null)
        and ((.kind // []) | type == "array")
        and ((.kind // []) | length <= 2)
        and (((.kind // []) - ["bug", "feature", "docs", "ci"]) | length == 0)
    ' <<<"$verdict" >/dev/null 2>&1; then
        # STRICT, and malformed is treated as ABSENT rather than as a partial
        # answer: a half-parsed verdict is how a hallucinated field would get a
        # vote. The mechanical floor above still applies.
        log_warn "the json:pr-labels block did not validate; treating it as absent"
    else
        bump=$(jq -r '.bump // "patch"' <<<"$verdict")
        why=$(jq -r '(.why // "") | .[0:200]' <<<"$verdict")
        log_info "review verdict: bump=${bump} kind=$(jq -rc '.kind // []' <<<"$verdict") why=${why:-<none>}"
        case "$bump" in
            # The ONLY verdict that subtracts a release. Safe to apply on the
            # model's word alone in a way `major` is not: a wrong `none` costs a
            # release that the next release-worthy merge picks up anyway (the
            # commits still ship, they just do not earn their own tag), while a
            # wrong `major` is a permanent statement to every consumer of the
            # version stream.
            none) add_desired bump-none ;;
            minor) add_desired bump-minor ;;
            major)
                log_warn "the review RECOMMENDS a major bump (${why:-no reason given}). bump-major is never applied automatically; apply it by hand if you agree."
                ;;
        esac
        while IFS= read -r kind; do
            [[ -n "$kind" ]] || continue
            case "$kind" in
                bug) add_desired bug ;;
                feature) add_desired enhancement ;;
                docs) add_desired documentation ;;
                ci) add_desired ci ;;
            esac
        done < <(jq -r '(.kind // [])[]' <<<"$verdict")
    fi

    # --- 3. reconcile against the ledger, never a blind sync ---------------
    # The ledger records what THIS arm applied last time. Removal is scoped to
    # that record, so a hand-applied label -- full-ci, rollback, a human's
    # bump-minor -- is never touched no matter what the model says. It is also
    # re-filtered through the managed set on the way out: the ledger is a PR
    # comment, and a comment is editable by anyone with write access, so a
    # tampered "applied:" line must not become a delete-arbitrary-label
    # primitive.
    prev=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$LEDGER_PREFIX\")) | .body" 2>/dev/null </dev/null |
        sed -n 's/^applied:[[:space:]]*//p' | tail -n 1) || prev=""
    if [[ -n "$prev" ]]; then
        while IFS= read -r stale; do
            [[ -n "$stale" ]] || continue
            case $'\n'"$desired" in
                *$'\n'"$stale"$'\n'*) continue ;;
            esac
            if ! is_managed "$stale"; then
                log_warn "ledger names '$stale', which is not in the managed set; refusing to remove it"
                continue
            fi
            if gh api -X DELETE "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/labels/${stale}" \
                >/dev/null 2>&1 </dev/null; then
                log_info "removed stale label '$stale'"
            else
                log_warn "could not remove the stale label '$stale'"
            fi
        done < <(tr ',' '\n' <<<"$prev" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
    fi

    while IFS= read -r label; do
        [[ -n "$label" ]] || continue
        row=""
        for candidate in "${CREATE_ON_DEMAND_LABELS[@]}"; do
            [[ "${candidate%%|*}" == "$label" ]] && row="$candidate"
        done
        if [[ -n "$row" ]] &&
            ! gh api "repos/${GITHUB_REPOSITORY}/labels/${label}" >/dev/null 2>&1 </dev/null; then
            rest="${row#*|}"
            gh api -X POST "repos/${GITHUB_REPOSITORY}/labels" \
                -f name="$label" -f color="${rest%%|*}" \
                -f description="${rest#*|}" >/dev/null 2>&1 </dev/null ||
                log_warn "could not create the '$label' label"
        fi
        gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/labels" \
            -f "labels[]=$label" >/dev/null 2>&1 </dev/null ||
            log_warn "could not apply the label '$label'"
    done <<<"$desired"

    applied=$(printf '%s' "$desired" | sed '/^$/d' | paste -sd, -)
    body="${LEDGER_PREFIX} ${HEAD_SHA} -->
applied: ${applied}"
    ledger_id=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$LEDGER_PREFIX\")) | .id" 2>/dev/null </dev/null |
        tail -n 1) || ledger_id=""
    if [[ -n "$ledger_id" ]]; then
        gh api -X PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${ledger_id}" \
            -f body="$body" >/dev/null 2>&1 </dev/null ||
            log_warn "could not update the label ledger comment"
    else
        gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
            -f body="$body" >/dev/null 2>&1 </dev/null ||
            log_warn "could not post the label ledger comment"
    fi
    log_info "labels for ${HEAD_SHA:0:7}: ${applied:-<none>}"
    exit 0
fi

if [[ "${1:-}" == "--mark" ]]; then
    require_var PR_NUMBER
    require_var HEAD_SHA

    # SPENT-ATTEMPT PATH (operator decision 2026-07-30). A review that burned
    # its budget and produced nothing still COST money, and until now it cost it
    # for free: the step failed, every following step was skipped by implicit
    # success(), no marker was written, and review_report_count -- which counts
    # POSTED reports -- stayed at zero. So the cap never advanced and the same
    # SHA was re-reviewed at full price on every subsequent green push, able to
    # fail identically forever.
    #
    # Measured on PR #546, run 30552035566: `"subtype": "error_max_turns"`,
    # zero github-actions comments on the PR, no marker. The S-2 spike predicted
    # exactly this shape for a budget halt ("red job, no report, no findings, no
    # marker SHA, and the next run re-reviews the same SHA and pays again"); it
    # arrived via max_turns instead.
    #
    # An attempt marker is deliberately NOT a reviewed marker. It carries its own
    # prefix so `last_marker_sha` still cannot see it -- a spent attempt must
    # never suppress a later genuine review of the same SHA by pretending the
    # code was read -- but `review_spent_attempt_count` does, so it consumes budget.
    # It records WHY, because "we stopped reviewing this PR" is only a
    # defensible message if it says what was spent on.
    # ONE MARKER PER HEAD, upserted with its own attempt count (2026-08-09).
    # The marker used to be POSTed fresh on every failure, so N deaths on one
    # head meant N comments and N charged units. That was right for a verdict
    # and wrong for an infrastructure death: on PR #560 an `error_max_turns`
    # told a fully-green, autopilot-driven PR to "push a change to earn another
    # pass" when there was no legitimate change to push, and the loop stalled
    # behind a human. An infra-class failure now gets bounded free re-attempts
    # on the same head; see the block above review_attempt_states() in
    # ../lib/common.sh for why the bound is as important as the retry.
    if [[ "${REVIEW_OUTCOME:-}" != "success" ]]; then
        why="review step did not succeed"
        if [[ -n "${EXECUTION_FILE:-}" && -f "${EXECUTION_FILE:-}" ]]; then
            subtype=$(jq -r '
                (if type == "array" then [.[] | select(.type == "result")][-1] else . end) as $r
                | select($r != null) | $r.subtype // empty
            ' "$EXECUTION_FILE" 2>/dev/null) || subtype=""
            [[ -n "$subtype" ]] && why="$subtype"
        fi

        attempt_id=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
            --jq ".[] | select(.body | startswith(\"$ATTEMPT_PREFIX\"))
                      | select(.body | contains(\"$HEAD_SHA\")) | .id" 2>/dev/null </dev/null |
            tail -n 1) || attempt_id=""
        prior=$(review_head_attempt_state \
            "$(review_attempt_states "$PR_NUMBER" "$ATTEMPT_PREFIX")" "$HEAD_SHA")
        attempts=$((${prior%% *} + 1))

        if review_attempt_class_is_infra "$why" &&
            [[ "$attempts" -le "$REVIEW_FREE_REATTEMPTS_PER_HEAD" ]]; then
            verdict_line="That is an INFRASTRUCTURE-class failure, not a verdict on the code, so it does not
close this head's budget yet: attempt ${attempts} of ${REVIEW_MAX_ATTEMPTS_PER_HEAD}.
Re-run it on the same head, no push required:
\`gh workflow run claude-review.yml --ref <this PR's branch> -f pr_number=${PR_NUMBER}\`"
        else
            verdict_line="That is attempt ${attempts} of ${REVIEW_MAX_ATTEMPTS_PER_HEAD} on this head, so it counts against this PR's
review budget because it spent real turns and tokens.
Push a change to earn another pass."
        fi

        body="${ATTEMPT_PREFIX} ${HEAD_SHA} -->
attempts: ${attempts}
class: ${why}
A review pass was attempted on \`${HEAD_SHA:0:7}\` and produced no report (\`${why}\`).
${verdict_line}"
        if [[ -n "$attempt_id" ]]; then
            gh api -X PATCH "repos/${GITHUB_REPOSITORY}/issues/comments/${attempt_id}" \
                -f body="$body" >/dev/null 2>&1 </dev/null ||
                log_warn "could not update the spent attempt for ${HEAD_SHA:0:7}"
        else
            # -X POST explicitly. gh infers it from -f, but leaving it implicit
            # made this write indistinguishable from a read to anything parsing
            # the argv -- including this pipeline's own test harness, which
            # served it a fixture instead of capturing it.
            gh api -X POST "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" \
                -f body="$body" >/dev/null 2>&1 </dev/null ||
                log_warn "could not record the spent attempt for ${HEAD_SHA:0:7}"
        fi
        log_info "recorded SPENT ATTEMPT ${attempts}/${REVIEW_MAX_ATTEMPTS_PER_HEAD} for ${HEAD_SHA:0:7} (${why}); it does not mark the SHA reviewed"
        exit 0
    fi
    # A marker is a CLAIM that a review happened. Step success alone proved
    # false once: the reviewer "succeeded" with 36 permission denials and
    # posted nothing, and the marker then suppressed the retry. Only mark if
    # a NON-marker comment or an inline review comment landed recently.
    # --paginate + stream-count: without it GitHub returns the OLDEST page
    # only, so on a >100-comment PR a just-posted review is invisible and
    # this guard would refuse to mark forever (found by the automated review
    # itself, PR #531 first pass). Per-page --jq emits matches as lines;
    # wc -l totals across pages -- same pattern as last_marker_sha above.
    #
    # EVERY BOOKKEEPING PREFIX IS EXCLUDED, not just the marker. The guard asks
    # "did this review produce OUTPUT", and only a report or an inline comment
    # answers that. The attempt marker and the label ledger are written BY this
    # pipeline about itself, so counting them lets the pipeline satisfy its own
    # honesty guard: a review that succeeded and posted nothing (the 36-
    # permission-denials shape) would be stamped as reviewed on the strength of
    # a ledger comment written seconds earlier by --apply-labels. The attempt
    # marker had the same hole already -- a spent attempt inside the same hour
    # would vouch for the next pass -- which is why this excludes the class
    # rather than the one new prefix.
    recent=$(gh api "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$MARKER_PREFIX\") | not)
                  | select(.body | startswith(\"$ATTEMPT_PREFIX\") | not)
                  | select(.body | startswith(\"$LEDGER_PREFIX\") | not)
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

reports_posted=$(review_report_count "$pr")
# Fetched ONCE: the cap needs the chargeable total, the per-head ceiling needs
# this head's own row, and paying for the same paginated listing twice on every
# invocation is how a cheap guard becomes an expensive one.
attempt_states=$(review_attempt_states "$pr" "$ATTEMPT_PREFIX")
attempts_spent=$(review_chargeable_attempts "$attempt_states")

# THE PER-HEAD CEILING. Free re-attempts have to end somewhere, and it cannot be
# the per-PR cap alone: the free ones are not charged, so without this a head
# that dies infra-class could be retried forever at no visible cost. Checked
# BEFORE the cap so the message names the real reason.
head_state=$(review_head_attempt_state "$attempt_states" "$head_sha")
if review_head_is_exhausted "$attempt_states" "$head_sha"; then
    emit false "$pr" "$head_sha" "" \
        "head ${head_sha:0:7} has spent all ${REVIEW_MAX_ATTEMPTS_PER_HEAD} attempts (${head_state% *} recorded, class ${head_state#* }); push a change to earn another pass"
fi
# Budget is what was SPENT, not what was delivered. A pass that burned its turns
# and posted nothing cost the same as one that posted a full report, and
# charging only for successes is what let a failing SHA be re-reviewed forever.
#
# Via the SHARED helper, not a local sum: review-status.sh caps on the same total,
# and when it summed differently (posted only) it read 0/3 while this script read
# 3/3 on PR #553 -- so its deadlock guard could not fire and the PR went
# permanently unmergeable. One numerator, in ../lib/common.sh.
review_count=$(review_spend_total "$pr" "$ATTEMPT_PREFIX" "$reports_posted" "$attempts_spent")
pr_loc=$(pr_diff_loc "$pr")
MAX_REVIEWS_PER_PR=$(review_cap_for "$pr_loc")
if [[ "${review_count:-0}" -ge "$MAX_REVIEWS_PER_PR" ]]; then
    emit false "$pr" "$head_sha" "" \
        "review cap reached ($review_count/$MAX_REVIEWS_PER_PR spent: ${reports_posted:-0} report(s) posted, ${attempts_spent:-0} attempt(s) that produced none; cap is $MAX_REVIEWS_PER_PR for a ${pr_loc}-line diff)"
fi
log_info "review budget: $review_count/$MAX_REVIEWS_PER_PR spent (${reports_posted:-0} posted, ${attempts_spent:-0} produced nothing; ${pr_loc} changed lines)"

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
