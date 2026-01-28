#!/bin/bash
# Shell script compatibility check using ShellCheck
# Used by both ./run.sh quality shell and CI
#
# Checks all shell scripts for cross-platform compatibility issues
#
# Exclusions:
#   SC1091 - Not following sourced files (common.sh is sourced dynamically)
#   SC2034 - Variable appears unused (false positive for exported constants)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Colors (disabled in CI)
if [[ "${CI:-}" == "true" ]]; then
    RED="" GREEN="" NC=""
else
    RED='\033[0;31m' GREEN='\033[0;32m' NC='\033[0m'
fi

log_error() { echo -e "${RED}error: $1${NC}" >&2; }
log_success() { echo -e "${GREEN}success: $1${NC}"; }
log_info() { echo "info: $1"; }

# ShellCheck options
# -e SC1090: Can't follow non-constant source (dynamic sourcing)
# -e SC1091: Not following sourced files (dynamic sourcing)
# -e SC2034: Ignore "appears unused" (false positive for exported constants)
# -S warning: Only fail on warnings or errors (not info/style)
SHELLCHECK_OPTS="-e SC1090 -e SC1091 -e SC2034 -S warning"

main() {
    cd "$ROOT_DIR"

    log_info "Checking shell script compatibility"

    # Verify shellcheck is installed
    if ! command -v shellcheck &>/dev/null; then
        log_error "shellcheck is not installed"
        log_info "Install with: apt install shellcheck (Ubuntu) or brew install shellcheck (macOS)"
        exit 1
    fi

    shellcheck --version

    # Check all shell scripts in .ci directory
    log_info "Checking .ci/**/*.sh"
    # shellcheck disable=SC2086
    find .ci -name "*.sh" -type f -exec shellcheck $SHELLCHECK_OPTS {} +

    # Check the main run.sh script
    log_info "Checking ./run.sh"
    # shellcheck disable=SC2086
    shellcheck $SHELLCHECK_OPTS ./run.sh

    # Check for bash 4+ features in build scripts (which run on macOS with bash 3.2)
    # ShellCheck doesn't warn about these since they're valid bash, but macOS
    # uses an old bash version due to GPL licensing.
    # Only check .ci/scripts/build/ since those run on macOS for desktop builds.
    log_info "Checking build scripts for bash 4+ features (macOS compatibility)"
    BASH4_ISSUES=""

    # Check for associative arrays (declare -A) - requires bash 4.0+
    MATCHES=$(grep -rn "declare -A" .ci/scripts/build --include="*.sh" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
        BASH4_ISSUES="$BASH4_ISSUES\ndeclare -A (associative arrays require bash 4.0+):\n$MATCHES"
    fi

    # Check for |& (pipe stderr) - requires bash 4.0+
    MATCHES=$(grep -rn '[^#]*|&' .ci/scripts/build --include="*.sh" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
        BASH4_ISSUES="$BASH4_ISSUES\n|& (pipe stderr requires bash 4.0+):\n$MATCHES"
    fi

    # Check for coproc - requires bash 4.0+
    MATCHES=$(grep -rwn "coproc" .ci/scripts/build --include="*.sh" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
        BASH4_ISSUES="$BASH4_ISSUES\ncoproc (requires bash 4.0+):\n$MATCHES"
    fi

    # Check for mapfile/readarray - requires bash 4.0+
    # Note: pattern built dynamically to avoid false positive from check-commands.sh
    READ_ARR="read""array"
    MAP_FILE="map""file"
    MATCHES=$(grep -rwn -E "^[^#]*($MAP_FILE|$READ_ARR)" .ci/scripts/build --include="*.sh" 2>/dev/null || true)
    if [[ -n "$MATCHES" ]]; then
        BASH4_ISSUES="$BASH4_ISSUES\nmapfile/readarray (requires bash 4.0+):\n$MATCHES"
    fi

    if [[ -n "$BASH4_ISSUES" ]]; then
        log_error "Found bash 4+ features in build scripts that don't work on macOS (bash 3.2):"
        echo -e "$BASH4_ISSUES"
        log_info "macOS ships with bash 3.2 due to GPLv3 licensing. Use bash 3.x compatible alternatives."
        exit 1
    fi

    # Check for duplicated constants that should be in common.sh
    # These constants are defined in .ci/scripts/lib/common.sh and should not be redefined elsewhere
    log_info "Checking for duplicated constants (should be in common.sh only)"
    SHARED_CONSTANTS="MAX_GEMINI_REVIEWS"
    DUPE_ISSUES=""

    for const in $SHARED_CONSTANTS; do
        # Find assignments like CONST=value (not comments, not references)
        MATCHES=$(grep -rn "^[[:space:]]*${const}=" .ci/scripts --include="*.sh" 2>/dev/null | grep -v "lib/common.sh" || true)
        if [[ -n "$MATCHES" ]]; then
            DUPE_ISSUES="$DUPE_ISSUES\n$const is defined in common.sh but also in:\n$MATCHES"
        fi
    done

    if [[ -n "$DUPE_ISSUES" ]]; then
        log_error "Found duplicated constants that should only be in common.sh:"
        echo -e "$DUPE_ISSUES"
        log_info "Move shared constants to .ci/scripts/lib/common.sh and reference them from there."
        exit 1
    fi

    log_success "Shell scripts passed"
}

main "$@"
