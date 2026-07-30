#!/bin/bash
# Validate that D1 migrations apply cleanly against a clone of every regional
# production database.
#
# WHY: a migration that works on an empty schema can still fail on real data
# (a NOT NULL added to a populated column, a unique index over existing
# duplicates). Cloning each regional DB and applying migrations to the clone
# catches that before a release touches production.
#
# Edge databases are tested FIRST: edge is the release soak environment, so a
# regression should surface there before it can propagate to stable on the next
# promotion.
#
# Every clone is ephemeral and deleted by an EXIT trap, including on failure.
# No worker is deployed and no public URL is created.
#
# Usage:
#   CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... \
#     .ci/scripts/deploy/test-d1-migrations.sh
#
# Required env:
#   CLOUDFLARE_API_TOKEN    Cloudflare token with D1 access (secret — env, never argv)
#   CLOUDFLARE_ACCOUNT_ID   Cloudflare account
# Optional env:
#   GITHUB_RUN_ID / GITHUB_RUN_ATTEMPT   used to make clone names unique and
#                                        attributable; default to 'local'
#   GITHUB_WORKSPACE                     defaults to the repo root
#
# Reads regions.json for the database names, so adding a region needs no change
# here.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

require_cmd jq
require_cmd npx

: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID is required}"

RUN_ID="${GITHUB_RUN_ID:-local}"
RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
WORKSPACE="${GITHUB_WORKSPACE:-$REPO_ROOT}"

# Edges first (see header), then the stable clones.
# Portable read loop rather than `mapfile`: check-commands.sh bans bash-4-only
# builtins because the ubuntu-slim runner's shell does not ship them.
EDGE_DBS=()
while IFS= read -r _db; do
    [[ -n "$_db" ]] && EDGE_DBS+=("$_db")
done < <(jq -r '.regions[].edgeD1.name' regions.json)
STABLE_DBS=()
while IFS= read -r _db; do
    [[ -n "$_db" ]] && STABLE_DBS+=("$_db")
done < <(jq -r '.regions[].d1.name' regions.json)
ALL_DBS=("${EDGE_DBS[@]}" "${STABLE_DBS[@]}")
CLEANUP_DBS=()

cleanup() {
    echo "::group::Cleanup: deleting test databases"
    for db in "${CLEANUP_DBS[@]}"; do
        # Report what actually happened. The old form swallowed stderr, ignored
        # the exit code and then printed "Deleted $db" unconditionally, so a
        # clone left behind in the Cloudflare account announced itself as
        # cleaned up. Still non-fatal -- this is an EXIT trap and must not mask
        # the real failure that triggered it -- but now it says so.
        if npx wrangler d1 delete "$db" --skip-confirmation >/dev/null 2>&1; then
            echo "  Deleted $db"
        else
            # NOT "needs manual removal". A pre-reap step runs
            # .ci/scripts/housekeeping/cleanup-stale-d1.sh --max-age 60 before
            # every migration-test job (ct-tests.yml), so an orphan left here is
            # swept by the next run. Saying otherwise sends someone to the
            # Cloudflare dashboard for work that already happens on its own --
            # which is exactly what it did after run 30443624545, where a
            # Cloudflare 7500 stranded one database.
            echo "  ::warning::FAILED to delete test database $db. It is orphaned in the Cloudflare account; the pre-reap step on the next migration-test run deletes anything older than 60 minutes, so no manual action is needed unless it survives that."
        fi
    done
    echo "::endgroup::"
}
trap cleanup EXIT

for SOURCE_DB in "${ALL_DBS[@]}"; do
    # REGION_ID strips either account-db- or edge-account-db- prefix.
    REGION_ID="${SOURCE_DB#account-db-}"
    REGION_ID="${REGION_ID#edge-account-db-}"
    # Tag the test DB name so edge vs stable clones are visible in logs and any
    # leaked test DB is trivially attributable to its source.
    if [[ "$SOURCE_DB" == edge-account-db-* ]]; then
        CHANNEL_TAG="edge"
    else
        CHANNEL_TAG="stable"
    fi
    DB_NAME="migration-test-${CHANNEL_TAG}-${REGION_ID}-${RUN_ID}-${RUN_ATTEMPT}"
    CLEANUP_DBS+=("$DB_NAME")

    echo "::group::Test migrations against $SOURCE_DB (${CHANNEL_TAG}/${REGION_ID})"

    npx wrangler d1 create "$DB_NAME" --location eeur
    DB_UUID="$(npx wrangler d1 info "$DB_NAME" --json 2>/dev/null |
        sed -n '/^[[:space:]]*[{[]/,$p' |
        jq -r '.uuid // empty')"

    if [[ -z "$DB_UUID" ]]; then
        log_error "Failed to get UUID for $DB_NAME"
        exit 1
    fi

    "$SCRIPT_DIR/clone-d1.sh" --source "$SOURCE_DB" --target "$DB_NAME"

    TMPCONFIG="workers/www/wrangler-migration-test.toml"
    cat >"$TMPCONFIG" <<TOML
name = "migration-test"
main = "src/index.ts"
compatibility_date = "2026-01-20"

[[d1_databases]]
binding = "DB"
database_name = "$DB_NAME"
database_id = "$DB_UUID"
migrations_dir = "../../private/account/drizzle"
TOML

    cd workers/www
    npx wrangler d1 migrations apply "$DB_NAME" --remote --config wrangler-migration-test.toml
    rm -f wrangler-migration-test.toml
    cd "$WORKSPACE"

    echo "  $SOURCE_DB (${CHANNEL_TAG}/${REGION_ID}): migrations applied successfully"
    echo "::endgroup::"
done

log_info "All ${#ALL_DBS[@]} regional migration tests passed (${#EDGE_DBS[@]} edge + ${#STABLE_DBS[@]} stable)"
