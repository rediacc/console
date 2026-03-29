#!/bin/bash
# Merge submodule feature branches into main before CD version bump.
#
# When a console PR merges with submodule pointer changes pointing at a feature
# branch commit, that commit only lives on the feature branch.  The CD version
# bump (bump-submodules.sh) resets every submodule to origin/main via
# sync_to_origin_main(), silently losing those changes.
#
# This script detects submodules whose tracked commit is ahead of origin/main
# and merges the corresponding PR (or fast-forward pushes) so the commit is on
# main before the bump runs.
#
# Usage:
#   merge-submodule-branches.sh [--dry-run]
#
# Options:
#   --dry-run    Show actions without merging or pushing
#
# Environment:
#   GITHUB_PAT   Token for git push authentication
#   GH_TOKEN     Token for gh CLI (PR merge)

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

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Ensure authenticated access for pushes in CI
if [[ -n "${GITHUB_PAT:-}" ]]; then
    git config --global url."https://x-access-token:${GITHUB_PAT}@github.com/".insteadOf "https://github.com/"
fi

# Submodule path -> GitHub repo mapping (derived from .gitmodules)
declare -A SUBMODULE_REPOS=(
    ["private/middleware"]="rediacc/middleware"
    ["private/renet"]="rediacc/renet"
    ["private/homebrew-tap"]="rediacc/homebrew-tap"
    ["private/account"]="rediacc/account"
    ["private/elite"]="rediacc/elite"
    ["private/sql"]="rediacc/sql"
)

ERRORS=0

process_submodule() {
    local sm_path="$1"
    local repo="${SUBMODULE_REPOS[$sm_path]}"

    log_step "Checking $sm_path ($repo)..."

    # 1. Read the commit SHA that console HEAD records for this submodule
    local tracked_commit
    tracked_commit=$(git ls-tree HEAD -- "$sm_path" 2>/dev/null | awk '{ print $3 }')

    if [[ -z "$tracked_commit" ]]; then
        log_info "$sm_path: not tracked by console HEAD, skipping"
        return 0
    fi

    # 2. Fetch submodule's origin/main
    if [[ ! -d "$sm_path/.git" ]] && [[ ! -f "$sm_path/.git" ]]; then
        log_warn "$sm_path: submodule not initialized, skipping"
        return 0
    fi

    git -C "$sm_path" fetch origin main --quiet 2>/dev/null || true

    local origin_main
    origin_main=$(git -C "$sm_path" rev-parse origin/main 2>/dev/null)

    if [[ -z "$origin_main" ]]; then
        log_error "$sm_path: could not resolve origin/main"
        ((ERRORS++))
        return 1
    fi

    # 3. Compare tracked commit with origin/main
    if [[ "$tracked_commit" == "$origin_main" ]]; then
        log_info "$sm_path: already at origin/main ($tracked_commit)"
        return 0
    fi

    # Check if tracked commit is ancestor of origin/main (already merged)
    if git -C "$sm_path" merge-base --is-ancestor "$tracked_commit" "$origin_main" 2>/dev/null; then
        log_info "$sm_path: tracked commit $tracked_commit is ancestor of origin/main, already merged"
        return 0
    fi

    # Check if origin/main is ancestor of tracked commit (needs merge / FF)
    if git -C "$sm_path" merge-base --is-ancestor "$origin_main" "$tracked_commit" 2>/dev/null; then
        log_info "$sm_path: tracked commit $tracked_commit is ahead of origin/main, needs merge"
    else
        # Diverged — cannot fast-forward, manual resolution required
        log_error "$sm_path: tracked commit $tracked_commit and origin/main $origin_main have diverged"
        log_error "  Manual resolution required — rebase or merge the submodule branch"
        ((ERRORS++))
        return 1
    fi

    # 4. Find an open PR targeting main whose head contains the tracked commit
    local pr_json pr_number pr_head_sha
    pr_json=""

    if command -v gh &>/dev/null && [[ -n "${GH_TOKEN:-}" ]]; then
        pr_json=$(gh pr list --repo "$repo" --state open --base main \
            --json number,headRefName,headRefOid \
            --jq ".[] | select(.headRefOid == \"$tracked_commit\") | {number, headRefName, headRefOid}" \
            2>/dev/null || echo "")

        # If exact SHA match fails, check if tracked commit is on any PR's head branch
        if [[ -z "$pr_json" ]]; then
            local all_prs
            all_prs=$(gh pr list --repo "$repo" --state open --base main \
                --json number,headRefName,headRefOid 2>/dev/null || echo "[]")

            # Batch-fetch all PR branches in one network call
            local branches_to_fetch
            branches_to_fetch=$(echo "$all_prs" | jq -r '.[].headRefName | select(.)' | tr '\n' ' ')
            if [[ -n "$branches_to_fetch" ]]; then
                # shellcheck disable=SC2086
                git -C "$sm_path" fetch origin $branches_to_fetch --quiet 2>/dev/null || true
            fi

            while IFS= read -r pr_entry; do
                [[ -z "$pr_entry" ]] && continue
                local branch_name
                branch_name=$(echo "$pr_entry" | jq -r '.headRefName')

                if git -C "$sm_path" merge-base --is-ancestor "$tracked_commit" "origin/$branch_name" 2>/dev/null; then
                    pr_json="$pr_entry"
                    break
                fi
            done < <(echo "$all_prs" | jq -c '.[]')
        fi
    fi

    if [[ -n "$pr_json" ]]; then
        pr_number=$(echo "$pr_json" | jq -r '.number')
        local pr_branch
        pr_branch=$(echo "$pr_json" | jq -r '.headRefName')

        log_info "$sm_path: found open PR #$pr_number (branch: $pr_branch)"

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would merge PR #$pr_number in $repo"
            return 0
        fi

        # Merge the PR using --merge (not squash) to preserve commit history
        if gh pr merge "$pr_number" --repo "$repo" --merge --admin; then
            log_info "$sm_path: PR #$pr_number merged successfully"
        else
            log_error "$sm_path: failed to merge PR #$pr_number"
            ((ERRORS++))
            return 1
        fi
    else
        # No PR found — fall back to git fast-forward push
        log_warn "$sm_path: no open PR found, falling back to fast-forward push"

        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY-RUN] Would push $tracked_commit to $repo main"
            return 0
        fi

        if git -C "$sm_path" push origin "$tracked_commit:refs/heads/main"; then
            log_info "$sm_path: fast-forward pushed $tracked_commit to main"
        else
            log_error "$sm_path: failed to fast-forward push to main"
            ((ERRORS++))
            return 1
        fi
    fi
}

log_step "Merging submodule branches to main..."

for sm_path in "${!SUBMODULE_REPOS[@]}"; do
    process_submodule "$sm_path"
done

if [[ $ERRORS -gt 0 ]]; then
    log_error "Submodule branch merge failed with $ERRORS error(s)"
    exit 1
fi

log_info "Submodule branch merge complete"
