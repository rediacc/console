#!/bin/bash
# Export D1 databases to local .backups/ folder.
#
# Usage:
#   export CF_MANAGEMENT_TOKEN="<scoped-api-token>"
#   ./scripts/dev/backup-d1.sh [--dry-run] [--self-destruct] [production|edge]
#
# Auth:
#   CF_MANAGEMENT_TOKEN  - Scoped API token (recommended)
#   CF_API_KEY + CF_EMAIL - Global API Key (legacy)
#   See rotate-secrets.sh header for token creation guide.
#
# Flags:
#   --dry-run        Show what would be done without exporting
#   --self-destruct  Delete CF_MANAGEMENT_TOKEN after backup (off by default for backups)
#   production|edge  Only back up one environment
#
# Outputs:
#   .backups/production/account-db-YYYY-MM-DDTHH-MM-SS.sql
#   .backups/edge/edge-account-db-YYYY-MM-DDTHH-MM-SS.sql
#
# Exit codes:
#   0 - Success
#   1 - Error

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"
source "$SCRIPT_DIR/lib/cf-auth.sh"

ACCOUNT_ID="fa51e4a18d553c30e1633288e9733d04"
BACKUP_DIR="$ROOT_DIR/.backups"

# D1 databases to back up
PROD_DB="account-db"
EDGE_DB="edge-account-db"

# =============================================================================
# ARGUMENT PARSING
# =============================================================================

DRY_RUN=false
SELF_DESTRUCT=false
TARGET=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --self-destruct) SELF_DESTRUCT=true ;;
        production | prod) TARGET="production" ;;
        edge) TARGET="edge" ;;
        *)
            log_error "Unknown argument: $arg"
            log_error "Usage: backup-d1.sh [--dry-run] [--self-destruct] [production|edge]"
            exit 1
            ;;
    esac
done

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd npx

resolve_cf_auth

if [[ "$SELF_DESTRUCT" == "true" ]]; then
    check_self_destruct_capable
fi

# Map to wrangler env vars
if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
    export CLOUDFLARE_API_TOKEN="$CF_MANAGEMENT_TOKEN"
elif [[ -n "${CF_API_KEY:-}" ]]; then
    export CLOUDFLARE_API_KEY="$CF_API_KEY"
    export CLOUDFLARE_EMAIL="$CF_EMAIL"
fi
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"

# =============================================================================
# HELPERS
# =============================================================================

backup_database() {
    local env_name="$1" db_name="$2"
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H-%M-%S")
    local out_dir="$BACKUP_DIR/$env_name"
    local out_file="$out_dir/${db_name}-${timestamp}.sql"

    log_step "Backing up $env_name: $db_name"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would export $db_name to $out_file"
        return
    fi

    mkdir -p "$out_dir"

    # Wrangler prints a pre-signed R2 URL valid for 1 hour -- strip it to avoid leaking
    npx wrangler d1 export "$db_name" --remote --output="$out_file" 2>&1 |
        grep -v 'r2.cloudflarestorage.com\|valid for one hour'

    local lines size
    lines=$(wc -l <"$out_file")
    size=$(du -h "$out_file" | cut -f1)
    log_info "Exported $lines lines ($size) -> $out_file"
}

# =============================================================================
# MAIN
# =============================================================================

log_step "D1 Database Backup"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "DRY-RUN mode: no exports will be performed"
fi

if [[ -z "$TARGET" || "$TARGET" == "production" ]]; then
    backup_database "production" "$PROD_DB"
fi

if [[ -z "$TARGET" || "$TARGET" == "edge" ]]; then
    backup_database "edge" "$EDGE_DB"
fi

log_info "Backup complete"

# ---- Self-destruct (opt-in for backups) ----
if [[ "$SELF_DESTRUCT" == "true" ]]; then
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "[DRY-RUN] Would delete CF management token"
    else
        self_destruct_credentials
    fi
fi
