#!/bin/bash
# Delete Cloudflare Pages preview deployments for a specific branch
# Usage: cleanup-cf-preview.sh --branch <branch_name> [--dry-run]
#
# Called on PR close to remove preview deployments that are no longer needed.
# Gracefully handles the CF API restriction that the latest deployment per
# branch cannot be deleted.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

parse_args "$@"

BRANCH="${ARG_BRANCH:-}"
DRY_RUN="${ARG_DRY_RUN:-false}"
CF_PAGES_PROJECT="rediacc"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd curl
require_cmd jq
require_var CLOUDFLARE_API_TOKEN
require_var CLOUDFLARE_ACCOUNT_ID

if [[ -z "$BRANCH" ]]; then
    log_error "Usage: cleanup-cf-preview.sh --branch <branch_name> [--dry-run]"
    exit 1
fi

# =============================================================================
# HELPERS
# =============================================================================

# Cloudflare API request helper
cf_api() {
    local method="$1" endpoint="$2"
    shift 2
    curl -s -X "$method" \
        "https://api.cloudflare.com/client/v4$endpoint" \
        -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
        -H "Content-Type: application/json" \
        "$@"
}

# =============================================================================
# MAIN
# =============================================================================

log_step "Cleaning up CF Pages preview deployments for branch: $BRANCH"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN mode: no deletions will be performed"
fi

# Paginate through all preview deployments
all_deployments="[]"
page=1

while true; do
    response="$(cf_api GET "/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$CF_PAGES_PROJECT/deployments?env=preview&per_page=25&page=$page" 2>/dev/null || echo '{"result":[]}')"

    success="$(echo "$response" | jq -r '.success // false')"
    if [[ "$success" != "true" ]]; then
        log_warn "CF API request failed on page $page"
        break
    fi

    page_results="$(echo "$response" | jq --arg branch "$BRANCH" \
        '[.result[] | select(.deployment_trigger.metadata.branch == $branch) | {id: .id, created_on: .created_on}]')"

    all_results="$(echo "$response" | jq '.result | length')"
    all_deployments="$(echo "$all_deployments" | jq ". + $page_results")"

    if [[ "$all_results" -lt 25 ]]; then
        break
    fi
    page=$((page + 1))
done

total="$(echo "$all_deployments" | jq 'length')"
log_step "Found $total preview deployments for branch '$BRANCH'"

if [[ "$total" -eq 0 ]]; then
    log_info "No preview deployments to clean up"
    exit 0
fi

deleted=0

while IFS= read -r deployment; do
    dep_id="$(echo "$deployment" | jq -r '.id')"
    created_on="$(echo "$deployment" | jq -r '.created_on')"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete: $dep_id (created: $created_on)"
        deleted=$((deleted + 1))
    else
        del_response="$(cf_api DELETE "/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$CF_PAGES_PROJECT/deployments/$dep_id?force=true" 2>/dev/null || echo '{"success":false}')"
        del_success="$(echo "$del_response" | jq -r '.success // false')"

        if [[ "$del_success" == "true" ]]; then
            log_debug "Deleted: $dep_id"
            deleted=$((deleted + 1))
        else
            # Gracefully handle "latest deployment cannot be deleted" or other errors
            error_msg="$(echo "$del_response" | jq -r '.errors[0].message // "unknown error"')"
            log_warn "Could not delete $dep_id: $error_msg"
        fi
    fi
done < <(echo "$all_deployments" | jq -c '.[]')

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Would delete $deleted of $total deployments for branch '$BRANCH'"
else
    log_info "Deleted $deleted of $total deployments for branch '$BRANCH'"
fi
