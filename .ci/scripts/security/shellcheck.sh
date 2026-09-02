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
# The gate acquires its own tool AT the pin; see the block in main().
# shellcheck source=/dev/null
. "$ROOT_DIR/.ci/scripts/lib/toolchain.sh"
toolchain_load || exit 1

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

    # ACQUIRE AT THE PIN, not merely "present". A bare `command -v` accepts any
    # version, so a stale binary on a developer's PATH silently decided this
    # gate's verdict -- measured 2026-08-25: host shellcheck 0.9.0 against CI's
    # 0.10.0, and two unpinned shfmt installs that agreed only by luck.
    if ! SHELLCHECK_BIN="$(toolchain_acquire shellcheck)"; then
        log_error "shellcheck is unusable for this gate"
        log_info "Every lane's toolchain: .ci/scripts/lib/toolchain.sh --report"
        log_info "Or run the gate where it is pinned: ./run.sh devbox exec -- .ci/scripts/security/shellcheck.sh"
        exit 1
    fi

    "$SHELLCHECK_BIN" --version

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
    # ALSO the untracked ones. `git ls-files` alone made this gate blind to any
    # .sh a session had written but not yet committed, which is exactly when it
    # is most useful: three new gate tests were invisible here until commit. Same
    # blind spot the lint gate had for untracked .py. --others --exclude-standard
    # adds untracked files while still honouring .gitignore, so node_modules and
    # build output stay out.
    log_info "Checking every tracked and untracked *.sh file"
    SH_FILES="$(
        git ls-files '*.sh'
        git ls-files --others --exclude-standard '*.sh'
    )"
    SH_FILES="$(printf '%s\n' "$SH_FILES" | awk 'NF' | sort -u)"
    # A tracked file deleted in the working tree (rm without git rm) stays in
    # `git ls-files` and makes shellcheck die on "openBinaryFile: does not exist",
    # which reads as a lint finding. Drop those and say so (2026-09-02).
    missing="$(printf '%s\n' "$SH_FILES" | while IFS= read -r f; do [ -e "$f" ] || printf '%s\n' "$f"; done)"
    if [ -n "$missing" ]; then
        log_info "skipping $(printf '%s\n' "$missing" | awk 'NF' | wc -l) tracked file(s) deleted in the working tree: $(printf '%s' "$missing" | tr '\n' ' ')"
        SH_FILES="$(printf '%s\n' "$SH_FILES" | while IFS= read -r f; do [ -e "$f" ] && printf '%s\n' "$f"; done)"
    fi

    # A gate that lints nothing exits 0 and looks identical to a gate that lints
    # everything. Refuse the empty list rather than pass it.
    if [ -z "$SH_FILES" ]; then
        log_error "no tracked *.sh files found: the enumerator is broken, not the tree clean"
        exit 1
    fi
    log_info "$(printf '%s\n' "$SH_FILES" | wc -l | tr -d ' ') file(s)"

    # BLOCKER: SHELLCHECK_OPTS is a space-separated set of CLI flags, and SH_FILES is a newline-separated file list; word-splitting is intentional for both
    # shellcheck disable=SC2086
    # BATCHED -- but batching is NOT what fixed the OOM, and saying so matters
    # because the wrong lesson here is expensive.
    #
    # Measured 2026-08-25 with the pinned 0.10.0, peak RSS in isolated processes:
    #     451 files, dataflow on ............ 3074 MB   (OOM-killed on a 6.6 GB box)
    #      40 files, dataflow on .............. 98 MB
    #   ONE file (test-worklist-v5.sh, 11,955 lines) .. 2714 MB
    #
    # Almost the entire cost is ONE FILE, so a batch of 40 that happens to
    # contain it still pays 2714 MB and still dies. The actual fix is the
    # `# shellcheck extended-analysis=false` directive in that file, which takes
    # it to 199 MB. Batching only caps the much smaller many-files component
    # (~360 MB -> ~98 MB), which is worth keeping as a floor for the next large
    # file nobody has noticed yet.
    #
    # -P1 deliberately: npm run ci already parallelises across gates, and a
    # second layer of parallelism is how the box ran out of memory to begin with.
    if ! printf '%s\n' "$SH_FILES" | xargs -r -n 40 -P1 "$SHELLCHECK_BIN" $SHELLCHECK_OPTS; then
        log_error "shellcheck reported findings"
        exit 1
    fi

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
