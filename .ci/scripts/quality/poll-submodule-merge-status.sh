#!/bin/bash
# Poll all open console PRs for submodule merge readiness and update commit statuses.
#
# For each open PR that has submodule pointer changes, checks whether the
# tracked commit for each submodule is already on that submodule's main branch.
# Posts quality/submodule-merge-readiness commit status accordingly.
#
# Uses the GitHub API exclusively (no local checkout of submodules required).
#
# Usage:
#   poll-submodule-merge-status.sh [--dry-run]
#
# Environment:
#   GH_TOKEN              Token with contents:read (app token for cross-repo access)
#   STATUS_TOKEN          Token with statuses:write (github.token)
#   GITHUB_REPOSITORY     owner/repo (e.g., rediacc/console)
#   DISPATCH_SUBMODULE    (optional) Submodule name that triggered the dispatch
#   DISPATCH_BRANCH       (optional) Branch that was merged in the submodule

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help)
            echo "Usage: $0 [--dry-run]"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

require_var GITHUB_REPOSITORY
require_cmd gh
require_cmd jq

STATUS_CONTEXT="quality/submodule-merge-readiness"

# Submodule directory name -> GitHub repo mapping
declare -A SUBMODULE_REPOS=(
    ["middleware"]="rediacc/middleware"
    ["renet"]="rediacc/renet"
    ["license-server"]="rediacc/license-server"
    ["elite"]="rediacc/elite"
)

# Post commit status via GitHub API using STATUS_TOKEN (github.token).
# Usage: post_status <sha> <state> <description>
post_status() {
    local sha="$1" state="$2" description="$3"
    local token="${STATUS_TOKEN:-${GH_TOKEN:-}}"

    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY-RUN] Would post $state on ${sha:0:8}: $description"
        return 0
    fi

    GH_TOKEN="$token" gh api "repos/${GITHUB_REPOSITORY}/statuses/${sha}" \
        -X POST \
        -f state="$state" \
        -f context="$STATUS_CONTEXT" \
        -f description="$description" \
        >/dev/null 2>&1 || log_warn "Failed to post status on ${sha:0:8}"
}

# Check if a commit is on a repo's main branch (ancestor or identical).
# Uses GitHub compare API — no local checkout needed.
# Returns 0 if merged, 1 otherwise.
# Usage: is_commit_on_main <repo> <commit_sha>
is_commit_on_main() {
    local repo="$1" commit="$2"
    local status
    status=$(gh api "repos/${repo}/compare/main...${commit}" \
        --jq '.status' 2>/dev/null || echo "error")
    [[ "$status" == "behind" || "$status" == "identical" ]]
}

# Get the tree SHA for the 'private' directory at a given ref.
# Usage: get_private_tree <ref>
get_private_tree() {
    local ref="$1"
    gh api "repos/${GITHUB_REPOSITORY}/git/trees/${ref}" \
        --jq '.tree[] | select(.path == "private") | .sha' \
        2>/dev/null || echo ""
}

# Get submodule pointers from a 'private' tree SHA.
# Outputs lines of "name sha" for each gitlink (mode 160000) entry.
# Usage: get_submodule_pointers <tree_sha>
get_submodule_pointers() {
    local tree_sha="$1"
    gh api "repos/${GITHUB_REPOSITORY}/git/trees/${tree_sha}" \
        --jq '.tree[] | select(.mode == "160000") | "\(.path) \(.sha)"' \
        2>/dev/null || echo ""
}

# Evaluate a single PR for submodule merge readiness.
# Usage: evaluate_pr <pr_number> <head_sha>
evaluate_pr() {
    local pr_number="$1" head_sha="$2"

    log_step "Evaluating PR #$pr_number (HEAD: ${head_sha:0:8})..."

    # Get submodule pointers at PR HEAD and main
    local pr_private_tree main_private_tree
    pr_private_tree=$(get_private_tree "$head_sha")
    main_private_tree=$(get_private_tree "main")

    if [[ -z "$pr_private_tree" || -z "$main_private_tree" ]]; then
        log_warn "  Could not resolve private/ tree, skipping"
        return 0
    fi

    local pr_pointers main_pointers
    pr_pointers=$(get_submodule_pointers "$pr_private_tree")
    main_pointers=$(get_submodule_pointers "$main_private_tree")

    local has_unmerged=false
    local has_submodule_changes=false

    for sm_name in "${!SUBMODULE_REPOS[@]}"; do
        local repo="${SUBMODULE_REPOS[$sm_name]}"

        # Extract pointer SHAs from the tree listings
        local pr_pointer main_pointer
        pr_pointer=$(echo "$pr_pointers" | awk -v name="$sm_name" '$1 == name { print $2 }')
        main_pointer=$(echo "$main_pointers" | awk -v name="$sm_name" '$1 == name { print $2 }')

        if [[ -z "$pr_pointer" || -z "$main_pointer" ]]; then
            continue
        fi

        if [[ "$pr_pointer" == "$main_pointer" ]]; then
            continue
        fi

        has_submodule_changes=true

        if ! is_commit_on_main "$repo" "$pr_pointer"; then
            has_unmerged=true
            log_info "  $sm_name: ${pr_pointer:0:8} NOT yet on $repo main"
        else
            log_info "  $sm_name: ${pr_pointer:0:8} is on $repo main"
        fi
    done

    if [[ "$has_submodule_changes" == "false" ]]; then
        post_status "$head_sha" "success" "No submodule pointer changes"
    elif [[ "$has_unmerged" == "true" ]]; then
        post_status "$head_sha" "pending" "Submodule PRs still open — merge them first"
    else
        post_status "$head_sha" "success" "All submodule PRs merged"
    fi
}

main() {
    log_step "Polling open PRs for submodule merge readiness..."

    if [[ -n "${DISPATCH_SUBMODULE:-}" ]]; then
        log_info "Triggered by merge in $DISPATCH_SUBMODULE (branch: ${DISPATCH_BRANCH:-unknown})"
    fi

    # Fetch all open non-draft PRs
    local prs
    prs=$(gh pr list --repo "$GITHUB_REPOSITORY" --state open \
        --json number,headRefOid,isDraft \
        --jq '[.[] | select(.isDraft == false)]' \
        2>/dev/null || echo "[]")

    local count
    count=$(echo "$prs" | jq 'length')
    log_info "Found $count open non-draft PR(s) to evaluate"

    if [[ "$count" -eq 0 ]]; then
        return 0
    fi

    while IFS= read -r pr_entry; do
        [[ -z "$pr_entry" ]] && continue
        local number head_sha
        number=$(echo "$pr_entry" | jq -r '.number')
        head_sha=$(echo "$pr_entry" | jq -r '.headRefOid')
        evaluate_pr "$number" "$head_sha"
    done < <(echo "$prs" | jq -c '.[]')

    log_info "Polling complete"
}

main "$@"
