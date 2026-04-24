#!/bin/bash
# Check Go direct dependencies are up-to-date across all Go submodules.
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
# Exit codes:
#   0 - All direct Go deps are up-to-date (or blocked/major only)
#   1 - Outdated minor/patch deps found

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

REPO_ROOT="$(get_repo_root)"

# Load blocklist via shared BLOCKER-aware parser; fail loudly if any entry
# lacks a substantive "# BLOCKER: <reason>" annotation.
# shellcheck source=../lib/blocker-validator.sh
# BLOCKER: shared BLOCKER parser + quality validator used by every suppression gate
source "$SCRIPT_DIR/../lib/blocker-validator.sh"
# shellcheck source=../lib/age-check.sh
# BLOCKER: age-based rot detection for blocklist entries; forces yearly re-review
source "$SCRIPT_DIR/../lib/age-check.sh"

BLOCKLIST_FILE="$REPO_ROOT/.go-deps-upgrade-blocklist"
declare -A BLOCKED_MODULES=() BLOCKED_MODULE_REASONS=()
if [[ -f "$BLOCKLIST_FILE" ]]; then
    parse_blockered_list "$BLOCKLIST_FILE" BLOCKED_MODULES BLOCKED_MODULE_REASONS
    if ! verify_all_blockers "$BLOCKLIST_FILE" BLOCKED_MODULE_REASONS; then
        log_error "Go deps blocklist entries must include quality '# BLOCKER: <reason>' — strict gate enforced"
        exit 1
    fi
    age_fail=0
    for mod in "${!BLOCKED_MODULES[@]}"; do
        check_entry_age "$BLOCKLIST_FILE" "$mod" "$mod" "go-deps-blocklist entry" || age_fail=1
    done
    if [[ $age_fail -ne 0 ]]; then
        log_error "Go deps blocklist entries older than $AGE_FAIL_DAYS days must be re-reviewed"
        exit 1
    fi
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

# Minor/patch upgrades needed
exit 1
