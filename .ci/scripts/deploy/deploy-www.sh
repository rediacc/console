#!/bin/bash
# Deploy the www Worker to Cloudflare
#
# Handles both production and preview deployments.
# Both use the same index.ts entry point which embeds the account server directly.
# - Production: uses wrangler.toml as-is, applies migrations
# - Preview: creates per-PR D1 database, applies migrations, deploys with preview config
#
# Usage:
#   deploy-www.sh                  # production
#   deploy-www.sh --name pr-379    # preview

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

parse_args "$@"

REPO_ROOT="$(get_repo_root)"
WORKER_DIR="$REPO_ROOT/workers/www"

if [[ ! -f "$WORKER_DIR/wrangler.toml" ]]; then
    log_error "www worker not found at $WORKER_DIR"
    exit 1
fi

cd "$WORKER_DIR"

# Install deps if not already installed
if [[ ! -d "node_modules" ]]; then
    npm install
fi

# Get D1 database UUID by name. Returns UUID or empty string if not found.
get_d1_uuid() {
    local db_name="$1"
    npx wrangler d1 info "$db_name" --json 2>/dev/null | jq -r '.uuid // empty' || true
}

if [[ -n "${ARG_NAME:-}" ]]; then
    # ---- PREVIEW DEPLOYMENT ----
    log_step "Deploying preview worker: $ARG_NAME"

    PR_NUM="${ARG_NAME#pr-}"
    DB_NAME="account-db-pr-${PR_NUM}"

    # Create D1 database if it does not already exist
    DB_UUID="$(get_d1_uuid "$DB_NAME")"
    if [[ -z "$DB_UUID" ]]; then
        log_step "Creating D1 database: $DB_NAME"
        npx wrangler d1 create "$DB_NAME" --location eeur
        DB_UUID="$(get_d1_uuid "$DB_NAME")"
        if [[ -z "$DB_UUID" ]]; then
            log_error "Failed to retrieve UUID for newly created D1 database: $DB_NAME"
            exit 1
        fi
        log_info "Created D1 database $DB_NAME (UUID: $DB_UUID)"
    else
        log_info "D1 database $DB_NAME already exists (UUID: $DB_UUID)"
    fi

    cat >wrangler.preview.toml <<TOML
name = "$ARG_NAME"
main = "src/index.ts"
compatibility_date = "2026-01-20"
compatibility_flags = ["nodejs_compat"]

[assets]
directory = "./dist"
binding = "ASSETS"
not_found_handling = "404-page"
run_worker_first = ["/account", "/account/*"]

[[d1_databases]]
binding = "DB"
database_name = "$DB_NAME"
database_id = "$DB_UUID"
migrations_dir = "../../private/account/drizzle"
TOML

    # Apply migrations (idempotent — skips already-applied)
    log_step "Applying migrations to $DB_NAME..."
    npx wrangler d1 migrations apply "$DB_NAME" --remote --config wrangler.preview.toml
    log_info "Migrations applied to $DB_NAME"

    npx wrangler deploy --config wrangler.preview.toml
    rm -f wrangler.preview.toml
else
    # ---- PRODUCTION DEPLOYMENT ----
    log_step "Deploying www production worker..."

    # Apply migrations (idempotent — skips already-applied)
    log_step "Applying migrations to account-db..."
    npx wrangler d1 migrations apply account-db --remote
    log_info "Migrations applied to account-db"

    npx wrangler deploy
fi
