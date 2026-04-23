#!/bin/bash
# Clone a D1 database from source to target
#
# Exports the source database, wraps with PRAGMA foreign_keys=OFF for safe
# import (D1 exports tables alphabetically, not in FK dependency order),
# imports into the target database, and verifies FK integrity.
#
# Usage:
#   clone-d1.sh --source account-db-eu --target edge-account-db-eu
#   clone-d1.sh --source account-db-eu --target account-db-pr-42 --wrangler-config wrangler.preview.toml
#
# Requires: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
SOURCE_DB=""
TARGET_DB=""
WRANGLER_CONFIG=""
SANITIZE="false"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            SOURCE_DB="$2"
            shift 2
            ;;
        --target)
            TARGET_DB="$2"
            shift 2
            ;;
        --wrangler-config)
            WRANGLER_CONFIG="$2"
            shift 2
            ;;
        --sanitize)
            SANITIZE="true"
            shift
            ;;
        *)
            log_error "Unknown argument: $1"
            exit 1
            ;;
    esac
done

if [[ -z "$SOURCE_DB" ]] || [[ -z "$TARGET_DB" ]]; then
    log_error "Usage: clone-d1.sh --source <db-name> --target <db-name> [--wrangler-config <path>]"
    exit 1
fi

require_var CLOUDFLARE_API_TOKEN

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

CONFIG_FLAG=""
if [[ -n "$WRANGLER_CONFIG" ]]; then
    CONFIG_FLAG="--config $WRANGLER_CONFIG"
fi

# Step 1: Export source database
# Wrangler prints a pre-signed R2 URL valid for 1 hour -- strip it from output
# to prevent leaking a database download link in CI logs.
log_step "Exporting D1 database: $SOURCE_DB"
npx wrangler d1 export "$SOURCE_DB" --remote --output="$TMPDIR/export.sql" 2>&1 |
    grep -v 'r2.cloudflarestorage.com\|valid for one hour'
log_info "Exported $(wc -l <"$TMPDIR/export.sql") lines ($(du -h "$TMPDIR/export.sql" | cut -f1))"

# Step 1.5: Sanitize via local sqlite3 if requested
if [[ "$SANITIZE" == "true" ]]; then
    log_step "Sanitizing data via local sqlite3"
    require_cmd sqlite3

    # Import into local temp DB, run sanitization, re-export.
    # The target D1 never sees real PII.
    sqlite3 "$TMPDIR/temp.db" <"$TMPDIR/export.sql"
    sqlite3 "$TMPDIR/temp.db" <"$SCRIPT_DIR/sanitize-d1.sql"
    sqlite3 "$TMPDIR/temp.db" .dump >"$TMPDIR/export.sql"
    rm -f "$TMPDIR/temp.db"

    log_info "Sanitized ($(wc -l <"$TMPDIR/export.sql") lines)"
fi

# Step 2: Strip transaction statements (D1 rejects raw BEGIN/COMMIT in SQL imports)
# These come from sqlite3 .dump output during sanitization or from wrangler export.
sed -i '/^BEGIN TRANSACTION;$/d; /^COMMIT;$/d; /^BEGIN;$/d; /^SAVEPOINT /d; /^RELEASE /d' "$TMPDIR/export.sql"

# Step 3: Generate DROP statements for all tables in the export
log_step "Preparing import with FK safety wrapper"
{
    echo "PRAGMA defer_foreign_keys=ON;"
    echo "PRAGMA foreign_keys=OFF;"
    # Drop existing tables so re-cloning into a non-empty DB works
    # Handles: CREATE TABLE name(, CREATE TABLE `name` (, CREATE TABLE IF NOT EXISTS "name" (
    sed -n 's/^CREATE TABLE \(IF NOT EXISTS \)\?[`"]*\([a-zA-Z_][a-zA-Z0-9_]*\)[`"]*.*/DROP TABLE IF EXISTS "\2";/p' "$TMPDIR/export.sql"
    cat "$TMPDIR/export.sql"
    echo "PRAGMA foreign_keys=ON;"
} >"$TMPDIR/import.sql"

# Step 4: Import into target database
log_step "Importing into D1 database: $TARGET_DB"
# shellcheck disable=SC2086
npx wrangler d1 execute "$TARGET_DB" --remote $CONFIG_FLAG --file="$TMPDIR/import.sql"
log_info "Import complete"

# Step 5: Verify FK integrity
log_step "Verifying foreign key integrity"
# shellcheck disable=SC2086
FK_RESULT=$(npx wrangler d1 execute "$TARGET_DB" --remote $CONFIG_FLAG --command="PRAGMA foreign_key_check" --json 2>/dev/null || true)
FK_COUNT=$(echo "$FK_RESULT" | jq '.[0].results | length' 2>/dev/null || echo "0")
if [[ "$FK_COUNT" -gt 0 ]]; then
    log_error "Foreign key violations found: $FK_COUNT"
    echo "$FK_RESULT" | jq '.[0].results' 2>/dev/null
    exit 1
fi
log_info "FK integrity check passed (0 violations)"
