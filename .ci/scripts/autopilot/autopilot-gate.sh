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
#   --event   $GITHUB_EVENT_PATH of the workflow_run event, verbatim. On the
#             workflow_dispatch path the workflow SYNTHESIZES this from the
#             head's completed CI run and adds one key the real payload never
#             has: {autopilot_dispatch: {actor, pr_input, model, max_rounds}}.
#             Its presence is what makes this a dispatch-armed round.
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
#   AUTOPILOT_MAX_ROUNDS         round cap fallback (default: 25)
#
# THREE WAYS TO ARM, one escalation latch. `autopilot-blocked` is checked
# FIRST and beats all three. Then, in order:
#   label     the arming label is applied (the manual path, unchanged)
#   dispatch  a workflow_dispatch carrying a pr_number - THE DISPATCH IS THE
#             ARMING ACT, so round 1 runs straight off it with no label
#   campaign  the trusted state comment says `campaign: open` and rounds
#             remain - this is what carries the loop across the workflow_run
#             rounds that follow the dispatch
# Each path carries its own trust check: label -> the label applier, dispatch
# -> the dispatching actor, campaign -> nothing further, because the state
# comment is only trusted when its AUTHOR is the autopilot app (enforced by
# state-comment.sh select, upstream in the workflow). The author allowlist
# applies on all three.
#
# Output: {"decision":"go"|"no-go","mode":...,"reason":...,"round":N,
#          "push_allowed":bool,"armed_by":...,"model":...,"rounds_max":N,
#          "campaign":"open"|"closed"|"none","dispatch_trusted":bool,
#          "sig":"<hex8>"|"none","sig_count":N}.
#          Exit 0 for any decision; 2 for
#          usage errors (a wiring bug must be loud, never read as a quiet
#          no-go). `model`, `rounds_max` and `campaign` are what the workflow
#          feeds to claude_args and to the next state-comment write.
#
# THE STUCK SIGNATURE, 03-v2-autonomy.md section 4's flapping bound made
# mechanical: `sig` is the first 8 hex of sha256 over the SORTED failed-job
# set, and `sig_count` is how many consecutive rounds have now faced that same
# set (read back from the state comment, written forward by the workflow). At
# STUCK_LIMIT the fix arm refuses instead of spending another round on a fix
# that has twice failed to move the red, which is the difference between
# escalating at round 3 and escalating at the 25-round cap.
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
[[ "$MAX_ROUNDS" =~ ^[0-9]{1,4}$ ]] || MAX_ROUNDS=25
LABEL="${AUTOPILOT_LABEL:-autopilot}"
PUSH_ALLOWED=false
[[ "${AUTOPILOT_ALLOW_PUSH:-}" == "true" ]] && PUSH_ALLOWED=true

# The only models a round may be dispatched with. An unknown value is a
# TYPO, not an instruction: it falls back to the default rather than reaching
# claude_args, where it would fail the round after paying for the runner.
DEFAULT_MODEL="claude-sonnet-5"
MODEL_ALLOWED="claude-sonnet-5,claude-opus-5"
RESOLVED_MODEL="$DEFAULT_MODEL"
CAMPAIGN_STATE="none"
ARMED_BY="none"
DISPATCH_TRUSTED=false

# The third consecutive round facing an unchanged failed-job set is the one
# that refuses: two distinct fixes have already failed to move it.
STUCK_LIMIT=3
SIG="none"
SIG_COUNT=0

# sha256_hex - read stdin, print the hex digest. coreutils on the runner,
# shasum on macOS; every .ci script documents itself as locally runnable.
sha256_hex() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum | cut -d' ' -f1
    else
        shasum -a 256 | cut -d' ' -f1
    fi
}

# Round number this invocation would become: ledger entries + 1. The ledger
# in the trusted-author state comment is the ONLY round counter (wall 3: the
# cap must be enforced by the harness, never by the model).
ROUNDS_DONE=0
if [[ -n "$STATE" && -s "$STATE" ]]; then
    ROUNDS_DONE="$(grep -cE '^r[0-9]+ \| run ' "$STATE" || true)"
fi
ROUND=$((ROUNDS_DONE + 1))

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

emit() { # emit <decision> <mode> <reason>
    # The campaign value the NEXT state-comment write should record. A
    # dispatch-armed round opens the campaign; reaching mode done closes it;
    # anything else carries the current value forward untouched, so a
    # label-armed round never closes a campaign it knows nothing about.
    local campaign_next="$CAMPAIGN_STATE"
    if [[ "$2" == "done" ]]; then
        [[ "$CAMPAIGN_STATE" == "none" ]] || campaign_next="closed"
    elif [[ "$1" == "go" && "$ARMED_BY" == "dispatch" ]]; then
        campaign_next="open"
    fi
    jq -cn \
        --arg decision "$1" \
        --arg mode "$2" \
        --arg reason "$3" \
        --argjson round "$ROUND" \
        --argjson push_allowed "$PUSH_ALLOWED" \
        --arg armed_by "$ARMED_BY" \
        --arg model "$RESOLVED_MODEL" \
        --argjson rounds_max "$MAX_ROUNDS" \
        --arg campaign "$campaign_next" \
        --argjson dispatch_trusted "$DISPATCH_TRUSTED" \
        --arg sig "$SIG" \
        --argjson sig_count "$SIG_COUNT" \
        '{decision: $decision, mode: $mode, reason: $reason, round: $round, push_allowed: $push_allowed,
          armed_by: $armed_by, model: $model, rounds_max: $rounds_max, campaign: $campaign,
          dispatch_trusted: $dispatch_trusted, sig: $sig, sig_count: $sig_count}'
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

# Dispatch facts. The key is absent on the workflow_run path, so `is_dispatch`
# is false there without the gate needing to know the event name twice.
is_dispatch=false
jq -e '.autopilot_dispatch' "$EVENT" >/dev/null 2>&1 && is_dispatch=true
dispatch_actor="$(jq -r '.autopilot_dispatch.actor // empty' "$EVENT")"
dispatch_pr="$(jq -r '.autopilot_dispatch.pr_input // empty' "$EVENT")"
dispatch_model="$(jq -r '.autopilot_dispatch.model // empty' "$EVENT")"
dispatch_rounds="$(jq -r '.autopilot_dispatch.max_rounds // empty' "$EVENT")"

# Is the DISPATCHER trusted? Reported separately from the arming decision
# because the workflow gates its hold-open debug session on it, and that
# session is a human shell on the runner. Arming can succeed by label (whose
# trust check is the label APPLIER, a different person) while the actor who
# pressed Run workflow is nobody in particular, so "this round is armed" is
# not the same claim as "this dispatcher may open a shell here".
DISPATCH_TRUSTED=false
if [[ "$is_dispatch" == "true" ]] &&
    in_csv_allowlist "$dispatch_actor" "${AUTOPILOT_APPLIER_ALLOWLIST:-${AUTOPILOT_AUTHOR_ALLOWLIST:-}}"; then
    DISPATCH_TRUSTED=true
fi

# Campaign fields, read back through state-comment.sh rather than parsed here.
# The metadata line therefore has exactly ONE writer and ONE reader; a second
# copy of the format in this file is how the two would drift apart silently.
# Every value it returns is already normalized there.
campaign_fields='{"campaign":"none","model":"none","rounds_max":0}'
if [[ -n "$STATE" && -s "$STATE" ]]; then
    campaign_fields="$("$SCRIPT_DIR/state-comment.sh" fields --body "$STATE")"
fi
CAMPAIGN_STATE="$(jq -r '.campaign' <<<"$campaign_fields")"
campaign_model="$(jq -r '.model' <<<"$campaign_fields")"
campaign_rounds="$(jq -r '.rounds_max' <<<"$campaign_fields")"
campaign_last_sig="$(jq -r '.last_sig' <<<"$campaign_fields")"
campaign_sig_count="$(jq -r '.sig_count' <<<"$campaign_fields")"

# Failure signature: sorted, so the same set of red jobs hashes the same
# regardless of the order the jobs API happened to return them in. An empty or
# absent list is 'none' and never matches a previous signature -- a green run
# must not look like a repeat of the last red one.
if [[ -n "$FAILED_JOBS" && -s "$FAILED_JOBS" ]]; then
    SIG="$(LC_ALL=C sort "$FAILED_JOBS" | sha256_hex | cut -c1-8)"
fi
SIG_COUNT=1
if [[ "$SIG" != "none" && "$SIG" == "$campaign_last_sig" ]]; then
    SIG_COUNT=$((campaign_sig_count + 1))
fi

# Model resolution, in the design's order: the dispatch input beats the
# campaign's recorded model, which beats the default. An unrecognised value at
# either level degrades to the default rather than failing the round.
if [[ "$is_dispatch" == "true" && -n "$dispatch_model" ]]; then
    RESOLVED_MODEL="$dispatch_model"
elif [[ "$campaign_model" != "none" ]]; then
    RESOLVED_MODEL="$campaign_model"
fi
if ! in_csv_allowlist "$RESOLVED_MODEL" "$MODEL_ALLOWED"; then
    log_warn "model '$RESOLVED_MODEL' is not one of $MODEL_ALLOWED; falling back to $DEFAULT_MODEL"
    RESOLVED_MODEL="$DEFAULT_MODEL"
fi

# Round-cap resolution, same order, with the repo variable as the third
# fallback (already loaded into MAX_ROUNDS above) and 25 as the fourth.
if [[ "$is_dispatch" == "true" && "$dispatch_rounds" =~ ^[0-9]{1,4}$ ]] && ((dispatch_rounds > 0)); then
    MAX_ROUNDS="$dispatch_rounds"
elif ((campaign_rounds > 0)); then
    MAX_ROUNDS="$campaign_rounds"
fi

# 2. Fork guard, in both records: the run's head repo and the PR's head repo
# must both equal the base repo. The autopilot never touches fork-sourced
# heads (03-v2-autonomy.md section 2, check 2).
if [[ -n "$event_head_repo" && "$event_head_repo" != "$event_repo" ]]; then
    no_go "fork-pr: workflow_run head repository '$event_head_repo' is not the base repo"
fi
if [[ -z "$pr_head_repo" || "$pr_head_repo" != "$pr_base_repo" ]]; then
    no_go "fork-pr: PR head repo '$pr_head_repo' is not the base repo '$pr_base_repo'"
fi

# 3. Arming. The blocked label is the escalation latch and is checked FIRST,
# so it beats every arming path including a fresh dispatch: cancelling a run
# kills one round, `autopilot-blocked` kills the loop.
if jq -e --arg l "autopilot-blocked" '.labels // [] | index($l)' "$PR" >/dev/null; then
    no_go "blocked-label: 'autopilot-blocked' is applied; a human must clear the escalation first"
fi
if jq -e --arg l "$LABEL" '.labels // [] | index($l)' "$PR" >/dev/null; then
    ARMED_BY="label"
elif [[ "$is_dispatch" == "true" && -n "$dispatch_pr" ]]; then
    # The dispatch IS the arming act (03-v2-autonomy.md section 2, corrected
    # 2026-08-05): round 1 runs straight off it, and the state-comment write
    # at the end of that round records the campaign so the workflow_run
    # rounds that follow can continue without a label ever existing.
    ARMED_BY="dispatch"
elif [[ "$CAMPAIGN_STATE" == "open" ]] && ((ROUNDS_DONE < MAX_ROUNDS)); then
    # The campaign path. Trust comes from the state comment's AUTHORSHIP,
    # already enforced upstream by state-comment.sh select (bot author + exact
    # header), so there is deliberately no applier/actor check below for it:
    # an outsider cannot post a comment this gate would read at all.
    ARMED_BY="campaign"
else
    no_go "not-armed: no '$LABEL' label, no dispatch with a PR number, and no open campaign with rounds remaining (campaign: $CAMPAIGN_STATE, rounds done: $ROUNDS_DONE/$MAX_ROUNDS)"
fi

# 4. Author allowlist: the autopilot never babysits a stranger's PR. An empty
# allowlist allows nobody (fail closed), by construction of the membership
# test above.
if ! in_csv_allowlist "$pr_author" "${AUTOPILOT_AUTHOR_ALLOWLIST:-}"; then
    no_go "author-not-allowlisted: PR author '$pr_author' is not in AUTOPILOT_AUTHOR_ALLOWLIST"
fi

# 5. Arming trust, per path. Anyone with triage can apply a label on a public
# repo and anyone with write can dispatch a workflow, so whoever performed the
# ARMING ACT is a separate trust decision from the PR author. Same allowlist
# for both: the act is the same delegation either way.
case "$ARMED_BY" in
    label)
        if ! in_csv_allowlist "$pr_applier" "${AUTOPILOT_APPLIER_ALLOWLIST:-${AUTOPILOT_AUTHOR_ALLOWLIST:-}}"; then
            no_go "applier-not-allowlisted: label applier '$pr_applier' is not allowlisted"
        fi
        ;;
    dispatch)
        if ! in_csv_allowlist "$dispatch_actor" "${AUTOPILOT_APPLIER_ALLOWLIST:-${AUTOPILOT_AUTHOR_ALLOWLIST:-}}"; then
            no_go "dispatch-actor-not-allowlisted: dispatching actor '$dispatch_actor' is not allowlisted"
        fi
        ;;
    campaign) ;; # see the arming block: authorship of the state comment is the check
esac

# 6. Dedup by (run_id, attempt): a queued duplicate of an already-handled
# event must exit without a round (concurrency is cancel-in-progress:false,
# so duplicates are expected, not exceptional).
if [[ -n "$STATE" && -s "$STATE" ]] && grep -qE "run ${run_id}/${run_attempt}([^0-9]|$)" "$STATE"; then
    no_go "already-handled: run ${run_id}/${run_attempt} is in the ledger"
fi

# 7. Round cap, from the trusted ledger only. This is also what ends a
# campaign the operator never stops: the arming path above will not re-arm on
# a campaign once the cap is reached, and a label-armed PR dies here with the
# reason spelled out instead of a bare "not armed".
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
        # Flapping bound before the fix round, not after: by the time the same
        # failed-job set arrives for the STUCK_LIMIT-th time, two distinct
        # fixes have already been spent on it and a third is a worse bet than
        # the operator's attention.
        if [[ "$SIG" != "none" ]] && ((SIG_COUNT >= STUCK_LIMIT)); then
            no_go "stuck-signature: failed-job set ${SIG} is unchanged after $((SIG_COUNT - 1)) fix round(s); escalating rather than burning the round cap"
        fi
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
            # A red Review Gate with NOTHING outstanding to answer is the
            # review pipeline needing to run again, not the model needing to
            # think: the deterministic rerun costs zero model tokens
            # (03-v2-autonomy.md section 9 lists review-gate rerun among the
            # zero-cost paths). With threads open there IS something to
            # answer, so that case still buys a round.
            if ((pr_threads == 0)); then
                emit "go" "rerun-review" "review-gate-red-no-threads: the Review Gate is red with nothing outstanding to answer; deterministic rerun, no model"
            fi
            emit "go" "review-response" "review-gate-red: CI green, the Review Gate is red, and ${pr_threads} thread(s) are outstanding"
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
