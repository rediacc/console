#!/bin/bash
# Detect version bump type from PR labels on the merge commit
#
# Reads the HEAD commit message, extracts PR number(s), queries their labels
# via the GitHub CLI, and outputs the highest-priority bump type.
#
# Priority: major > minor > patch
#
# Usage:
#   detect-bump-type.sh              # Outputs: patch, minor, or major
#   detect-bump-type.sh --verbose    # With debug logging
#
# Environment variables:
#   GITHUB_REPOSITORY  - owner/repo (set by GitHub Actions)
#   GH_TOKEN           - GitHub token for API access
#
# Fallback: Always outputs "patch" on any error (missing token, API failure, etc.)

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

# Read HEAD commit title (first line only — squash merge bodies contain
# sub-commit PR references that are not the PR being merged)
commit_title=$(git log -1 --format="%s" 2>/dev/null) || fallback_patch "failed to read commit message"
verbose_log "Commit message: $commit_title"

# Extract PR numbers from patterns like (#123) in the title line
pr_numbers=$(echo "$commit_title" | grep -oE '\(#[0-9]+\)' | grep -oE '[0-9]+' || true)

if [[ -z "$pr_numbers" ]]; then
    fallback_patch "no PR numbers found in commit message"
fi

verbose_log "Found PR numbers: $(echo "$pr_numbers" | tr '\n' ' ')"

# Query labels for each PR, track highest priority
found_major=false
found_minor=false

while IFS= read -r pr_num; do
    [[ -z "$pr_num" ]] && continue

    verbose_log "Querying labels for PR #$pr_num..."

    # Use if-! pattern so set -e doesn't exit on gh failure
    if ! output=$(gh pr view "$pr_num" \
        --repo "$GITHUB_REPOSITORY" \
        --json labels \
        --jq '.labels[].name' 2>&1); then
        verbose_log "Failed to query PR #$pr_num, skipping. Error: $output"
        continue
    fi
    labels=$output

    verbose_log "PR #$pr_num labels: $(echo "$labels" | tr '\n' ', ')"

    if echo "$labels" | grep -qx "bump-major"; then
        found_major=true
        verbose_log "Found bump-major label on PR #$pr_num"
        break # Short-circuit: major is highest priority
    fi

    if echo "$labels" | grep -qx "bump-minor"; then
        found_minor=true
        verbose_log "Found bump-minor label on PR #$pr_num"
    fi
done <<<"$pr_numbers"

# Output highest priority
if [[ "$found_major" == "true" ]]; then
    echo "major"
elif [[ "$found_minor" == "true" ]]; then
    echo "minor"
else
    echo "patch"
fi
