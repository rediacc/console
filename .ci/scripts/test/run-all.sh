#!/bin/bash
# Cross-cutting test runner for every quality-gate test.
#
# Invoked via `npm run test:quality-gates`. Runs every
# .ci/scripts/test/gates/test-*.sh (the new BLOCKER / advisory / age-check
# gate tests) and reports pass/fail count. Exits non-zero on any failure.
#
# NOTE: this runner only executes gate tests. The other bash tests under
# .ci/scripts/test/ (install script, linux packages, etc.) are run by
# separate CI jobs with different timing / infrastructure needs.
#
# Usage:
#   ./run-all.sh                      # run all gate tests
#   ./run-all.sh --verbose            # show stdout of each test
#   ./run-all.sh 'test-blocker*.sh'   # run only matching tests

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATES_DIR="$SCRIPT_DIR/gates"
# shellcheck source=lib/test-helpers.sh
# BLOCKER: shared test-runner colour / status helpers
source "$SCRIPT_DIR/lib/test-helpers.sh"

VERBOSE=false
PATTERN="test-*.sh"

while (($# > 0)); do
    case "$1" in
        --verbose | -v)
            VERBOSE=true
            shift
            ;;
        *)
            PATTERN="$1"
            shift
            ;;
    esac
done

cd "$GATES_DIR"
shopt -s nullglob
# BLOCKER: intentional glob expansion of user-supplied $PATTERN into the TEST_FILES array; quoting would prevent shopt nullglob from filtering non-matches
# shellcheck disable=SC2206
# BLOCKER: intentional glob expansion of user-supplied $PATTERN
TEST_FILES=($PATTERN)
shopt -u nullglob

if ((${#TEST_FILES[@]} == 0)); then
    log_fail "No test files matched pattern: $PATTERN in $GATES_DIR"
fi

pass=0
fail=0
assertions_total=0
failed_tests=()

# log_pass() colours its output, so a PASS line starts with a real ESC byte.
# The previous pattern spelled that byte '\x1b', which POSIX ERE does not
# interpret as an escape -- GNU grep read it as the literal text "x1b", so this
# summary matched NOTHING and every colour-emitting gate test contributed zero
# visible evidence to the non-verbose run. The counter was still right, which is
# why it went unnoticed: "20 passed" with no assertions listed looks identical to
# 20 tests that assert nothing. $'...' puts the actual byte in the pattern.
PASS_RE=$'^(\033\\[0;32m)?PASS:'

for test_file in "${TEST_FILES[@]}"; do
    log_test "$test_file"
    local_log="$(mktemp)"
    if "./$test_file" >"$local_log" 2>&1; then
        # Count the assertions the test actually made. A test that exits 0
        # without emitting a single PASS is vacuous -- it asserted nothing and
        # must not be reported as a passing gate.
        assertions="$(grep -acE "$PASS_RE" "$local_log" || true)"
        if ((assertions == 0)); then
            fail=$((fail + 1))
            failed_tests+=("$test_file (exited 0 but made no assertions)")
            cat "$local_log"
            # Not log_fail: that exits, and the remaining tests still need to run.
            echo -e "${RED}FAIL:${NC} $test_file exited 0 without a single PASS: line" >&2
        else
            pass=$((pass + 1))
            assertions_total=$((assertions_total + assertions))
            if [[ "$VERBOSE" == "true" ]]; then
                cat "$local_log"
            else
                grep -aE "$PASS_RE" "$local_log" || true
            fi
        fi
    else
        fail=$((fail + 1))
        failed_tests+=("$test_file")
        cat "$local_log"
    fi
    rm -f "$local_log"
    echo ""
done

echo "=============================================="
echo "Quality-gate tests: $pass passed, $fail failed ($assertions_total assertions)"
echo "=============================================="

if ((fail > 0)); then
    echo "Failed tests:"
    printf '  - %s\n' "${failed_tests[@]}"
    exit 1
fi
