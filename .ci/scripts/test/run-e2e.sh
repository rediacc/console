#!/bin/bash
# Run E2E tests with Playwright
# Usage: run-e2e.sh --projects <project1> [project2] ... [options]
#
# Options:
#   --projects  Space-separated list of Playwright projects to run
#   --workers   Number of parallel workers (default: auto)
#   --test      Test filter(s) passed to Playwright (file path, :line, or --grep)
#   --headed    Run tests with visible browser
#   --debug     Open Playwright Inspector for debugging
#   --ui        Open Playwright UI mode (interactive)
#   --slowmo    Slow down actions by N milliseconds
#
# Example:
#   .ci/scripts/test/run-e2e.sh --projects chromium firefox webkit
#   .ci/scripts/test/run-e2e.sh --projects chromium --headed
#   .ci/scripts/test/run-e2e.sh --projects chromium --debug
#   .ci/scripts/test/run-e2e.sh --projects chromium --ui
#   .ci/scripts/test/run-e2e.sh --projects chromium --headed --slowmo 500
#   .ci/scripts/test/run-e2e.sh --projects chromium --test user/005-user-permission.test.ts:24

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
PROJECTS=()
WORKERS=""
TEST_FILTERS=()
HEADED=false
DEBUG=false
UI=false
SLOWMO=""
CURRENT_ARG=""

for arg in "$@"; do
    case "$arg" in
        --projects)
            CURRENT_ARG="projects"
            ;;
        --workers)
            CURRENT_ARG="workers"
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
        --slowmo)
            CURRENT_ARG="slowmo"
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
                test)
                    TEST_FILTERS+=("$arg")
                    CURRENT_ARG=""
                    ;;
                slowmo)
                    SLOWMO="$arg"
                    CURRENT_ARG=""
                    ;;
            esac
            ;;
    esac
done

# Validate required arguments
if [[ ${#PROJECTS[@]} -eq 0 ]]; then
    log_error "Usage: run-e2e.sh --projects <project1> [project2] ... [options]"
    log_error "Options: --workers <n> --test <filter> --headed --debug --ui --slowmo <ms>"
    exit 1
fi

# Change to repo root
cd "$(get_repo_root)"

E2E_DIR="packages/e2e"

log_step "Running E2E tests for projects: ${PROJECTS[*]}"

for project in "${PROJECTS[@]}"; do
    log_step "Running E2E tests: $project"

    CMD=(npx playwright test "--project=$project")
    if [[ -n "$WORKERS" ]]; then
        CMD+=("--workers=$WORKERS")
    fi
    if [[ ${#TEST_FILTERS[@]} -gt 0 ]]; then
        CMD+=("${TEST_FILTERS[@]}")
    fi
    if [[ "$HEADED" == "true" ]]; then
        CMD+=("--headed")
    fi
    if [[ "$DEBUG" == "true" ]]; then
        CMD+=("--debug")
    fi
    if [[ "$UI" == "true" ]]; then
        CMD+=("--ui")
    fi

    # Build environment variables (slowmo is passed via env, not CLI)
    ENV_VARS=()
    if [[ -n "$SLOWMO" ]]; then
        ENV_VARS+=("PWSLOWMO=$SLOWMO")
    fi

    if (cd "$E2E_DIR" && env ${ENV_VARS[@]+"${ENV_VARS[@]}"} "${CMD[@]}"); then
        log_info "E2E tests passed: $project"
    else
        log_error "E2E tests failed: $project"
        exit 1
    fi
done

log_info "All E2E tests passed"
