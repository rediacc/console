#!/bin/bash
# Run E2E tests with Playwright
# Usage: run-e2e.sh [options]
#
# Options:
#   --workers       Number of parallel workers (default: 1 in CI, 4 local)
#   --config        Playwright config file (default: playwright.config.ts)
#   --filter        Test name filter pattern (passed to --grep)
#   --grep          Alias for --filter (passed to Playwright --grep)
#   --grep-invert   Exclude tests matching pattern (passed to Playwright --grep-invert)
#   --test          Test file filter(s) passed to Playwright
#   --headed        Run tests with visible browser
#   --debug         Open Playwright Inspector for debugging
#   --ui            Open Playwright UI mode (interactive)
#   --fail-on-skip  Fail (exit 1) if ANY test was skipped. Reads the
#                   TextFileReporter's E2E_SKIPPED sentinel; fails closed if
#                   the sentinel is absent. The zero-skip contract: a job must
#                   select only tests its topology can run, never skip.
#
# Example:
#   .ci/scripts/test/run-e2e.sh
#   .ci/scripts/test/run-e2e.sh --workers 2
#   .ci/scripts/test/run-e2e.sh --config playwright.ceph.config.ts
#   .ci/scripts/test/run-e2e.sh --filter "system-checks"
#   .ci/scripts/test/run-e2e.sh --grep "@ceph"
#   .ci/scripts/test/run-e2e.sh --grep-invert "@ceph"
#   .ci/scripts/test/run-e2e.sh --test tests/01-system-checks.test.ts
#   .ci/scripts/test/run-e2e.sh --debug

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
WORKERS=""
CONFIG=""
FILTER=""
GREP_INVERT=""
TEST_FILES=()
HEADED=false
DEBUG=false
UI=false
FAIL_ON_SKIP=false
CURRENT_ARG=""

for arg in "$@"; do
    case "$arg" in
        --workers)
            CURRENT_ARG="workers"
            ;;
        --config)
            CURRENT_ARG="config"
            ;;
        --filter | --grep)
            CURRENT_ARG="filter"
            ;;
        --grep-invert)
            CURRENT_ARG="grep-invert"
            ;;
        --test)
            CURRENT_ARG="test"
            ;;
        --headed)
            HEADED=true
            ;;
        --debug)
            DEBUG=true
            ;;
        --ui)
            UI=true
            ;;
        --fail-on-skip)
            FAIL_ON_SKIP=true
            ;;
        *)
            case "$CURRENT_ARG" in
                workers)
                    WORKERS="$arg"
                    CURRENT_ARG=""
                    ;;
                config)
                    CONFIG="$arg"
                    CURRENT_ARG=""
                    ;;
                filter)
                    FILTER="$arg"
                    CURRENT_ARG=""
                    ;;
                grep-invert)
                    GREP_INVERT="$arg"
                    CURRENT_ARG=""
                    ;;
                test)
                    TEST_FILES+=("$arg")
                    CURRENT_ARG=""
                    ;;
            esac
            ;;
    esac
done

# Change to repo root
cd "$(get_repo_root)"

E2E_TESTS_DIR="packages/e2e-tests"

# Determine workers
if [[ -z "$WORKERS" ]]; then
    if is_ci; then
        WORKERS=1
    else
        WORKERS=4
    fi
fi

log_step "Running E2E tests (workers: $WORKERS)..."

# Build command
CMD=(npx playwright test)
CMD+=("--workers=$WORKERS")

# Add config if provided
[[ -n "$CONFIG" ]] && CMD+=("--config" "$CONFIG")

# Add filter if provided
[[ -n "$FILTER" ]] && CMD+=("--grep" "$FILTER")

# Add grep-invert if provided
[[ -n "$GREP_INVERT" ]] && CMD+=("--grep-invert" "$GREP_INVERT")

# Add test files if provided
if [[ ${#TEST_FILES[@]} -gt 0 ]]; then
    CMD+=("${TEST_FILES[@]}")
fi

# Fail fast: stop after 3 failures to avoid wasting 60+ minutes on cascading timeouts
# (e.g., when repository_create fails on Fedora, all downstream tests would also timeout)
if is_ci; then
    CMD+=("--max-failures=3")
fi

# Add optional flags
if [[ "$HEADED" == "true" ]]; then
    CMD+=("--headed")
fi
if [[ "$DEBUG" == "true" ]]; then
    CMD+=("--debug")
fi
if [[ "$UI" == "true" ]]; then
    CMD+=("--ui")
fi

# Capture output (still streamed live via tee) so the zero-skip gate can
# inspect the TextFileReporter's E2E_SKIPPED sentinel after the run.
E2E_LOG="$(mktemp)"
set +e
(cd "$E2E_TESTS_DIR" && "${CMD[@]}") 2>&1 | tee "$E2E_LOG"
RC=${PIPESTATUS[0]}
set -e

if [[ "$FAIL_ON_SKIP" == "true" ]]; then
    # Fail closed if the sentinel is absent: the reporter didn't run, so we
    # cannot prove zero skips and must not pass an uninspected run.
    if ! grep -q 'E2E_SKIPPED=' "$E2E_LOG"; then
        log_error "Zero-skip gate ON but no E2E_SKIPPED sentinel found (TextFileReporter missing?). Failing closed."
        rm -f "$E2E_LOG"
        exit 1
    fi
    SKIPPED=$(grep -oE 'E2E_SKIPPED=[0-9]+' "$E2E_LOG" | grep -oE '[0-9]+$' | awk '{s+=$1} END{print s+0}' || true)
    if [[ "${SKIPPED:-0}" -gt 0 ]]; then
        log_error "Zero-skip gate: ${SKIPPED} test(s) were SKIPPED (must be 0). A skipped test is invisible coverage loss."
        log_error "Each E2E job must SELECT only the tests its topology can run (config testMatch/testIgnore), not collect-then-skip."
        echo "----- skipped tests -----"
        grep -E '0\.0s, skipped\)|, skipped\)' "$E2E_LOG" | head -80 || true
        rm -f "$E2E_LOG"
        exit 1
    fi
    log_info "Zero-skip gate: 0 skipped tests"
fi
rm -f "$E2E_LOG"

if [[ $RC -eq 0 ]]; then
    log_info "E2E tests passed"
else
    log_error "E2E tests failed"
    exit 1
fi
