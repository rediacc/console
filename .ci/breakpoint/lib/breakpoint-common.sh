#!/bin/bash
# Minimal shared library for breakpoint. VENDORED ON PURPOSE.
#
# WHY THIS IS A COPY AND NOT `source ../../scripts/lib/common.sh`
# ----------------------------------------------------------------
# breakpoint is copied wholesale into other repositories and its integrity is
# proven by MANIFEST.sha256. If it sourced console's common.sh, the manifest
# would have to cover common.sh too -- and then an unrelated change there (a new
# R2 helper, say) turns every downstream repo's drift gate red. A gate that
# reddens on unrelated churn gets suppressed, and a suppressed gate is the bug.
#
# Two concrete landmines make this more than a style preference:
#   - common.sh's get_repo_root() hardcodes "3 levels up from .ci/scripts/lib".
#     Sourced from .ci/breakpoint/lib/ that is 2 levels, so it would silently
#     return the PARENT of the repo. A wrong path, not an error.
#   - common.sh's require_submodule() hard-exits 1 in CI with a console-specific
#     diagnostic, which is nonsense in a repo that has no submodules.
#
# So: the functions below are copied VERBATIM from
# .ci/scripts/lib/common.sh so that a reader of both sees identical semantics.
# Do not "improve" them here -- a silent semantic fork is worse than a quirk.
# Functions with no console equivalent are grouped at the bottom under NEW.
#
# DELIBERATELY NOT COPIED: get_repo_root, r2_count_objects, require_submodule,
# sed_in_place, retry_with_backoff, run_with_timeout, wait_for, detect_os, is_ci.
#
# BANNED CONSTRUCTS (.ci/scripts/security/check-commands.sh globs `find .ci`):
# no seq(1), no timeout(1), no mapfile. Counting loops are `for ((...))` and
# waits are while+sleep+elapsed.

set -euo pipefail

# =============================================================================
# COLORS AND LOGGING  (verbatim from common.sh:17-55)
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

# Every logger writes to STDERR. This is load-bearing, not incidental: several
# breakpoint scripts put their real result (a URL, a mode, a descriptor) on
# stdout, and a logger that leaked into stdout would corrupt that contract.
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
# ARGUMENT PARSING  (verbatim from common.sh:270-307)
# =============================================================================
#
# ONE DELIBERATE DIVERGENCE FROM common.sh: assignment uses `printf -v`, NOT
# `eval "$key=\"$2\""`. This is the single place the vendored copy is not
# verbatim, and it is a security fix, not a style preference.
#
# `eval` re-parses its argument as a fresh command line, so a value containing
# backticks, $(...) or a `;` is EXECUTED rather than stored. That is a second
# injection layer underneath the workflow, and this feature is what first routes
# a free-text, operator-supplied value (`access-emails`) through parse_args --
# every earlier caller in this codepath passed a choice-enum. `printf -v`
# assigns the bytes and interprets nothing.
#
# Behavioural delta, stated so nobody is surprised: `--foo '$HOME'` now stores
# the literal string `$HOME` instead of the expanded path. Nothing here wants
# that expansion, and silently expanding a caller's data was never intended.
# Console's own common.sh still uses eval; see the PR discussion.
#
# THREE QUIRKS, PRESERVED DELIBERATELY AND PINNED BY test-breakpoint-mode-selection.sh:
#   1. Repeated flags DO NOT accumulate. `--mode a --mode b` yields ARG_MODE=b,
#      because each eval overwrites the same variable name. No script in
#      breakpoint may rely on a repeated flag.
#   2. A flag with no following value becomes the literal STRING "true", not a
#      shell boolean. Test it as [[ "$X" == "true" ]].
#   3. A value beginning with -- is NOT consumed; the flag silently becomes
#      "true" instead. So `--label --foo` sets ARG_LABEL=true.

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
                printf -v "$key" '%s' "$value"
                shift
                ;;
            --*)
                local key="${1#--}"
                key="${key//-/_}"
                key="ARG_$(to_upper "$key")"
                if [[ $# -gt 1 ]] && [[ ! "$2" =~ ^-- ]]; then
                    printf -v "$key" '%s' "$2"
                    shift 2
                else
                    printf -v "$key" '%s' "true"
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
# ENVIRONMENT  (verbatim from common.sh:96-147)
# =============================================================================

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

# =============================================================================
# NEW -- no console equivalent, or console's shape is wrong for this feature
# =============================================================================

# Absolute path of the .ci/breakpoint folder, resolved from the CALLING script.
# This REPLACES common.sh's get_repo_root(), which breakpoint must never have:
# breakpoint knows where it is, and deliberately does not know where the repo
# root is, because that is the assumption that would not survive a copy.
bp_root() {
    local script_dir="${1:-$SCRIPT_DIR}"
    (cd "$script_dir/.." && pwd)
}

# Runtime state directory. ALWAYS outside the folder: the folder is read-only at
# runtime, which is what keeps it copyable.
bp_state_dir() {
    echo "$(get_temp_dir)/breakpoint"
}

# Load breakpoint.conf if present. Absent conf is NOT an error -- the defaults
# below every consumer are the zero-config path (quick mode, no email).
bp_load_conf() {
    local conf
    conf="$(bp_root "${1:-$SCRIPT_DIR}")/breakpoint.conf"
    if [[ -f "$conf" ]]; then
        # shellcheck source=/dev/null
        source "$conf"
        log_debug "loaded $conf"
    else
        log_debug "no breakpoint.conf at $conf, using defaults"
    fi
}

# Wait for a regex to appear in a log file.
#
# Console's wait_for() is the wrong shape here: it runs its probe under
# `&>/dev/null` and returns 1 silently, so a failure tells you nothing. For a
# DEBUG feature whose entire job is explaining why something did not come up,
# swallowing the diagnostic is the opposite of useful -- so this one tails the
# file on failure.
#
# Usage: bp_wait_for_log_line <file> <regex> <deadline_seconds> [interval]
# Stdout: the FIRST match (the whole matched token), on success only.
bp_wait_for_log_line() {
    local file="$1" regex="$2" deadline="$3" interval="${4:-2}"
    local elapsed=0 match=""

    while [[ $elapsed -lt $deadline ]]; do
        if [[ -f "$file" ]]; then
            match="$(grep -oE "$regex" "$file" 2>/dev/null | head -1 || true)"
            if [[ -n "$match" ]]; then
                echo "$match"
                return 0
            fi
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    log_error "timed out after ${deadline}s waiting for /$regex/ in $file"
    if [[ -f "$file" ]]; then
        log_error "--- last 30 lines of $file ---"
        tail -30 "$file" >&2 || true
        log_error "--- end ---"
    else
        log_error "(the file was never created)"
    fi
    return 1
}

# Wait for a TCP port to accept connections.
# Usage: bp_wait_for_port <port> <deadline_seconds> [interval]
bp_wait_for_port() {
    local port="$1" deadline="$2" interval="${3:-1}"
    local elapsed=0

    while [[ $elapsed -lt $deadline ]]; do
        # bash's /dev/tcp needs no nc(1), which is not guaranteed on every image.
        if (echo >"/dev/tcp/127.0.0.1/$port") 2>/dev/null; then
            return 0
        fi
        sleep "$interval"
        elapsed=$((elapsed + interval))
    done

    log_error "timed out after ${deadline}s waiting for port $port"
    return 1
}

# -----------------------------------------------------------------------------
# SESSION STATE
# -----------------------------------------------------------------------------
# A flat, sourceable KEY=value file rather than JSON, for one concrete reason:
# ubuntu-slim does not ship jq (both slim jobs in ci.yml and
# backfill-release-sentinel.yml run `command -v jq || apt-get install -y jq`
# first), and the per-CI-round lifecycle leg runs on slim in QUICK mode. Quick
# mode must therefore need no JSON parser at all. Named mode does parse
# Cloudflare API responses with jq, but named mode only ever runs on
# ubuntu-latest, where jq is present.
#
# Written INCREMENTALLY: every remote object id lands here the instant its API
# call returns, and the file is created with the identity fields BEFORE anything
# is created remotely. It records INTENT, not just outcome -- so a session that
# dies between "tunnel created" and "tunnel id recorded" still leaves a file
# naming what it was trying to build.
#
# The file is a CONVENIENCE, never a dependency: it lives on a runner that can
# vanish. The durable channel is the tunnel NAME (see derive-descriptor.sh).

bp_state_file() {
    echo "$(bp_state_dir)/session.env"
}

# bp_state_set <key> <value>
bp_state_set() {
    local key="$1" value="$2" file
    file="$(bp_state_file)"
    mkdir -p "$(dirname "$file")"
    touch "$file"
    # Rewrite in place rather than appending, so re-setting a key does not leave
    # two lines whose later `source` order decides the winner.
    grep -v "^${key}=" "$file" >"${file}.tmp" 2>/dev/null || true
    printf '%s=%q\n' "$key" "$value" >>"${file}.tmp"
    mv "${file}.tmp" "$file"
}

# bp_regex_escape <string> -- escape ERE metacharacters in a literal
#
# For building a regex whose needle is DATA (an email address, a path). Without
# it, the `.` in "bob@example.com" matches any character, so the address would
# also be satisfied by "bobXexample.com" -- which matters when the regex is the
# thing deciding whether somebody gets a shell.
bp_regex_escape() {
    printf '%s' "$1" | sed -E 's/[][(){}.*+?^$|\\]/\\&/g'
}

# bp_state_get <key>  -- empty string when unset or when there is no state file
bp_state_get() {
    local key="$1" file
    file="$(bp_state_file)"
    [[ -f "$file" ]] || return 0
    # shellcheck source=/dev/null
    (source "$file" 2>/dev/null && echo "${!key:-}")
}

# Record a PID we started, so teardown kills ONLY what we own.
#
# The deleted tmate action got this wrong twice, and both bugs are the reason
# this function exists: stop-session.sh ran `pkill -f "tmate.*new-session"`
# (which kills a CONCURRENT job's session) and `rm -f /tmp/tmate-*.log` (which
# globs other jobs' files). Never pattern-kill; kill recorded PIDs.
bp_record_pid() {
    local name="$1" pid="$2" dir
    dir="$(bp_state_dir)/pids"
    mkdir -p "$dir"
    echo "$pid" >"$dir/$name.pid"
    log_debug "recorded $name pid=$pid"
}

# Kill a recorded PID and remove its pidfile. Idempotent and never fails:
# a stale pidfile (process already gone) is a normal, expected state, because
# teardown runs both in-job and again from the sweeper.
bp_kill_recorded() {
    local name="$1" dir pidfile pid
    dir="$(bp_state_dir)/pids"
    pidfile="$dir/$name.pid"
    [[ -f "$pidfile" ]] || return 0

    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        # Give it a moment, then insist.
        local waited=0
        while [[ $waited -lt 5 ]] && kill -0 "$pid" 2>/dev/null; do
            sleep 1
            waited=$((waited + 1))
        done
        kill -9 "$pid" 2>/dev/null || true
        log_info "stopped $name (pid $pid)"
    else
        log_debug "$name pid ${pid:-<empty>} already gone"
    fi
    rm -f "$pidfile"
}

# Emit a GitHub Actions workflow command, but only when running under Actions.
# Guarded so every script stays runnable on a laptop.
bp_gha_warning() {
    if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
        echo "::warning::$*"
    fi
    log_warn "$*"
}

bp_gha_mask() {
    if [[ -n "${GITHUB_ACTIONS:-}" ]] && [[ -n "${1:-}" ]]; then
        echo "::add-mask::$1"
    fi
}

# Append key=value to $GITHUB_OUTPUT when present. No-op locally.
bp_set_output() {
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        echo "$1=$2" >>"$GITHUB_OUTPUT"
    fi
}

# Export CI_TEMP the way console's common.sh does, so the two behave alike.
CI_TEMP="$(get_temp_dir)"
export CI_TEMP
