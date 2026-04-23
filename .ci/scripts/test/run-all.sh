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
# shellcheck disable=SC2206
# BLOCKER: intentional glob expansion of user-supplied $PATTERN
TEST_FILES=($PATTERN)
shopt -u nullglob

if ((${#TEST_FILES[@]} == 0)); then
    log_fail "No test files matched pattern: $PATTERN in $GATES_DIR"
fi

pass=0
fail=0
failed_tests=()

for test_file in "${TEST_FILES[@]}"; do
    log_test "$test_file"
    local_log="$(mktemp)"
    if "./$test_file" >"$local_log" 2>&1; then
        pass=$((pass + 1))
        if [[ "$VERBOSE" == "true" ]]; then
            cat "$local_log"
        else
            grep -E '^(\x1b\[0;32m)?PASS:' "$local_log" || true
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
echo "Quality-gate tests: $pass passed, $fail failed"
echo "=============================================="

if ((fail > 0)); then
    echo "Failed tests:"
    printf '  - %s\n' "${failed_tests[@]}"
    exit 1
fi
