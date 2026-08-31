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
# exists to assert. (A bad ARGUMENT is different: that is a wiring bug, and it
# exits 2.)
#
# MODES. The decision and the dispatch are separable because the CI job needs to
# ask the question BEFORE it seals the version:
#
#   (no flag)        decide, then dispatch if the answer was "release".
#   --decide-only    decide and report; never dispatches, never calls
#                    `gh workflow run`. On SKIP it writes skip_release=true to
#                    $GITHUB_OUTPUT so the steps that seal and dispatch can be
#                    guarded. On every other outcome it writes NOTHING there --
#                    including all three fail-open paths, whose whole purpose is
#                    to end in a release.
#   --dispatch-only  dispatch, with no API lookup at all. The decision was
#                    already made by an earlier --decide-only step; asking twice
#                    would double the API calls and could answer differently if
#                    a label changed between the two.
#
# Every mode prints exactly one `decision: release` or `decision: skip` line to
# stdout, so the behaviour is assertable without a $GITHUB_OUTPUT fixture.
#
# WHY THE SPLIT EXISTS AT ALL. finalize-release-sentinel used to seal the
# version (write-release-sentinel.sh) one step BEFORE this script decided
# whether the commit earned a release. On a bump-none merge the sentinel was
# therefore written and the release then skipped, leaving R2 holding
# cli/v<X>/.released with no matching git tag -- exactly the drift the release
# contract forbids. Observed live on CI run 32491717875: sealed 15:12:12,
# "release SKIPPED: #570 carries 'bump-none'" 15:12:16.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/common.sh
# BLOCKER: log_info / log_warn used throughout this script
source "$SCRIPT_DIR/../lib/common.sh"

SKIP_LABEL='bump-none'

# --decide-only / --dispatch-only / nothing. No flag keeps the original
# end-to-end behaviour, which is what every existing caller and test drives.
MODE='full'
case "${1:-}" in
    '') ;;
    --decide-only) MODE='decide' ;;
    --dispatch-only) MODE='dispatch' ;;
    *)
        log_error "unknown argument '$1' (expected --decide-only, --dispatch-only, or no argument)"
        exit 2
        ;;
esac

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

# Does this commit earn a release? 0 = yes, 1 = no.
#
# Logs its reasoning and emits the same GHA notices it always did, in whichever
# mode it runs -- under the CI wiring this function runs exactly once, in the
# --decide-only step, so suppressing the notices here would mean nothing ever
# printed why a release was withheld or why a fail-open path released anyway.
# What it does NOT do is touch $GITHUB_OUTPUT; that is the caller's job, and it
# happens for the skip verdict only.
decide() {
    local rows
    # Every merged PR containing this commit, as "<number> <label,label,...>".
    # Identical call to detect-bump-type.sh's, deliberately: `commits/{sha}/pulls`
    # follows rebased commits, which this repo needs since it rebase-merges and the
    # PR number is therefore absent from the commit message.
    if ! rows=$(gh api "repos/${GITHUB_REPOSITORY}/commits/${GITHUB_SHA}/pulls" \
        --jq '.[] | select(.merged_at != null) | "\(.number) \((.labels // []) | map(.name) | join(","))"' \
        2>&1 </dev/null); then
        log_warn "could not resolve the PR for ${GITHUB_SHA:0:7} (${rows}); dispatching the release anyway"
        echo "::notice title=Release::PR lookup failed for ${GITHUB_SHA:0:7}; releasing rather than risking a silently withheld release."
        return 0
    fi

    if [[ -z "${rows//[[:space:]]/}" ]]; then
        log_info "no merged PR contains ${GITHUB_SHA:0:7} (direct push, or the API knows of none); dispatching"
        return 0
    fi

    local skip_prs='' keep_prs='' row pr_num labels
    while IFS= read -r row; do
        [[ -n "$row" ]] || continue
        pr_num="${row%% *}"
        labels="${row#"$pr_num"}"
        labels="${labels# }"
        if grep -qx "$SKIP_LABEL" <<<"${labels//,/$'\n'}"; then
            skip_prs="${skip_prs}#${pr_num} "
        else
            keep_prs="${keep_prs}#${pr_num} "
        fi
    done <<<"$rows"

    if [[ -n "$skip_prs" && -z "$keep_prs" ]]; then
        log_info "release SKIPPED: ${skip_prs% } carries '$SKIP_LABEL'"
        echo "::notice title=Release skipped::${skip_prs% } is labelled ${SKIP_LABEL}, so ${GITHUB_SHA:0:7} earns no release: no tag, no GitHub release, no R2 upload, no edge deploy. Its commits ship with the next release-worthy merge."
        return 1
    fi

    if [[ -n "$skip_prs" ]]; then
        log_warn "${skip_prs% } carries '$SKIP_LABEL' but ${keep_prs% } does not; releasing"
        echo "::notice title=Release::${skip_prs% } is labelled ${SKIP_LABEL}, but ${keep_prs% } also contains ${GITHUB_SHA:0:7} and is not; releasing."
    fi

    log_info "dispatching cd-v2 for ${GITHUB_SHA:0:7} (${keep_prs:-no PR})"
    return 0
}

skip_release=false
if [[ "$MODE" != 'dispatch' ]]; then
    decide || skip_release=true
fi

case "$MODE" in
    decide)
        if [[ "$skip_release" == 'true' ]]; then
            echo 'decision: skip'
            if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
                echo 'skip_release=true' >>"$GITHUB_OUTPUT"
            fi
        else
            echo 'decision: release'
        fi
        ;;
    dispatch)
        # No lookup, by design: --decide-only already asked.
        echo 'decision: release'
        dispatch
        ;;
    full)
        if [[ "$skip_release" == 'true' ]]; then
            echo 'decision: skip'
        else
            echo 'decision: release'
            dispatch
        fi
        ;;
esac

exit 0
