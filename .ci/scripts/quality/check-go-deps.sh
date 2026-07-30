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
# shellcheck source=../lib/release-age.sh
# BLOCKER: shared daily-batch freshness rule; defers just-published module updates like the npm gates
source "$SCRIPT_DIR/../lib/release-age.sh"

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
# Outputs: lines of "MODULE CURRENT LATEST TYPE" where TYPE is major|minor|blocked|toofresh
check_go_dir() {
    local dir="$1"
    cd "$dir"

    # JSON stream of direct deps with an available update; carry the update's
    # publish time (.Update.Time) so freshly-released versions can be deferred
    # (daily batch) exactly like the npm gates instead of forcing an immediate
    # bump minutes after a release drops.
    #
    # A FAILED PROBE IS NOT "NOTHING IS OUTDATED". This used to read
    # `go list ... 2>/dev/null | jq ... 2>/dev/null || true`, so any failure of
    # either command produced an empty result set, which is byte-identical to a
    # clean tree: the gate printed "All Go direct dependencies are up-to-date"
    # and exited 0. Observed 2026-07-27: a local run reported all-clean while
    # CI failed on the same commit, because `go list` was exiting 1 (go.mod
    # requires go >= 1.25 and the toolchain on PATH was 1.24). The gate was not
    # disagreeing with CI, it was silently reporting nothing at all.
    #
    # So the probe's exit status is now load-bearing, and a failure is reported
    # to the caller through a sentinel line rather than swallowed. The sentinel
    # (not a bare `exit 1`) is required because this function runs inside a
    # process substitution, where an exit would be invisible to the caller.
    local outdated raw stderr_file status=0
    stderr_file=$(mktemp)
    raw=$(go list -u -m -json all 2>"$stderr_file") || status=$?
    if ((status != 0)); then
        echo "__PROBE_FAILED__ go-list exit=$status $(tr '\n' ' ' <"$stderr_file" | head -c 300)"
        rm -f "$stderr_file"
        cd "$REPO_ROOT"
        return 0
    fi
    rm -f "$stderr_file"

    # An empty module list means the probe returned nothing usable. `go list -m`
    # on a real module always emits at least the main module, so zero is broken,
    # not clean.
    local seen
    seen=$(printf '%s' "$raw" | jq -rs 'length' 2>/dev/null || echo 0)
    if [[ "$seen" -eq 0 ]]; then
        echo "__PROBE_FAILED__ go-list returned no modules at all"
        cd "$REPO_ROOT"
        return 0
    fi

    if ! outdated=$(printf '%s' "$raw" | jq -rs '.[] | select((.Indirect != true) and (.Update != null))
                | "\(.Path) \(.Version) \(.Update.Version) \(.Update.Time // "")"' 2>&1); then
        echo "__PROBE_FAILED__ jq failed to parse go-list output: $(printf '%s' "$outdated" | tr '\n' ' ' | head -c 200)"
        cd "$REPO_ROOT"
        return 0
    fi

    local path current latest uptime cur_major lat_major epoch
    while IFS=' ' read -r path current latest uptime; do
        [[ -z "$path" ]] && continue
        cur_major=$(get_major "$current")
        lat_major=$(get_major "$latest")

        if [[ "${BLOCKED_MODULES[$path]+_}" ]]; then
            echo "$path $current $latest blocked"
            continue
        fi

        # Defer a just-published update until the next UTC day after it ages 24h.
        #
        # An unparseable timestamp used to vanish into `|| echo ""`. The
        # direction is safe (no deferral is applied, so the module is still
        # reported as outdated and the gate stays red rather than going quiet),
        # but silence still hides a real breakage: if the upstream timestamp
        # format ever changed, EVERY module would silently lose its
        # minimum-release-age deferral and the gate would start demanding bumps
        # it should be holding back. Warn on stderr, which does not disturb the
        # machine-readable records this function writes to stdout.
        epoch=""
        if [[ -n "$uptime" ]]; then
            if ! epoch=$(date -u -d "$uptime" +%s 2>/dev/null); then
                log_warn "could not parse update timestamp '$uptime' for $path; freshness deferral not applied"
                epoch=""
            fi
        fi
        if [[ -n "$epoch" ]] && is_release_deferred "$epoch"; then
            echo "$path $current $latest toofresh"
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
declare -a ALL_TOOFRESH=()
declare -a DIRS_WITH_MINOR=()
declare -a PROBE_FAILURES=()

for dir in "${GO_DIRS[@]}"; do
    name=$(basename "$dir")
    log_step "Checking Go deps in $name..."

    has_minor=false
    while IFS=' ' read -r path current latest kind; do
        [[ -z "$path" ]] && continue
        # The probe could not report on this module. Collect it and keep going,
        # so one broken submodule still lets the others be checked, then fail
        # loudly at the end. Never treat this as "up-to-date".
        if [[ "$path" == "__PROBE_FAILED__" ]]; then
            PROBE_FAILURES+=("  $name: $current $latest $kind")
            continue
        fi
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
                # Surface the BLOCKER reason like the npm deps gate does.
                ALL_BLOCKED+=("    Reason: ${BLOCKED_MODULE_REASONS[$path]:-}")
                ;;
            toofresh)
                ALL_TOOFRESH+=("  $name: $path $current -> $latest (too new)")
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
if [[ ${#ALL_TOOFRESH[@]} -gt 0 ]]; then
    echo ""
    log_info "Too new — within freshness window, deferred until next UTC day:"
    for line in "${ALL_TOOFRESH[@]}"; do echo "$line"; done
fi

# A probe that could not run is a hard failure, checked BEFORE the all-good
# path. Reporting "up-to-date" on the strength of a command that errored is the
# exact defect this guard replaces.
if [[ ${#PROBE_FAILURES[@]} -gt 0 ]]; then
    echo ""
    log_error "Go dependency probe FAILED — this is not the same as 'up-to-date':"
    for line in "${PROBE_FAILURES[@]}"; do echo "$line"; done
    log_error "Fix the Go toolchain or module access and re-run; the gate cannot vouch for these modules."
    exit 1
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
