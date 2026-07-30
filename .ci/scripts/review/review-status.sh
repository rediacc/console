#!/bin/bash
# "Review Complete" check-run -- the SHA-aware, event-driven successor to the
# `Review Gate` job inside Console CI.
#
# WHY THIS IS NOT A CI JOB. Console CI's `Review Gate` runs on `pull_request`,
# i.e. BEFORE the review it is named after can possibly have happened, and it
# asserts nothing about WHICH commit was reviewed: the three scripts it runs
# take PR_NUMBER + GITHUB_REPOSITORY and no SHA at all. The assertion cannot be
# moved into CI either, because the review only starts once CI is green -- a CI
# job that waits for the review deadlocks the pipeline that produces it. So the
# verdict is posted as an INDEPENDENT check-run from a workflow that no CI job
# references. That acyclicity is the property to preserve: never add a `needs:`
# or a `wait-for` on `Review Complete` anywhere inside Console CI.
#
# TWO ASSERTIONS
#   CURRENCY  the reviewed-SHA marker comment must name the PR's CURRENT head,
#             or the diff marker...head must be empty or submodule-gitlink only.
#   HYGIENE   the three existing review-hygiene scripts must pass, unchanged:
#             check-resolved-threads.sh, check-review-comments.sh,
#             check-review-report-replies.sh.
#
# CONCLUSIONS
#   success   current + clean.
#   success   WITH A WARNING when the review cap is reached and the marker is
#             stale. The pipeline will never review this head again, so failing
#             here would make the PR permanently unmergeable. This edge case is
#             the one that turns the whole design into a deadlock if missed.
#   neutral   draft PR -- no review is expected yet.
#   failure   stale/unreviewed head (names BOTH SHAs), the triggering Claude
#             Review run concluded failure (with a link), or a hygiene script
#             failed.
#
# The script exits 0 after posting a `failure` conclusion: the verdict lives in
# the check-run, and a red JOB would be a second, confusing signal on the same
# head SHA. A non-zero exit therefore always means the REPORTER broke, never
# that the PR is unhealthy.
#
# CONSTANTS ARE READ OUT OF claude-review-gate.sh, not copied. Two files
# disagreeing about MAX_REVIEWS_PER_PR would resurrect exactly the deadlock the
# warning path exists to prevent, and a copied MARKER_PREFIX that drifts makes
# this check silently unable to find any marker (every head reads as
# unreviewed). A parse failure is fatal rather than defaulted.
#
# Env (workflow-supplied):
#   GH_TOKEN GITHUB_REPOSITORY EVENT_NAME
#   workflow_run:           WR_CONCLUSION WR_HEAD_SHA WR_HTML_URL
#   review/comment events:  PR_NUMBER
#
# Test seams (see .ci/scripts/test/gates/test-review-status.sh):
#   REVIEW_STATUS_HYGIENE_DIR  dir holding the three check-*.sh (default ../quality)
#   REVIEW_STATUS_GATE_SCRIPT  gate script to read the constants from
#   CHECK_NAME                 check-run name (default "Review Complete")
#
# Local dry-run: CHECK_NAME=scratch-review-status with a checks:write token
# posts a throwaway check-run and mutates nothing else.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: shared logging / require_var / require_cmd helpers used by every .ci script
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh
require_cmd jq

require_var GITHUB_REPOSITORY

CHECK_NAME="${CHECK_NAME:-Review Complete}"
HYGIENE_DIR="${REVIEW_STATUS_HYGIENE_DIR:-$SCRIPT_DIR/../quality}"
HYGIENE_SCRIPTS=(
    check-resolved-threads.sh
    check-review-comments.sh
    check-review-report-replies.sh
)

# --- constants, sourced from the gate script rather than duplicated ----------
GATE_SCRIPT="${REVIEW_STATUS_GATE_SCRIPT:-$SCRIPT_DIR/claude-review-gate.sh}"
if [[ ! -f "$GATE_SCRIPT" ]]; then
    log_error "cannot read review constants: $GATE_SCRIPT does not exist"
    exit 1
fi

MARKER_PREFIX="$(sed -n "s/^MARKER_PREFIX='\(.*\)'[[:space:]]*$/\1/p" "$GATE_SCRIPT")"
MARKER_PREFIX="${MARKER_PREFIX%%$'\n'*}"
# The cap is no longer a constant in the gate script: it is sized to the diff by
# review_cap_for() in ../lib/common.sh, which BOTH scripts source. That is the
# whole point -- sed-parsing a number out of the other file was always one edit
# away from the two disagreeing, which is the deadlock this file exists to stop.
if [[ -z "$MARKER_PREFIX" ]]; then
    log_error "could not parse MARKER_PREFIX out of $GATE_SCRIPT"
    log_error "  Fix: keep it as a plain top-level assignment there, or update this parser."
    exit 1
fi
if ! declare -F review_cap_for >/dev/null; then
    log_error "review_cap_for() is missing from ../lib/common.sh"
    log_error "  Fix: restore it there; both review scripts depend on one shared table."
    exit 1
fi

# --- GitHub reads ------------------------------------------------------------

# Newest reviewed-SHA marker on the PR. Same shape as claude-review-gate.sh's
# reader: the marker BODY is multi-line, so extract the SHA from every line and
# take the last, never `tail` first.
last_marker_sha() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"$MARKER_PREFIX\")) | .body" 2>/dev/null |
        sed -n 's/.*claude-reviewed: \([0-9a-f]\{40\}\).*/\1/p' | tail -n 1 || true
}

# Finished review reports posted so far -- the same signature the gate script
# counts against MAX_REVIEWS_PER_PR, so both files agree on "cap reached".
review_report_count() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.user.login | contains(\"github-actions\"))
                  | select(.body | startswith(\"**Claude finished\"))
                  | select((.body | contains(\"json:review-findings\")) or (.body | contains(\"### Review\")))
                  | .id" 2>/dev/null | wc -l || true
}

# --- resolve the pull request -----------------------------------------------
log_step "Review Complete: resolving the PR (event: ${EVENT_NAME:-unset})"

pr=""
case "${EVENT_NAME:-}" in
    workflow_run)
        require_var WR_HEAD_SHA
        # The commit->PRs endpoint, not the branch: a workflow_run payload's
        # head_branch can belong to several PRs, and the SHA is the fact we
        # actually hold. The PR's CURRENT head is re-read below regardless, so
        # a superseded push is detected rather than assumed away.
        pr="$(gh api "repos/${GITHUB_REPOSITORY}/commits/${WR_HEAD_SHA}/pulls" \
            --jq '[.[] | select(.state == "open")] | first | .number // empty')"
        ;;
    pull_request_review | pull_request_review_comment | issue_comment)
        require_var PR_NUMBER
        pr="$PR_NUMBER"
        ;;
    *)
        log_error "Unsupported EVENT_NAME: ${EVENT_NAME:-unset}"
        exit 1
        ;;
esac

if [[ -z "$pr" ]]; then
    log_info "no open PR for ${WR_HEAD_SHA:-?}; nothing to report"
    exit 0
fi

pr_json="$(gh api "repos/${GITHUB_REPOSITORY}/pulls/${pr}" \
    --jq '{state: .state, draft: .draft, head: .head.sha}')"
pr_state="$(jq -r '.state // empty' <<<"$pr_json")"
pr_draft="$(jq -r '.draft // false' <<<"$pr_json")"
head_sha="$(jq -r '.head // empty' <<<"$pr_json")"

if [[ "$pr_state" != "open" ]]; then
    log_info "PR #${pr} is ${pr_state:-unknown}, not open; nothing to report"
    exit 0
fi
if [[ -z "$head_sha" ]]; then
    log_error "PR #${pr} returned no head SHA; refusing to post a check-run with no anchor"
    exit 1
fi

log_info "PR #${pr} head ${head_sha}"

# --- post_check <conclusion> <title> <summary> -------------------------------
# Upserts the named check-run on the PR's CURRENT head SHA. Upsert rather than
# always-POST because these events fire on every comment, and a fresh check-run
# per keystroke buries the PR's checks list.
post_check() {
    local conclusion="$1" title="$2" summary="$3"
    local payload existing

    payload="$(jq -n \
        --arg name "$CHECK_NAME" \
        --arg sha "$head_sha" \
        --arg conclusion "$conclusion" \
        --arg title "$title" \
        --arg summary "$summary" \
        '{name: $name, head_sha: $sha, status: "completed", conclusion: $conclusion,
          output: {title: $title, summary: $summary}}')"

    existing="$(gh api -X GET "repos/${GITHUB_REPOSITORY}/commits/${head_sha}/check-runs" \
        -f check_name="$CHECK_NAME" \
        --jq '[.check_runs[]? | select(.app.slug == "github-actions")] | last | .id // empty')" ||
        existing=""

    if [[ -n "$existing" ]]; then
        # head_sha is not a PATCH field; sending it on an update is rejected.
        jq 'del(.head_sha)' <<<"$payload" |
            gh api -X PATCH "repos/${GITHUB_REPOSITORY}/check-runs/${existing}" --input - >/dev/null
        log_info "updated check-run ${existing}: ${CHECK_NAME} = ${conclusion}"
    else
        gh api -X POST "repos/${GITHUB_REPOSITORY}/check-runs" --input - <<<"$payload" >/dev/null
        log_info "created check-run: ${CHECK_NAME} = ${conclusion} on ${head_sha}"
    fi
}

# --- draft: nothing is expected yet ------------------------------------------
if [[ "$pr_draft" == "true" ]]; then
    post_check neutral "Draft PR -- review not expected" \
        "PR #${pr} is a draft. The review pipeline only fires for a non-draft PR whose current head has green CI, so there is nothing to assert about commit \`${head_sha}\` yet. Flip the PR ready for review and this check re-evaluates."
    exit 0
fi

failures=()
warnings=()
notes=()

# --- did the triggering review run itself fail? ------------------------------
# `cancelled` is deliberately NOT a failure: Claude Review runs with
# cancel-in-progress, so a superseded push cancels the older run by design and
# a newer run is already on its way.
if [[ "${EVENT_NAME:-}" == "workflow_run" ]]; then
    case "${WR_CONCLUSION:-}" in
        failure | timed_out)
            failures+=("The triggering **Claude Review** run concluded \`${WR_CONCLUSION}\`, so no review verdict was produced for this head: ${WR_HTML_URL:-<run url unavailable>}")
            ;;
        *)
            notes+=("Triggering Claude Review run: \`${WR_CONCLUSION:-n/a}\`.")
            ;;
    esac
fi

# --- ASSERTION 1: currency ---------------------------------------------------
log_step "CURRENCY: is the reviewed-SHA marker on the current head?"

last_sha="$(last_marker_sha "$pr")"
currency_ok=false
currency_detail=""

if [[ -n "$last_sha" && "$last_sha" == "$head_sha" ]]; then
    currency_ok=true
    currency_detail="head \`${head_sha}\` is the reviewed SHA"
elif [[ -z "$last_sha" ]]; then
    currency_detail="no reviewed-SHA marker comment on this PR, so head \`${head_sha}\` has not been reviewed"
else
    # Fail CLOSED on a compare failure. claude-review-gate.sh fails OPEN there
    # (worst case: one extra review); here failing open would ASSERT a head was
    # reviewed when nothing proved it.
    files_json="$(gh api "repos/${GITHUB_REPOSITORY}/compare/${last_sha}...${head_sha}" \
        --jq '[.files[]?.filename]' 2>/dev/null)" || files_json=""

    if [[ -z "$files_json" ]]; then
        log_warn "compare ${last_sha:0:7}...${head_sha:0:7} failed; treating head as unreviewed"
        currency_detail="could not compare \`${last_sha}\` with \`${head_sha}\` (compare API failed), so equivalence is unproven"
    elif [[ "$(jq 'length' <<<"$files_json")" -eq 0 ]]; then
        currency_ok=true
        currency_detail="empty diff between reviewed \`${last_sha}\` and head \`${head_sha}\`"
    else
        submodule_paths="$(git config -f .gitmodules --get-regexp '^submodule\..*\.path$' 2>/dev/null |
            awk '{print $2}' || true)"
        subs_json="$(printf '%s\n' "$submodule_paths" | jq -R . | jq -s '[.[] | select(length > 0)]')"
        non_gitlink="$(jq -r --argjson subs "$subs_json" \
            '[.[] | select(. as $f | $subs | index($f) | not)] | length' <<<"$files_json")"
        if [[ "$non_gitlink" -eq 0 ]]; then
            currency_ok=true
            currency_detail="only submodule pointer bumps between reviewed \`${last_sha}\` and head \`${head_sha}\`"
        else
            currency_detail="${non_gitlink} non-submodule file(s) changed since the reviewed SHA"
        fi
    fi
fi

review_count="$(review_report_count "$pr")"
review_count="${review_count//[[:space:]]/}"
# Y in "X/Y" is sized to THIS PR's diff, via the shared table in ../lib/common.sh.
pr_loc="$(pr_diff_loc "$pr")"
MAX_REVIEWS_PER_PR="$(review_cap_for "$pr_loc")"
notes+=("Currency: ${currency_detail}.")
notes+=("Review reports posted: ${review_count:-0}/${MAX_REVIEWS_PER_PR} (cap ${MAX_REVIEWS_PER_PR} for a ${pr_loc}-line diff).")

if [[ "$currency_ok" == true ]]; then
    log_info "CURRENCY ok: $currency_detail"
else
    if [[ "${review_count:-0}" -ge "$MAX_REVIEWS_PER_PR" ]]; then
        # THE DEADLOCK GUARD. The gate script refuses to review once the cap is
        # reached, so the marker can never advance to this head. Failing here
        # would make the PR permanently unmergeable through no fault of its
        # author. Pass, loudly.
        warnings+=("**REVIEW CAP REACHED** (${review_count}/${MAX_REVIEWS_PER_PR}) and the marker is stale: ${currency_detail}. The review pipeline will not run again on this PR, so the marker can never reach \`${head_sha}\`. Passing so the PR stays mergeable -- review the delta by hand.")
        log_warn "CURRENCY stale but review cap reached (${review_count}/${MAX_REVIEWS_PER_PR}); passing with a warning"
    else
        failures+=("Head \`${head_sha}\` has not been reviewed. Last reviewed SHA: \`${last_sha:-<none>}\`. Detail: ${currency_detail}.")
        log_error "CURRENCY failed: $currency_detail"
    fi
fi

# --- ASSERTION 2: hygiene ----------------------------------------------------
log_step "HYGIENE: running the three review-hygiene checks"

for script in "${HYGIENE_SCRIPTS[@]}"; do
    path="$HYGIENE_DIR/$script"
    if [[ ! -x "$path" ]]; then
        # Anti-vacuity: a wrong HYGIENE_DIR would silently reduce this check to
        # the currency assertion alone and still report success.
        log_error "hygiene script missing or not executable: $path"
        exit 1
    fi
    out_file="$(mktemp)"
    if PR_NUMBER="$pr" GITHUB_REPOSITORY="$GITHUB_REPOSITORY" "$path" >"$out_file" 2>&1; then
        log_info "hygiene ok: $script"
    else
        failures+=("\`${script}\` failed:

\`\`\`
$(tail -n 20 "$out_file")
\`\`\`")
        log_error "hygiene failed: $script"
    fi
    cat "$out_file"
    rm -f "$out_file"
done

# --- verdict -----------------------------------------------------------------
conclusion="success"
title="Reviewed at the current head"
if ((${#failures[@]} > 0)); then
    conclusion="failure"
    title="Review is not complete for this head"
elif ((${#warnings[@]} > 0)); then
    conclusion="success"
    title="Reviewed, with warnings"
fi

summary="PR #${pr} -- head \`${head_sha}\`, last reviewed \`${last_sha:-<none>}\`."
if ((${#failures[@]} > 0)); then
    summary="${summary}

## Failures
"
    for item in "${failures[@]}"; do summary="${summary}
- ${item}"; done
fi
if ((${#warnings[@]} > 0)); then
    summary="${summary}

## Warnings
"
    for item in "${warnings[@]}"; do summary="${summary}
- ${item}"; done
fi
if ((${#notes[@]} > 0)); then
    summary="${summary}

## Context
"
    for item in "${notes[@]}"; do summary="${summary}
- ${item}"; done
fi
summary="${summary}

_This check is posted by \`.ci/scripts/review/review-status.sh\` from a workflow no CI job references, so it can never block Console CI._"

post_check "$conclusion" "$title" "$summary"

# Exit 0 even on a `failure` conclusion -- see the header. A non-zero exit here
# means the reporter broke, not that the PR is unhealthy.
exit 0
