#!/bin/bash
# Delete the empty `pr-N` ENVIRONMENT objects GitHub leaves behind.
# Usage: cleanup-pr-environments.sh --repo <owner/repo> [--dry-run]
#
# WHY THIS IS SEPARATE FROM cleanup-github-deployments.sh. That script deletes
# deployment RECORDS, which needs only deployments:write, and its header explains
# why it stops there: deleting the environment OBJECT needs Administration:write,
# which neither GITHUB_TOKEN nor the housekeeping App token carries. So the
# records go and the empty shells accumulate -- measured 2026-09-03, 25 `pr-*`
# environments with ZERO deployments between them, all of them cluttering
# /deployments long after their PR merged.
#
# So this is an OPERATOR-RUN script, not a CI step: it needs a token with
# Administration:write on the repo. Wiring it into a workflow with the tokens CI
# has would produce a step that fails on every run.
#
# THREE REFUSALS, because this deletes something GitHub cannot restore:
#   1. only names matching ^pr-[0-9]+$ are ever touched -- `edge`, `stable`,
#      `production-eu` and friends live in the same list and are named nothing
#      like a PR;
#   2. an environment whose PR is still OPEN is skipped, because deleting it
#      under a live PR drops any protection rule or scoped secret its next
#      deploy depends on;
#   3. an environment that still HOLDS deployments is skipped and reported --
#      the records are cleanup-github-deployments.sh's job, and a shell that
#      still has records is not the thing this script was written for.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_* helpers and parse_args, shared by every .ci/scripts entry point
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"
REPO="${ARG_REPO:-}"
DRY_RUN="${ARG_DRY_RUN:-false}"

require_cmd gh

if [[ -z "$REPO" ]]; then
    log_error "Usage: cleanup-pr-environments.sh --repo <owner/repo> [--dry-run]"
    exit 1
fi

log_step "Cleaning up empty pr-N environments in $REPO"
[[ "$DRY_RUN" == "true" ]] && log_warn "DRY-RUN mode: no deletions will be performed"

envs="$(gh api "repos/$REPO/environments" --paginate --jq '.environments[]?.name' 2>/dev/null |
    grep -E '^pr-[0-9]+$' | sort -t- -k2 -n)"
if [[ -z "$envs" ]]; then
    log_info "No pr-N environments found"
    exit 0
fi

deleted=0 skipped=0 total=0
while IFS= read -r env; do
    [[ -z "$env" ]] && continue
    total=$((total + 1))
    num="${env#pr-}"

    state="$(gh pr view "$num" --repo "$REPO" --json state --jq .state 2>/dev/null || echo UNKNOWN)"
    if [[ "$state" == "OPEN" ]]; then
        log_warn "SKIP $env: PR #$num is still OPEN"
        skipped=$((skipped + 1))
        continue
    fi

    n_dep="$(gh api "repos/$REPO/deployments?environment=$env&per_page=100" --jq 'length' 2>/dev/null || echo unknown)"
    if [[ "$n_dep" != "0" ]]; then
        log_warn "SKIP $env: still holds $n_dep deployment record(s) -- run cleanup-github-deployments.sh first"
        skipped=$((skipped + 1))
        continue
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete environment $env (PR #$num $state, 0 deployments)"
        continue
    fi
    if gh api -X DELETE "repos/$REPO/environments/$env" >/dev/null 2>&1; then
        log_info "Deleted $env (PR #$num $state)"
        deleted=$((deleted + 1))
    else
        log_warn "Failed to delete $env -- this needs a token with Administration:write"
        skipped=$((skipped + 1))
    fi
done <<<"$envs"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Would delete $((total - skipped)) of $total pr-N environment(s)"
else
    log_info "Deleted $deleted of $total pr-N environment(s); $skipped skipped"
fi
