#!/bin/bash
# Wipe the bench environment back to a clean state.
#
# This is destructive: it deletes ALL rows from every table in the bench D1
# database, then re-applies migrations to recreate the schema, and finally
# deletes every object in the bench R2 bucket. The worker code itself is
# left alone — re-deploy via scripts/dev/deploy-bench.sh if you also want
# fresh worker code.
#
# Use this when:
#   - bench accumulated cruft and you want a clean slate for testing
#   - a migration is broken on bench and you want to reset and re-deploy
#   - someone else's test data is in the way
#
# Auth (uses scripts/dev/lib/cf-auth.sh — see that file's header for details):
#   CF_API_KEY + CF_EMAIL    Global API Key (recommended)
#   CF_MANAGEMENT_TOKEN      Pre-created scoped API token
#   Interactive prompt       Asks for one of the above when neither is set
#
# bench is internal-only, so there's no soft-confirm dance: pass --yes to
# skip the single confirmation prompt for non-interactive use.
#
# Usage:
#   ./scripts/dev/reset-bench.sh                # interactive (asks once)
#   ./scripts/dev/reset-bench.sh --yes          # non-interactive
#   ./scripts/dev/reset-bench.sh --d1-only      # skip R2 wipe
#   ./scripts/dev/reset-bench.sh --r2-only      # skip D1 wipe
#
# Resources this script touches:
#   D1:     account-db-bench
#   R2:     rediacc-configs-bench
#
# Does NOT touch the worker code or DNS — see scripts/dev/deploy-bench.sh
# for that.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
source "$ROOT_DIR/.ci/scripts/lib/common.sh"
source "$SCRIPT_DIR/lib/cf-auth.sh"

# ─── Argument parsing ──────────────────────────────────────────────────
ASSUME_YES=false
DO_D1=true
DO_R2=true
for arg in "$@"; do
    case "$arg" in
        --yes | -y) ASSUME_YES=true ;;
        --d1-only) DO_R2=false ;;
        --r2-only) DO_D1=false ;;
        -h | --help)
            grep '^# ' "$0" | sed 's/^# \?//'
            exit 0
            ;;
        *)
            log_error "Unknown argument: $arg"
            log_error "Run with --help for usage."
            exit 2
            ;;
    esac
done

# ─── Prereqs ───────────────────────────────────────────────────────────
require_cmd curl
require_cmd jq
require_cmd npx

ACCOUNT_ID="fa51e4a18d553c30e1633288e9733d04"
DB_UUID="ac45c2de-053b-404c-bc47-9ad9cbd2bb15"
DB_NAME="account-db-bench"
BUCKET="rediacc-configs-bench"

# ─── Cloudflare auth ───────────────────────────────────────────────────
resolve_cf_auth
trap 'self_destruct_credentials 2>/dev/null || true' EXIT INT TERM

if [[ -n "${CF_MANAGEMENT_TOKEN:-}" ]]; then
    export CLOUDFLARE_API_TOKEN="$CF_MANAGEMENT_TOKEN"
else
    log_error "resolve_cf_auth did not produce a management token (unexpected)"
    exit 1
fi
export CLOUDFLARE_ACCOUNT_ID="$ACCOUNT_ID"

# Unset the legacy global-key envs so wrangler only sees CLOUDFLARE_API_TOKEN.
# Note: cf-auth.sh's CF_AUTH_HEADERS still uses Bearer $CF_MANAGEMENT_TOKEN
# (set by resolve_cf_auth), so curl calls keep working.
unset CF_API_KEY CF_EMAIL

# ─── Confirmation ──────────────────────────────────────────────────────
if [[ "$ASSUME_YES" == "false" ]]; then
    echo
    log_warn "About to wipe the bench environment:"
    [[ "$DO_D1" == "true" ]] && echo "  D1: drop all rows from $DB_NAME, then re-apply migrations"
    [[ "$DO_R2" == "true" ]] && echo "  R2: delete all objects from $BUCKET"
    echo
    read -rp "Type 'wipe bench' to continue: " confirm
    [[ "$confirm" == "wipe bench" ]] || {
        log_error "Aborted."
        exit 1
    }
fi

# ─── D1 wipe ───────────────────────────────────────────────────────────
if [[ "$DO_D1" == "true" ]]; then
    log_step "Querying D1 table list ($DB_NAME)"
    # The d1/database/{uuid}/query endpoint runs against the remote D1.
    # Uses CF_AUTH_HEADERS populated by resolve_cf_auth.
    # Includes d1_migrations: wrangler uses this ledger to decide which
    # migrations to apply, so leaving it intact would cause `wrangler d1
    # migrations apply` to no-op after the wipe and skip schema recreation.
    # _cf_% (Cloudflare-internal) and sqlite_% (SQLite metadata) stay.
    tables_json=$(curl -sS -X POST "$CF_API_BASE/accounts/$ACCOUNT_ID/d1/database/$DB_UUID/query" \
        "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
        -d '{"sql":"SELECT name FROM sqlite_master WHERE type='\''table'\'' AND name NOT LIKE '\''sqlite_%'\'' AND name NOT LIKE '\''_cf_%'\''"}')

    success=$(echo "$tables_json" | jq -r '.success')
    if [[ "$success" != "true" ]]; then
        echo "$tables_json" | jq .
        log_error "D1 query failed"
        exit 1
    fi

    mapfile -t tables < <(echo "$tables_json" | jq -r '.result[0].results[].name')
    if [[ ${#tables[@]} -eq 0 ]]; then
        log_info "No user tables to drop"
    else
        log_step "Dropping ${#tables[@]} tables: ${tables[*]}"
        # Single multi-statement SQL with FK off, then drop drizzle journal so
        # the next migrate run replays from scratch.
        sql='PRAGMA foreign_keys = OFF;'
        for t in "${tables[@]}"; do
            sql="$sql DROP TABLE IF EXISTS \"$t\";"
        done
        sql="$sql DROP TABLE IF EXISTS \"__drizzle_migrations\"; PRAGMA foreign_keys = ON;"

        result=$(curl -sS -X POST "$CF_API_BASE/accounts/$ACCOUNT_ID/d1/database/$DB_UUID/query" \
            "${CF_AUTH_HEADERS[@]}" -H "Content-Type: application/json" \
            -d "$(jq -n --arg sql "$sql" '{sql: $sql}')")
        if ! echo "$result" | jq -r '.success' | grep -q true; then
            echo "$result" | jq .
            log_error "Drop tables failed"
            exit 1
        fi
        log_info "All tables dropped"
    fi

    log_step "Re-applying migrations to $DB_NAME"
    cd "$ROOT_DIR/workers/account"
    [[ -d node_modules ]] || npm install
    npx wrangler d1 migrations apply "$DB_NAME" --remote --config wrangler.bench.toml
    log_info "Schema recreated"
fi

# ─── R2 wipe ───────────────────────────────────────────────────────────
if [[ "$DO_R2" == "true" ]]; then
    log_step "Listing objects in $BUCKET (via wrangler r2 object)"
    cd "$ROOT_DIR/workers/account"
    [[ -d node_modules ]] || npm install

    # The R2 bucket-management API doesn't list objects (those go through the
    # S3-compatible endpoint with R2 access keys). Paginate via cursor so a
    # bucket with >1000 objects doesn't leave orphans behind.
    keys=()
    cursor=""
    while :; do
        url="$CF_API_BASE/accounts/$ACCOUNT_ID/r2/buckets/$BUCKET/objects?per_page=1000"
        [[ -n "$cursor" ]] && url="${url}&cursor=${cursor}"
        keys_json=$(curl -sS "$url" "${CF_AUTH_HEADERS[@]}" 2>/dev/null || echo '{"result":[]}')
        while IFS= read -r k; do
            [[ -n "$k" ]] && keys+=("$k")
        done < <(echo "$keys_json" | jq -r '.result[]?.key // empty' 2>/dev/null)
        cursor=$(echo "$keys_json" | jq -r '.result_info.cursor // ""' 2>/dev/null)
        [[ -z "$cursor" || "$cursor" == "null" ]] && break
    done

    if [[ ${#keys[@]} -eq 0 ]]; then
        log_info "Bucket is already empty (or listing API not available — continuing)"
    else
        log_step "Deleting ${#keys[@]} objects from $BUCKET"
        for k in "${keys[@]}"; do
            npx wrangler r2 object delete "$BUCKET/$k" --remote >/dev/null
        done
        log_info "Objects deleted"
    fi
fi

echo
log_info "bench has been reset"
echo "  Worker code is unchanged. To redeploy fresh code: scripts/dev/deploy-bench.sh"
