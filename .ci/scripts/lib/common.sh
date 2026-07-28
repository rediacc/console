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
# Emit the number of objects under s3://<bucket>/<prefix>/ to stdout, and
# return 0. An UNREACHABLE bucket returns 1 with a diagnostic and emits
# nothing.
#
# Rationale: `aws s3 ls --recursive` returns exit code 1 when the prefix
# is empty, which under `set -eo pipefail` aborts the calling script
# mid-loop with no diagnostic (this bit scrub-sentinel.sh, assert-r2-sentinel.sh,
# and cleanup-versions.sh Phase 8). `aws s3api list-objects-v2` with
# `length(Contents || `[]`)` returns 0 cleanly for empty prefixes, which
# is what callers actually want.
#
# WHY THE FAILURE PATH IS SEPARATE FROM THE EMPTY PATH. This used to end in
# `|| echo 0`, which made an expired credential, a DNS failure and a genuinely
# empty prefix produce the same "0". Callers use this count to decide whether a
# release prefix holds bytes, so a swallowed failure reads as "the bytes are
# gone" and the caller acts on it. An empty prefix is data; an unreachable
# bucket is an absence of data, and the two must not share a return value.
#
# Requires AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY exported, or callers
# may set them inline from R2_* before invocation.
r2_count_objects() {
    local bucket="${1:?bucket required}"
    local prefix="${2:?prefix required}"
    local endpoint="${3:-${R2_ENDPOINT:-}}"
    local count err rc=0
    err="$(mktemp)"
    count="$(aws s3api list-objects-v2 \
        --bucket "$bucket" \
        --prefix "$prefix" \
        ${endpoint:+--endpoint-url "$endpoint"} \
        --query 'length(Contents || `[]`)' \
        --output text 2>"$err")" || rc=$?
    if ((rc != 0)); then
        log_error "r2_count_objects: list-objects-v2 failed for s3://${bucket}/${prefix} (exit $rc)"
        [[ -s "$err" ]] && sed 's/^/    /' "$err" >&2
        rm -f "$err"
        return 1
    fi
    rm -f "$err"
    # list-objects-v2 emits "None" instead of an integer when the prefix is
    # missing. That is a genuine "no objects", unlike the failure above.
    if [[ "$count" == "None" ]]; then
        count=0
    fi
    if ! [[ "$count" =~ ^[0-9]+$ ]]; then
        log_error "r2_count_objects: unparseable count '$count' for s3://${bucket}/${prefix}"
        return 1
    fi
    printf '%s\n' "$count"
}

# =============================================================================
# GITHUB CLI HELPERS
# =============================================================================

# _gh_probe <require-json:true|false> <what> -- <gh args...>
#
# Run `gh <args>`, echo its stdout, and return non-zero when the call did not
# actually succeed. Retries twice on a transient failure.
#
# WHY THIS EXISTS. Nine call sites across the review, attribution and
# submodule-branch gates were spelled `X=$(gh api ... 2>/dev/null || echo "[]")`.
# A rate limit, an expired token or a network blip produced the same value as
# "this PR has no review comments", so the gate printed its success message and
# exited 0. Those are merge-blocking gates: a swallowed failure there is a
# silent green on the check that is supposed to stop the merge.
#
# `gh api --jq` emits plain text rather than JSON, and an empty result can be
# legitimate (a PR with an empty body), so JSON validation is opt-in. The exit
# status is always checked, because that is the part that was being thrown away.
_gh_probe() {
    local require_json="$1" what="$2"
    shift 2
    [[ "${1:-}" == "--" ]] && shift
    local err out attempt=1 rc=0
    err="$(mktemp)"
    while ((attempt <= 3)); do
        rc=0
        out="$(gh "$@" 2>"$err")" || rc=$?
        if ((rc == 0)); then
            if [[ "$require_json" != "true" ]]; then
                rm -f "$err"
                printf '%s' "$out"
                return 0
            fi
            # `gh api graphql` can exit 0 while returning a truncated or
            # malformed body, so an exit-code check alone misses it.
            if [[ -n "$out" ]] && jq -e . >/dev/null 2>&1 <<<"$out"; then
                rm -f "$err"
                printf '%s' "$out"
                return 0
            fi
        fi
        if ((attempt < 3)); then
            log_warn "$what: gh call failed or returned unusable output (attempt $attempt/3), retrying..."
            sleep $((attempt * 3))
        fi
        attempt=$((attempt + 1))
    done
    log_error "$what: gh failed after 3 attempts (last exit $rc)."
    [[ -s "$err" ]] && sed 's/^/    /' "$err" >&2
    rm -f "$err"
    return 1
}

# gh_retry <what> -- <gh args...>   exit status checked; output may be anything
gh_retry() { _gh_probe false "$@"; }

# gh_json <what> -- <gh args...>    exit status checked AND body must parse as JSON
gh_json() { _gh_probe true "$@"; }

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
