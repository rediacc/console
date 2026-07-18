#!/bin/bash
# Delete all GitHub deployment records for one environment
# Usage: cleanup-github-deployments.sh --repo <owner/repo> --environment <name> [--dry-run]
#
# Called on PR close to drop the pr-N environment from the repo's Deployments
# view. Deleting the environment OBJECT requires Administration:write, which
# neither GITHUB_TOKEN nor the housekeeping App token carries -- but the
# Deployments view is driven by the deployment RECORDS, which need only
# deployments:write, so deleting the records achieves the visible cleanup
# without admin rights. Requires an authenticated `gh` (GH_TOKEN).

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

parse_args "$@"

REPO="${ARG_REPO:-}"
ENVIRONMENT="${ARG_ENVIRONMENT:-}"
DRY_RUN="${ARG_DRY_RUN:-false}"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd gh

if [[ -z "$REPO" ]] || [[ -z "$ENVIRONMENT" ]]; then
    log_error "Usage: cleanup-github-deployments.sh --repo <owner/repo> --environment <name> [--dry-run]"
    exit 1
fi

# =============================================================================
# MAIN
# =============================================================================

log_step "Cleaning up GitHub deployments for environment: $ENVIRONMENT ($REPO)"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN mode: no deletions will be performed"
fi

ids="$(gh api "repos/$REPO/deployments?environment=$ENVIRONMENT&per_page=100" --paginate --jq '.[].id')"

if [[ -z "$ids" ]]; then
    log_info "No deployments found for $ENVIRONMENT"
    exit 0
fi

deleted=0
total=0
while IFS= read -r id; do
    [[ -z "$id" ]] && continue
    total=$((total + 1))
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete deployment $id ($ENVIRONMENT)"
        continue
    fi
    # Active deployments cannot be deleted; mark inactive first (best-effort)
    gh api "repos/$REPO/deployments/$id/statuses" -X POST -f state=inactive >/dev/null 2>&1 || true
    if gh api -X DELETE "repos/$REPO/deployments/$id" >/dev/null 2>&1; then
        deleted=$((deleted + 1))
    else
        log_warn "Failed to delete deployment $id ($ENVIRONMENT)"
    fi
done <<<"$ids"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Would delete $total deployment(s) for $ENVIRONMENT"
else
    log_info "Deleted $deleted of $total deployment(s) for $ENVIRONMENT"
fi
