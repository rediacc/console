#!/bin/bash
# Report whether a PR branch is up-to-date with its base branch, and whether
# rebasing it would conflict. DETECTION ONLY -- this script never rewrites
# history, never moves a ref, and never publishes anything.
#
# WHY IT ONLY REPORTS. It used to `git rebase origin/<base>` and then republish
# the branch from CI, so the bot rewrote contributors' branches out from under
# them (observed: "rediacc-ci-cd Bot force-pushed the 0827-1 branch"). That
# required a contents:write app token in a job whose code comes from the PR
# itself, and it rewrote a real checkout that other work may be sitting in. The
# rebase is now the operator's, run locally where the tooling for it lives
# (/branch-rebase and the worklist --git verbs); CI's job is to say that a
# rebase is needed, not to perform one.
#
# Usage:
#   .ci/scripts/quality/check-branch.sh
#
# Environment variables:
#   GITHUB_BASE_REF - Base branch name (e.g., 'main') - set by GitHub Actions
#   GITHUB_HEAD_REF - PR branch name (optional; only used to name the branch in
#                     the printed recipe) - set by GitHub Actions
#   GITHUB_EVENT_NAME - GitHub event type (e.g., 'pull_request')
#
# Exit codes:
#   0 - Branch is up-to-date with the base (or this is not a pull request)
#   1 - Branch is behind the base and must be rebased locally. The message
#       separates the two cases the probe can tell apart:
#         - Branch has conflicts  -> resolve them during the local rebase
#         - no conflicts detected -> a plain local rebase is enough
#       Exit 1 is also how an UNANSWERABLE check reports itself: if the
#       behind-count cannot be computed the branch must not be called current.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"
cd "$REPO_ROOT"

# Skip check for non-PR events
if [[ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]]; then
    log_info "Skipping branch check (not a pull request)"
    exit 0
fi

BASE_BRANCH="${GITHUB_BASE_REF:-main}"
HEAD_BRANCH="${GITHUB_HEAD_REF:-}"

log_step "Checking branch status against origin/${BASE_BRANCH}..."

# Fetch the base branch to ensure we have latest.
#
# AN EXPLICIT REFSPEC, because every line below reads `origin/${BASE_BRANCH}`
# and a bare `git fetch origin <branch>` does not promise to write it. The
# remote-tracking ref is updated only when the fetched ref matches
# remote.origin.fetch, and actions/checkout configures that narrowly in some
# shapes -- proven both directions in scripts/check-pr-task-trailers.ts's
# selftest, where a bare fetch under a narrow refspec leaves origin/main absent
# while the explicit form creates it. This works today because the checkout
# above names a branch; spelling it out means it keeps working if that changes.
log_info "Fetching origin/${BASE_BRANCH}..."
git fetch origin "+refs/heads/${BASE_BRANCH}:refs/remotes/origin/${BASE_BRANCH}" --quiet

# Check 1: Is the PR behind the base branch?
#
# FAIL LOUDLY. This used to end in `|| echo "0"`, and 0 is the same value the
# gate reads as "up-to-date" two lines down, where it exits 0. So a missing
# origin ref, a shallow clone with no merge base, or any other rev-list failure
# reported the branch as current and let the merge proceed. The fetch above has
# to have succeeded for the ref to exist, so a failure here is a real breakage.
REV_LIST_ERR="$(mktemp)"
BEHIND_RC=0
BEHIND_COUNT=$(git rev-list --count "HEAD..origin/${BASE_BRANCH}" 2>"$REV_LIST_ERR") || BEHIND_RC=$?
if ((BEHIND_RC != 0)); then
    log_error "git rev-list failed for HEAD..origin/${BASE_BRANCH} (exit ${BEHIND_RC})"
    [[ -s "$REV_LIST_ERR" ]] && sed 's/^/    /' "$REV_LIST_ERR" >&2
    rm -f "$REV_LIST_ERR"
    log_error "Cannot tell whether this branch is behind ${BASE_BRANCH}, so it must not be reported as up-to-date."
    exit 1
fi
rm -f "$REV_LIST_ERR"

if [[ "$BEHIND_COUNT" -eq 0 ]]; then
    log_info "Branch is up-to-date with origin/${BASE_BRANCH}"
    exit 0
fi

log_warn "Branch is ${BEHIND_COUNT} commit(s) behind origin/${BASE_BRANCH}"
echo ""
echo "Recent commits on ${BASE_BRANCH} not in this branch:"
git log --oneline "HEAD..origin/${BASE_BRANCH}" | head -5
echo ""

# Check 2: would rebasing conflict?
#
# `git merge-tree --write-tree` answers this WITHOUT touching the working tree,
# the index, HEAD, or any ref -- it writes only loose objects into the object
# database. That is the whole reason it replaced the in-place `git rebase` that
# used to live here: this job's checkout is a real tree, and a gate has no
# business rewriting one.
#
# It is a THREE-WAY MERGE probe, not a replay of each commit, so read it as an
# indication and not a proof: a merge that resolves cleanly can still stop a
# per-commit rebase, and vice versa. Exit 0 = clean, 1 = conflicts, anything
# else = the probe itself could not run (e.g. unrelated histories), which is
# reported as unknown rather than silently as "clean".
log_step "Probing whether a rebase onto origin/${BASE_BRANCH} would conflict..."

MERGE_TREE_OUT="$(mktemp)"
MERGE_TREE_RC=0
git merge-tree --write-tree "origin/${BASE_BRANCH}" HEAD >"$MERGE_TREE_OUT" 2>&1 || MERGE_TREE_RC=$?

case "$MERGE_TREE_RC" in
    0)
        log_info "No conflicts detected - a plain rebase should apply cleanly"
        ;;
    1)
        log_error "Branch has conflicts: rebasing onto origin/${BASE_BRANCH} needs manual resolution"
        echo ""
        echo "Conflicting paths (merge-tree stage entries):"
        # Line 1 is the toplevel tree oid; the conflict report follows it.
        sed -n '2,$p' "$MERGE_TREE_OUT" | head -20 | sed 's/^/    /'
        echo ""
        ;;
    *)
        log_warn "Conflict probe could not run (git merge-tree exit ${MERGE_TREE_RC}); reporting as unknown"
        [[ -s "$MERGE_TREE_OUT" ]] && sed 's/^/    /' "$MERGE_TREE_OUT" >&2
        echo ""
        ;;
esac
rm -f "$MERGE_TREE_OUT"

log_error "This branch must be rebased before it can merge. CI does not do it for you."
echo ""
echo "=============================================="
echo "REBASE LOCALLY${HEAD_BRANCH:+ (branch: ${HEAD_BRANCH})}"
echo "=============================================="
echo ""
echo "  /branch-rebase ${BASE_BRANCH}"
echo ""
echo "    Rebases the console repo AND every submodule carrying a branch of the"
echo "    same name, resolving the gitlink conflicts that a plain 'git rebase'"
echo "    gets wrong. It rebases and verifies only; it lands nothing."
echo ""
echo "  If the rebase halts on a conflict:"
echo ""
echo "    .claude/hooks/stop/worklist.py --git rebase-resolve"
echo "        reports where it stopped and stages the paths it can decide"
echo "        (gitlinks by ancestry, registry unions). All-or-nothing: if any"
echo "        path needs you, nothing is written."
echo "    .claude/hooks/stop/worklist.py --git rebase-continue --execute"
echo "        continues the rebase once every conflicted path is staged."
echo ""
echo "  Prove no commit was lost across the rebase:"
echo ""
echo "    .claude/hooks/stop/worklist.py --git snapshot > /tmp/pre.snap   # BEFORE"
echo "    .claude/hooks/stop/worklist.py --git verify-rebase /tmp/pre.snap origin/${BASE_BRANCH}"
echo ""
echo "=============================================="

exit 1
