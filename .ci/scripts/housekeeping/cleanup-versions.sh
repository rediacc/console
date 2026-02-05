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

# GHCR packages to clean (under ghcr.io/rediacc/elite/*)
GHCR_PACKAGES=("api" "bridge" "web" "plugin-terminal" "plugin-browser" "cli")

# Repos to clean deployments from
DEPLOYMENT_REPOS=("console")

# Release repo
RELEASE_REPO="rediacc/console"

# Cloudflare Pages project for preview deployments
CF_PAGES_PROJECT="rediacc"

# =============================================================================
# PREREQUISITES
# =============================================================================

require_cmd gh
require_cmd jq
require_cmd curl
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
                if retry_with_backoff 3 2 gh release delete "$tag" --repo "$RELEASE_REPO" --yes --cleanup-tag; then
                    log_debug "Deleted release: $tag"
                    deleted=$((deleted + 1))
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

    for package in "${GHCR_PACKAGES[@]}"; do
        local package_name="elite/${package}"
        local encoded_package
        encoded_package="$(echo "$package_name" | sed 's|/|%2F|g')"

        log_step "  Processing package: $package_name"

        # List versions with pagination (sorted newest first by API default)
        local versions
        versions="$(gh api "orgs/$GITHUB_ORG/packages/container/$encoded_package/versions" \
            --paginate \
            --jq '[.[] | {id: .id, tags: .metadata.container.tags, created: .created_at}]' \
            2>/dev/null || echo "[]")"

        # Flatten paginated results and sort by created date
        versions="$(echo "$versions" | jq -s 'flatten | sort_by(.created) | reverse')"

        local total
        total="$(echo "$versions" | jq 'length')"
        log_debug "  Found $total versions for $package_name"

        local deleted=0
        local index=0

        while IFS= read -r version; do
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
                    local http_code
                    http_code="$(gh api -X DELETE "orgs/$GITHUB_ORG/packages/container/$encoded_package/versions/$version_id" \
                        2>&1 && echo "204" || echo "failed")"

                    if [[ "$http_code" == "204" ]]; then
                        log_debug "  Deleted version: $version_id (tags: $tags)"
                        deleted=$((deleted + 1))
                    else
                        # Handle 400 errors gracefully (e.g., >5000 downloads)
                        log_warn "  Could not delete version $version_id (tags: $tags) - may have >5000 downloads"
                    fi
                fi
            fi

            index=$((index + 1))
        done < <(echo "$versions" | jq -c '.[]')

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

        local deleted=0
        local index=0

        while IFS= read -r deployment; do
            local dep_id environment created_at
            dep_id="$(echo "$deployment" | jq -r '.id')"
            environment="$(echo "$deployment" | jq -r '.environment')"
            created_at="$(echo "$deployment" | jq -r '.created_at')"

            if should_retain "$created_at" "$index"; then
                log_debug "  Keeping deployment: $dep_id ($environment)"
            else
                if [[ "$DRY_RUN" == "true" ]]; then
                    log_warn "  [DRY-RUN] Would delete deployment: $dep_id ($environment, created: $created_at)"
                else
                    # Must set deployment to inactive before deletion
                    if gh api "repos/$full_repo/deployments/$dep_id/statuses" \
                        -X POST -f state=inactive >/dev/null 2>&1 &&
                        retry_with_backoff 3 2 gh api -X DELETE "repos/$full_repo/deployments/$dep_id" 2>/dev/null; then
                        log_debug "  Deleted deployment: $dep_id ($environment)"
                        deleted=$((deleted + 1))
                    else
                        log_warn "  Failed to delete deployment: $dep_id"
                    fi
                fi
            fi

            index=$((index + 1))
        done < <(echo "$deployments" | jq -c '.[]')

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "  Deployments ($full_repo): would delete $deleted of $total"
        else
            log_info "  Deployments ($full_repo): deleted $deleted of $total"
        fi
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
log_info "Housekeeping complete"
