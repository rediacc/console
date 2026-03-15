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

require_var CLOUDFLARE_API_TOKEN
require_var CLOUDFLARE_ACCOUNT_ID
require_cmd jq

# Cloudflare API token must be a single-line raw token (no Bearer prefix/newlines).
# GitHub secrets can accidentally include trailing newlines from copy/paste.
CLOUDFLARE_API_TOKEN="$(printf '%s' "$CLOUDFLARE_API_TOKEN" | tr -d '\r\n')"
export CLOUDFLARE_API_TOKEN

# Install deps if not already installed
if [[ ! -d "node_modules" ]]; then
    npm install
fi

# Get D1 database UUID by name. Returns UUID or empty string if not found.
get_d1_uuid() {
    local db_name="$1"
    local output
    output="$(npx wrangler d1 info "$db_name" --json 2>/dev/null || true)"
    if [[ -z "$output" ]]; then
        return 0
    fi

    # Wrangler may print non-JSON banners/warnings before JSON.
    # Parse from the first JSON object/array onward to keep this resilient.
    local json_start
    json_start="$(echo "$output" | sed -n '/^[[:space:]]*[{[]/,$p')"
    if [[ -z "$json_start" ]]; then
        return 0
    fi

    echo "$json_start" | jq -r '.uuid // empty' 2>/dev/null || true
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
upload_source_maps = true

[observability]
enabled = true

[observability.logs]
enabled = true
invocation_logs = false # Disabled to reduce high-volume per-request log noise/cost.

[observability.traces]
enabled = true
head_sampling_rate = 1

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
