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

    # EVERY TRACKED .sh FILE, enumerated from git rather than from a list of
    # roots. It used to be four hardcoded roots (.ci, .claude/hooks, run.sh,
    # scripts/), and the omission was invisible by construction: a file outside
    # them produced no error and no mention, just a green tick over an unread
    # file. Found on 2026-08-15 when a helper added under .claude/lib passed both
    # shell gates carrying a blatant SC2086. Widening to .claude/** would have
    # fixed that one file and left 13 others unscanned, among them the PUBLIC
    # install.sh that users pipe into bash.
    #
    # git ls-files is the enumerator because it needs no maintenance: a new
    # script is covered the moment it is tracked, which is exactly the property
    # a root list cannot have.
    log_info "Checking every tracked *.sh file"
    SH_FILES="$(git ls-files '*.sh')"

    # A gate that lints nothing exits 0 and looks identical to a gate that lints
    # everything. Refuse the empty list rather than pass it.
    if [ -z "$SH_FILES" ]; then
        log_error "no tracked *.sh files found: the enumerator is broken, not the tree clean"
        exit 1
    fi
    log_info "$(printf '%s\n' "$SH_FILES" | wc -l | tr -d ' ') file(s)"

    # BLOCKER: SHELLCHECK_OPTS is a space-separated set of CLI flags, and SH_FILES is a newline-separated file list; word-splitting is intentional for both
    # shellcheck disable=SC2086
    shellcheck $SHELLCHECK_OPTS $SH_FILES

    # Check for bash 4+ features in build scripts (which run on macOS with bash 3.2)
    # ShellCheck doesn't warn about these since they're valid bash, but macOS
    # uses an old bash version due to GPL licensing.
    # Only check .ci/scripts/build/ since those run on macOS for the CLI SEA
    # builds (ci-build-cli.yml uses macos-latest and macos-15-intel).
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

    # NOTE: a "duplicated shared constants" check lived here until 2026-07-22.
    # It guarded exactly one constant (MAX_GEMINI_REVIEWS, removed with the
    # Gemini review machinery) and an empty guard list checks nothing.
    # Reintroduce the loop if common.sh ever grows shared constants again.

    log_success "Shell scripts passed"
}

main "$@"
