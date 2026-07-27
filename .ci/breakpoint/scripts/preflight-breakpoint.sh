#!/bin/bash
# Validate a dispatch's inputs before anything is created.
#
# THE ONE THING THIS EXISTS FOR: a `runs-on` label that does not exist for this
# org does NOT fail fast. The job QUEUES, indefinitely -- timeout-minutes does
# not bound queue time (it starts when the job starts), and GitHub only drops
# jobs queued past 24 hours. So an operator who picks a paid larger runner on an
# org that has none sees a spinner, not an error, and has no idea why.
#
# This cannot be prevented (GitHub resolves labels at scheduling time, not at
# parse time), so it is ANNOUNCED instead, from a job on a runner label that is
# always available.
#
# It deliberately touches NO Cloudflare API and creates NOTHING. That is what
# makes a permanently-queued session harmless: nothing exists until the main job
# actually starts running.
#
# Env: BP_RUNNER, BP_MODE, BP_LABEL, BP_DURATION, BP_ACTOR, GITHUB_RUN_ID
# Exit: 0 ok (warnings are not failures), 1 an input combination that cannot work.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"

bp_load_conf "$SCRIPT_DIR"

RUNNER="${BP_RUNNER:-ubuntu-latest}"
MODE="${BP_MODE:-quick}"
LABEL="${BP_LABEL:-rdc-ci}"
DURATION="${BP_DURATION:-30}"
ACTOR="${BP_ACTOR:-}"

FAILED=false

# ---------------------------------------------------------------------------
# Runner availability
# ---------------------------------------------------------------------------
# GitHub's free tier for public repos covers these. Everything else is a paid
# larger runner that must be provisioned at the org level on a Team or
# Enterprise Cloud plan.
FREE_RUNNERS="ubuntu-latest ubuntu-24.04 ubuntu-22.04 ubuntu-26.04 ubuntu-24.04-arm ubuntu-22.04-arm ubuntu-26.04-arm"

runner_is_free=false
for r in $FREE_RUNNERS; do
    if [[ "$RUNNER" == "$r" ]]; then
        runner_is_free=true
        break
    fi
done

if [[ "$runner_is_free" != "true" ]]; then
    bp_gha_warning "runner '${RUNNER}' is a PAID larger runner. If this org has no larger-runner group provisioned, the session job will QUEUE INDEFINITELY rather than fail -- watch for a job that never starts, and cancel it from the UI. Nothing is created until it starts, so a queued job leaks nothing."
fi

# ubuntu-slim would be a disaster here and is not in the workflow's choice list,
# but a hand-crafted API dispatch can still pass it.
if [[ "$RUNNER" == "ubuntu-slim" ]]; then
    log_error "ubuntu-slim has a HARD 15-minute job cap; a debug session cannot run on it."
    log_error "Pick ubuntu-latest (linux amd64) or another full-size label."
    FAILED=true
fi

# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------
if [[ ! "$DURATION" =~ ^[0-9]+$ ]] || [[ "$DURATION" -lt 1 ]] || [[ "$DURATION" -gt 300 ]]; then
    log_error "duration '${DURATION}' is out of range (1-300 minutes)"
    log_error "the cap is 300 because timeout-minutes is duration+40 and must stay under GitHub's 360-minute job cap"
    FAILED=true
fi

# NAMED MODE NEEDS TIME FOR A HUMAN TO LOG IN, and this refusal exists because
# the alternative failure is actively misleading.
#
# Observed on the first real named session (run 30259141278, duration 5):
#   10:43:47  URL emailed to the operator
#   10:48:48  Access application DELETED by teardown
# In those five minutes the operator had to read the mail, open the URL, submit
# their address, wait for Cloudflare's one-time-PIN email, and enter the code.
# Teardown removed the application mid-flow, and Cloudflare answered the
# callback with:
#
#   That account does not have access.
#
# Which points at the POLICY -- the one thing that was correct. The operator
# reasonably went looking for a permissions bug that did not exist. A short
# named session is not a short session; it is a session that ends in a wrong
# diagnosis.
#
# Quick mode is deliberately unaffected: it has no login step, so a 5-minute
# quick session is a perfectly reasonable thing to ask for.
readonly BP_NAMED_MIN_DURATION=15
if [[ "$MODE" == "named" ]] && [[ "$DURATION" =~ ^[0-9]+$ ]] && [[ "$DURATION" -lt "$BP_NAMED_MIN_DURATION" ]]; then
    log_error "duration ${DURATION}m is too short for named mode (minimum ${BP_NAMED_MIN_DURATION}m)"
    log_error "Rejected because: named mode puts Cloudflare Access in front of the box, and the"
    log_error "                  one-time-PIN login is two round trips through EMAIL. Teardown"
    log_error "                  deletes the Access app the moment the timer expires, so a short"
    log_error "                  session dies mid-login and reports 'That account does not have"
    log_error "                  access' -- blaming the policy, which is not the problem."
    log_error "Action, pick one:"
    log_error "  1. Dispatch with duration >= ${BP_NAMED_MIN_DURATION}."
    log_error "  2. Use tunnel-mode: quick if you only need a few minutes and no authentication."
    FAILED=true
fi

# ---------------------------------------------------------------------------
# Identity derivation must work BEFORE the session starts
# ---------------------------------------------------------------------------
# A label the sweeper's regex cannot match would leak its objects permanently,
# so prove the name derives here rather than discovering it after creation.
if ! NAME="$("$SCRIPT_DIR/derive-descriptor.sh" --field name --label "$LABEL" 2>&1)"; then
    log_error "cannot derive a session name for label '${LABEL}':"
    log_error "$NAME"
    FAILED=true
else
    log_info "session identity: ${NAME}"
fi

# ---------------------------------------------------------------------------
# Actor allow-list
# ---------------------------------------------------------------------------
# Empty means anyone who can dispatch, which is right for a single-operator repo
# and probably wrong for one with outside contributors. A session is a tunnel
# plus a shell on a box holding your source, so this is a real control.
ALLOWED="${BREAKPOINT_ALLOWED_ACTORS:-}"
if [[ -n "$ALLOWED" ]]; then
    actor_ok=false
    for a in $ALLOWED; do
        if [[ "$ACTOR" == "$a" ]]; then
            actor_ok=true
            break
        fi
    done
    if [[ "$actor_ok" != "true" ]]; then
        log_error "actor '${ACTOR}' is not in BREAKPOINT_ALLOWED_ACTORS"
        FAILED=true
    fi
fi

# ---------------------------------------------------------------------------
# Delivery channel preview
# ---------------------------------------------------------------------------
# Told here, before the session exists, so the operator can cancel instead of
# discovering the exposure in the log 40 minutes later.
if [[ "$MODE" == "quick" ]]; then
    if ! "$SCRIPT_DIR/resolve-recipient.sh" --actor "$ACTOR" >/dev/null 2>&1; then
        bp_gha_warning "actor '${ACTOR}' has no entry in BREAKPOINT_ACTOR_EMAILS, so the tunnel URL will be PRINTED IN THIS PUBLIC LOG rather than emailed. Anyone who can read this run will be able to reach the box for ${DURATION} minutes."
    else
        log_info "access details will be emailed, not printed"
    fi
fi

if [[ "$FAILED" == "true" ]]; then
    log_error "preflight failed; no session was started and nothing was created"
    exit 1
fi

log_info "preflight ok: runner=${RUNNER} mode=${MODE} duration=${DURATION}m"
