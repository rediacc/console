#!/bin/bash
# Run bridge tests with Playwright
# Usage: run-bridge.sh [options]
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
#
# Example:
#   .ci/scripts/test/run-bridge.sh
#   .ci/scripts/test/run-bridge.sh --workers 2
#   .ci/scripts/test/run-bridge.sh --config playwright.ceph.config.ts
#   .ci/scripts/test/run-bridge.sh --filter "system-checks"
#   .ci/scripts/test/run-bridge.sh --grep "@ceph"
#   .ci/scripts/test/run-bridge.sh --grep-invert "@ceph"
#   .ci/scripts/test/run-bridge.sh --test tests/01-system-checks.test.ts
#   .ci/scripts/test/run-bridge.sh --debug

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

BRIDGE_TESTS_DIR="packages/bridge-tests"

# Determine workers
if [[ -z "$WORKERS" ]]; then
    if is_ci; then
        WORKERS=1
    else
        WORKERS=4
    fi
fi

log_step "Running bridge tests (workers: $WORKERS)..."

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

if (cd "$BRIDGE_TESTS_DIR" && "${CMD[@]}"); then
    log_info "Bridge tests passed"
else
    log_error "Bridge tests failed"
    exit 1
fi
