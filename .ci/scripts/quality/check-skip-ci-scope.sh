#!/bin/bash
# Validate scope of [skip ci] commits.
#
# If HEAD (or a specified SHA) has a commit message containing [skip ci],
# the diff MUST only touch files in a narrow allowlist. This prevents
# [skip ci] from being used to bypass CI on substantive changes.
#
# Allowlist:
#   - any path under private/ that is a submodule pointer (git mode 160000)
#   - CHANGELOG* files at any path
#   - *.csproj files (middleware <Version> bumps)
#   - package.json — only when the diff hunks touch the "version" key
#
# Usage:
#   .ci/scripts/quality/check-skip-ci-scope.sh                # checks HEAD
#   .ci/scripts/quality/check-skip-ci-scope.sh <sha>          # checks given SHA
#   HEAD_SHA=<sha> HEAD_MESSAGE="..." .ci/scripts/.../...sh   # env override (test)
#
# Exit codes:
#   0 — HEAD is not [skip ci], or it is [skip ci] and scope is valid
#   1 — HEAD is [skip ci] and scope is violated
#   2 — internal error (bad git state, missing commit)
#
# Platform note on the companion workflow:
#   GitHub Actions skips every `on: push` and `on: pull_request` workflow
#   when the commit message contains [skip ci]. We therefore cannot catch
#   a scope violation via push. Instead, the companion workflow runs on
#   `schedule` + `workflow_dispatch` to sweep recent main commits, and
#   this script runs locally via `npm run ci` during development.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/emit-advisory.sh
# BLOCKER: ci_error / log_info / log_success come from emit-advisory.sh
source "$SCRIPT_DIR/../lib/emit-advisory.sh"

TARGET_SHA="${1:-${HEAD_SHA:-HEAD}}"
REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"

RESOLVED_SHA=$(git -C "$REPO_ROOT" rev-parse --verify "$TARGET_SHA" 2>/dev/null || true)
if [[ -z "$RESOLVED_SHA" ]]; then
    ci_error "Could not resolve SHA: $TARGET_SHA"
    exit 2
fi

HEAD_MESSAGE="${HEAD_MESSAGE:-$(git -C "$REPO_ROOT" log -1 --format=%B "$RESOLVED_SHA")}"

# Case-insensitive match for any of: [skip ci], [ci skip], [no ci]
# (GitHub treats these as equivalent skip markers.)
if ! echo "$HEAD_MESSAGE" | grep -qiE '\[(skip ci|ci skip|no ci)\]'; then
    log_success "Commit $RESOLVED_SHA does not contain a skip-ci marker — scope check skipped"
    exit 0
fi

log_info "Commit $RESOLVED_SHA contains a skip-ci marker; validating diff scope..."

CHANGED_FILES=()
while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    CHANGED_FILES+=("$line")
done < <(git -C "$REPO_ROOT" diff-tree --no-commit-id --name-only -r "$RESOLVED_SHA")

if ((${#CHANGED_FILES[@]} == 0)); then
    log_success "No changed files in $RESOLVED_SHA; scope check vacuous"
    exit 0
fi

is_submodule_pointer() {
    local path="$1"
    local mode
    mode=$(git -C "$REPO_ROOT" ls-tree "$RESOLVED_SHA" -- "$path" 2>/dev/null | awk '{print $1}')
    [[ "$mode" == "160000" ]]
}

is_package_json_version_only() {
    # Grab the diff against parent; any +/- content line that does NOT contain
    # "version": is a non-version edit and disqualifies the commit.
    local parent diff bad
    parent=$(git -C "$REPO_ROOT" rev-parse "${RESOLVED_SHA}^" 2>/dev/null || echo "")
    if [[ -z "$parent" ]]; then
        # Root commit — can't narrow; treat as non-allowlisted.
        return 1
    fi
    diff=$(git -C "$REPO_ROOT" diff "$parent" "$RESOLVED_SHA" -- package.json)
    bad=$(echo "$diff" |
        grep -E '^[+-]([^+-]|$)' |
        grep -vE '"version"[[:space:]]*:' || true)
    [[ -z "$bad" ]]
}

violations=()
for path in "${CHANGED_FILES[@]}"; do
    case "$path" in
        CHANGELOG | CHANGELOG.md | */CHANGELOG | */CHANGELOG.md)
            continue
            ;;
        *.csproj)
            continue
            ;;
        package.json)
            if is_package_json_version_only; then
                continue
            fi
            violations+=("$path (non-'version' field changed)")
            ;;
        private/*)
            if is_submodule_pointer "$path"; then
                continue
            fi
            violations+=("$path (inside private/ but not a submodule pointer)")
            ;;
        *)
            violations+=("$path (path not in allowlist)")
            ;;
    esac
done

if ((${#violations[@]} > 0)); then
    ci_error "[skip ci] commit $RESOLVED_SHA touches files outside the allowlist"
    for v in "${violations[@]}"; do
        echo "  - $v"
    done
    echo "  Fix: [skip ci] is reserved for submodule-pointer bumps, CHANGELOG edits, *.csproj <Version> bumps, and package.json 'version' updates."
    echo "  Action: remove [skip ci] from the commit message, OR split non-allowlisted changes into a separate commit (one substantive, one skip-ci)."
    exit 1
fi

log_success "[skip ci] scope OK for $RESOLVED_SHA (${#CHANGED_FILES[@]} file(s), all allowlisted)"
exit 0
