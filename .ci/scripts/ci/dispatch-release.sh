#!/bin/bash
# Dispatch the cd-v2 release for this main commit -- unless the PR it came from
# said the commit earns no release at all.
#
# WHY THIS IS A SCRIPT AND NOT A `run:` BLOCK. It was two lines of `gh workflow
# run` inline in ci.yml. The skip decision needs an API lookup, a fail-open
# branch and a reason worth logging, and check-workflow-gates caps a `run:`
# block at 8 logic lines precisely so policy does not accumulate where no test
# can reach it. The dispatch itself is unchanged; only the decision moved.
#
# THE RULE. `bump-none` on the merged PR containing this commit means "no
# user-facing change" (see .github/labels.yml and the reviewer's pr-labels
# vocabulary). Merging it skips the WHOLE release: no tag, no GitHub release, no
# R2 upload, no edge deploy. The commits are not lost -- the next
# release-worthy merge tags everything since the last tag, so they ship with it,
# they simply do not earn a release of their own.
#
# WHY THE HEAD COMMIT AND NOT THE RELEASE RANGE. detect-bump-type.sh scans
# <last tag>..HEAD to size a release, because a release CONTAINS many PRs. This
# asks a different question -- "did the merge that triggered this run earn a
# release" -- and the range answer would be wrong in the dangerous direction: a
# range holding one bump-none PR and one real one must still release.
#
# FAIL OPEN, ALWAYS. Every failure path below dispatches. A flaky lookup that
# silently withheld a release is far worse than one unnecessary release: the
# release is cheap and repeatable, while a withheld one is invisible until
# somebody notices the version stream stopped moving. The same asymmetry is why
# the skip requires EVERY merged PR containing this commit to carry the label
# rather than any one of them.
#
# Env:
#   GH_TOKEN            required, for both the lookup and the dispatch
#   GITHUB_REPOSITORY   owner/repo
#   GITHUB_SHA          the commit being released
#   GITHUB_RUN_ID       passed through to cd-v2 as ci_run_id
#   DISPATCH_RELEASE_DRY_RUN  test seam: print the dispatch instead of running it
#
# Exit: 0 whether it dispatched or skipped. A non-zero exit here would fail the
# release-sentinel job over a decision, and the decision is not what that job
# exists to assert.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_info / log_warn used throughout this script
source "$SCRIPT_DIR/../lib/common.sh"

SKIP_LABEL='bump-none'

require_var GITHUB_REPOSITORY
require_var GITHUB_SHA

dispatch() {
    if [[ -n "${DISPATCH_RELEASE_DRY_RUN:-}" ]]; then
        echo "DRY-RUN: gh workflow run cd-v2.yml --ref main -f release_mode=patch -f ci_run_id=${GITHUB_RUN_ID:-}"
        return 0
    fi
    gh workflow run cd-v2.yml \
        --ref main \
        -f release_mode=patch \
        -f ci_run_id="${GITHUB_RUN_ID:-}"
}

# Every merged PR containing this commit, as "<number> <label,label,...>".
# Identical call to detect-bump-type.sh's, deliberately: `commits/{sha}/pulls`
# follows rebased commits, which this repo needs since it rebase-merges and the
# PR number is therefore absent from the commit message.
if ! rows=$(gh api "repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls" \
    --jq '.[] | select(.merged_at != null) | "\(.number) \((.labels // []) | map(.name) | join(","))"' \
    2>&1 </dev/null); then
    log_warn "could not resolve the PR for ${GITHUB_SHA:0:7} (${rows}); dispatching the release anyway"
    echo "::notice title=Release::PR lookup failed for ${GITHUB_SHA:0:7}; releasing rather than risking a silently withheld release."
    dispatch
    exit 0
fi

if [[ -z "${rows//[[:space:]]/}" ]]; then
    log_info "no merged PR contains ${GITHUB_SHA:0:7} (direct push, or the API knows of none); dispatching"
    dispatch
    exit 0
fi

skip_prs=""
keep_prs=""
while IFS= read -r row; do
    [[ -n "$row" ]] || continue
    pr_num="${row%% *}"
    labels="${row#"$pr_num"}"
    labels="${labels# }"
    if printf '%s\n' "${labels//,/$'\n'}" | grep -qx "$SKIP_LABEL"; then
        skip_prs="${skip_prs}#${pr_num} "
    else
        keep_prs="${keep_prs}#${pr_num} "
    fi
done <<<"$rows"

if [[ -n "$skip_prs" && -z "$keep_prs" ]]; then
    log_info "release SKIPPED: ${skip_prs% } carries '$SKIP_LABEL'"
    echo "::notice title=Release skipped::${skip_prs% } is labelled ${SKIP_LABEL}, so ${GITHUB_SHA:0:7} earns no release: no tag, no GitHub release, no R2 upload, no edge deploy. Its commits ship with the next release-worthy merge."
    exit 0
fi

if [[ -n "$skip_prs" ]]; then
    log_warn "${skip_prs% } carries '$SKIP_LABEL' but ${keep_prs% } does not; releasing"
    echo "::notice title=Release::${skip_prs% } is labelled ${SKIP_LABEL}, but ${keep_prs% } also contains ${GITHUB_SHA:0:7} and is not; releasing."
fi

log_info "dispatching cd-v2 for ${GITHUB_SHA:0:7} (${keep_prs:-no PR})"
dispatch
