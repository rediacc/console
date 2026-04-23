#!/bin/bash
# Cross-cutting test runner for every quality-gate test in the repo.
#
# Invoked via `npm run test:quality-gates`. Runs every .ci/scripts/test/test-*.sh
# and reports pass/fail count. Exits non-zero on any failure.
#
# The underlying tests are self-contained bash scripts following the pattern
# of test-write-once-guard.sh — each one sets set -euo pipefail, sources
# lib/test-helpers.sh, and calls its own test_* functions.
#
# Usage:
#   ./run-all.sh                    # run all tests
#   ./run-all.sh --verbose          # show stdout of each test
#   ./run-all.sh test-blocker*.sh   # run only matching tests

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

cd "$SCRIPT_DIR"
shopt -s nullglob
# shellcheck disable=SC2206  # intentional glob expansion of $PATTERN
TEST_FILES=($PATTERN)
shopt -u nullglob

if ((${#TEST_FILES[@]} == 0)); then
    log_fail "No test files matched pattern: $PATTERN"
fi

pass=0
fail=0
failed_tests=()

for test_file in "${TEST_FILES[@]}"; do
    # Skip the runner itself
    [[ "$test_file" == "run-all.sh" ]] && continue
    # Skip helper-only files under lib/
    [[ "$test_file" == lib/* ]] && continue
    log_test "$test_file"
    local_log="$(mktemp)"
    if "./$test_file" >"$local_log" 2>&1; then
        pass=$((pass + 1))
        if [[ "$VERBOSE" == "true" ]]; then
            cat "$local_log"
        else
            # Show just the PASS lines
            grep -E '^(\[0;32m)?PASS:' "$local_log" || true
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
