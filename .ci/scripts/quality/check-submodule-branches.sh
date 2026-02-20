#!/bin/bash
# ==============================================================================
# SUBMODULE BRANCH VALIDATION - AI-FRIENDLY DOCUMENTATION
# ==============================================================================
#
# PURPOSE: Validates that submodule branches match the console branch when expected,
#          ensures submodule PRs are properly linked, and verifies all review
#          comments on submodule PRs have been addressed.
#
# WHEN THIS CHECK RUNS:
#   - On every PR (pull_request event)
#   - On pushes to main (push event to refs/heads/main)
#
# WHAT IT CHECKS:
#   1. For each submodule with pointer changes (different from origin/main):
#      a. If the commit is an ancestor of origin/main (pointer bump to
#         already-merged work), it passes automatically — no branch/PR needed.
#      b. Otherwise (new code beyond main), it requires:
#         - A matching branch in the submodule repo
#         - An open PR for that branch
#         - The PR linked in the console PR description
#         - All review comments on the submodule PR addressed
#   2. For submodules without pointer changes:
#      - Confirms they are on 'main' (expected behavior)
#
# AI TROUBLESHOOTING GUIDE:
# -------------------------
# ERROR: "Submodule private/middleware expected on branch 0203-1 but is on main"
#   CAUSE: Submodule has pointer changes but no matching branch was created
#   FIX:
#     cd private/middleware
#     git checkout -b 0203-1
#     git push -u origin 0203-1
#
# ERROR: "Branch 0203-1 does not exist in private/renet remote"
#   CAUSE: Branch exists locally but wasn't pushed to remote
#   FIX:
#     cd private/renet
#     git push -u origin 0203-1
#
# ERROR: "Submodule pointer changed but no matching branch"
#   CAUSE: Console tracks a different commit than origin/main, but developer
#          didn't create a branch in the submodule for coordinated testing
#   FIX: Either:
#     1. Create the branch: cd private/<submodule> && git checkout -b <branch>
#     2. Or reset pointer: git checkout origin/main -- private/<submodule>
#
# ERROR: "No open PR found for branch 0203-1 in rediacc/middleware"
#   CAUSE: Branch exists but no PR was created for it
#   FIX:
#     cd private/middleware
#     gh pr create --title "feat: your changes" --body "Description"
#
# ERROR: "PR not linked in console PR description"
#   CAUSE: Submodule PR exists but is not mentioned in console PR
#   FIX: Edit console PR description to include the submodule PR URL:
#     ## Related PRs
#     - https://github.com/rediacc/middleware/pull/123
#
# ERROR: "Submodule PR has N unreplied review comments"
#   CAUSE: Review comments on the submodule PR haven't been addressed
#   FIX: Go to the submodule PR and reply to all review comments with
#        substantive responses (not just "ok", "done", "fixed", etc.)
#
# SKIP CONDITIONS:
#   - is_bot == 'true': Skip for bot-generated PRs
#   - Submodule not initialized: Skip with warning
#   - Not a PR context: PR linking check skipped
#
# EXIT CODES:
#   0 - All submodule branches are valid
#   1 - Branch mismatch, PR linking, or review comments error detected
#   2 - Configuration error (missing env vars, etc.)
#
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Submodule to repo mapping
declare -A SUBMODULE_REPOS=(
    ["private/middleware"]="rediacc/middleware"
    ["private/renet"]="rediacc/renet"
    ["private/homebrew-tap"]="rediacc/homebrew-tap"
    ["private/account"]="rediacc/account"
    ["private/elite"]="rediacc/elite"
    ["private/sql"]="rediacc/sql"
    ["private/growth"]="rediacc/growth"
)

# Patterns for low-effort replies that don't count as real responses
# These are case-insensitive and match the entire reply (with optional punctuation)
LOW_EFFORT_PATTERNS=(
    "acknowledged"
    "ack"
    "ok"
    "okay"
    "understood"
    "noted"
    "done"
    "fixed"
    "will do"
    "will fix"
    "got it"
    "thanks"
    "thank you"
    "ty"
    "thx"
    "yes"
    "no"
    "sure"
    "agreed"
    "makes sense"
    "good point"
    "right"
    "correct"
    "i see"
    "see above"
    "addressed"
    "updated"
    "changed"
    "applied"
)

# Check if a reply is low-effort (returns 0 if low-effort, 1 if substantive)
is_low_effort_reply() {
    local reply="$1"
    # Normalize: lowercase, trim whitespace, remove trailing punctuation
    local normalized
    normalized=$(echo "$reply" | tr '[:upper:]' '[:lower:]' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sed 's/[.!?]*$//')

    # Check against patterns
    for pattern in "${LOW_EFFORT_PATTERNS[@]}"; do
        if [[ "$normalized" == "$pattern" ]]; then
            return 0 # Is low-effort
        fi
    done

    # Also reject very short replies (less than 10 chars after normalization)
    if [[ ${#normalized} -lt 10 ]]; then
        return 0 # Is low-effort
    fi

    return 1 # Is substantive
}

# Get current branch name
get_current_branch() {
    if [[ -n "${GITHUB_HEAD_REF:-}" ]]; then
        echo "$GITHUB_HEAD_REF"
    elif [[ -n "${GITHUB_REF_NAME:-}" ]]; then
        echo "$GITHUB_REF_NAME"
    else
        git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main"
    fi
}

# Check if submodule pointer differs from origin/main
submodule_has_pointer_changes() {
    local sm_path="$1"
    local head_commit origin_commit

    head_commit=$(git ls-tree HEAD -- "$sm_path" 2>/dev/null | awk '{ print $3 }')
    origin_commit=$(git ls-tree origin/main -- "$sm_path" 2>/dev/null | awk '{ print $3 }')

    [[ -n "$head_commit" && -n "$origin_commit" && "$head_commit" != "$origin_commit" ]]
}

# Get submodule's current branch
get_submodule_branch() {
    local sm_path="$1"
    git -C "$sm_path" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "detached"
}

# Check if branch exists in submodule remote
branch_exists_in_remote() {
    local sm_path="$1"
    local branch="$2"
    git -C "$sm_path" ls-remote --heads origin "$branch" 2>/dev/null | grep -q "$branch"
}

# Get open PR number and URL for a branch in a repo
# Returns "number|url" if found, empty string if not
get_pr_for_branch() {
    local repo="$1"
    local branch="$2"

    if ! command -v gh &>/dev/null; then
        return 0
    fi

    gh pr list --repo "$repo" --head "$branch" --state open --json number,url --jq '.[0] // empty | "\(.number)|\(.url)"' 2>/dev/null || echo ""
}

# Check if a merged PR exists for a branch in a repo
# Returns 0 if merged PR exists, 1 otherwise
branch_has_merged_pr() {
    local repo="$1"
    local branch="$2"

    if ! command -v gh &>/dev/null; then
        return 1
    fi

    local merged_count
    merged_count=$(gh pr list --repo "$repo" --head "$branch" --state merged --json number --jq 'length' 2>/dev/null || echo "0")
    [[ "$merged_count" -gt 0 ]]
}

# Get console PR description
get_console_pr_body() {
    local pr_number="${PR_NUMBER:-}"

    if [[ -z "$pr_number" ]]; then
        return 0
    fi

    if ! command -v gh &>/dev/null; then
        return 0
    fi

    gh pr view "$pr_number" --json body --jq '.body // empty' 2>/dev/null || echo ""
}

# Check if PR URL is mentioned in text
pr_is_linked() {
    local pr_url="$1"
    local text="$2"

    if [[ -z "$pr_url" || -z "$text" ]]; then
        return 1
    fi

    # Check for exact URL or PR number pattern (e.g., org/repo#123)
    local pr_number
    pr_number=$(echo "$pr_url" | grep -oE '[0-9]+$' || echo "")

    # Check if URL is in the text
    if echo "$text" | grep -qF "$pr_url"; then
        return 0
    fi

    # Check if repo#number pattern is in the text (e.g., rediacc/middleware#123)
    local repo
    repo=$(echo "$pr_url" | grep -oE 'github\.com/[^/]+/[^/]+' | sed 's|github.com/||')
    if [[ -n "$repo" && -n "$pr_number" ]]; then
        if echo "$text" | grep -qE "${repo}#${pr_number}|${repo}/pull/${pr_number}"; then
            return 0
        fi
    fi

    return 1
}

# Check for unreplied review comments on a PR
# Returns the count of unreplied comments (0 if all addressed)
check_pr_review_comments() {
    local repo="$1"
    local pr_number="$2"

    if ! command -v gh &>/dev/null; then
        echo "0"
        return 0
    fi

    # Fetch all review comments
    local comments
    comments=$(gh api "repos/${repo}/pulls/${pr_number}/comments" --paginate 2>/dev/null || echo "[]")

    if [[ "$comments" == "[]" ]]; then
        echo "0"
        return 0
    fi

    # Get all replies (comments with in_reply_to_id)
    local replies
    replies=$(echo "$comments" | jq -r '[.[] | select(.in_reply_to_id != null)]')

    # Get all original comments (no in_reply_to_id) - these need replies
    local original_comments
    original_comments=$(echo "$comments" | jq -r '[.[] | select(.in_reply_to_id == null)]')
    local original_count
    original_count=$(echo "$original_comments" | jq 'length')

    if [[ "$original_count" -eq 0 ]]; then
        echo "0"
        return 0
    fi

    # Build a map of original comment IDs to their substantive reply status
    declare -A has_substantive_reply

    # Check each reply to see if it's substantive
    while IFS= read -r reply; do
        [[ -z "$reply" ]] && continue
        local reply_to_id reply_body
        reply_to_id=$(echo "$reply" | jq -r '.in_reply_to_id')
        reply_body=$(echo "$reply" | jq -r '.body')

        # Check if this reply is substantive
        if ! is_low_effort_reply "$reply_body"; then
            has_substantive_reply[$reply_to_id]=1
        fi
    done < <(echo "$replies" | jq -c '.[]')

    # Count which original comments have no substantive replies
    local unreplied_count=0
    while IFS= read -r comment; do
        [[ -z "$comment" ]] && continue
        local comment_id
        comment_id=$(echo "$comment" | jq -r '.id')

        # Check if this comment has a substantive reply
        if [[ -z "${has_substantive_reply[$comment_id]:-}" ]]; then
            ((unreplied_count++))
        fi
    done < <(echo "$original_comments" | jq -c '.[]')

    echo "$unreplied_count"
}

# Post a GitHub commit status for submodule merge readiness.
# Usage: post_commit_status <state> <description>
# States: pending, success, failure
post_commit_status() {
    local state="$1"
    local description="$2"
    local sha="${COMMIT_SHA:-}"
    local repo="${GITHUB_REPOSITORY:-}"

    if [[ -z "$sha" || -z "$repo" ]]; then
        log_warn "COMMIT_SHA or GITHUB_REPOSITORY not set — skipping status post"
        return 0
    fi

    if ! command -v gh &>/dev/null; then
        log_warn "gh CLI not available — skipping status post"
        return 0
    fi

    local token="${STATUS_TOKEN:-${GH_TOKEN:-}}"
    if [[ -z "$token" ]]; then
        log_warn "No token available for status posting"
        return 0
    fi

    log_info "Posting commit status: $state ($description)"
    GH_TOKEN="$token" gh api "repos/${repo}/statuses/${sha}" \
        -X POST \
        -f state="$state" \
        -f context="quality/submodule-merge-readiness" \
        -f description="$description" \
        2>/dev/null || log_warn "Failed to post commit status"
}

# Main validation
main() {
    local current_branch
    current_branch="$(get_current_branch)"
    local errors=0
    local warnings=0
    local has_open_submodule_prs=false
    local console_pr_body=""

    log_step "Validating submodule branches (console branch: $current_branch)"

    # Skip check on main branch (no coordinated branches needed)
    if [[ "$current_branch" == "main" ]]; then
        log_info "On main branch - submodule branch validation skipped"
        exit 0
    fi

    # Fetch origin/main for comparison
    git fetch origin main --quiet 2>/dev/null || true

    # Get console PR body for linking check (only in CI with PR context)
    if [[ -n "${PR_NUMBER:-}" ]] && command -v gh &>/dev/null; then
        console_pr_body="$(get_console_pr_body)"
    fi

    # Check each submodule
    for sm_path in private/middleware private/renet private/homebrew-tap private/account private/elite private/sql private/growth; do
        if [[ ! -d "$sm_path/.git" ]] && [[ ! -f "$sm_path/.git" ]]; then
            log_warn "Submodule $sm_path not initialized - skipping"
            ((warnings++))
            continue
        fi

        local repo="${SUBMODULE_REPOS[$sm_path]:-}"

        if submodule_has_pointer_changes "$sm_path"; then
            # Check if the submodule commit is an ancestor of origin/main.
            # If so, we're just bumping the pointer to already-merged work
            # — no coordinated branch/PR needed.
            local sm_commit
            sm_commit=$(git ls-tree HEAD -- "$sm_path" 2>/dev/null | awk '{ print $3 }')
            if git -C "$sm_path" merge-base --is-ancestor "$sm_commit" origin/main 2>/dev/null; then
                log_info "✓ $sm_path: pointer changed but commit is on main (pointer bump only)"
                continue
            fi

            # Submodule has changes beyond main - should be on matching branch
            local sm_branch
            sm_branch="$(get_submodule_branch "$sm_path")"

            if [[ "$sm_branch" == "$current_branch" ]] || branch_exists_in_remote "$sm_path" "$current_branch"; then
                log_info "✓ $sm_path: branch '$current_branch' exists (has pointer changes)"

                # Check for PR linking if we have PR context
                if [[ -n "$repo" ]] && [[ -n "${PR_NUMBER:-}" ]] && command -v gh &>/dev/null; then
                    local pr_info submodule_pr_number submodule_pr_url
                    pr_info="$(get_pr_for_branch "$repo" "$current_branch")"

                    if [[ -z "$pr_info" ]]; then
                        # No open PR - check if PR was already merged (that's fine)
                        if branch_has_merged_pr "$repo" "$current_branch"; then
                            log_info "✓ $sm_path: PR for branch '$current_branch' was already merged"
                        else
                            log_error "✗ $sm_path: no open PR found for branch '$current_branch' in $repo"
                            log_error "  AI FIX: cd $sm_path && gh pr create --title 'Your PR title' --body 'Description'"
                            ((errors++))
                        fi
                    else
                        submodule_pr_number="${pr_info%%|*}"
                        submodule_pr_url="${pr_info##*|}"
                        has_open_submodule_prs=true

                        if [[ -n "$console_pr_body" ]] && ! pr_is_linked "$submodule_pr_url" "$console_pr_body"; then
                            log_error "✗ $sm_path: PR $submodule_pr_url not linked in console PR description"
                            log_error "  AI FIX: Edit console PR description to include: $submodule_pr_url"
                            ((errors++))
                        else
                            log_info "✓ $sm_path: PR $submodule_pr_url is linked"
                        fi

                        # Check for unreplied review comments on submodule PR
                        local unreplied_count
                        unreplied_count="$(check_pr_review_comments "$repo" "$submodule_pr_number")"

                        if [[ "$unreplied_count" -gt 0 ]]; then
                            log_error "✗ $sm_path: PR has $unreplied_count unreplied review comment(s)"
                            log_error "  AI FIX: Go to $submodule_pr_url and reply to all review comments"
                            log_error "  NOTE: Low-effort replies like 'ok', 'done', 'fixed' don't count"
                            ((errors++))
                        else
                            log_info "✓ $sm_path: all review comments addressed"
                        fi
                    fi
                fi
            else
                log_error "✗ $sm_path: has pointer changes but branch '$current_branch' not found"
                log_error "  AI FIX: cd $sm_path && git checkout -b $current_branch && git push -u origin $current_branch"
                ((errors++))
            fi
        else
            # Submodule has no changes - should be on main
            local sm_branch
            sm_branch="$(get_submodule_branch "$sm_path")"

            if [[ "$sm_branch" == "main" || "$sm_branch" == "detached" || "$sm_branch" == "HEAD" ]]; then
                log_info "✓ $sm_path: no pointer changes, on '$sm_branch' (expected)"
            else
                log_warn "⚠ $sm_path: no pointer changes but on branch '$sm_branch' (expected main)"
                ((warnings++))
            fi
        fi
    done

    echo ""

    # Post commit status for submodule merge readiness
    if [[ $errors -gt 0 ]]; then
        post_commit_status "failure" "Submodule validation failed with $errors error(s)"
    elif [[ "$has_open_submodule_prs" == "true" ]]; then
        post_commit_status "pending" "Submodule PRs still open — merge them first"
    else
        post_commit_status "success" "All submodule PRs merged or no submodule changes"
    fi

    if [[ $errors -gt 0 ]]; then
        log_error "Submodule branch validation failed with $errors error(s)"
        exit 1
    elif [[ $warnings -gt 0 ]]; then
        log_warn "Submodule branch validation passed with $warnings warning(s)"
        exit 0
    else
        log_info "All submodule branches validated successfully"
        exit 0
    fi
}

main "$@"
