#!/bin/bash
# Common utilities for CI scripts
# Source this file at the beginning of each script:
#   source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
#
# ⚠️  IMPORTANT: When adding/modifying utility functions:
# ⚠️  1. Update this file (common.sh)
# ⚠️  2. Test affected CI scripts (run-unit.sh, run-e2e.sh, etc.)
# ⚠️  3. Update the main 'go' script if functions are used there

set -euo pipefail

# =============================================================================
# COLORS AND LOGGING
# =============================================================================

# Colors (disabled if not a terminal or if NO_COLOR is set)
if [[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    NC='\033[0m' # No Color
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    NC=''
fi

# Logging functions
log_info() {
    echo -e "${GREEN}✓${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $*" >&2
}

log_error() {
    echo -e "${RED}✗${NC} $*" >&2
}

log_step() {
    echo -e "${BLUE}→${NC} $*" >&2
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo -e "${CYAN}[DEBUG]${NC} $*" >&2
    fi
}

# =============================================================================
# ENVIRONMENT DETECTION
# =============================================================================

# Detect operating system
# Returns: linux, macos, or windows
detect_os() {
    case "$(uname -s)" in
        Linux*) echo "linux" ;;
        Darwin*) echo "macos" ;;
        CYGWIN*) echo "windows" ;;
        MINGW*) echo "windows" ;;
        MSYS*) echo "windows" ;;
        *) echo "unknown" ;;
    esac
}

# Portable in-place sed.
#
# GNU sed takes `-i` with no argument; BSD/macOS sed REQUIRES a backup-suffix
# argument, so `sed -i 's/a/b/' f` on macOS consumes the expression as the
# suffix and then fails with "no input files" -- or, worse, silently edits the
# wrong thing. Every .ci script documents itself as locally runnable, so the
# platform is not ours to assume.
#
# Pass ALL sed arguments through, file last, exactly as you would to sed:
#   sed_in_place -E "s/x/y/" "$file"
#   sed_in_place -e "s/a/b/" -e "s/c/d/" "$file"
#
# This lived privately inside update-homebrew-tap.sh with a fixed (expr, file)
# signature, which is why five other sites reached for bare `sed -i` instead.
sed_in_place() {
    if [[ "$(detect_os)" == "macos" ]]; then
        sed -i '' "$@"
    else
        sed -i "$@"
    fi
}

# Detect architecture
# Returns: x64, arm64, or unknown
detect_arch() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64 | amd64) echo "x64" ;;
        aarch64 | arm64) echo "arm64" ;;
        *) echo "unknown" ;;
    esac
}

# Check if running in CI environment
# Returns: 0 if CI, 1 otherwise
is_ci() {
    [[ "${CI:-false}" == "true" ]] || [[ -n "${GITHUB_ACTIONS:-}" ]] || [[ -n "${GITLAB_CI:-}" ]]
}

# Get temporary directory (CI-aware)
get_temp_dir() {
    if [[ -n "${RUNNER_TEMP:-}" ]]; then
        echo "$RUNNER_TEMP"
    elif [[ -n "${TMPDIR:-}" ]]; then
        echo "$TMPDIR"
    else
        echo "/tmp"
    fi
}

# =============================================================================
# VALIDATION HELPERS
# =============================================================================

# Check if a required environment variable is set
# Usage: require_var VAR_NAME
require_var() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        log_error "Required environment variable '$var_name' is not set"
        exit 1
    fi
}

# Check if a command exists
# Usage: require_cmd command_name
require_cmd() {
    local cmd="$1"
    if ! command -v "$cmd" &>/dev/null; then
        log_error "Required command '$cmd' is not available"
        exit 1
    fi
}

# Check if a file exists
# Usage: require_file /path/to/file
require_file() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        log_error "Required file '$file' does not exist"
        exit 1
    fi
}

# Check if a directory exists
# Usage: require_dir /path/to/dir
require_dir() {
    local dir="$1"
    if [[ ! -d "$dir" ]]; then
        log_error "Required directory '$dir' does not exist"
        exit 1
    fi
}

# =============================================================================
# PATH HELPERS
# =============================================================================

# Get the repository root directory
# Assumes scripts are in .ci/scripts/
get_repo_root() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # Go up from .ci/scripts/lib to repo root (3 levels)
    cd "$script_dir/../../.." && pwd
}

# =============================================================================
# RETRY HELPERS
# =============================================================================

# Retry a command with exponential backoff
# Usage: retry_with_backoff <max_attempts> <initial_delay> <command...>
retry_with_backoff() {
    local max_attempts="$1"
    local delay="$2"
    shift 2

    local attempt=1
    while [[ $attempt -le $max_attempts ]]; do
        if "$@"; then
            return 0
        fi

        if [[ $attempt -lt $max_attempts ]]; then
            log_warn "Attempt $attempt/$max_attempts failed, retrying in ${delay}s..."
            sleep "$delay"
            delay=$((delay * 2))
        fi

        attempt=$((attempt + 1))
    done

    log_error "Command failed after $max_attempts attempts"
    return 1
}

# Wait for a condition with timeout
# Usage: wait_for <timeout_seconds> <interval_seconds> <command...>
wait_for() {
    local timeout="$1"
    local interval="$2"
    shift 2

    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if "$@" &>/dev/null; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
        log_debug "Waiting... (${elapsed}s / ${timeout}s)"
    done

    return 1
}

# Poll a condition with watchdog timeout and optional progress tracking
# Usage: poll_with_watchdog <timeout> <interval> <condition_cmd> [on_poll_cmd]
#
# Arguments:
#   timeout        - Maximum wait time in seconds
#   interval       - Polling interval in seconds
#   condition_cmd  - Command/function returning 0 when condition met
#   on_poll_cmd    - Optional: called each poll with (elapsed, timeout, interval_num)
#
# Environment (set for callbacks):
#   WATCHDOG_ELAPSED  - Elapsed seconds
#   WATCHDOG_TIMEOUT  - Timeout value
#   WATCHDOG_INTERVAL - Current interval number
#
# Returns: 0 on success, 124 on timeout
#
# Example:
#   poll_with_watchdog 300 5 "check_api_health" "log_progress"
#
poll_with_watchdog() {
    local timeout="$1"
    local interval="$2"
    local condition_cmd="$3"
    local on_poll_cmd="${4:-}"

    local elapsed=0
    local interval_num=0

    # Export for callbacks
    export WATCHDOG_TIMEOUT="$timeout"

    while [[ $elapsed -lt $timeout ]]; do
        export WATCHDOG_ELAPSED="$elapsed"
        export WATCHDOG_INTERVAL="$((++interval_num))"

        # Check condition
        if $condition_cmd; then
            return 0
        fi

        # Call progress callback if provided
        if [[ -n "$on_poll_cmd" ]]; then
            $on_poll_cmd "$elapsed" "$timeout" "$interval_num" || true
        fi

        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    # Timeout reached
    export WATCHDOG_ELAPSED="$elapsed"
    return 124
}

# Run a command with a timeout (portable: works on Linux, macOS, Windows Git Bash)
# Usage: run_with_timeout <timeout_seconds> <command...>
# Returns: 0 on success, 124 on timeout, or command's exit code on failure
run_with_timeout() {
    local timeout_secs="$1"
    shift

    # Run command in background
    "$@" &
    local cmd_pid=$!

    # Monitor in background
    (
        sleep "$timeout_secs"
        kill -0 "$cmd_pid" 2>/dev/null && kill -TERM "$cmd_pid" 2>/dev/null
    ) &
    local watchdog_pid=$!

    # Wait for command
    local exit_code=0
    wait "$cmd_pid" 2>/dev/null || exit_code=$?

    # Clean up watchdog
    kill -0 "$watchdog_pid" 2>/dev/null && kill "$watchdog_pid" 2>/dev/null
    wait "$watchdog_pid" 2>/dev/null || true

    # Check if killed by timeout (SIGTERM = 143)
    if [[ $exit_code -eq 143 ]]; then
        return 124 # Standard timeout exit code
    fi

    return "$exit_code"
}

# =============================================================================
# ARGUMENT PARSING HELPERS
# =============================================================================

# Convert string to uppercase (portable for bash 3.x on macOS)
to_upper() {
    echo "$1" | tr '[:lower:]' '[:upper:]'
}

# Parse --key=value or --key value style arguments
# Usage: parse_args "$@"
# Sets variables like: ARG_KEY=value
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --*=*)
                local key="${1%%=*}"
                local value="${1#*=}"
                key="${key#--}"
                key="${key//-/_}"
                key="ARG_$(to_upper "$key")"
                eval "$key=\"$value\""
                shift
                ;;
            --*)
                local key="${1#--}"
                key="${key//-/_}"
                key="ARG_$(to_upper "$key")"
                if [[ $# -gt 1 ]] && [[ ! "$2" =~ ^-- ]]; then
                    eval "$key=\"$2\""
                    shift 2
                else
                    eval "$key=true"
                    shift
                fi
                ;;
            *)
                shift
                ;;
        esac
    done
}

# =============================================================================
# R2 / AWS HELPERS
# =============================================================================

# r2_count_objects <bucket> <prefix> [<endpoint>]
#
# Emit the number of objects under s3://<bucket>/<prefix>/ to stdout.
# Always exits 0 — empty prefix returns "0" rather than erroring out.
#
# Rationale: `aws s3 ls --recursive` returns exit code 1 when the prefix
# is empty, which under `set -eo pipefail` aborts the calling script
# mid-loop with no diagnostic (this bit scrub-sentinel.sh, assert-r2-sentinel.sh,
# and cleanup-versions.sh Phase 8). `aws s3api list-objects-v2` with
# `length(Contents || `[]`)` returns 0 cleanly for empty prefixes, which
# is what callers actually want.
#
# Requires AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY exported, or callers
# may set them inline from R2_* before invocation.
r2_count_objects() {
    local bucket="${1:?bucket required}"
    local prefix="${2:?prefix required}"
    local endpoint="${3:-${R2_ENDPOINT:-}}"
    local count
    count="$(aws s3api list-objects-v2 \
        --bucket "$bucket" \
        --prefix "$prefix" \
        ${endpoint:+--endpoint-url "$endpoint"} \
        --query 'length(Contents || `[]`)' \
        --output text 2>/dev/null || echo 0)"
    # Defensive: list-objects-v2 emits "None" instead of an integer when
    # the prefix is missing in some edge cases. Normalise to 0.
    if ! [[ "$count" =~ ^[0-9]+$ ]]; then
        count=0
    fi
    printf '%s\n' "$count"
}

# =============================================================================
# SHARED CONSTANTS
# =============================================================================
# Define constants here to avoid duplication across scripts.
# The shellcheck.sh linter will catch if these are redefined elsewhere.

# Maximum number of Gemini review triggers per PR
# This limit prevents excessive API usage on PRs with many iterations.
# Value chosen based on typical PR lifecycle: initial review (1) +
# ~5 rounds of feedback + ~5 additional edge cases = 11 reviews max.
# Exceeding this suggests the PR should be split or closed.
MAX_GEMINI_REVIEWS=11

# =============================================================================
# SUBMODULE GUARDS
# =============================================================================

# require_submodule <marker-path> <label>
#
# Returns 0 when the submodule is present. When it is absent:
#   - in CI  -> hard failure, because a gate that silently skips is worse than
#               no gate at all. check:ci-renet rides on this, and it carries
#               govulncheck (Go CVE scanning), deadcode and golangci-lint --
#               all three would report success while checking nothing.
#   - locally -> warn and return 1, so a fresh clone without --recursive is
#               still workable. Callers do: require_submodule ... || exit 0
require_submodule() {
    local marker="$1" label="$2"

    [[ -e "$marker" ]] && return 0

    if [[ "${CI:-false}" == "true" ]]; then
        log_error "$label is required in CI but missing: $marker"
        log_error "  A gate skipped here would report success while checking nothing."
        log_error "  Fix the workflow checkout (submodules: true, or git submodule update --init)."
        exit 1
    fi

    log_warn "$label not available, skipping (this is a hard failure in CI)"
    return 1
}

# =============================================================================
# INITIALIZATION
# =============================================================================

# Set up common variables
CI_OS="$(detect_os)"
CI_ARCH="$(detect_arch)"
CI_TEMP="$(get_temp_dir)"

# Export for subprocesses
export CI_OS CI_ARCH CI_TEMP
