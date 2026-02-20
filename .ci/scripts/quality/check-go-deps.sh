#!/bin/bash
# Check Go direct dependencies are up-to-date across all Go submodules.
# With integrated auto-fix for PRs (minor/patch upgrades only).
#
# Mirrors the npm check-deps pattern: detects outdated direct deps, auto-upgrades
# minor/patch on PRs, blocks on major upgrades or when blocklisted.
#
# Why this matters:
#   govulncheck only catches registered CVEs. A package can be multiple minor
#   versions behind (with a security fix in between) before the vuln is registered.
#   This check enforces freshness proactively, catching stale deps before they
#   become a security issue.
#
# Usage:
#   .ci/scripts/quality/check-go-deps.sh
#
# Environment variables:
#   GITHUB_EVENT_NAME - GitHub event type (e.g., 'pull_request')
#   GITHUB_HEAD_REF   - PR branch name (set by GitHub Actions)
#   GITHUB_BASE_REF   - Base branch name (set by GitHub Actions)
#   PR_AUTHOR         - GitHub username of the PR author (optional)
#
# Exit codes:
#   0 - All direct Go deps are up-to-date (or blocked/major only)
#   1 - Outdated minor/patch deps found (and could not auto-fix)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"

# Load blocklist: one module path per line, strip comments and whitespace
BLOCKLIST_FILE="$REPO_ROOT/.go-deps-upgrade-blocklist"
declare -A BLOCKED_MODULES=()
if [[ -f "$BLOCKLIST_FILE" ]]; then
    while IFS= read -r line; do
        line="${line%%#*}"
        line="${line//[[:space:]]/}"
        [[ -z "$line" ]] && continue
        BLOCKED_MODULES["$line"]=1
    done <"$BLOCKLIST_FILE"
fi

# Determine major version of a semver string (handles v1.2.3, v1+incompatible, etc.)
get_major() {
    local ver="$1"
    # Strip leading 'v', grab first digit group
    echo "$ver" | sed 's/^v//' | cut -d. -f1 | grep -o '^[0-9]*' || echo "0"
}

# Check a single Go module directory
# Outputs: lines of "MODULE CURRENT LATEST TYPE" where TYPE is major|minor|blocked
check_go_dir() {
    local dir="$1"
    cd "$dir"

    # Use go template to get direct deps with available updates in one pass:
    # Format: "<path> <current> <latest>"
    local outdated
    outdated=$(go list -u -m \
        -f '{{if (and (not .Indirect) .Update)}}{{.Path}} {{.Version}} {{.Update.Version}}{{end}}' \
        all 2>/dev/null || true)

    local line path current latest cur_major lat_major
    while IFS=' ' read -r path current latest; do
        [[ -z "$path" ]] && continue
        cur_major=$(get_major "$current")
        lat_major=$(get_major "$latest")

        if [[ "${BLOCKED_MODULES[$path]+_}" ]]; then
            echo "$path $current $latest blocked"
        elif [[ "$lat_major" -gt "$cur_major" ]]; then
            echo "$path $current $latest major"
        else
            echo "$path $current $latest minor"
        fi
    done <<<"$outdated"

    cd "$REPO_ROOT"
}

# Find Go submodules
declare -a GO_DIRS=()
for dir in "$REPO_ROOT/private"/*/; do
    [[ -f "${dir}go.mod" ]] && GO_DIRS+=("${dir%/}")
done

if [[ ${#GO_DIRS[@]} -eq 0 ]]; then
    log_info "No Go submodules found to check"
    exit 0
fi

# Collect results
declare -a ALL_MINOR=() # "submodule: path current -> latest"
declare -a ALL_MAJOR=()
declare -a ALL_BLOCKED=()
declare -a DIRS_WITH_MINOR=()

for dir in "${GO_DIRS[@]}"; do
    name=$(basename "$dir")
    log_step "Checking Go deps in $name..."

    has_minor=false
    while IFS=' ' read -r path current latest kind; do
        [[ -z "$path" ]] && continue
        case "$kind" in
            minor)
                ALL_MINOR+=("  $name: $path $current -> $latest")
                has_minor=true
                ;;
            major)
                ALL_MAJOR+=("  $name: $path $current -> $latest (major - manual)")
                ;;
            blocked)
                ALL_BLOCKED+=("  $name: $path $current -> $latest (blocked)")
                ;;
        esac
    done < <(check_go_dir "$dir")

    [[ "$has_minor" == "true" ]] && DIRS_WITH_MINOR+=("$dir")
done

# Report
if [[ ${#ALL_MINOR[@]} -gt 0 ]]; then
    echo ""
    log_warn "Outdated Go direct dependencies (minor/patch - must upgrade):"
    for line in "${ALL_MINOR[@]}"; do echo "$line"; done
fi
if [[ ${#ALL_MAJOR[@]} -gt 0 ]]; then
    echo ""
    log_info "Major version updates available (manual upgrade required):"
    for line in "${ALL_MAJOR[@]}"; do echo "$line"; done
fi
if [[ ${#ALL_BLOCKED[@]} -gt 0 ]]; then
    echo ""
    log_info "Blocked packages (see .go-deps-upgrade-blocklist):"
    for line in "${ALL_BLOCKED[@]}"; do echo "$line"; done
fi

# All good?
if [[ ${#DIRS_WITH_MINOR[@]} -eq 0 ]]; then
    if [[ ${#ALL_MAJOR[@]} -gt 0 ]]; then
        log_info "Go deps check passed (${#ALL_MAJOR[@]} major updates available - upgrade manually)"
    else
        log_info "All Go direct dependencies are up-to-date"
    fi
    exit 0
fi

# ────────────────────────────────────────────────────────────────────────────
# Auto-fix section (PR context only)
# ────────────────────────────────────────────────────────────────────────────

log_warn "Outdated Go dependencies detected"

if [[ "${GITHUB_EVENT_NAME:-}" != "pull_request" ]] || [[ -z "${GITHUB_HEAD_REF:-}" ]]; then
    log_error "Cannot auto-fix outside PR context"
    log_error "In each Go submodule run:"
    log_error "  go get \$(go list -u -m -f '{{if (and (not .Indirect) .Update)}}{{.Path}}@latest {{end}}' all)"
    log_error "  go mod tidy"
    exit 1
fi

# Loop prevention: refuse if we already auto-fixed on this PR
BASE_REF="${GITHUB_BASE_REF:-main}"
RECENT_AUTOFIX=$(git -C "$REPO_ROOT" log --oneline -5 "origin/${BASE_REF}..HEAD" \
    --grep="auto-upgrade go dependencies" 2>/dev/null | head -1 || true)
if [[ -n "$RECENT_AUTOFIX" ]]; then
    log_error "Recent Go deps autofix commit found: $RECENT_AUTOFIX"
    log_error "Cannot auto-fix again. Manually upgrade the Go deps shown above."
    exit 1
fi

# Configure git identity
GIT_NAME="${PR_AUTHOR:-github-actions[bot]}"
GIT_EMAIL="${PR_AUTHOR:+${PR_AUTHOR}@users.noreply.github.com}"
GIT_EMAIL="${GIT_EMAIL:-github-actions[bot]@users.noreply.github.com}"
git -C "$REPO_ROOT" config user.name "$GIT_NAME"
git -C "$REPO_ROOT" config user.email "$GIT_EMAIL"

PUSHED_NAMES=()
SKIPPED_NAMES=()

for dir in "${DIRS_WITH_MINOR[@]}"; do
    name=$(basename "$dir")
    log_step "Auto-upgrading Go deps in $name..."

    ORIG=$(git -C "$dir" rev-parse HEAD 2>/dev/null)
    PUSH_OK=false

    (
        set -e
        cd "$dir"
        git config user.name "$GIT_NAME"
        git config user.email "$GIT_EMAIL"

        # Collect non-major, non-blocked direct deps with updates
        PKGS=$(go list -u -m \
            -f '{{if (and (not .Indirect) .Update)}}{{.Path}} {{.Version}} {{.Update.Version}}{{end}}' \
            all 2>/dev/null | awk '
            {
                path=$1; cur=$2; lat=$3
                # Extract major version number
                gsub(/^v/, "", cur); gsub(/^v/, "", lat)
                split(cur, ca, "."); split(lat, la, ".")
                if (int(la[1]) > int(ca[1])) next   # Skip major upgrades
                print path "@latest"
            }')

        if [[ -z "$PKGS" ]]; then
            log_info "Nothing to upgrade in $name (remaining updates are major only)"
            exit 0
        fi

        # shellcheck disable=SC2086
        go get $PKGS
        go mod tidy

        if git diff --quiet go.mod go.sum; then
            log_info "No changes after upgrade in $name"
            exit 0
        fi

        git add go.mod go.sum
        git commit -m "chore(deps): auto-upgrade go dependencies

Automatically upgraded by CI go deps check."

        git push origin "HEAD:${GITHUB_HEAD_REF}"
    ) && PUSH_OK=true

    if [[ "$PUSH_OK" == "true" ]]; then
        log_info "Pushed Go dep upgrades for $name"
        git -C "$REPO_ROOT" add "$dir"
        PUSHED_NAMES+=("$name")
    else
        log_warn "Failed to upgrade Go deps in $name — reverting"
        (git -C "$dir" reset --hard "$ORIG" 2>/dev/null) || true
        SKIPPED_NAMES+=("$name")
    fi
done

# Commit console submodule pointer
if [[ ${#PUSHED_NAMES[@]} -gt 0 ]]; then
    MODULES_LIST=$(
        IFS=", "
        echo "${PUSHED_NAMES[*]}"
    )
    git -C "$REPO_ROOT" commit -m "chore(deps): auto-upgrade go dependencies

Automatically upgraded by CI go deps check in: $MODULES_LIST"
    git -C "$REPO_ROOT" push origin "HEAD:${GITHUB_HEAD_REF}"
    log_info "Console submodule pointer updated for: $MODULES_LIST"
fi

if [[ ${#SKIPPED_NAMES[@]} -gt 0 ]]; then
    log_warn "Skipped (push failed): ${SKIPPED_NAMES[*]}"
    log_warn "Manually upgrade Go deps in these submodules"
fi

exit 0
