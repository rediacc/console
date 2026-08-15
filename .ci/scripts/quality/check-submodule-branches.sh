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
#   - On pushes to main, and on the nightly, where it asserts the STRONGER rule
#     that every gitlink is reachable from the submodule's own origin/main
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
# ERROR: "Submodule private/renet expected on branch 0203-1 but is on main"
#   CAUSE: Submodule has pointer changes but no matching branch was created
#   FIX:
#     cd private/renet
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
# ERROR: "No open PR found for branch 0203-1 in rediacc/renet"
#   CAUSE: Branch exists but no PR was created for it
#   FIX:
#     cd private/renet
#     gh pr create --title "feat: your changes" --body "Description"
#
# ERROR: "PR not linked in console PR description"
#   CAUSE: Submodule PR exists but is not mentioned in console PR
#   FIX: Edit console PR description to include the submodule PR URL:
#     ## Related PRs
#     - https://github.com/rediacc/renet/pull/123
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
    ["private/renet"]="rediacc/renet"
    ["private/homebrew-tap"]="rediacc/homebrew-tap"
    ["private/account"]="rediacc/account"
    ["private/elite"]="rediacc/elite"
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

    # A failed probe used to become "0", i.e. "no merged PR". The direction is
    # safe (the caller reports the branch as unmerged, which is the louder
    # answer), but it is still a guess presented as a fact. Say so instead.
    local merged_count
    if ! merged_count=$(gh_retry "merged-PR lookup for ${repo}#${branch}" -- \
        pr list --repo "$repo" --head "$branch" --state merged --json number --jq 'length'); then
        log_warn "${repo}: could not determine whether ${branch} has a merged PR; treating it as NOT merged"
        return 1
    fi
    [[ "$merged_count" =~ ^[0-9]+$ ]] || return 1
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
    # Use here-string instead of pipe to avoid SIGPIPE with grep -q under pipefail
    if grep -qF "$pr_url" <<<"$text"; then
        return 0
    fi

    # Check if repo#number pattern is in the text (e.g., rediacc/renet#123)
    local repo
    repo=$(echo "$pr_url" | grep -oE 'github\.com/[^/]+/[^/]+' | sed 's|github.com/||')
    if [[ -n "$repo" && -n "$pr_number" ]]; then
        if grep -qE "${repo}#${pr_number}|${repo}/pull/${pr_number}" <<<"$text"; then
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

    # Fetch all review comments.
    #
    # FAIL CLOSED. `|| echo "[]"` here meant a gh failure produced the same
    # value as a PR with no review comments, and the function then echoed "0"
    # unreplied comments, which the caller reads as "this submodule PR is
    # clean". Return non-zero so the caller can tell a real zero from an
    # unanswered question.
    local comments
    if ! comments=$(gh_json "review comments for ${repo}#${pr_number}" -- \
        api "repos/${repo}/pulls/${pr_number}/comments" --paginate); then
        log_error "${repo}#${pr_number}: could not fetch review comments; refusing to report zero unreplied"
        return 1
    fi

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
            unreplied_count=$((unreplied_count + 1))
        fi
    done < <(echo "$original_comments" | jq -c '.[]')

    echo "$unreplied_count"
}

# The newest top-level "**Claude finished" report on a PR must have a later
# comment by a different author. Echoes: "none" (no report exists),
# "answered", or "unanswered". Returns non-zero when the comments cannot be
# read (fail closed, same rationale as check_pr_review_comments).
check_pr_report_answered() {
    local repo="$1" pr_number="$2"
    if ! command -v gh &>/dev/null; then
        echo "none"
        return 0
    fi
    local comments
    if ! comments=$(gh_json "issue comments for ${repo}#${pr_number}" -- \
        api "repos/${repo}/issues/${pr_number}/comments" --paginate); then
        return 1
    fi
    # jq does the whole judgement so bash never parses comment bodies: pick
    # the newest report by created_at, then ask whether ANY comment from a
    # different login was created after it.
    echo "$comments" | jq -r '
        ([.[] | select(.body | startswith("**Claude finished"))] | sort_by(.created_at) | last) as $r
        | if $r == null then "none"
          elif ([.[] | select(.created_at > $r.created_at and .user.login != $r.user.login)] | length) > 0
          then "answered"
          else "unanswered" end'
}

# Main validation
main() {
    local current_branch
    current_branch="$(get_current_branch)"
    local errors=0
    local warnings=0
    local console_pr_body=""

    log_step "Validating submodule branches (console branch: $current_branch)"

    # On main the coordinated-branch rules do not apply, but a DIFFERENT and
    # stronger invariant does, and until now nothing checked it.
    #
    # THE HOLE THIS CLOSES, hit for real on 2026-07-28. console#541 merged while
    # rediacc/account#69 was still open, so main's gitlink pointed at b0ea51f, a
    # commit that existed ONLY on that PR's branch. Had the branch been deleted
    # (which merging normally does), every `submodule update` on main would have
    # failed with "reference is not a tree", and nothing would have warned. The
    # PR-side rules cannot catch this: they legitimately ALLOW a pointer at an
    # unmerged branch commit, because submodule-first means the submodule PR is
    # still open while the console PR runs.
    #
    # So on main, assert the thing that must be true once everything has landed:
    # every gitlink is reachable from the submodule's own origin/main.
    if [[ "$current_branch" == "main" ]]; then
        log_step "On main: asserting every submodule pointer is on the submodule's main"
        local main_errors=0
        for sm_path in private/renet private/homebrew-tap private/account private/elite; do
            if [[ ! -d "$sm_path/.git" ]] && [[ ! -f "$sm_path/.git" ]]; then
                log_warn "Submodule $sm_path not initialized - cannot verify its pointer"
                continue
            fi
            local sm_commit
            sm_commit=$(git ls-tree HEAD -- "$sm_path" 2>/dev/null | awk '{ print $3 }')
            if [[ -z "$sm_commit" ]]; then
                log_warn "$sm_path: no gitlink recorded at HEAD - skipping"
                continue
            fi
            git -C "$sm_path" fetch origin main --quiet 2>/dev/null || true
            if git -C "$sm_path" merge-base --is-ancestor "$sm_commit" origin/main 2>/dev/null; then
                log_info "✓ $sm_path: pointer $sm_commit is on ${SUBMODULE_REPOS[$sm_path]:-origin}/main"
            else
                log_error "✗ $sm_path: pointer $sm_commit is NOT reachable from origin/main"
                log_error "  main must never depend on a commit that lives only on a branch:"
                log_error "  delete that branch and the superproject stops resolving."
                log_error "  Fix: merge the submodule PR, then bump this pointer to the merge commit."
                main_errors=$((main_errors + 1))
            fi
        done
        if [[ "$main_errors" -gt 0 ]]; then
            log_error "$main_errors submodule pointer(s) on main are not on the submodule's main"
            exit 1
        fi
        log_info "All submodule pointers on main are reachable from their own main"
        exit 0
    fi

    # Fetch origin/main for comparison
    git fetch origin main --quiet 2>/dev/null || true

    # Get console PR body for linking check (only in CI with PR context)
    if [[ -n "${PR_NUMBER:-}" ]] && command -v gh &>/dev/null; then
        console_pr_body="$(get_console_pr_body)"
    fi

    # Check each submodule
    for sm_path in private/renet private/homebrew-tap private/account private/elite; do
        if [[ ! -d "$sm_path/.git" ]] && [[ ! -f "$sm_path/.git" ]]; then
            log_warn "Submodule $sm_path not initialized - skipping"
            warnings=$((warnings + 1))
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
                            errors=$((errors + 1))
                        fi
                    else
                        submodule_pr_number="${pr_info%%|*}"
                        submodule_pr_url="${pr_info##*|}"

                        if [[ -n "$console_pr_body" ]] && ! pr_is_linked "$submodule_pr_url" "$console_pr_body"; then
                            log_error "✗ $sm_path: PR $submodule_pr_url not linked in console PR description"
                            log_error "  AI FIX: Edit console PR description to include: $submodule_pr_url"
                            errors=$((errors + 1))
                        else
                            log_info "✓ $sm_path: PR $submodule_pr_url is linked"
                        fi

                        # Check for unreplied review comments on submodule PR.
                        # A non-zero return means the comments could not be
                        # read, which is a finding rather than a clean PR: this
                        # branch used to be reachable only with a real count,
                        # because the fetch fell back to "[]" and echoed 0.
                        local unreplied_count unreplied_rc=0
                        unreplied_count="$(check_pr_review_comments "$repo" "$submodule_pr_number")" || unreplied_rc=$?

                        if ((unreplied_rc != 0)); then
                            log_error "✗ $sm_path: could not read review comments for $submodule_pr_url"
                            log_error "  This gate cannot certify the PR is clean, so it counts as an error."
                            errors=$((errors + 1))
                        elif [[ "$unreplied_count" -gt 0 ]]; then
                            log_error "✗ $sm_path: PR has $unreplied_count unreplied review comment(s)"
                            log_error "  AI FIX: Go to $submodule_pr_url and reply to all review comments"
                            log_error "  NOTE: Low-effort replies like 'ok', 'done', 'fixed' don't count"
                            errors=$((errors + 1))
                        else
                            log_info "✓ $sm_path: all review comments addressed"
                        fi

                        # The REPORT hole, hit live on 2026-08-09 while landing
                        # console#561: rediacc/account#78's automated review
                        # posted a top-level REPORT (no inline threads), and
                        # nothing console-side checked it -- the thread check
                        # above sees only pulls/comments, and the report landed
                        # AFTER the last console run, so no per-commit check
                        # ever re-evaluated. Only the local block-admin-merge
                        # hook caught it, which a web-UI merge would bypass.
                        # Rule (same oracle as check-review-report-replies.sh):
                        # the NEWEST "**Claude finished" report on the sub-PR
                        # must have a LATER comment by someone other than the
                        # bot that posted it.
                        local report_state
                        if ! report_state="$(check_pr_report_answered "$repo" "$submodule_pr_number")"; then
                            log_error "✗ $sm_path: could not read issue comments for $submodule_pr_url"
                            log_error "  This gate cannot certify the report state, so it counts as an error."
                            errors=$((errors + 1))
                        elif [[ "$report_state" == "unanswered" ]]; then
                            log_error "✗ $sm_path: the newest automated review REPORT on $submodule_pr_url has no reply"
                            log_error "  AI FIX: answer the report substantively (a top-level PR comment posted after it)"
                            errors=$((errors + 1))
                        else
                            log_info "✓ $sm_path: review report answered ($report_state)"
                        fi
                    fi
                fi
            else
                log_error "✗ $sm_path: has pointer changes but branch '$current_branch' not found"
                log_error "  AI FIX: cd $sm_path && git checkout -b $current_branch && git push -u origin $current_branch"
                errors=$((errors + 1))
            fi
        else
            # Submodule has no changes - should be on main
            local sm_branch
            sm_branch="$(get_submodule_branch "$sm_path")"

            if [[ "$sm_branch" == "main" || "$sm_branch" == "detached" || "$sm_branch" == "HEAD" ]]; then
                log_info "✓ $sm_path: no pointer changes, on '$sm_branch' (expected)"
            else
                log_warn "⚠ $sm_path: no pointer changes but on branch '$sm_branch' (expected main)"
                warnings=$((warnings + 1))
            fi
        fi
    done

    echo ""

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
