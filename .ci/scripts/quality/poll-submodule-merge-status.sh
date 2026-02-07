#!/bin/bash
# ==============================================================================
# SUBMODULE MERGE READINESS POLLER
# ==============================================================================
#
# PURPOSE: Polls all open console PRs and updates the
#          quality/submodule-merge-readiness commit status based on whether
#          submodule PRs have merged. This allows the merge button to unblock
#          without a full CI re-run when submodule PRs merge.
#
# TRIGGERED BY: Scheduled workflow (every 5 min) or manual workflow_dispatch.
#
# LOGIC:
#   1. List open console PRs
#   2. For each PR, fetch its head ref and compare submodule pointers to main
#   3. For changed submodules, check if the submodule PR (same branch) is merged
#   4. Set commit status: "success" if all merged, "pending" if any still open
#
# REQUIRED ENV VARS:
#   GH_TOKEN            - GitHub token with statuses:write, pull-requests:read
#   GITHUB_REPOSITORY   - Owner/repo (e.g., rediacc/console)
#
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

SUBMODULE_STATUS_CONTEXT="quality/submodule-merge-readiness"
SUBMODULE_REPOS=("rediacc/middleware" "rediacc/renet" "rediacc/license-server")
SUBMODULE_PATHS=("private/middleware" "private/renet" "private/license-server")

require_var GITHUB_REPOSITORY

# Check if a merged PR exists for a branch in a repo
# Same logic as branch_has_merged_pr in check-submodule-branches.sh,
# self-contained here to avoid sourcing that script's globals/main.
branch_has_merged_pr_for_poll() {
    local repo="$1"
    local branch="$2"
    local merged_count
    merged_count=$(gh pr list --repo "$repo" --head "$branch" --state merged --json number --jq 'length' 2>/dev/null || echo "0")
    [[ "$merged_count" -gt 0 ]]
}

# Check if an open PR exists for a branch in a repo
branch_has_open_pr_for_poll() {
    local repo="$1"
    local branch="$2"
    local open_count
    open_count=$(gh pr list --repo "$repo" --head "$branch" --state open --json number --jq 'length' 2>/dev/null || echo "0")
    [[ "$open_count" -gt 0 ]]
}

# List open PRs: number, headSHA, branch
pr_list=$(gh pr list --repo "$GITHUB_REPOSITORY" --state open \
    --json number,headRefOid,headRefName \
    --jq '.[] | "\(.number) \(.headRefOid) \(.headRefName)"' 2>/dev/null || echo "")

if [[ -z "$pr_list" ]]; then
    log_info "No open PRs — nothing to do"
    exit 0
fi

# Ensure origin/main is available for comparison
git fetch origin main --quiet 2>/dev/null || true

while IFS=' ' read -r pr_number pr_sha branch; do
    [[ -z "$pr_number" ]] && continue

    # Fetch PR head (shallow — only need tree object)
    if ! git fetch origin "pull/$pr_number/head:refs/pr/$pr_number" --depth=1 --quiet 2>/dev/null; then
        log_warn "PR #$pr_number: failed to fetch head ref — skipping"
        continue
    fi

    has_unmerged=false
    pending=()

    for i in "${!SUBMODULE_PATHS[@]}"; do
        sm_path="${SUBMODULE_PATHS[$i]}"
        repo="${SUBMODULE_REPOS[$i]}"

        pr_commit=$(git ls-tree "refs/pr/$pr_number" -- "$sm_path" 2>/dev/null | awk '{print $3}')
        main_commit=$(git ls-tree origin/main -- "$sm_path" 2>/dev/null | awk '{print $3}')

        # No pointer change → skip
        [[ -z "$pr_commit" || -z "$main_commit" || "$pr_commit" == "$main_commit" ]] && continue

        # Pointer changed — check if submodule PR for this branch is merged
        if ! branch_has_merged_pr_for_poll "$repo" "$branch"; then
            has_unmerged=true
            pending+=("$repo")
        fi
    done

    if [[ "$has_unmerged" == "true" ]]; then
        desc="Waiting: ${pending[*]}"
        [[ ${#desc} -gt 140 ]] && desc="${desc:0:137}..."
        gh api "repos/${GITHUB_REPOSITORY}/statuses/${pr_sha}" \
            -f state="pending" \
            -f context="$SUBMODULE_STATUS_CONTEXT" \
            -f description="$desc" 2>/dev/null || true
        log_info "PR #$pr_number: pending (${pending[*]})"
    else
        gh api "repos/${GITHUB_REPOSITORY}/statuses/${pr_sha}" \
            -f state="success" \
            -f context="$SUBMODULE_STATUS_CONTEXT" \
            -f description="All submodule PRs merged" 2>/dev/null || true
        log_info "PR #$pr_number: success"
    fi
done <<< "$pr_list"
