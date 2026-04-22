#!/bin/bash
# Cleanup old GitHub releases, git tags, and GHCR package versions
# Usage: cleanup-versions.sh [options]
#
# Options:
#   --days N       Retention days (default: 10)
#   --versions N   Number of versions to always keep (default: 10)
#   --dry-run      Preview what would be deleted without deleting

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"
source "$SCRIPT_DIR/../../config/constants.sh"

# =============================================================================
# CONFIGURATION
# =============================================================================

parse_args "$@"

RETENTION_DAYS="${ARG_DAYS:-10}"
KEEP_VERSIONS="${ARG_VERSIONS:-10}"
DRY_RUN="${ARG_DRY_RUN:-false}"

# GitHub organization
GITHUB_ORG="rediacc"

# Repos to clean tags from
TAG_REPOS=("console" "renet" "middleware")

# GHCR packages to clean. Each entry is the full package path under
# ghcr.io/rediacc/* (org-relative). Most images live under elite/, but the
# customer-facing on-prem image is at ghcr.io/rediacc/server (no namespace).
GHCR_PACKAGES=(
    "elite/api"
    "elite/bridge"
    "elite/web"
    "elite/plugin-terminal"
    "elite/plugin-browser"
    "elite/cli"
    "server"
)

# Repos to clean deployments from
DEPLOYMENT_REPOS=("console")

# Repos to clean stale branches from (all repos in the org)
BRANCH_REPOS=("console" "renet" "middleware" "account" "elite" "homebrew-tap" "sql")
BRANCH_MAX_AGE_DAYS=30

# Release repo
RELEASE_REPO="rediacc/console"

# Cloudflare Pages project for preview deployments
CF_PAGES_PROJECT="rediacc"

# R2 cleanup
R2_BUCKET="${RELEASES_BUCKET:-rediacc-releases}"
R2_RETENTION_DAYS=7
R2_FORMAT_DIRS=("cli" "desktop" "npm" "apt" "rpm" "apk" "archlinux")
# Orphan v*/ under cli/ and desktop/ older than this are deletable. Conservative
# double of R2_RETENTION_DAYS so a real release whose tag was pruned still has
# time to be noticed before its R2 bytes are reaped.
R2_ORPHAN_VERSION_AGE_DAYS=14
# pr-N/ under any format dir older than this is reaped regardless of PR state.
# A new push on the PR regenerates artifacts via CI, so this only affects
# stale open PRs that nobody touches.
R2_PR_MAX_AGE_DAYS=3
# Package-manager channel retention (apt/, rpm/, apk/, archlinux/).
# Each aws s3 sync during release adds new rediacc-cli-<semver>.<ext> without
# deleting predecessors -- without retention the channel dir grows unbounded.
# Keep if rank < R2_PACKAGE_KEEP_VERSIONS OR age < R2_PACKAGE_KEEP_DAYS.
R2_PACKAGE_KEEP_VERSIONS=7
R2_PACKAGE_KEEP_DAYS=10

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd gh
require_cmd jq
require_cmd curl
require_cmd aws
require_var GH_TOKEN

# =============================================================================
# HELPERS
# =============================================================================

# Cloudflare API request helper
# Usage: cf_api <method> <endpoint>
cf_api() {
    local method="$1" endpoint="$2"
    shift 2
    curl -s -X "$method" \
        "https://api.cloudflare.com/client/v4$endpoint" \
        -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
        -H "Content-Type: application/json" \
        "$@"
}

# Check if a version should be retained
# Usage: should_retain <created_at_iso> <index_from_newest>
# Returns 0 if should keep, 1 if can delete
should_retain() {
    local created_at="$1"
    local index="$2"

    # Keep if within last N versions (0-indexed)
    if [[ "$index" -lt "$KEEP_VERSIONS" ]]; then
        return 0
    fi

    # Keep if within retention days
    local created_epoch
    created_epoch="$(date -d "$created_at" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%SZ" "$created_at" +%s 2>/dev/null || echo 0)"
    local cutoff_epoch
    cutoff_epoch="$(date -d "$RETENTION_DAYS days ago" +%s 2>/dev/null || date -v-${RETENTION_DAYS}d +%s 2>/dev/null)"

    # If date parsing failed, retain by default (don't delete what we can't date)
    if [[ "$created_epoch" -eq 0 ]]; then
        log_warn "Could not parse date '$created_at' - retaining item"
        return 0
    fi

    if [[ "$created_epoch" -gt "$cutoff_epoch" ]]; then
        return 0
    fi

    # Both conditions met: old AND outside keep count
    return 1
}

# =============================================================================
# PHASE 1: GITHUB RELEASES
# =============================================================================

cleanup_releases() {
    log_step "Phase 1: Cleaning up GitHub releases ($RELEASE_REPO)"

    local releases
    releases="$(gh release list --repo "$RELEASE_REPO" --limit 200 --json tagName,createdAt,isDraft,isPrerelease \
        --jq 'sort_by(.createdAt) | reverse' 2>/dev/null || echo "[]")"

    local total
    total="$(echo "$releases" | jq 'length')"
    log_debug "Found $total releases"

    local deleted=0
    local index=0

    while IFS= read -r release; do
        local tag created_at
        tag="$(echo "$release" | jq -r '.tagName')"
        created_at="$(echo "$release" | jq -r '.createdAt')"

        if should_retain "$created_at" "$index"; then
            log_debug "Keeping release: $tag (index=$index)"
        else
            if [[ "$DRY_RUN" == "true" ]]; then
                log_warn "[DRY-RUN] Would delete release: $tag (created: $created_at)"
            else
                # Delete release first, then clean up the tag separately.
                # Using --cleanup-tag can fail if the tag ref is already gone,
                # which causes the entire command to fail even though the release
                # was deleted, leading to "release not found" on retry.
                if retry_with_backoff 3 2 gh release delete "$tag" --repo "$RELEASE_REPO" --yes; then
                    log_debug "Deleted release: $tag"
                    deleted=$((deleted + 1))
                    # Best-effort tag cleanup (may already be gone)
                    gh api -X DELETE "repos/$RELEASE_REPO/git/refs/tags/$tag" 2>/dev/null || true
                else
                    log_warn "Failed to delete release: $tag"
                fi
            fi
        fi

        index=$((index + 1))
    done < <(echo "$releases" | jq -c '.[]')

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "Releases: would delete $deleted of $total"
    else
        log_info "Releases: deleted $deleted of $total"
    fi
}

# =============================================================================
# PHASE 2: GIT TAGS
# =============================================================================

cleanup_tags() {
    log_step "Phase 2: Cleaning up git tags"

    for repo in "${TAG_REPOS[@]}"; do
        local full_repo="$GITHUB_ORG/$repo"
        log_step "  Processing tags for $full_repo"

        # List tags sorted by date (newest first)
        local tags
        tags="$(gh api "repos/$full_repo/tags" --paginate --jq '.[].name' 2>/dev/null || echo "")"

        if [[ -z "$tags" ]]; then
            log_debug "  No tags found for $full_repo"
            continue
        fi

        # Get tag details with dates
        local tag_data="[]"
        while IFS= read -r tag_name; do
            [[ -z "$tag_name" ]] && continue

            # Try to get annotated tag date, fall back to commit date
            local ref_data
            ref_data="$(gh api "repos/$full_repo/git/ref/tags/$tag_name" 2>/dev/null || echo "")"
            if [[ -z "$ref_data" ]]; then
                continue
            fi

            local obj_type obj_sha
            obj_type="$(echo "$ref_data" | jq -r '.object.type')"
            obj_sha="$(echo "$ref_data" | jq -r '.object.sha')"

            local tag_date=""
            if [[ "$obj_type" == "tag" ]]; then
                # Annotated tag - get tagger date
                tag_date="$(gh api "repos/$full_repo/git/tags/$obj_sha" --jq '.tagger.date' 2>/dev/null || echo "")"
            fi

            if [[ -z "$tag_date" ]]; then
                # Lightweight tag or fallback - use commit date
                local commit_sha="$obj_sha"
                if [[ "$obj_type" == "tag" ]]; then
                    commit_sha="$(gh api "repos/$full_repo/git/tags/$obj_sha" --jq '.object.sha' 2>/dev/null || echo "$obj_sha")"
                fi
                tag_date="$(gh api "repos/$full_repo/git/commits/$commit_sha" --jq '.committer.date' 2>/dev/null || echo "")"
            fi

            if [[ -n "$tag_date" ]]; then
                tag_data="$(echo "$tag_data" | jq --arg name "$tag_name" --arg date "$tag_date" '. + [{"name": $name, "date": $date}]')"
            fi
        done <<<"$tags"

        # Sort by date descending and apply retention
        tag_data="$(echo "$tag_data" | jq 'sort_by(.date) | reverse')"
        local total
        total="$(echo "$tag_data" | jq 'length')"

        local deleted=0
        local index=0

        while IFS= read -r entry; do
            local tag_name tag_date
            tag_name="$(echo "$entry" | jq -r '.name')"
            tag_date="$(echo "$entry" | jq -r '.date')"

            if should_retain "$tag_date" "$index"; then
                log_debug "  Keeping tag: $tag_name"
            else
                if [[ "$DRY_RUN" == "true" ]]; then
                    log_warn "  [DRY-RUN] Would delete tag: $tag_name ($tag_date)"
                else
                    if retry_with_backoff 3 2 gh api -X DELETE "repos/$full_repo/git/refs/tags/$tag_name" 2>/dev/null; then
                        log_debug "  Deleted tag: $tag_name"
                        deleted=$((deleted + 1))
                    else
                        log_warn "  Failed to delete tag: $tag_name"
                    fi
                fi
            fi

            index=$((index + 1))
        done < <(echo "$tag_data" | jq -c '.[]')

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "  Tags ($full_repo): would delete $deleted of $total"
        else
            log_info "  Tags ($full_repo): deleted $deleted of $total"
        fi
    done
}

# =============================================================================
# PHASE 3: GHCR PACKAGE VERSIONS
# =============================================================================

cleanup_packages() {
    log_step "Phase 3: Cleaning up GHCR package versions"

    for package_name in "${GHCR_PACKAGES[@]}"; do
        local encoded_package
        encoded_package="$(echo "$package_name" | sed 's|/|%2F|g')"

        log_step "  Processing package: $package_name"

        # List versions (newest first, single page — avoids OOM on large repos).
        # The API returns newest first by default. We fetch 100 per page which is
        # enough to apply retention (keep N) and clean up a batch per run.
        local raw_versions versions
        raw_versions="$(gh api "orgs/$GITHUB_ORG/packages/container/$encoded_package/versions?per_page=100" 2>/dev/null || echo "")"

        # Validate response is a JSON array (not an error object)
        if [[ -z "$raw_versions" ]] || ! echo "$raw_versions" | jq -e 'type == "array"' >/dev/null 2>&1; then
            log_warn "  Skipping $package_name: package not accessible (app token may lack org-level packages permission)"
            continue
        fi

        versions="$(echo "$raw_versions" | jq '[.[] | {id: .id, tags: .metadata.container.tags, created: .created_at}] | sort_by(.created) | reverse')"

        local total
        total="$(echo "$versions" | jq 'length')"
        log_debug "  Found $total versions for $package_name"

        local deleted=0
        local index=0
        local consecutive_failures=0

        # Materialize the version list to a temp variable to avoid broken pipe
        # when the loop breaks early while jq is still writing
        local version_lines
        version_lines="$(echo "$versions" | jq -c '.[]' 2>/dev/null || true)"

        while IFS= read -r version; do
            [[ -z "$version" ]] && continue

            local version_id created_at tags
            version_id="$(echo "$version" | jq -r '.id')"
            created_at="$(echo "$version" | jq -r '.created')"
            tags="$(echo "$version" | jq -r '.tags // [] | join(", ")')"

            if should_retain "$created_at" "$index"; then
                log_debug "  Keeping version: $version_id (tags: $tags)"
            else
                if [[ "$DRY_RUN" == "true" ]]; then
                    log_warn "  [DRY-RUN] Would delete version: $version_id (tags: $tags, created: $created_at)"
                else
                    local api_output
                    api_output="$(gh api -X DELETE "orgs/$GITHUB_ORG/packages/container/$encoded_package/versions/$version_id" 2>&1)"
                    local api_exit=$?

                    if [[ $api_exit -eq 0 ]]; then
                        log_debug "  Deleted version: $version_id (tags: $tags)"
                        deleted=$((deleted + 1))
                        consecutive_failures=0
                    else
                        consecutive_failures=$((consecutive_failures + 1))
                        log_warn "  Could not delete version $version_id (tags: $tags): $api_output"
                        if [[ "$consecutive_failures" -ge 5 ]]; then
                            log_warn "  Skipping remaining versions for $package_name after $consecutive_failures consecutive failures"
                            break
                        fi
                    fi
                fi
            fi

            index=$((index + 1))
        done <<<"$version_lines"

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "  Package $package_name: would delete $deleted of $total versions"
        else
            log_info "  Package $package_name: deleted $deleted of $total versions"
        fi
    done
}

# =============================================================================
# PHASE 4: GITHUB DEPLOYMENTS
# =============================================================================

cleanup_deployments() {
    log_step "Phase 4: Cleaning up GitHub deployments"
    local keep_per_env=2 # Keep last N deployments per environment

    for repo in "${DEPLOYMENT_REPOS[@]}"; do
        local full_repo="$GITHUB_ORG/$repo"
        log_step "  Processing deployments for $full_repo"

        # Fetch all deployments, sorted newest first
        local deployments
        deployments="$(gh api "repos/$full_repo/deployments?per_page=100" \
            --paginate \
            --jq '[.[] | {id: .id, environment: .environment, created_at: .created_at}]' \
            2>/dev/null || echo "[]")"

        # Flatten paginated results and sort by date (newest first)
        deployments="$(echo "$deployments" | jq -s 'flatten | sort_by(.created_at) | reverse')"

        local total
        total="$(echo "$deployments" | jq 'length')"
        log_debug "  Found $total deployments"

        # Group by environment, keep last N per environment, delete the rest
        local environments
        environments="$(echo "$deployments" | jq -r '[.[].environment] | unique | .[]')"

        local deleted=0
        for env in $environments; do
            local env_deps
            env_deps="$(echo "$deployments" | jq -c "[.[] | select(.environment == \"$env\")]")"
            local env_count
            env_count="$(echo "$env_deps" | jq 'length')"

            if [[ "$env_count" -le "$keep_per_env" ]]; then
                log_debug "  $env: $env_count deployment(s), all retained"
                continue
            fi

            # Skip the first N (newest), delete the rest
            local to_delete
            to_delete="$(echo "$env_deps" | jq -c ".[$keep_per_env:][]")"

            while IFS= read -r dep; do
                [[ -z "$dep" ]] && continue
                local dep_id created_at
                dep_id="$(echo "$dep" | jq -r '.id')"
                created_at="$(echo "$dep" | jq -r '.created_at')"

                if [[ "$DRY_RUN" == "true" ]]; then
                    log_warn "  [DRY-RUN] Would delete: $dep_id ($env, $created_at)"
                    deleted=$((deleted + 1))
                else
                    # Set inactive then delete (GitHub requires inactive before deletion).
                    # Both calls are best-effort -- a failure here (e.g. 403 because the
                    # token lacks deployments:write, or GitHub protecting the latest per
                    # environment) must NOT kill the housekeeping job, since the rest of
                    # the cleanup is independent and was already paid for by the release.
                    gh api "repos/$full_repo/deployments/$dep_id/statuses" \
                        -X POST -f state=inactive >/dev/null 2>&1 || true
                    if retry_with_backoff 3 2 gh api -X DELETE "repos/$full_repo/deployments/$dep_id" 2>/dev/null; then
                        log_debug "  Deleted: $dep_id ($env)"
                        deleted=$((deleted + 1))
                    fi
                fi
            done <<<"$to_delete"
        done

        log_info "  Deployments ($full_repo): deleted $deleted of $total (keeping $keep_per_env per environment)"
    done
}

# =============================================================================
# PHASE 5: CLOUDFLARE PAGES PREVIEW DEPLOYMENTS
# =============================================================================

cleanup_cf_pages() {
    log_step "Phase 5: Cleaning up Cloudflare Pages preview deployments"

    # Soft prerequisite check -- skip if CF credentials are missing
    if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]] || [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
        log_warn "  CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set, skipping CF Pages cleanup"
        return 0
    fi

    local project="$CF_PAGES_PROJECT"
    log_step "  Processing CF Pages project: $project"

    # Paginate through all preview deployments
    local all_deployments="[]"
    local page=1

    while true; do
        local response
        response="$(cf_api GET "/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$project/deployments?env=preview&per_page=25&page=$page" 2>/dev/null || echo '{"result":[]}')"

        local success
        success="$(echo "$response" | jq -r '.success // false')"
        if [[ "$success" != "true" ]]; then
            log_warn "  CF API request failed on page $page"
            break
        fi

        local page_results
        page_results="$(echo "$response" | jq '[.result[] | {id: .id, created_on: .created_on, branch: .deployment_trigger.metadata.branch}]')"

        local count
        count="$(echo "$page_results" | jq 'length')"

        all_deployments="$(echo "$all_deployments" | jq ". + $page_results")"

        if [[ "$count" -lt 25 ]]; then
            break
        fi
        page=$((page + 1))
    done

    # Sort by created_on descending (newest first)
    all_deployments="$(echo "$all_deployments" | jq 'sort_by(.created_on) | reverse')"

    # Identify latest deployment per branch (CF API restriction: cannot delete these)
    local branch_latest
    branch_latest="$(echo "$all_deployments" | jq '[group_by(.branch)[] | .[0].id]')"

    local total
    total="$(echo "$all_deployments" | jq 'length')"
    log_debug "  Found $total preview deployments"

    local deleted=0
    local skipped_latest=0
    local index=0

    while IFS= read -r deployment; do
        local dep_id created_on branch
        dep_id="$(echo "$deployment" | jq -r '.id')"
        created_on="$(echo "$deployment" | jq -r '.created_on')"
        branch="$(echo "$deployment" | jq -r '.branch')"

        # Skip latest deployment per branch (undeletable)
        local is_branch_latest
        is_branch_latest="$(echo "$branch_latest" | jq --arg id "$dep_id" 'index($id) != null')"

        if [[ "$is_branch_latest" == "true" ]]; then
            log_debug "  Skipping (latest for branch '$branch'): $dep_id"
            skipped_latest=$((skipped_latest + 1))
            index=$((index + 1))
            continue
        fi

        if should_retain "$created_on" "$index"; then
            log_debug "  Keeping deployment: $dep_id (branch: $branch)"
        else
            if [[ "$DRY_RUN" == "true" ]]; then
                log_warn "  [DRY-RUN] Would delete CF deployment: $dep_id (branch: $branch, created: $created_on)"
            else
                local del_response
                del_response="$(cf_api DELETE "/accounts/$CLOUDFLARE_ACCOUNT_ID/pages/projects/$project/deployments/$dep_id?force=true" 2>/dev/null || echo '{"success":false}')"
                local del_success
                del_success="$(echo "$del_response" | jq -r '.success // false')"

                if [[ "$del_success" == "true" ]]; then
                    log_debug "  Deleted CF deployment: $dep_id (branch: $branch)"
                    deleted=$((deleted + 1))
                else
                    log_warn "  Failed to delete CF deployment: $dep_id (branch: $branch)"
                fi
            fi
        fi

        index=$((index + 1))
    done < <(echo "$all_deployments" | jq -c '.[]')

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "  CF Pages ($project): would delete $deleted of $total preview deployments ($skipped_latest latest-per-branch, skipped)"
    else
        log_info "  CF Pages ($project): deleted $deleted of $total preview deployments ($skipped_latest latest-per-branch, skipped)"
    fi
}

# =============================================================================
# PHASE 6: GITHUB ENVIRONMENTS (PR previews)
# =============================================================================

cleanup_environments() {
    log_step "Phase 6: Cleaning up stale GitHub preview environments"

    for repo in "${DEPLOYMENT_REPOS[@]}"; do
        local full_repo="$GITHUB_ORG/$repo"
        log_step "  Processing environments for $full_repo"

        # List all environments
        local environments
        environments="$(gh api "repos/$full_repo/environments" --jq '[.environments[] | {name: .name, created: .created_at, updated: .updated_at}]' 2>/dev/null || echo "[]")"

        # Filter to only pr-* environments
        local pr_envs
        pr_envs="$(echo "$environments" | jq '[.[] | select(.name | test("^pr-[0-9]+$"))]')"

        local total
        total="$(echo "$pr_envs" | jq 'length')"
        log_debug "  Found $total pr-* environments"

        if [[ "$total" -eq 0 ]]; then
            log_info "  No stale preview environments to clean up"
            continue
        fi

        # Check each pr-* environment against open PRs
        local deleted=0

        while IFS= read -r env_entry; do
            local env_name pr_number
            env_name="$(echo "$env_entry" | jq -r '.name')"
            pr_number="$(echo "$env_name" | sed 's/^pr-//')"

            # Check if the PR is still open
            local pr_state
            pr_state="$(gh pr view "$pr_number" --repo "$full_repo" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")"

            if [[ "$pr_state" == "OPEN" ]]; then
                log_debug "  Keeping environment: $env_name (PR #$pr_number is open)"
                continue
            fi

            if [[ "$DRY_RUN" == "true" ]]; then
                log_warn "  [DRY-RUN] Would delete environment: $env_name (PR #$pr_number state: $pr_state)"
                deleted=$((deleted + 1))
            else
                if gh api -X DELETE "repos/$full_repo/environments/$env_name" 2>/dev/null; then
                    log_debug "  Deleted environment: $env_name (PR #$pr_number state: $pr_state)"
                    deleted=$((deleted + 1))
                else
                    log_warn "  Failed to delete environment: $env_name"
                fi
            fi
        done < <(echo "$pr_envs" | jq -c '.[]')

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "  Environments ($full_repo): would delete $deleted of $total pr-* environments"
        else
            log_info "  Environments ($full_repo): deleted $deleted of $total pr-* environments"
        fi
    done
}

# =============================================================================
# PHASE 7: CLOUDFLARE D1 PREVIEW DATABASES
# =============================================================================

cleanup_d1_databases() {
    log_step "Phase 7: Cleaning up orphaned D1 preview databases"

    if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]] || [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
        log_warn "  CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set, skipping D1 cleanup"
        return 0
    fi

    # List all D1 databases via CF REST API
    local response
    response="$(cf_api GET "/accounts/$CLOUDFLARE_ACCOUNT_ID/d1/database?per_page=100" 2>/dev/null || echo '{"success":false}')"

    local success
    success="$(echo "$response" | jq -r '.success // false')"
    if [[ "$success" != "true" ]]; then
        log_warn "  D1 list API request failed, skipping D1 cleanup"
        return 0
    fi

    # Filter to only account-db-pr-N databases
    local pr_databases
    pr_databases="$(echo "$response" | jq -c '[.result[] | select(.name | test("^account-db-pr-[0-9]+$")) | {name: .name, uuid: .uuid}]')"

    local total
    total="$(echo "$pr_databases" | jq 'length')"

    if [[ "$total" -eq 0 ]]; then
        log_info "  No pr-* D1 databases found"
        return 0
    fi

    log_debug "  Found $total pr-* D1 databases"

    local deleted=0
    local skipped=0

    while IFS= read -r db_entry; do
        [[ -z "$db_entry" ]] && continue

        local db_name db_uuid pr_number
        db_name="$(echo "$db_entry" | jq -r '.name')"
        db_uuid="$(echo "$db_entry" | jq -r '.uuid')"
        pr_number="${db_name#account-db-pr-}"

        # Check if the PR is still open
        local pr_state
        pr_state="$(gh pr view "$pr_number" --repo "$RELEASE_REPO" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")"

        if [[ "$pr_state" == "OPEN" ]]; then
            log_debug "  Keeping D1 database: $db_name (PR #$pr_number is open)"
            skipped=$((skipped + 1))
            continue
        fi

        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "  [DRY-RUN] Would delete D1 database: $db_name (PR #$pr_number state: $pr_state)"
            deleted=$((deleted + 1))
        else
            local del_response
            del_response="$(cf_api DELETE "/accounts/$CLOUDFLARE_ACCOUNT_ID/d1/database/$db_uuid" 2>/dev/null || echo '{"success":false}')"
            local del_success
            del_success="$(echo "$del_response" | jq -r '.success // false')"

            if [[ "$del_success" == "true" ]]; then
                log_info "  Deleted D1 database: $db_name (PR #$pr_number state: $pr_state)"
                deleted=$((deleted + 1))
            else
                log_warn "  Failed to delete D1 database: $db_name"
            fi
        fi
    done < <(echo "$pr_databases" | jq -c '.[]')

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "  D1 databases: would delete $deleted of $total ($skipped open PRs, skipped)"
    else
        log_info "  D1 databases: deleted $deleted of $total ($skipped open PRs, skipped)"
    fi
}

# =============================================================================
# PHASE 7b: ORPHAN PER-PR TURNSTILE WIDGETS
# Delete Cloudflare Turnstile widgets named `rediacc-console-pr-N` whose PR
# is no longer open. Widget names that don't match the per-PR pattern (e.g.
# the production `rediacc-console` and bench `rediacc-console-bench`) are
# never touched. 24h grace window so the explicit cleanup-preview path
# always wins races with this sweep.
# Mirrors the D1 phase shape; same env requirements + dry-run behavior.
# =============================================================================

cleanup_orphan_turnstile_widgets() {
    log_step "Phase 7b: Cleaning up orphan per-PR Turnstile widgets"

    if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]] || [[ -z "${CLOUDFLARE_ACCOUNT_ID:-}" ]]; then
        log_warn "  CLOUDFLARE_API_TOKEN or CLOUDFLARE_ACCOUNT_ID not set, skipping Turnstile cleanup"
        return 0
    fi

    local response
    response="$(cf_api GET "/accounts/$CLOUDFLARE_ACCOUNT_ID/challenges/widgets?per_page=100" 2>/dev/null || echo '{"success":false}')"

    local success
    success="$(echo "$response" | jq -r '.success // false')"
    if [[ "$success" != "true" ]]; then
        log_warn "  Turnstile widget list API request failed, skipping Turnstile cleanup"
        return 0
    fi

    # Filter to only `rediacc-console-pr-N` widgets. Production + bench
    # widgets (rediacc-console, rediacc-console-bench) don't match this
    # regex and are intentionally untouched.
    local pr_widgets
    pr_widgets="$(echo "$response" | jq -c '[.result[] | select(.name | test("^rediacc-console-pr-[0-9]+$")) | {name: .name, sitekey: .sitekey, created_on: .created_on}]')"

    local total
    total="$(echo "$pr_widgets" | jq 'length')"

    if [[ "$total" -eq 0 ]]; then
        log_info "  No per-PR Turnstile widgets found"
        return 0
    fi

    log_debug "  Found $total per-PR Turnstile widgets"

    local deleted=0
    local skipped=0
    local now_epoch
    now_epoch="$(date -u +%s)"
    local grace_seconds=$((24 * 60 * 60))

    while IFS= read -r widget_entry; do
        [[ -z "$widget_entry" ]] && continue

        local widget_name widget_sitekey created_on pr_number
        widget_name="$(echo "$widget_entry" | jq -r '.name')"
        widget_sitekey="$(echo "$widget_entry" | jq -r '.sitekey')"
        created_on="$(echo "$widget_entry" | jq -r '.created_on')"
        pr_number="${widget_name#rediacc-console-pr-}"

        local pr_state
        pr_state="$(gh pr view "$pr_number" --repo "$RELEASE_REPO" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")"

        if [[ "$pr_state" == "OPEN" ]]; then
            log_debug "  Keeping Turnstile widget: $widget_name (PR #$pr_number is open)"
            skipped=$((skipped + 1))
            continue
        fi

        # 24h grace window so cleanup-preview.yml always wins races
        local created_epoch age_seconds
        created_epoch="$(date -u -d "$created_on" +%s 2>/dev/null || echo 0)"
        age_seconds=$((now_epoch - created_epoch))
        if [[ "$age_seconds" -lt "$grace_seconds" ]]; then
            local remain_hrs=$(((grace_seconds - age_seconds + 3599) / 3600))
            log_debug "  Holding Turnstile widget: $widget_name (PR #$pr_number $pr_state, only $((age_seconds / 3600))h old; ${remain_hrs}h grace remaining)"
            skipped=$((skipped + 1))
            continue
        fi

        if [[ "$DRY_RUN" == "true" ]]; then
            log_warn "  [DRY-RUN] Would delete Turnstile widget: $widget_name (PR #$pr_number state: $pr_state)"
            deleted=$((deleted + 1))
        else
            local del_response
            del_response="$(cf_api DELETE "/accounts/$CLOUDFLARE_ACCOUNT_ID/challenges/widgets/$widget_sitekey" 2>/dev/null || echo '{"success":false}')"
            local del_success
            del_success="$(echo "$del_response" | jq -r '.success // false')"

            if [[ "$del_success" == "true" ]]; then
                log_info "  Deleted Turnstile widget: $widget_name (PR #$pr_number state: $pr_state)"
                deleted=$((deleted + 1))
            else
                log_warn "  Failed to delete Turnstile widget: $widget_name"
            fi
        fi
    done < <(echo "$pr_widgets" | jq -c '.[]')

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "  Turnstile widgets: would delete $deleted of $total ($skipped open or in grace, skipped)"
    else
        log_info "  Turnstile widgets: deleted $deleted of $total ($skipped open or in grace, skipped)"
    fi
}

# =============================================================================
# PHASE 8: R2 ORPHANS
# Reap R2 state the other phases do not cover:
#   - dryrun-<sha>/ prefixes older than R2_RETENTION_DAYS across every format
#     dir (left behind by workflow_dispatch / nightly dryruns)
#   - pr-N/ prefixes whose PR is closed + older than a 24h grace window
#     (belt-and-braces over cleanup-r2-staging.yml; also catches the
#     pre-fix npm/pr-N/ accumulation)
#   - Legacy dead top-level prefixes (staging/, packages/, cli/latest/) --
#     unconditional noop delete each run, protects against regression writes
#   - v<semver>/ under cli/ and desktop/ that is neither in the authoritative
#     versions.json tracker nor a git tag, AND older than
#     R2_ORPHAN_VERSION_AGE_DAYS (reaps PR-pollution such as v1.0.3/ that
#     was never released)
# =============================================================================

# List immediate children of a prefix (returns "PRE dir/" lines unchanged).
r2_ls_prefix() {
    local prefix="$1"
    aws s3 ls "s3://${R2_BUCKET}/${prefix}" \
        --endpoint-url "$R2_ENDPOINT" 2>/dev/null || true
}

# Return LastModified (ISO8601) of the first object under a prefix; empty if
# the prefix is empty or unreadable.
r2_prefix_last_modified() {
    local prefix="$1"
    aws s3 ls "s3://${R2_BUCKET}/${prefix}" --recursive \
        --endpoint-url "$R2_ENDPOINT" 2>/dev/null |
        awk 'NR==1 {print $1"T"$2"Z"; exit}'
}

# Delete a prefix recursively, or log the intent in dry-run.
r2_rm_recursive() {
    local prefix="$1" label="${2:-}"
    if [[ "$DRY_RUN" == "true" ]]; then
        log_warn "  [DRY-RUN] Would delete s3://${R2_BUCKET}/${prefix}${label:+ ($label)}"
        return 0
    fi
    aws s3 rm "s3://${R2_BUCKET}/${prefix}" --recursive \
        --endpoint-url "$R2_ENDPOINT" --quiet 2>/dev/null || true
    log_info "  Deleted s3://${R2_BUCKET}/${prefix}${label:+ ($label)}"
}

cleanup_r2() {
    log_step "Phase 8: Cleaning up R2 orphans"

    # Skip if R2 creds unset; housekeeping job in ci.yml provides them, but
    # local invocations without them should not blow up.
    if [[ -z "${R2_ACCESS_KEY_ID:-}" ]] || [[ -z "${R2_SECRET_ACCESS_KEY:-}" ]] || [[ -z "${R2_ENDPOINT:-}" ]]; then
        log_warn "  R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / R2_ENDPOINT not set, skipping R2 cleanup"
        return 0
    fi

    export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
    export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
    export AWS_DEFAULT_REGION="auto"

    local now_epoch
    now_epoch="$(date -u +%s)"
    local dryrun_max_age=$((R2_RETENTION_DAYS * 86400))
    local orphan_ver_max_age=$((R2_ORPHAN_VERSION_AGE_DAYS * 86400))

    # 8a. Dryrun reaper ------------------------------------------------------
    log_step "  8a: dryrun-*/ older than ${R2_RETENTION_DAYS}d"
    local dryrun_deleted=0
    for dir in "${R2_FORMAT_DIRS[@]}"; do
        while IFS= read -r line; do
            local sub
            sub="$(echo "$line" | awk '/^[[:space:]]*PRE[[:space:]]dryrun-/ {print $2}')"
            [[ -z "$sub" ]] && continue
            local prefix="${dir}/${sub}"
            local last
            last="$(r2_prefix_last_modified "$prefix")"
            [[ -z "$last" ]] && continue
            local last_epoch
            last_epoch="$(date -u -d "$last" +%s 2>/dev/null || echo 0)"
            [[ "$last_epoch" -eq 0 ]] && continue
            if ((now_epoch - last_epoch > dryrun_max_age)); then
                r2_rm_recursive "$prefix" "dryrun $(((now_epoch - last_epoch) / 86400))d old"
                dryrun_deleted=$((dryrun_deleted + 1))
            fi
        done < <(r2_ls_prefix "${dir}/")
    done
    log_info "  8a: processed ${#R2_FORMAT_DIRS[@]} format dirs, deleted $dryrun_deleted dryrun prefix(es)"

    # 8b. PR channel reaper --------------------------------------------------
    # Deletes pr-N/ when EITHER condition holds:
    #   * PR state != OPEN (no grace -- cleanup-r2-staging.yml on PR close
    #     also runs; this sweep is just a backstop)
    #   * last-modified > R2_PR_MAX_AGE_DAYS regardless of PR state
    # The age cap catches stale bytes on long-lived open PRs; next push on
    # the PR regenerates artifacts via CI.
    log_step "  8b: pr-N/ closed or older than ${R2_PR_MAX_AGE_DAYS}d"
    local pr_deleted=0
    local pr_age_max=$((R2_PR_MAX_AGE_DAYS * 86400))
    for dir in "${R2_FORMAT_DIRS[@]}"; do
        while IFS= read -r line; do
            local sub
            sub="$(echo "$line" | awk '/^[[:space:]]*PRE[[:space:]]pr-[0-9]+\// {print $2}')"
            [[ -z "$sub" ]] && continue
            local pr_num="${sub#pr-}"
            pr_num="${pr_num%/}"
            local prefix="${dir}/${sub}"
            local last
            last="$(r2_prefix_last_modified "$prefix")"
            [[ -z "$last" ]] && continue
            local last_epoch
            last_epoch="$(date -u -d "$last" +%s 2>/dev/null || echo 0)"
            [[ "$last_epoch" -eq 0 ]] && continue
            local age=$((now_epoch - last_epoch))
            local reason=""
            if ((age > pr_age_max)); then
                reason="stale $((age / 86400))d"
            else
                local state
                state="$(gh pr view "$pr_num" --repo "$RELEASE_REPO" --json state --jq '.state' 2>/dev/null || echo "UNKNOWN")"
                if [[ "$state" != "OPEN" ]]; then
                    reason="PR #${pr_num} ${state}"
                fi
            fi
            if [[ -n "$reason" ]]; then
                r2_rm_recursive "$prefix" "$reason"
                pr_deleted=$((pr_deleted + 1))
            fi
        done < <(r2_ls_prefix "${dir}/")
    done
    log_info "  8b: deleted $pr_deleted PR channel prefix(es)"

    # 8c. Legacy dead prefixes ----------------------------------------------
    log_step "  8c: legacy dead prefixes"
    for dead in "staging/" "packages/" "cli/latest/"; do
        # Only log when there's actually something there, to avoid noise.
        if [[ -n "$(r2_ls_prefix "$dead")" ]]; then
            r2_rm_recursive "$dead" "legacy"
        fi
    done

    # 8d. Orphan v<semver>/ under cli/ and desktop/ --------------------------
    log_step "  8d: orphan v<semver>/ with no tracker entry and no git tag"
    local git_tags
    git_tags="$(gh api "repos/${RELEASE_REPO}/tags" --paginate --jq '.[].name' 2>/dev/null | grep -E '^v[0-9]' || true)"
    local orphan_ver_deleted=0
    for dir in "cli" "desktop"; do
        local tracker
        tracker="$(aws s3 cp "s3://${R2_BUCKET}/${dir}/versions.json" - \
            --endpoint-url "$R2_ENDPOINT" 2>/dev/null || echo "[]")"
        [[ -z "$tracker" ]] && tracker="[]"
        while IFS= read -r line; do
            local sub
            sub="$(echo "$line" | awk '/^[[:space:]]*PRE[[:space:]]v[0-9]+\./ {print $2}')"
            [[ -z "$sub" ]] && continue
            local ver="${sub#v}"
            ver="${ver%/}"
            local tag="v${ver}"
            # Keep if in tracker
            if echo "$tracker" | jq -e --arg v "$ver" 'index($v) != null' >/dev/null 2>&1; then
                continue
            fi
            # Keep if a git tag exists
            if echo "$git_tags" | grep -qxF "$tag"; then
                continue
            fi
            local prefix="${dir}/${sub}"
            local last
            last="$(r2_prefix_last_modified "$prefix")"
            [[ -z "$last" ]] && continue
            local last_epoch
            last_epoch="$(date -u -d "$last" +%s 2>/dev/null || echo 0)"
            [[ "$last_epoch" -eq 0 ]] && continue
            if ((now_epoch - last_epoch > orphan_ver_max_age)); then
                r2_rm_recursive "$prefix" "orphan ${tag} (not in versions.json, no git tag)"
                orphan_ver_deleted=$((orphan_ver_deleted + 1))
            fi
        done < <(r2_ls_prefix "${dir}/")
    done
    log_info "  8d: deleted $orphan_ver_deleted orphan versioned prefix(es)"

    # 8f. Channel artifact retention ----------------------------------------
    # Every release appends to <fmt>/<channel>/ without ever removing the
    # previous file (aws s3 sync runs without --delete). Accumulating
    # filename patterns:
    #   apt/<channel>/     -> rediacc-cli_<ver>_<arch>.deb (underscore sep)
    #   rpm/<channel>/     -> rediacc-cli-<ver>.<arch>.rpm
    #   apk/<channel>/     -> rediacc-cli-<ver>.apk
    #   archlinux/<ch>/    -> rediacc-cli-<ver>-<arch>.pkg.tar.zst
    #   npm/<channel>/     -> rediacc-cli-<ver>.tgz
    #   desktop/<channel>/ -> rediacc-desktop-<ver>-<platform>.<ext> (+.blockmap)
    # Retention: keep if rank < R2_PACKAGE_KEEP_VERSIONS OR age < KEEP_DAYS.
    # Special case: rediacc-desktop-0.0.0-dev-* are PR CI pollution from
    # before the version-injection fix; always delete.
    # Metadata (Packages.gz, Release*, InRelease, APKINDEX.tar.gz, repodata/,
    # *.db.tar.gz, latest-*.yml, manifest.json, gpg.key, rediacc-cli-latest.tgz)
    # is left alone; next release rewrites it.
    log_step "  8f: channel artifact retention (keep ${R2_PACKAGE_KEEP_VERSIONS}v or ${R2_PACKAGE_KEEP_DAYS}d; zap 0.0.0-dev)"
    local pkg_keep_age=$((R2_PACKAGE_KEEP_DAYS * 86400))
    local pkg_deleted=0
    for fmt in apt rpm apk archlinux npm desktop; do
        for channel in stable edge; do
            local channel_root="${fmt}/${channel}/"
            [[ -z "$(r2_ls_prefix "$channel_root")" ]] && continue
            # listing format: "<iso-ts>|<semver>|<is_dev>|<s3-key>", sorted
            # by semver desc. is_dev=1 for rediacc-desktop-0.0.0-dev-* etc.
            local listing
            listing="$(aws s3 ls "s3://${R2_BUCKET}/${channel_root}" --recursive \
                --endpoint-url "$R2_ENDPOINT" 2>/dev/null |
                awk '{
                    n = split($4, p, "/"); fname = p[n];
                    if (fname !~ /^rediacc-(cli|desktop)[-_]/) next
                    rest = fname; sub(/^rediacc-(cli|desktop)[-_]/, "", rest);
                    if (match(rest, /^[0-9]+\.[0-9]+\.[0-9]+/)) {
                        semver = substr(rest, 1, RLENGTH);
                        after = substr(rest, RLENGTH + 1);
                        is_dev = (semver == "0.0.0" && after ~ /^-dev/) ? 1 : 0;
                        print $1"T"$2"Z""|"semver"|"is_dev"|"$4
                    }
                }' | sort -t'|' -k2,2 -V -r)"
            [[ -z "$listing" ]] && continue
            local idx=0
            while IFS='|' read -r ts semver is_dev key; do
                [[ -z "$key" ]] && continue
                local ts_epoch
                ts_epoch="$(date -u -d "$ts" +%s 2>/dev/null || echo 0)"
                local age=$((now_epoch - ts_epoch))
                # Always delete 0.0.0-dev pollution regardless of rank/age.
                if [[ "$is_dev" != "1" ]]; then
                    if ((idx < R2_PACKAGE_KEEP_VERSIONS)) || ((age < pkg_keep_age)); then
                        idx=$((idx + 1))
                        continue
                    fi
                fi
                local tag="v${semver}, $((age / 86400))d"
                [[ "$is_dev" == "1" ]] && tag="0.0.0-dev pollution, $((age / 86400))d"
                if [[ "$DRY_RUN" == "true" ]]; then
                    log_warn "  [DRY-RUN] Would delete s3://${R2_BUCKET}/${key} (${tag})"
                else
                    aws s3 rm "s3://${R2_BUCKET}/${key}" --endpoint-url "$R2_ENDPOINT" --quiet 2>/dev/null || true
                    log_info "  Deleted ${key} (${tag})"
                fi
                pkg_deleted=$((pkg_deleted + 1))
                idx=$((idx + 1))
            done <<<"$listing"
        done
    done
    log_info "  8f: deleted $pkg_deleted stale artifact(s) across apt/rpm/apk/archlinux/npm/desktop"

    # 8e. Abort abandoned multipart uploads ---------------------------------
    # Successful multiparts complete in minutes; anything older than 24h is
    # an abandoned CI/promote run leaking storage until aborted.
    log_step "  8e: abort multipart uploads older than 24h"
    local uploads
    uploads="$(aws s3api list-multipart-uploads --bucket "$R2_BUCKET" \
        --endpoint-url "$R2_ENDPOINT" \
        --query 'Uploads[].{Key:Key,UploadId:UploadId,Initiated:Initiated}' \
        --output json 2>/dev/null || echo "[]")"
    local mpu_count
    mpu_count="$(echo "$uploads" | jq 'length')"
    if [[ "$mpu_count" -eq 0 ]]; then
        log_info "  8e: no ongoing multipart uploads"
    else
        local mpu_aborted=0
        local mpu_max_age=$((24 * 3600))
        while IFS=$'\t' read -r key upload_id initiated; do
            [[ -z "$key" ]] && continue
            local init_epoch
            init_epoch="$(date -u -d "$initiated" +%s 2>/dev/null || echo 0)"
            [[ "$init_epoch" -eq 0 ]] && continue
            if ((now_epoch - init_epoch <= mpu_max_age)); then
                continue
            fi
            if [[ "$DRY_RUN" == "true" ]]; then
                log_warn "  [DRY-RUN] Would abort multipart: $key (age $(((now_epoch - init_epoch) / 3600))h)"
                mpu_aborted=$((mpu_aborted + 1))
                continue
            fi
            aws s3api abort-multipart-upload \
                --bucket "$R2_BUCKET" --key "$key" --upload-id "$upload_id" \
                --endpoint-url "$R2_ENDPOINT" 2>/dev/null || continue
            log_info "  Aborted multipart: $key"
            mpu_aborted=$((mpu_aborted + 1))
        done < <(echo "$uploads" | jq -r '.[] | "\(.Key)\t\(.UploadId)\t\(.Initiated)"')
        log_info "  8e: aborted $mpu_aborted of $mpu_count (held $((mpu_count - mpu_aborted)) under 24h grace)"
    fi
}

# =============================================================================
# PHASE 9: STALE BRANCHES
# Delete branches with no open PR and no commits in the last N days.
# Runs across all org repos to prevent accumulation from merged PRs,
# bot-created branches, and abandoned feature branches.
# =============================================================================

cleanup_stale_branches() {
    log_step "Phase 9: Cleaning up stale branches (>${BRANCH_MAX_AGE_DAYS} days, no open PR)"

    local now_epoch
    now_epoch="$(date +%s)"
    local max_age_seconds=$((BRANCH_MAX_AGE_DAYS * 86400))

    for repo_name in "${BRANCH_REPOS[@]}"; do
        local full_repo="$GITHUB_ORG/$repo_name"

        log_step "  Processing branches for $full_repo"

        # List all branches
        local branches
        branches="$(gh api "repos/$full_repo/branches?per_page=100" --jq '.[].name' 2>/dev/null || echo "")"

        if [[ -z "$branches" ]]; then
            log_debug "  No branches found (or API error)"
            continue
        fi

        local deleted=0
        local kept=0

        while IFS= read -r branch; do
            [[ -z "$branch" ]] && continue
            [[ "$branch" == "main" ]] && continue

            # Check for open PR targeting this branch as head
            local open_prs
            open_prs="$(gh api "repos/$full_repo/pulls?head=$GITHUB_ORG:$branch&state=open&per_page=1" --jq 'length' 2>/dev/null || echo "0")"

            if [[ "$open_prs" -gt 0 ]]; then
                log_debug "    Keeping $branch (has open PR)"
                kept=$((kept + 1))
                continue
            fi

            # Check last commit date
            local last_commit_date
            last_commit_date="$(gh api "repos/$full_repo/branches/$branch" --jq '.commit.commit.committer.date' 2>/dev/null || echo "")"

            if [[ -z "$last_commit_date" ]]; then
                log_debug "    Keeping $branch (cannot determine age)"
                kept=$((kept + 1))
                continue
            fi

            local commit_epoch
            commit_epoch="$(date -d "$last_commit_date" +%s 2>/dev/null || echo "0")"
            local age_seconds=$((now_epoch - commit_epoch))

            if [[ $age_seconds -lt $max_age_seconds ]]; then
                log_debug "    Keeping $branch ($((age_seconds / 86400)) days old)"
                kept=$((kept + 1))
                continue
            fi

            local age_days=$((age_seconds / 86400))

            if [[ "$DRY_RUN" == "true" ]]; then
                log_warn "    [DRY-RUN] Would delete $branch (${age_days} days old, no open PR)"
                deleted=$((deleted + 1))
            else
                if gh api -X DELETE "repos/$full_repo/git/refs/heads/$branch" 2>/dev/null; then
                    log_info "    Deleted $branch (${age_days} days old)"
                    deleted=$((deleted + 1))
                else
                    log_warn "    Failed to delete $branch"
                fi
            fi
        done <<<"$branches"

        log_info "  Branches ($repo_name): deleted $deleted, kept $kept"
    done
}

# =============================================================================
# MAIN
# =============================================================================

log_step "Housekeeping: cleanup-versions"
log_step "  Retention: ${RETENTION_DAYS} days OR last ${KEEP_VERSIONS} versions"
if [[ "$DRY_RUN" == "true" ]]; then
    log_warn "  DRY-RUN mode: no deletions will be performed"
fi
echo ""

cleanup_releases
echo ""
cleanup_tags
echo ""
cleanup_packages
echo ""
cleanup_deployments
echo ""
cleanup_cf_pages
echo ""
cleanup_environments
echo ""
cleanup_d1_databases
echo ""
cleanup_orphan_turnstile_widgets
echo ""
cleanup_r2
echo ""
cleanup_stale_branches

echo ""
log_info "Housekeeping complete"
