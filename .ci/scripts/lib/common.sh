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
#
# ASSIGNMENT USES `printf -v`, NOT `eval`, and that is a security fix rather
# than a style preference. `eval` re-parses its argument as a fresh command
# line, so a value containing backticks, $(...) or a `;` is EXECUTED rather
# than stored. Proven, not argued: with value='a"; PROOF=INJECTED; :"' the old
# `eval "$key=\"$value\""` ran the injected assignment, while `printf -v`
# left it untouched and stored the literal bytes.
#
# The vendored copy at .ci/breakpoint/lib/breakpoint-common.sh:83-95 already
# made this change and called itself "the single place the vendored copy is not
# verbatim". That is now false in the right direction: the two agree, and the
# vendored file no longer diverges from its origin on this point.
#
# Behavioural delta, stated so nobody is surprised: `--foo '$HOME'` now stores
# the literal string `$HOME` instead of the expanded path. Nothing in this repo
# wants the expansion; every caller passes a path, a channel enum, or a flag.
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
    # Checked at CALL time, not source time: this is a library, and at source
    # time the caller has not exported anything yet.
    : "${AWS_ACCESS_KEY_ID:?r2_count_objects: AWS_ACCESS_KEY_ID must be exported (map it from CLOUDFLARE_R2_ACCESS_KEY_ID)}"
    local endpoint="${3:-${CLOUDFLARE_R2_ENDPOINT:-}}"
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

# --- Review budget, sized to the diff -----------------------------------------
#
# Operator directive (2026-07-29): a flat cap of 3 is right for a small PR and
# wrong for a consolidation. Big diffs need more passes because each pass can
# only hold so much of them at once.
#
#   up to  10,000 changed lines -> 3 reviews
#   up to  50,000               -> 5 reviews
#   above  50,000               -> 7 reviews
#
# The 50k-100k band lands in the TOP bucket deliberately: a 60,000-line diff is
# not meaningfully easier to review than a 100,000-line one, and the alternative
# is an arbitrary fourth tier nobody asked for.
#
# THIS LIVES IN THE SHARED LIB ON PURPOSE. claude-review-gate.sh decides whether
# to run a review and review-status.sh reports whether the cap is reached; the
# two disagreeing about the cap resurrects exactly the deadlock review-status.sh
# was written to prevent. One table, one function, both callers.
REVIEW_CAP_TIERS='10000:3 50000:5 :7'

# review_cap_for <changed-lines> -> the number of review passes allowed.
review_cap_for() {
    local loc="${1:-0}" tier limit bound
    [[ "$loc" =~ ^[0-9]+$ ]] || loc=0
    for tier in $REVIEW_CAP_TIERS; do
        bound="${tier%%:*}"
        limit="${tier##*:}"
        # An empty bound is the catch-all top tier.
        if [[ -z "$bound" || "$loc" -le "$bound" ]]; then
            echo "$limit"
            return 0
        fi
    done
    echo 3
}

# review_report_count <pr> -> how many review passes have been posted.
#
# This is the numerator in "X/Y reviews used", so an undercount means the cap
# never arrives and every subsequent push pays for another full review. It lived
# in claude-review-gate.sh and review-status.sh as two identical copies, which is
# the drift this file exists to prevent -- it sits beside review_cap_for() so the
# numerator and the denominator cannot disagree.
#
# KEY ON THE HEADER ALONE. Both copies used to AND this with
# (contains "json:review-findings" OR contains "### Review"), and that clause was
# a guess about the report's WORDING that no producer emits: --post-report wraps
# whatever the model's closing text happened to be, which is routinely a short
# wrap-up carrying neither marker. Measured against live PRs, the qualifier
# undercounted every one of them -- #551 counted 0 of 1 (a completed, marked
# review costing $4.66 registering as never having happened), #550 5 of 7, #546
# 3 of 7, #543 1 of 9. The header is different in kind: claude-review-gate.sh
# writes it verbatim, so it is a producer constant rather than a description of
# one, and a rename breaks posting in the same commit instead of silently
# zeroing the counter.
#
# Never re-add a content qualifier here. If a future report must be excluded,
# exclude it on something its producer emits on purpose.
# THE EPIC DIMENSION, added when the review became per-epic.
#
# A PR with five epics posts five reports per round. Counted flat, that spends a
# 3-pass cap on the first round and every later round is refused, so the epics
# reviewed last would never be reviewed at all. The budget therefore has to be
# per (PR, epic), which means the count has to be able to name an epic.
#
# It keys on the PRODUCER CONSTANT, exactly as the header does and for the same
# reason recorded above: claude-review-gate.sh writes "(epic <id>)" into the
# header verbatim, so a rename breaks posting in the same commit rather than
# silently zeroing a counter. It is NOT a content qualifier and must never
# become one.
#
# An empty epic argument counts every report, which is the pre-epic behaviour
# and what a PR with no epics still gets.
review_report_count() {
    local pr="$1" epic="${2:-}" needle="**Claude finished"
    [[ -n "$epic" ]] && needle="**Claude finished (epic ${epic})"
    gh api "repos/${GITHUB_REPOSITORY}/issues/${pr}/comments" --paginate \
        --jq ".[] | select(.user.login | contains(\"github-actions\"))
                  | select(.body | startswith(\"${needle}\"))
                  | .id" 2>/dev/null | wc -l || true
}

# review_epic_ids <branch> -> every epic id the published snapshot declares.
#
# The snapshot is the contract: agent/pr/<branch>.md is in the repo, the worklist
# store is in TMPDIR and unreadable from CI. No snapshot means no epics, which
# the caller treats as the flat, pre-epic review rather than as an error.
review_epic_ids() {
    local branch="${1:-}" snap root
    [[ -z "$branch" ]] && return 0
    # ANCHORED TO THE REPO ROOT, like its two siblings sync-epic-block.sh and
    # epic-context.sh. It used to be a bare relative path, so the answer
    # depended on the caller's CWD: a gate invoked from a subdirectory saw no
    # epics and silently took the flat path, which looks exactly like a PR that
    # declares none. WORKLIST_PUBLISH_ROOT lets a test point this at a fixture
    # without writing into the real tree, the same override --publish honours.
    root="${WORKLIST_PUBLISH_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}"
    snap="$root/agent/pr/${branch//\//-}.md"
    [[ -f "$snap" ]] || return 0
    grep -oE '^`?PR-TASK:[[:space:]]*[0-9a-f]{6,32}`?$' "$snap" |
        grep -oE '[0-9a-f]{6,32}' || true
}

# review_spent_attempt_count <pr> <attempt-prefix> -> passes that produced no report.
#
# review_spend_total <pr> <attempt-prefix> -> what the CAP is actually measured against.
#
# THESE LIVE HERE FOR THE REASON STATED ABOVE, AND IT WAS LEARNED THE HARD WAY.
# Moving review_cap_for() here fixed the DENOMINATOR drift and left the NUMERATOR
# split: claude-review-gate.sh counted `reports_posted + attempts_spent` while
# review-status.sh counted posted reports alone. On PR #553 (2026-08-07) that read
# as 3/3 in the gate and 0/3 in review-status simultaneously. The gate refused to
# review because the cap was reached; review-status could not see the cap as
# reached, so its DEADLOCK GUARD -- written precisely so a capped PR never becomes
# unmergeable -- did not fire, and posted a required FAILURE instead. The PR was
# green, ready and thread-clean, and permanently unmergeable through no fault of
# its author: exactly the outcome that guard exists to prevent.
#
# One numerator, one denominator, one file. Both callers use review_spend_total.
# --- Reportless attempts, and why they are not all the same ------------------
#
# A reportless attempt used to be terminal for its head: it consumed budget and
# its marker told the author to "push a change to earn another pass". For a
# hand-driven PR that is fine. For a fully-green autopilot-driven PR there IS no
# legitimate change to push, so an `error_max_turns` death stalled the loop
# behind a human -- observed live on PR #560.
#
# An INFRA-CLASS failure is not a verdict on the code. It says the harness ran
# out of turns or fell over, which the very next dispatch may not do, so the same
# head gets REVIEW_FREE_REATTEMPTS_PER_HEAD retries before the old rule applies.
# Anything else keeps the old rule exactly: unknown failures are not assumed
# retryable, because "we do not know why it died" is the case where retrying
# forever is most expensive.
#
# The bound matters as much as the retry. Three attempts cost three attempts'
# money, and only one of them is charged -- a deliberate under-charge that keeps
# the loop moving. What stops that being unbounded is the per-head ceiling: once
# a head has spent REVIEW_MAX_ATTEMPTS_PER_HEAD, the gate refuses it entirely and
# only a push (a new head) opens it again.
# Space-separated, and therefore SINGLE-TOKEN ONLY: the membership test word-
# splits this string, so a multi-word class added here would silently never
# match. Every value that reaches it is a result `subtype` from the execution
# file, which is always one token; the fallback "review step did not succeed"
# is deliberately multi-word AND deliberately not listed, since an unclassified
# failure gets no free retries.
REVIEW_ATTEMPT_INFRA_CLASSES="error_max_turns error_during_execution"
REVIEW_FREE_REATTEMPTS_PER_HEAD=2
REVIEW_MAX_ATTEMPTS_PER_HEAD=3

# review_attempt_class_is_infra <class> -> 0 when the class earns free re-attempts.
review_attempt_class_is_infra() {
    local want="$1" known
    for known in $REVIEW_ATTEMPT_INFRA_CLASSES; do
        [[ "$known" == "$want" ]] && return 0
    done
    return 1
}

# review_attempt_states <pr> <attempt-prefix> -> "<sha>\t<attempts>\t<class>" per marker.
#
# ONE marker per head, upserted by claude-review-gate.sh --mark, carrying its own
# attempt count. Parsed with awk over the raw bodies rather than with a jq regex
# because a marker body is multi-line and the count and class are lines within
# it. A LEGACY marker (written before the count existed) has neither line and
# reads as one attempt of unknown class, which is the old behaviour exactly.
review_attempt_states() {
    gh api "repos/${GITHUB_REPOSITORY}/issues/${1}/comments" --paginate \
        --jq ".[] | select(.body | startswith(\"${2}\")) | .body, \"---REVIEW-ATTEMPT-EOF---\"" 2>/dev/null |
        awk '
            function flush() { if (sha != "") print sha "\t" n "\t" cls; sha = ""; n = 1; cls = "" }
            BEGIN { sha = ""; n = 1; cls = "" }
            /^---REVIEW-ATTEMPT-EOF---$/ { flush(); next }
            /claude-review-attempt:/ && sha == "" {
                line = $0
                sub(/.*claude-review-attempt:[[:space:]]*/, "", line)
                sub(/[[:space:]].*$/, "", line)
                sha = line
            }
            /^attempts:[[:space:]]*[0-9]+/ { line = $0; sub(/^attempts:[[:space:]]*/, "", line); n = line + 0 }
            /^class:[[:space:]]*/ {
                line = $0
                sub(/^class:[[:space:]]*/, "", line)
                sub(/[[:space:]]*$/, "", line)
                cls = line
            }
            END { flush() }
        ' || true
}

# review_chargeable_attempts <states> -> how many of them the CAP counts.
#
# Pure, so both callers and the tests can drive it without a network.
review_chargeable_attempts() {
    local total=0 sha n cls charge
    while IFS=$'\t' read -r sha n cls; do
        [[ -n "$sha" ]] || continue
        charge="$n"
        if review_attempt_class_is_infra "$cls"; then
            charge=$((n - REVIEW_FREE_REATTEMPTS_PER_HEAD))
            [[ "$charge" -lt 0 ]] && charge=0
        fi
        total=$((total + charge))
    done <<<"${1:-}"
    echo "$total"
}

# review_head_attempt_state <states> <sha> -> "<attempts> <class>" for that head.
review_head_attempt_state() {
    local want="$2" sha n cls out="0 "
    while IFS=$'\t' read -r sha n cls; do
        [[ "$sha" == "$want" ]] && out="$n $cls"
    done <<<"${1:-}"
    echo "$out"
}

# review_head_is_exhausted <states> <sha> -> 0 when this head may not be retried.
#
# Only the infra path can exhaust: a non-infra reportless attempt was never
# per-head blocked, and making it one here would be a NEW restriction wearing
# the costume of a relaxation.
review_head_is_exhausted() {
    local state n cls
    state="$(review_head_attempt_state "$1" "$2")"
    n="${state%% *}"
    cls="${state#* }"
    review_attempt_class_is_infra "$cls" || return 1
    [[ "${n:-0}" -ge "$REVIEW_MAX_ATTEMPTS_PER_HEAD" ]]
}

# review_spent_attempt_count <pr> <attempt-prefix> -> the CHARGEABLE attempt count.
review_spent_attempt_count() {
    review_chargeable_attempts "$(review_attempt_states "$1" "$2")"
}

# review_spend_total <pr> <attempt-prefix> [posted] [spent]
#
# Optional pre-fetched counts, because claude-review-gate.sh needs the two numbers
# SEPARATELY for its log line and would otherwise pay for four paginated gh calls
# per invocation instead of two. Passing them keeps the single definition of "what
# the cap counts" here -- which is the whole point -- without the round trips.
review_spend_total() {
    local posted="${3:-}" spent="${4:-}"
    [[ -n "$posted" ]] || posted="$(review_report_count "$1")"
    [[ -n "$spent" ]] || spent="$(review_spent_attempt_count "$1" "$2")"
    echo $((${posted//[[:space:]]/} + ${spent//[[:space:]]/}))
}

# pr_diff_loc <pr> -> additions + deletions, or 0 when it cannot be read.
# Failing to 0 puts an unreadable PR in the SMALLEST bucket, which is the
# conservative direction: it spends fewer review passes, never more.
pr_diff_loc() {
    local n
    n=$(gh pr view "$1" --repo "$GITHUB_REPOSITORY" \
        --json additions,deletions --jq '.additions + .deletions' 2>/dev/null) || n=0
    [[ "$n" =~ ^[0-9]+$ ]] || n=0
    echo "$n"
}
