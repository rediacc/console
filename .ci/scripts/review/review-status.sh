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
#   review/comment/dispatch events:  PR_NUMBER
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
# python3 is declared because the artifact lookup below reads a zip member
# with it, and because of what an undeclared binary costs:
# An UNDECLARED binary here is not a missing feature, it is a mute death:
# under `set -euo pipefail` a command-not-found inside a command
# substitution exits 127 immediately, before any log_error and before
# post_check, leaving the head with no check-run and no annotation.
require_cmd python3

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
# The cap is measured against posted reports PLUS spent attempts, so this script
# needs the attempt prefix too. Parsed from the gate exactly like MARKER_PREFIX:
# a second hard-coded copy is the drift this file exists to prevent.
ATTEMPT_PREFIX="$(sed -n "s/^ATTEMPT_PREFIX='\(.*\)'[[:space:]]*$/\1/p" "$GATE_SCRIPT")"
ATTEMPT_PREFIX="${ATTEMPT_PREFIX%%$'\n'*}"
# The cap is no longer a constant in the gate script: it is sized to the diff by
# review_cap_for() in ../lib/common.sh, which BOTH scripts source. That is the
# whole point -- sed-parsing a number out of the other file was always one edit
# away from the two disagreeing, which is the deadlock this file exists to stop.
if [[ -z "$MARKER_PREFIX" ]]; then
    log_error "could not parse MARKER_PREFIX out of $GATE_SCRIPT"
    log_error "  Fix: keep it as a plain top-level assignment there, or update this parser."
    exit 1
fi
if [[ -z "$ATTEMPT_PREFIX" ]]; then
    log_error "could not parse ATTEMPT_PREFIX out of $GATE_SCRIPT"
    log_error "  Fix: keep it as a plain top-level assignment there, or update this parser."
    log_error "  Without it the cap reads LOWER here than in the gate, and the deadlock"
    log_error "  guard below cannot fire on a capped PR -- the #553 failure mode."
    exit 1
fi
if ! declare -F review_spend_total >/dev/null; then
    log_error "review_spend_total() is missing from ../lib/common.sh"
    log_error "  Fix: restore it there; the gate and this script must share ONE numerator."
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

# review_report_count() lives in ../lib/common.sh beside review_cap_for(), so the
# numerator this file reports and the denominator it reads come from one place.

# --- resolve the pull request -----------------------------------------------
log_step "Review Complete: resolving the PR (event: ${EVENT_NAME:-unset})"

pr=""
case "${EVENT_NAME:-}" in
    workflow_run)
        require_var WR_RUN_ID
        # THE ARTIFACT, not the SHA, and the difference is the whole bug this
        # replaced. Review Status is a SECOND-ORDER workflow_run (Console CI ->
        # Claude Review -> Review Status). GitHub stamps a workflow_run-triggered
        # run with the DEFAULT BRANCH tip, so `workflow_run.head_sha` was main's
        # SHA, `commits/<main>/pulls` returned [], and this arm exited 0 silently
        # printing a checkmark. The REQUIRED `Review Complete` check was
        # therefore never posted on the primary path, and every PR sat BLOCKED
        # with all checks green. Measured 2026-08-06: ten consecutive Claude
        # Review runs, all head_branch=main, all pull_requests=[]. This arm had
        # never resolved a PR since it was written.
        #
        # The old comment claimed "the SHA is the fact we actually hold". The
        # SHA we held was main's, and so was the branch -- neither could work.
        # Claude Review's gate resolves the PR authoritatively, so it now hands
        # the number over in a `review-target` artifact.
        #
        # ABSENT IS SILENT, PRESENT IS BINDING. A push to main also runs this
        # chain and legitimately has no PR; it writes no artifact and we exit 0
        # exactly as before. An artifact that EXISTS but cannot be honoured is a
        # reporter failure and must be loud, which is the case that used to be
        # indistinguishable from the main-push case.
        artifact_pr=""
        if gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${WR_RUN_ID}/artifacts" \
            --jq '.artifacts[] | select(.name == "review-target") | .id' 2>/dev/null | grep -q .; then
            art_id="$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${WR_RUN_ID}/artifacts" \
                --jq '[.artifacts[] | select(.name == "review-target")] | first | .id')"
            tmp_dir="$(mktemp -d)"
            tmp_zip="$tmp_dir/review-target.zip"
            if ! gh api "repos/${GITHUB_REPOSITORY}/actions/artifacts/${art_id}/zip" >"$tmp_zip" 2>/dev/null; then
                log_error "review-target artifact ${art_id} exists on run ${WR_RUN_ID} but could not be downloaded"
                rm -rf "$tmp_dir"
                exit 1
            fi
            # Read the member with python3, not `unzip`. unzip was undeclared, and
            # on any host without it this line killed the script at exit 127 before
            # either log_error below could speak -- the mute no-op that adding this
            # artifact lookup was meant to END. python3 is declared above, and is
            # already what the test harness uses to build this very fixture.
            artifact_pr="$(python3 -c '
import sys, zipfile
try:
    with zipfile.ZipFile(sys.argv[1]) as z:
        sys.stdout.write(z.read("review-target.txt").decode("utf-8", "replace"))
except Exception:
    pass
' "$tmp_zip" | tr -dc '0-9')"
            rm -rf "$tmp_dir"
            if [[ -z "$artifact_pr" ]]; then
                log_error "review-target artifact on run ${WR_RUN_ID} is present but carries no PR number"
                exit 1
            fi
            pr="$artifact_pr"
        fi
        ;;
    pull_request_review | pull_request_review_comment | issue_comment | workflow_dispatch)
        require_var PR_NUMBER
        pr="$PR_NUMBER"
        ;;
    *)
        log_error "Unsupported EVENT_NAME: ${EVENT_NAME:-unset}"
        exit 1
        ;;
esac

if [[ -z "$pr" ]]; then
    # Reachable only when no review-target artifact was written, i.e. the
    # triggering run had no PR at all (a push to main). Greppable on purpose:
    # if this line ever appears for a run that DID have a PR, the handoff broke
    # and the silence is the bug, not the verdict.
    log_info "no review-target artifact on run ${WR_RUN_ID:-?}; no PR to report on"
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

# Posted reports PLUS spent attempts -- the same total the gate caps on. Counting
# posted reports alone made this script read 0/3 while the gate read 3/3 on the
# SAME PR, which is why the deadlock guard below never fired. See common.sh.
review_count="$(review_spend_total "$pr" "$ATTEMPT_PREFIX")"
review_count="${review_count//[[:space:]]/}"
# Y in "X/Y" is sized to THIS PR's diff, via the shared table in ../lib/common.sh.
pr_loc="$(pr_diff_loc "$pr")"
MAX_REVIEWS_PER_PR="$(review_cap_for "$pr_loc")"
notes+=("Currency: ${currency_detail}.")
# "spent", not "posted": this number is reports PLUS attempts that burned their
# budget and posted nothing. Saying "3/3 posted" when zero were posted is the
# exact #553 confusion this file now fixes the logic for.
notes+=("Review passes spent: ${review_count:-0}/${MAX_REVIEWS_PER_PR} (posted reports + spent attempts; cap ${MAX_REVIEWS_PER_PR} for a ${pr_loc}-line diff).")

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
    elif review_head_is_exhausted "$(review_attempt_states "$pr" "$ATTEMPT_PREFIX")" "$head_sha"; then
        # THE SAME DEADLOCK, ONE LEVEL DOWN, and it arrived WITH the free
        # re-attempts rather than before them. Those attempts are deliberately
        # not charged, so a head can exhaust its own ceiling while the PR is
        # still well under its cap -- at which point the gate refuses this head
        # and the branch above cannot see why. Failing here would reproduce the
        # #553 outcome exactly: gate refuses, status fails, PR unmergeable
        # through no fault of its author.
        warnings+=("**HEAD REVIEW ATTEMPTS EXHAUSTED** for \`${head_sha}\` (${REVIEW_MAX_ATTEMPTS_PER_HEAD} reportless attempts, ${review_count}/${MAX_REVIEWS_PER_PR} of the PR budget spent): ${currency_detail}. The review pipeline will not retry this head, so the marker can never reach it. Passing so the PR stays mergeable -- push a change to earn another pass, or review the delta by hand.")
        log_warn "CURRENCY stale but head ${head_sha} exhausted its ${REVIEW_MAX_ATTEMPTS_PER_HEAD} attempts; passing with a warning"
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
    if [[ "$currency_ok" == true ]]; then
        title="Reviewed, but needs attention (see failures)"
    else
        title="Review is not complete for this head"
    fi
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
