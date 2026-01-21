#!/bin/bash
# Check if private submodules are accessible and sync to matching branches
# Returns: 0 if accessible, 1 if not
#
# Usage: .ci/scripts/private/detect-access.sh
#
# Branch Strategy:
#   1. Detects the current console branch
#   2. For each submodule, checks if the same branch exists
#   3. If yes, checks out that branch (for coordinated PR testing)
#   4. If no, uses the default branch (main)
#
# Environment variables:
#   GITHUB_PAT - Token for private repo access (required)
#   GITHUB_HEAD_REF - PR source branch (set by GitHub Actions)
#   GITHUB_REF_NAME - Current branch/tag name (set by GitHub Actions)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Detect current branch name
get_current_branch() {
    # In PR context, use the source branch
    if [[ -n "${GITHUB_HEAD_REF:-}" ]]; then
        echo "$GITHUB_HEAD_REF"
    # In push context, use the ref name
    elif [[ -n "${GITHUB_REF_NAME:-}" ]]; then
        echo "$GITHUB_REF_NAME"
    # Local development
    else
        git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"
    fi
}

# Sync submodule to matching branch or fallback to main
sync_submodule_branch() {
    local submodule_path="$1"
    local target_branch="$2"
    local fallback_branch="main"

    if [[ ! -d "$submodule_path" ]]; then
        return 1
    fi

    cd "$submodule_path"

    # Fetch all branches
    git fetch --all --quiet 2>/dev/null || true

    # Check if target branch exists in remote
    if git ls-remote --heads origin "$target_branch" | grep -q "$target_branch"; then
        log_step "Syncing $submodule_path to branch: $target_branch"
        git checkout "$target_branch" --quiet 2>/dev/null || git checkout -b "$target_branch" "origin/$target_branch" --quiet
        git pull origin "$target_branch" --quiet 2>/dev/null || true
    else
        log_step "Branch '$target_branch' not found in $submodule_path, using $fallback_branch"
        git checkout "$fallback_branch" --quiet 2>/dev/null || true
        git pull origin "$fallback_branch" --quiet 2>/dev/null || true
    fi

    cd "$REPO_ROOT"
}

# Check if submodules are already initialized
if [[ -f "private/middleware/.ci/ci.sh" ]] && [[ -f "private/renet/.ci/ci.sh" ]]; then
    CURRENT_BRANCH="$(get_current_branch)"
    log_info "Private submodules are available, syncing to branch: $CURRENT_BRANCH"

    # Sync each submodule to matching branch
    sync_submodule_branch "private/middleware" "$CURRENT_BRANCH"
    sync_submodule_branch "private/renet" "$CURRENT_BRANCH"

    exit 0
fi

# Check if private directory exists but submodules aren't initialized
if [[ -d "private" ]] || [[ -f ".gitmodules" ]]; then
    TOKEN="${GITHUB_PAT:-}"
    if [[ -z "$TOKEN" ]]; then
        log_error "ERROR: GITHUB_PAT is required but not set"
        log_error "This repository requires private submodule access."
        log_error "Configure the GH_PAT secret in: Settings > Secrets and variables > Actions"
        exit 1
    fi

    log_step "Attempting to initialize submodules..."

    # Configure git to use token for GitHub
    git config --global url."https://${TOKEN}@github.com/".insteadOf "https://github.com/"

    if git submodule update --init --recursive private/ 2>/dev/null; then
        # Verify initialization
        if [[ -f "private/middleware/.ci/ci.sh" ]] && [[ -f "private/renet/.ci/ci.sh" ]]; then
            CURRENT_BRANCH="$(get_current_branch)"
            log_info "Submodules initialized, syncing to branch: $CURRENT_BRANCH"

            # Sync each submodule to matching branch
            sync_submodule_branch "private/middleware" "$CURRENT_BRANCH"
            sync_submodule_branch "private/renet" "$CURRENT_BRANCH"

            exit 0
        fi
    fi

    log_error "Submodule initialization failed"
    exit 1
fi

log_error "Private submodules not accessible - .gitmodules or private/ directory not found"
exit 1
