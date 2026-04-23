#!/bin/bash
# Shared test assertion helpers for .ci/scripts/test/test-*.sh scripts.
#
# Usage:
#   source "$(dirname "$0")/lib/test-helpers.sh"
#   with_temp_dir test_my_case
#   log_pass "my case"
#
# Convention: every test function is named test_* and is called at the bottom
# of the test file. On pass, call log_pass "<name>". On fail, call log_fail
# which exits 1 immediately (tests are designed to halt on first failure for
# clear diagnostic output).

# Guard against double-sourcing.
[[ -n "${__TEST_HELPERS_SH_SOURCED:-}" ]] && return 0
readonly __TEST_HELPERS_SH_SOURCED=1

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_pass() { echo -e "${GREEN}PASS:${NC} $*"; }
log_fail() {
    echo -e "${RED}FAIL:${NC} $*" >&2
    exit 1
}
log_test() { echo -e "${YELLOW}TEST:${NC} $*"; }

# assert_eq <actual> <expected> [<message>]
assert_eq() {
    local actual="$1" expected="$2" msg="${3:-}"
    if [[ "$actual" != "$expected" ]]; then
        log_fail "${msg:-values differ}: expected '$expected', got '$actual'"
    fi
}

# assert_contains <haystack> <needle> [<message>]
assert_contains() {
    local haystack="$1" needle="$2" msg="${3:-}"
    if [[ "$haystack" != *"$needle"* ]]; then
        log_fail "${msg:-substring missing}: '$needle' not in \"$haystack\""
    fi
}

# assert_not_contains <haystack> <needle> [<message>]
assert_not_contains() {
    local haystack="$1" needle="$2" msg="${3:-}"
    if [[ "$haystack" == *"$needle"* ]]; then
        log_fail "${msg:-unexpected substring present}: '$needle' in \"$haystack\""
    fi
}

# assert_exit_code <expected> <actual> [<message>]
assert_exit_code() {
    local expected="$1" actual="$2" msg="${3:-}"
    if [[ "$actual" -ne "$expected" ]]; then
        log_fail "${msg:-wrong exit code}: expected $expected, got $actual"
    fi
}

# with_temp_dir <fn> [args...]
#
# Creates a temp dir, sets TEMP to its path, invokes <fn> (which may reference
# TEMP), and cleans up on exit. Nests safely (each call makes a fresh dir).
with_temp_dir() {
    local fn="$1"
    shift
    local TEMP
    TEMP="$(mktemp -d)"
    # shellcheck disable=SC2064
    # BLOCKER: expanding TEMP now is intentional — we want the specific path
    # captured in the trap, not the variable's later value
    trap "rm -rf '$TEMP'" EXIT
    "$fn" "$TEMP" "$@"
    rm -rf "$TEMP"
    trap - EXIT
}

# with_fake_gh <gh_output_file> <fn> [args...]
#
# Shims `gh` on PATH with a fake binary that cats <gh_output_file>. Use to
# isolate tests from GitHub API. <gh_output_file> should contain the exact
# stdout the real `gh api` call would produce.
with_fake_gh() {
    local output_file="$1"
    local fn="$2"
    shift 2
    local BIN
    BIN="$(mktemp -d)"
    cat >"$BIN/gh" <<FAKE
#!/bin/bash
cat "$output_file"
FAKE
    chmod +x "$BIN/gh"
    local OLD_PATH="$PATH"
    export PATH="$BIN:$PATH"
    "$fn" "$@"
    export PATH="$OLD_PATH"
    rm -rf "$BIN"
}
