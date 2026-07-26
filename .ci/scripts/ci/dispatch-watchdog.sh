#!/bin/bash
# Dispatch one generation of the chained watchdog monitor (watchdog-monitor.yml).
#
# The watchdog runs on ubuntu-slim, whose 15-minute job cap is a hard platform
# limit, so monitoring a 1-2h CI run takes a CHAIN of short generations: each
# one polls for ~8 minutes, then calls this script to dispatch the next. The
# generation cap below reproduces the old in-run watchdog's 3-hour backstop.
#
# Callers:
#   ci.yml (CI Watchdog bootstrap)       -> --generation 1
#   watchdog-monitor.yml (chain handoff) -> --generation N+1, or --generation 1
#                                           with the counter reset right after
#                                           the chain rerun starts attempt 2
#
# Usage:
#   GH_TOKEN=... GITHUB_REPOSITORY=owner/repo \
#     dispatch-watchdog.sh --run-id <ci-run-id> --generation <n> \
#       [--pr-number <n>] [--head-ref <branch>] [--pending-rerun true|false]
#
# --pr-number / --head-ref are exact values from the caller's event payload;
# when omitted (or empty) they are resolved from the run via the API. The
# dispatch targets the head branch's copy of the workflow, mirroring how the
# old in-run watchdog ran the PR's own copy, and falls back to the default
# branch for branches that predate watchdog-monitor.yml.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

require_cmd gh

RUN_ID=""
GENERATION=""
PR_NUMBER=""
HEAD_REF=""
PENDING_RERUN="false"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --run-id)
            RUN_ID="$2"
            shift 2
            ;;
        --generation)
            GENERATION="$2"
            shift 2
            ;;
        --pr-number)
            PR_NUMBER="$2"
            shift 2
            ;;
        --head-ref)
            HEAD_REF="$2"
            shift 2
            ;;
        --pending-rerun)
            PENDING_RERUN="${2:-false}"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

: "${RUN_ID:?--run-id is required}"
: "${GENERATION:?--generation is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
[[ "$RUN_ID" =~ ^[0-9]+$ ]] || {
    log_error "--run-id must be numeric, got: ${RUN_ID}"
    exit 1
}
[[ "$GENERATION" =~ ^[0-9]+$ ]] || {
    log_error "--generation must be numeric, got: ${GENERATION}"
    exit 1
}
[[ "$PENDING_RERUN" == "true" || "$PENDING_RERUN" == "false" ]] || {
    log_error "--pending-rerun must be true or false, got: ${PENDING_RERUN}"
    exit 1
}

# ~3 hours at ~8-minute generations, matching the monitor's own maxRuntime.
# Reaching the cap ends the chain fail-open: the run finishes unwatched and
# ci-complete still gates on every job's real conclusion.
MAX_GENERATIONS=22
if ((GENERATION > MAX_GENERATIONS)); then
    log_warn "Generation ${GENERATION} exceeds cap ${MAX_GENERATIONS} (~3h of coverage) - ending the watchdog chain"
    exit 0
fi

RUN_API="repos/${GITHUB_REPOSITORY}/actions/runs/${RUN_ID}"
if [[ -z "$HEAD_REF" ]]; then
    HEAD_REF="$(gh api "$RUN_API" --jq '.head_branch // ""')"
fi
if [[ -z "$PR_NUMBER" ]]; then
    # Best-effort: .pull_requests is populated for same-repo branches. When it
    # stays empty the monitor simply skips the PR-label reads.
    PR_NUMBER="$(gh api "$RUN_API" --jq '.pull_requests[0].number // ""')"
fi

dispatch() {
    gh workflow run watchdog-monitor.yml \
        --repo "$GITHUB_REPOSITORY" \
        --ref "$1" \
        -f "target_run_id=${RUN_ID}" \
        -f "generation=${GENERATION}" \
        -f "pr_number=${PR_NUMBER}" \
        -f "head_ref=${HEAD_REF}" \
        -f "pending_rerun=${PENDING_RERUN}"
}

DISPATCH_ERR=""
try_dispatch() {
    local out
    if out="$(dispatch "$1" 2>&1)"; then
        return 0
    fi
    DISPATCH_ERR="$out"
    return 1
}

if [[ -n "$HEAD_REF" ]] && try_dispatch "$HEAD_REF"; then
    log_info "Dispatched watchdog generation ${GENERATION} for run ${RUN_ID} on ref ${HEAD_REF}"
elif try_dispatch "$(gh api "repos/${GITHUB_REPOSITORY}" --jq '.default_branch')"; then
    log_info "Dispatched watchdog generation ${GENERATION} for run ${RUN_ID} on the default branch (head-ref copy unavailable)"
elif grep -qE "not found on the default branch|HTTP 404.*watchdog-monitor" <<<"$DISPATCH_ERR"; then
    # workflow_dispatch resolves the workflow FILENAME against the DEFAULT
    # branch's registry, so until watchdog-monitor.yml has landed on main it
    # cannot be dispatched from ANY ref (observed live: run 29936730679, HTTP
    # 404 on both the head-ref and default-branch attempts). One-time
    # bootstrap condition; fail OPEN with a loud warning instead of failing
    # the job -- the run finishes unwatched and ci-complete still gates.
    log_warn "watchdog-monitor.yml is not registered on the default branch yet (pre-merge bootstrap) - run ${RUN_ID} continues UNWATCHED"
    exit 0
else
    log_error "Failed to dispatch watchdog generation ${GENERATION} for run ${RUN_ID}: ${DISPATCH_ERR}"
    exit 1
fi
