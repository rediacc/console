#!/bin/bash
# Detect the version bump type for the release being built, from the labels of
# the PRs that release contains.
#
# WHY THIS WAS REWRITTEN (2026-08-08): THE LABELS WERE DEAD.
#
# The previous version read the HEAD commit TITLE and grepped `(#123)` out of
# it. That shape only ever exists on a squash merge. This repo switched to
# rebase-merge on 2026-07-30, and a rebase merge preserves the original commit
# titles, so the PR number is simply not in the message: 0 of the last 60
# commits on main carried `(#N)`. Every release since took the "no PR numbers
# found" fallback and shipped as a patch no matter what anyone labelled.
# bump-major and bump-minor were declared, documented, guide-listed and inert.
#
# The fix asks GitHub instead of the commit message. `commits/{sha}/pulls`
# resolves a commit to the PRs containing it and follows rebased commits
# (verified live: main's tip resolved to #556, a commit 8 deep to #555).
#
# WHY A RANGE AND NOT JUST HEAD. A release contains every commit since the last
# tag, not only the tip, and CI's auto-cancel means the run that releases need
# not be the run of the PR that carried the label. Scanning <latest tag>..HEAD
# is what "which PRs does this release contain" actually means. Commits BEFORE
# the tag are out of range on purpose: their labels were already consumed by
# the release that tagged them, and re-reading them would escalate a version
# twice.
#
# There is deliberately NO title-parsing fallback. One operator, no external
# consumers, no reason to keep a path that has been provably dead for a week.
#
# Priority: major > minor > patch.
#
# Usage:
#   detect-bump-type.sh              # Outputs: patch, minor, or major
#   detect-bump-type.sh --verbose    # With debug logging
#
# Environment variables:
#   GITHUB_REPOSITORY  - owner/repo (set by GitHub Actions)
#   GH_TOKEN           - GitHub token for API access
#   DETECT_BUMP_MAX_COMMITS - range cap (default 50; a test seam, and a bound
#                        on the API calls a very long release window can cost)
#
# Fallback: outputs "patch" on any error (missing token, API failure, no tag).
# Fail open and SMALL: a missed minor is a version number, an invented major is
# a statement to every consumer of the version stream.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

VERBOSE=false

for arg in "$@"; do
    case "$arg" in
        --verbose)
            VERBOSE=true
            ;;
    esac
done

MAX_COMMITS="${DETECT_BUMP_MAX_COMMITS:-50}"

verbose_log() {
    if [[ "$VERBOSE" == "true" ]]; then
        log_info "[detect-bump] $*" >&2
    fi
}

# Fallback: output patch and exit
fallback_patch() {
    local reason="${1:-unknown}"
    if [[ "$VERBOSE" == "true" ]]; then
        log_warn "[detect-bump] Falling back to patch: $reason" >&2
    fi
    echo "patch"
    exit 0
}

# Check prerequisites
if [[ -z "${GITHUB_REPOSITORY:-}" ]]; then
    fallback_patch "GITHUB_REPOSITORY not set"
fi

if [[ -z "${GH_TOKEN:-}" ]]; then
    fallback_patch "GH_TOKEN not set"
fi

if ! command -v gh &>/dev/null; then
    fallback_patch "gh CLI not available"
fi

# ---------------------------------------------------------------------------
# The commit range
# ---------------------------------------------------------------------------
# Same tag selection as resolve-version.sh (`git tag -l --sort=-v:refname`,
# never `git describe`, which needs the tag reachable from HEAD and fails in a
# shallow clone). Two things can go wrong and they need different answers:
#
#   - The tag exists and is an ancestor: scan the range. An EMPTY range means
#     nothing new since the last release, which is patch, not "look further".
#   - No usable tag: initialize.sh calls this BEFORE its own `git fetch --tags`,
#     so a shallow checkout legitimately has none yet. Fall back to HEAD alone
#     rather than to a blind window of history -- an unbounded `git log -n 50`
#     would re-read PRs a previous release already consumed.
latest_tag=$(git tag -l 'v*' --sort=-v:refname 2>/dev/null | head -1 || true)
if [[ -n "$latest_tag" ]] && git merge-base --is-ancestor "$latest_tag" HEAD 2>/dev/null; then
    commits=$(git log --format='%H' -n "$MAX_COMMITS" "${latest_tag}..HEAD" 2>/dev/null) ||
        fallback_patch "git log ${latest_tag}..HEAD failed"
    range_desc="${latest_tag}..HEAD"
    if [[ -z "$commits" ]]; then
        fallback_patch "no commits between $latest_tag and HEAD"
    fi
else
    commits=$(git rev-parse HEAD 2>/dev/null) || fallback_patch "cannot resolve HEAD"
    range_desc="HEAD alone (no usable version tag in this checkout)"
fi

verbose_log "Scanning $(printf '%s\n' "$commits" | sed '/^$/d' | wc -l) commit(s) in $range_desc"

# ---------------------------------------------------------------------------
# Commit -> PRs -> labels
# ---------------------------------------------------------------------------
# The labels ride along in the same response (a PR object carries them), so
# this is ONE API call per commit rather than one per commit plus one per PR.
# `merged_at != null` matters: an open PR can also contain a commit, and an
# unmerged PR's label describes a release that has not happened.
found_major=false
found_minor=false
seen_prs=""
api_ok=false

while IFS= read -r sha; do
    [[ -n "$sha" ]] || continue
    if ! rows=$(gh api "repos/${GITHUB_REPOSITORY}/commits/${sha}/pulls" \
        --jq '.[] | select(.merged_at != null) | "\(.number) \((.labels // []) | map(.name) | join(","))"' \
        2>&1 </dev/null); then
        verbose_log "commits/${sha:0:7}/pulls failed, skipping. Error: $rows"
        continue
    fi
    api_ok=true
    while IFS= read -r row; do
        [[ -n "$row" ]] || continue
        pr_num="${row%% *}"
        labels="${row#"$pr_num"}"
        labels="${labels# }"
        case " $seen_prs " in
            *" $pr_num "*) continue ;;
        esac
        seen_prs="$seen_prs $pr_num"
        verbose_log "PR #$pr_num labels: ${labels:-<none>}"
        if grep -qx "bump-major" <<<"${labels//,/$'\n'}"; then
            found_major=true
            verbose_log "Found bump-major label on PR #$pr_num"
        elif grep -qx "bump-minor" <<<"${labels//,/$'\n'}"; then
            found_minor=true
            verbose_log "Found bump-minor label on PR #$pr_num"
        fi
    done <<<"$rows"
    if [[ "$found_major" == "true" ]]; then
        verbose_log "major is the highest priority; short-circuiting the scan"
        break
    fi
done <<<"$commits"

if [[ -z "$seen_prs" ]]; then
    if [[ "$api_ok" == "true" ]]; then
        verbose_log "no merged PRs found in $range_desc"
    else
        fallback_patch "every commits/<sha>/pulls lookup failed"
    fi
fi

# Output highest priority
if [[ "$found_major" == "true" ]]; then
    echo "major"
elif [[ "$found_minor" == "true" ]]; then
    echo "minor"
else
    echo "patch"
fi
