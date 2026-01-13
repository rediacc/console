#!/bin/bash
# Run E2E tests with Playwright
# Usage: run-e2e.sh --projects <project1> [project2] ... [--workers <n>]
#
# Options:
#   --projects  Space-separated list of Playwright projects to run
#   --workers   Number of parallel workers (default: auto)
#
# Example:
#   .ci/scripts/test/run-e2e.sh --projects chromium firefox webkit
#   .ci/scripts/test/run-e2e.sh --projects resolution-1920x1080 resolution-1366x768

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
PROJECTS=()
WORKERS=""
CURRENT_ARG=""

for arg in "$@"; do
    case "$arg" in
        --projects)
            CURRENT_ARG="projects"
            ;;
        --workers)
            CURRENT_ARG="workers"
            ;;
        *)
            case "$CURRENT_ARG" in
                projects)
                    PROJECTS+=("$arg")
                    ;;
                workers)
                    WORKERS="$arg"
                    CURRENT_ARG=""
                    ;;
            esac
            ;;
    esac
done

# Validate required arguments
if [[ ${#PROJECTS[@]} -eq 0 ]]; then
    log_error "Usage: run-e2e.sh --projects <project1> [project2] ... [--workers <n>]"
    exit 1
fi

# Change to repo root
cd "$(get_repo_root)"

E2E_DIR="packages/e2e"
FAILED=false

log_step "Running E2E tests for projects: ${PROJECTS[*]}"

for project in "${PROJECTS[@]}"; do
    log_step "Running E2E tests: $project"

    CMD="npx playwright test --project=$project"
    if [[ -n "$WORKERS" ]]; then
        CMD="$CMD --workers=$WORKERS"
    fi

    if (cd "$E2E_DIR" && $CMD); then
        log_info "E2E tests passed: $project"
    else
        log_error "E2E tests failed: $project"
        FAILED=true
    fi
done

if [[ "$FAILED" == "true" ]]; then
    log_error "Some E2E tests failed"
    exit 1
fi

log_info "All E2E tests passed"
