#!/bin/bash
# Delete orphaned migration-test D1 databases
# Usage: cleanup-stale-d1.sh [--dry-run] [--max-age <minutes>]
#
# Finds D1 databases matching "account-db-migration-test-*" that are older
# than --max-age (default: 60 minutes) and deletes them. Defense-in-depth
# for the migration-test CI job, which normally cleans up via trap EXIT.
#
# Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

parse_args "$@"

DRY_RUN="${ARG_DRY_RUN:-false}"
MAX_AGE_MINUTES="${ARG_MAX_AGE:-60}"
PREFIX="account-db-migration-test-"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd jq
require_cmd npx
require_var CLOUDFLARE_API_TOKEN
require_var CLOUDFLARE_ACCOUNT_ID

# =============================================================================
# MAIN
# =============================================================================

log_step "Listing D1 databases..."

# Wrangler may print non-JSON banners before JSON output. Extract JSON only.
RAW_OUTPUT="$(npx wrangler d1 list --json 2>/dev/null || true)"
DBS="$(echo "$RAW_OUTPUT" | sed -n '/^\[/,$p')"
if [[ -z "$DBS" ]] || ! echo "$DBS" | jq empty 2>/dev/null; then
    log_info "No D1 databases found (or API unavailable)"
    exit 0
fi
TOTAL="$(echo "$DBS" | jq 'length')"
log_info "Found $TOTAL total D1 databases"

# Calculate cutoff timestamp (MAX_AGE_MINUTES ago)
if date --version >/dev/null 2>&1; then
    # GNU date (Linux)
    CUTOFF="$(date -u -d "${MAX_AGE_MINUTES} minutes ago" '+%Y-%m-%dT%H:%M:%S')"
else
    # BSD date (macOS)
    CUTOFF="$(date -u -v-"${MAX_AGE_MINUTES}"M '+%Y-%m-%dT%H:%M:%S')"
fi
log_info "Cutoff: $CUTOFF (databases older than ${MAX_AGE_MINUTES}m)"

# Filter for stale migration-test databases
STALE="$(echo "$DBS" | jq -r --arg prefix "$PREFIX" --arg cutoff "$CUTOFF" \
    '.[] | select(.name | startswith($prefix)) | select(.created_at < $cutoff) | .name')"

if [[ -z "$STALE" ]]; then
    log_info "No stale migration-test databases found"
    exit 0
fi

STALE_COUNT="$(echo "$STALE" | wc -l)"
log_step "Found $STALE_COUNT stale database(s)"

if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN mode: no deletions will be performed"
fi

deleted=0
while IFS= read -r db_name; do
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete: $db_name"
        deleted=$((deleted + 1))
    else
        log_info "Deleting: $db_name"
        if npx wrangler d1 delete "$db_name" --skip-confirmation 2>/dev/null; then
            deleted=$((deleted + 1))
        else
            log_warn "Failed to delete: $db_name"
        fi
    fi
done <<<"$STALE"

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Would delete $deleted of $STALE_COUNT stale databases"
else
    log_info "Deleted $deleted of $STALE_COUNT stale databases"
fi
