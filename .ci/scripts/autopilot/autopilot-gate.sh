#!/bin/bash
# The autopilot gate: every check that must pass BEFORE the model is invoked,
# so a no-go costs zero model tokens (03-v2-autonomy.md section 2). The gate
# is PURE: it consumes recorded fixture files and env, runs no network calls,
# and prints exactly one decision JSON line on stdout. Purity is what makes
# every branch here offline-testable, and an untested branch in this file is
# an untested security decision.
#
# THE WORKFLOW OWNS THE FETCHING. Each fixture is produced by the calling
# workflow (values env-passed, never interpolated into run:):
#   --event   $GITHUB_EVENT_PATH of the workflow_run event, verbatim.
#   --pr      {number, author, draft, labels[], label_applier, head_repo,
#              base_repo, head_sha, unresolved_threads, review_gate_red}
#             from `gh api repos/$R/pulls/$N` (author=.user.login,
#             labels=[.labels[].name], repos/sha under .head/.base),
#             label_applier = newest `labeled` actor for the autopilot label
#             in `gh api repos/$R/issues/$N/timeline`,
#             unresolved_threads from check-resolved-threads.sh,
#             review_gate_red from the Review Gate check conclusion.
#   --state   body of the trusted state comment (state-comment.sh select),
#             absent or empty file when no state exists yet.
#   --failed-jobs  one failed job display name per line for the triggering
#             run (empty/absent = zero failed jobs).
#   --watchdog     non-empty file = the watchdog holds a pending_rerun for
#             this head run; the gate defers so the two never race.
#
# Env flags (repo variables; ABSENT MEANS OFF, fail closed):
#   AUTOPILOT_ENABLED            master switch, must be exactly "true"
#   AUTOPILOT_ALLOW_PUSH         reported in the decision for the harness
#   AUTOPILOT_AUTHOR_ALLOWLIST   comma-separated PR authors (empty = no-go)
#   AUTOPILOT_APPLIER_ALLOWLIST  comma-separated label appliers
#                                (defaults to the author allowlist)
#   AUTOPILOT_LABEL              arming label (default: autopilot)
#   AUTOPILOT_MAX_ROUNDS         round cap (default: 25)
#
# Output: {"decision":"go"|"no-go","mode":...,"reason":...,"round":N,
#          "push_allowed":bool}. Exit 0 for any decision; 2 for usage errors
#          (a wiring bug must be loud, never read as a quiet no-go).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
source "$SCRIPT_DIR/../lib/common.sh"

MODE_ARG="${1:-}"
if [[ "$MODE_ARG" != "--classify" ]]; then
    log_error "usage: autopilot-gate.sh --classify --event <file> --pr <file> [--state <file>] [--failed-jobs <file>] [--watchdog <file>]"
    log_error "the gate is fixtures-only by design; the calling workflow gathers the fixtures (see header)"
    exit 2
fi
shift
parse_args "$@"
EVENT="${ARG_EVENT:-}"
PR="${ARG_PR:-}"
STATE="${ARG_STATE:-}"
FAILED_JOBS="${ARG_FAILED_JOBS:-}"
WATCHDOG="${ARG_WATCHDOG:-}"

[[ -n "$EVENT" && -n "$PR" ]] || {
    log_error "--event and --pr are required"
    exit 2
}
require_file "$EVENT"
require_file "$PR"
jq -e . "$EVENT" >/dev/null || {
    log_error "event payload is not valid JSON: $EVENT"
    exit 2
}
jq -e . "$PR" >/dev/null || {
    log_error "pr fixture is not valid JSON: $PR"
    exit 2
}

MAX_ROUNDS="${AUTOPILOT_MAX_ROUNDS:-25}"
LABEL="${AUTOPILOT_LABEL:-autopilot}"
PUSH_ALLOWED=false
[[ "${AUTOPILOT_ALLOW_PUSH:-}" == "true" ]] && PUSH_ALLOWED=true

# Round number this invocation would become: ledger entries + 1. The ledger
# in the trusted-author state comment is the ONLY round counter (wall 3: the
# cap must be enforced by the harness, never by the model).
ROUNDS_DONE=0
if [[ -n "$STATE" && -s "$STATE" ]]; then
    ROUNDS_DONE="$(grep -cE '^r[0-9]+ \| run ' "$STATE" || true)"
fi
ROUND=$((ROUNDS_DONE + 1))

emit() { # emit <decision> <mode> <reason>
    jq -cn \
        --arg decision "$1" \
        --arg mode "$2" \
        --arg reason "$3" \
        --argjson round "$ROUND" \
        --argjson push_allowed "$PUSH_ALLOWED" \
        '{decision: $decision, mode: $mode, reason: $reason, round: $round, push_allowed: $push_allowed}'
    exit 0
}
no_go() { emit "no-go" "none" "$1"; }

# 1. Master stage flag: absent is off, and only the literal "true" arms.
if [[ "${AUTOPILOT_ENABLED:-}" != "true" ]]; then
    no_go "stage-flag-disabled: AUTOPILOT_ENABLED is not 'true' (absent means off, fail closed)"
fi

# Event facts (all read via jq, never shell-interpolated from the payload).
conclusion="$(jq -r '.workflow_run.conclusion // empty' "$EVENT")"
run_id="$(jq -r '.workflow_run.id // empty' "$EVENT")"
run_attempt="$(jq -r '.workflow_run.run_attempt // 1' "$EVENT")"
event_head_sha="$(jq -r '.workflow_run.head_sha // empty' "$EVENT")"
event_repo="$(jq -r '.repository.full_name // empty' "$EVENT")"
event_head_repo="$(jq -r '.workflow_run.head_repository.full_name // empty' "$EVENT")"
[[ -n "$conclusion" && -n "$run_id" ]] || {
    log_error "event payload lacks workflow_run.conclusion or .id"
    exit 2
}

pr_author="$(jq -r '.author // empty' "$PR")"
pr_draft="$(jq -r '.draft // false' "$PR")"
pr_applier="$(jq -r '.label_applier // empty' "$PR")"
pr_head_repo="$(jq -r '.head_repo // empty' "$PR")"
pr_base_repo="$(jq -r '.base_repo // empty' "$PR")"
pr_head_sha="$(jq -r '.head_sha // empty' "$PR")"
pr_threads="$(jq -r '.unresolved_threads // 0' "$PR")"
[[ "$pr_threads" =~ ^[0-9]+$ ]] || pr_threads=0
pr_review_red="$(jq -r '.review_gate_red // false' "$PR")"

# 2. Fork guard, in both records: the run's head repo and the PR's head repo
# must both equal the base repo. The autopilot never touches fork-sourced
# heads (03-v2-autonomy.md section 2, check 2).
if [[ -n "$event_head_repo" && "$event_head_repo" != "$event_repo" ]]; then
    no_go "fork-pr: workflow_run head repository '$event_head_repo' is not the base repo"
fi
if [[ -z "$pr_head_repo" || "$pr_head_repo" != "$pr_base_repo" ]]; then
    no_go "fork-pr: PR head repo '$pr_head_repo' is not the base repo '$pr_base_repo'"
fi

# 3. The arming label is a state flag; no label, no autopilot. The blocked
# label is the escalation latch and always wins.
if jq -e --arg l "autopilot-blocked" '.labels // [] | index($l)' "$PR" >/dev/null; then
    no_go "blocked-label: 'autopilot-blocked' is applied; a human must clear the escalation first"
fi
if ! jq -e --arg l "$LABEL" '.labels // [] | index($l)' "$PR" >/dev/null; then
    no_go "label-absent: '$LABEL' is not applied to this PR"
fi

# in_csv_allowlist <value> <csv> - exact-name membership, whitespace-trimmed.
in_csv_allowlist() {
    local value="$1" csv="$2" item
    local -a __items=()
    IFS=',' read -ra __items <<<"$csv"
    for item in "${__items[@]}"; do
        item="${item//[[:space:]]/}"
        [[ -n "$item" && "$item" == "$value" ]] && return 0
    done
    return 1
}

# 4. Author allowlist: the autopilot never babysits a stranger's PR. An empty
# allowlist allows nobody (fail closed), by construction of the membership
# test above.
if ! in_csv_allowlist "$pr_author" "${AUTOPILOT_AUTHOR_ALLOWLIST:-}"; then
    no_go "author-not-allowlisted: PR author '$pr_author' is not in AUTOPILOT_AUTHOR_ALLOWLIST"
fi

# 5. Label applier allowlist: anyone with triage can apply a label on a
# public repo, so the applier is a separate trust decision from the author.
if ! in_csv_allowlist "$pr_applier" "${AUTOPILOT_APPLIER_ALLOWLIST:-${AUTOPILOT_AUTHOR_ALLOWLIST:-}}"; then
    no_go "applier-not-allowlisted: label applier '$pr_applier' is not allowlisted"
fi

# 6. Dedup by (run_id, attempt): a queued duplicate of an already-handled
# event must exit without a round (concurrency is cancel-in-progress:false,
# so duplicates are expected, not exceptional).
if [[ -n "$STATE" && -s "$STATE" ]] && grep -qE "run ${run_id}/${run_attempt}([^0-9]|$)" "$STATE"; then
    no_go "already-handled: run ${run_id}/${run_attempt} is in the ledger"
fi

# 7. Round cap, from the trusted ledger only.
if ((ROUNDS_DONE >= MAX_ROUNDS)); then
    no_go "round-cap: $ROUNDS_DONE rounds recorded, cap is $MAX_ROUNDS; escalating to the operator is the design working"
fi

# 8. Watchdog deferral: while a pending_rerun is held the watchdog owns this
# run's classification; acting now would race it.
if [[ -n "$WATCHDOG" && -s "$WATCHDOG" ]]; then
    no_go "watchdog-defer: a pending_rerun is held for this run; the gate defers so the two cannot race"
fi

failed_count=0
if [[ -n "$FAILED_JOBS" && -s "$FAILED_JOBS" ]]; then
    failed_count="$(grep -c . "$FAILED_JOBS" || true)"
fi

# 9. Mode selection (03-v2-autonomy.md section 2, check 6, in its order).
case "$conclusion" in
    failure)
        emit "go" "fix" "ci-failure: run ${run_id} concluded failure"
        ;;
    cancelled)
        if ((failed_count > 0)); then
            emit "go" "fix" "watchdog-kill: cancelled with ${failed_count} failed job(s)"
        fi
        if [[ -n "$event_head_sha" && -n "$pr_head_sha" && "$event_head_sha" != "$pr_head_sha" ]]; then
            no_go "superseded: run head $event_head_sha is no longer the PR head $pr_head_sha"
        fi
        no_go "cancelled-no-failure: cancelled with zero failed jobs and no newer head; nothing to act on"
        ;;
    success)
        if [[ "$pr_review_red" == "true" ]]; then
            emit "go" "review-response" "review-gate-red: CI green but the Review Gate is red"
        fi
        if [[ "$pr_draft" == "true" ]]; then
            emit "go" "ready-flip" "success-while-draft: deterministic ready-flip, no model"
        fi
        if ((pr_threads > 0)); then
            emit "go" "review-response" "unresolved-threads: ${pr_threads} review thread(s) outstanding"
        fi
        emit "go" "done" "done-conditions: green, ready, reviewed, no outstanding threads"
        ;;
    *)
        no_go "unhandled-conclusion: '$conclusion' is not an actionable run conclusion"
        ;;
esac
