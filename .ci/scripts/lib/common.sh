#!/bin/bash
# Common utilities for CI scripts
# Source this file at the beginning of each script:
#   source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
#
# ⚠️  IMPORTANT: When adding/modifying utility functions:
# ⚠️  1. Update this file (common.sh)
# ⚠️  2. Test affected CI scripts (run-unit.sh, run-cli.sh, run-e2e.sh, etc.)
# ⚠️  3. Update the main 'go' script if functions are used there

set -euo pipefail

# =============================================================================
# COLORS AND LOGGING
# =============================================================================

# Colors (disabled if not a terminal or if NO_COLOR is set)
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
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
    echo -e "${GREEN}✓${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $*"
}

log_error() {
    echo -e "${RED}✗${NC} $*" >&2
}

log_step() {
    echo -e "${BLUE}→${NC} $*"
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo -e "${CYAN}[DEBUG]${NC} $*"
    fi
}

# =============================================================================
# ENVIRONMENT DETECTION
# =============================================================================

# Detect operating system
# Returns: linux, macos, or windows
detect_os() {
    case "$(uname -s)" in
        Linux*)     echo "linux" ;;
        Darwin*)    echo "macos" ;;
        CYGWIN*)    echo "windows" ;;
        MINGW*)     echo "windows" ;;
        MSYS*)      echo "windows" ;;
        *)          echo "unknown" ;;
    esac
}

# Detect architecture
# Returns: x64, arm64, or unknown
detect_arch() {
    local arch
    arch="$(uname -m)"
    case "$arch" in
        x86_64|amd64)   echo "x64" ;;
        aarch64|arm64)  echo "arm64" ;;
        *)              echo "unknown" ;;
    esac
}

# Check if running in CI environment
# Returns: 0 if CI, 1 otherwise
is_ci() {
    [[ "${CI:-false}" == "true" ]] || [[ -n "${GITHUB_ACTIONS:-}" ]] || [[ -n "${GITLAB_CI:-}" ]]
}

# Check if running on GitHub Actions
is_github_actions() {
    [[ -n "${GITHUB_ACTIONS:-}" ]]
}

# Check if running on GitLab CI
is_gitlab_ci() {
    [[ -n "${GITLAB_CI:-}" ]]
}

# Get runner OS (for GitHub Actions compatibility)
# Returns: Linux, macOS, or Windows
get_runner_os() {
    if [[ -n "${RUNNER_OS:-}" ]]; then
        echo "$RUNNER_OS"
    else
        case "$(detect_os)" in
            linux)   echo "Linux" ;;
            macos)   echo "macOS" ;;
            windows) echo "Windows" ;;
            *)       echo "Unknown" ;;
        esac
    fi
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
    if ! command -v "$cmd" &> /dev/null; then
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

# Get the .ci directory
get_ci_dir() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    # Go up from .ci/scripts/lib to .ci (2 levels)
    cd "$script_dir/../.." && pwd
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
# INITIALIZATION
# =============================================================================

# Set up common variables
CI_OS="$(detect_os)"
CI_ARCH="$(detect_arch)"
CI_TEMP="$(get_temp_dir)"

# Export for subprocesses
export CI_OS CI_ARCH CI_TEMP
