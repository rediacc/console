#!/bin/bash
# Wait for completion signals from parallel CI jobs
# Usage: wait-for-signals.sh [options]
#
# Polls GitHub Actions artifacts to detect when parallel jobs have completed.
# Used by long-running backend jobs to wait for test jobs to finish.
#
# Options:
#   --timeout     Maximum wait time in seconds (default: 7200)
#   --interval    Polling interval in seconds (default: 30)
#
# Required environment variables:
#   GH_TOKEN            GitHub token for API calls
#   GITHUB_REPOSITORY   Repository in owner/repo format
#   GITHUB_RUN_ID       Current workflow run ID
#   E2E_BROWSERS        Space-separated list of browsers (e.g., "chromium firefox webkit")
#
# Example:
#   .ci/scripts/infra/wait-for-signals.sh --timeout 7200
#
# Signals expected (created by .ci/scripts/signal/create-complete.sh):
#   - test-complete-cli-{Linux,Windows,macOS}
#   - test-complete-e2e-{browser}
#   - test-complete-e2e-resolution-{resolution}
#   - test-complete-e2e-{device}
#   - test-complete-e2e-electron-{platform}-{arch}

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
parse_args "$@"

TIMEOUT="${ARG_TIMEOUT:-7200}"
INTERVAL="${ARG_INTERVAL:-30}"

# Validate required environment variables
require_var GH_TOKEN
require_var GITHUB_REPOSITORY
require_var GITHUB_RUN_ID

# Define expected signals
CLI_PLATFORMS=("Linux" "Windows" "macOS")
# TODO: Re-enable when resolution/device tests are active
# E2E_RESOLUTIONS=("resolution-1920x1080" "resolution-1366x768" "resolution-1536x864")
# E2E_DEVICES=("galaxy-s24" "galaxy-tab-s9" "iphone-15-pro-max" "ipad-pro-11")
E2E_RESOLUTIONS=()
E2E_DEVICES=()
E2E_ELECTRON=("electron-linux-x64" "electron-linux-arm64" "electron-macos-x64" "electron-macos-arm64" "electron-windows-x64" "electron-windows-arm64")

# Parse E2E_BROWSERS from environment
E2E_BROWSERS_STR="${E2E_BROWSERS:-chromium}"
IFS=' ' read -ra E2E_BROWSERS_ARR <<< "$E2E_BROWSERS_STR"

# Calculate expected count
EXPECTED_COUNT=$((${#CLI_PLATFORMS[@]} + ${#E2E_BROWSERS_ARR[@]} + ${#E2E_RESOLUTIONS[@]} + ${#E2E_DEVICES[@]} + ${#E2E_ELECTRON[@]}))

log_step "Waiting for $EXPECTED_COUNT completion signals (timeout: ${TIMEOUT}s)..."
log_info "CLI platforms: ${CLI_PLATFORMS[*]}"
log_info "E2E browsers: ${E2E_BROWSERS_ARR[*]}"
# TODO: Re-enable when resolution/device tests are active
# log_info "E2E resolutions: ${E2E_RESOLUTIONS[*]}"
# log_info "E2E devices: ${E2E_DEVICES[*]}"
log_info "E2E Electron: ${E2E_ELECTRON[*]}"

# Track completed signals
declare -a COMPLETED=()
ELAPSED=0

# Helper to check if signal is already completed
is_completed() {
    local signal="$1"
    for completed in "${COMPLETED[@]:-}"; do
        [[ "$completed" == "$signal" ]] && return 0
    done
    return 1
}

# Helper to mark signal as completed
mark_completed() {
    local signal="$1"
    if ! is_completed "$signal"; then
        COMPLETED+=("$signal")
        log_info "$signal completed (${#COMPLETED[@]}/${EXPECTED_COUNT})"
    fi
}

while [[ $ELAPSED -lt $TIMEOUT ]]; do
    # Fetch current artifacts
    ARTIFACTS=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts" --jq '.artifacts[].name' 2>/dev/null || echo "")

    # Check CLI platforms
    for platform in "${CLI_PLATFORMS[@]}"; do
        if echo "$ARTIFACTS" | grep -q "^test-complete-cli-${platform}$"; then
            mark_completed "cli-${platform}"
        fi
    done

    # Check E2E browsers
    for browser in "${E2E_BROWSERS_ARR[@]}"; do
        if echo "$ARTIFACTS" | grep -q "^test-complete-e2e-${browser}$"; then
            mark_completed "e2e-${browser}"
        fi
    done

    # TODO: Re-enable when resolution tests are active
    # Check E2E resolutions
    # for resolution in "${E2E_RESOLUTIONS[@]}"; do
    #     if echo "$ARTIFACTS" | grep -q "^test-complete-e2e-${resolution}$"; then
    #         mark_completed "e2e-${resolution}"
    #     fi
    # done

    # TODO: Re-enable when device tests are active
    # Check E2E devices
    # for device in "${E2E_DEVICES[@]}"; do
    #     if echo "$ARTIFACTS" | grep -q "^test-complete-e2e-${device}$"; then
    #         mark_completed "e2e-${device}"
    #     fi
    # done

    # Check E2E Electron platforms
    for platform in "${E2E_ELECTRON[@]}"; do
        if echo "$ARTIFACTS" | grep -q "^test-complete-e2e-${platform}$"; then
            mark_completed "e2e-${platform}"
        fi
    done

    # Check if all completed
    if [[ ${#COMPLETED[@]} -ge $EXPECTED_COUNT ]]; then
        log_info "All $EXPECTED_COUNT signals received!"
        exit 0
    fi

    # Wait and increment
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
    log_debug "Waiting... (${ELAPSED}s / ${TIMEOUT}s) - Completed: ${#COMPLETED[@]}/${EXPECTED_COUNT}"
done

# Timeout reached
log_warn "Timeout reached after ${TIMEOUT}s"
log_warn "Completed: ${#COMPLETED[@]}/${EXPECTED_COUNT}"
if [[ ${#COMPLETED[@]} -gt 0 ]]; then
    log_info "Received signals: ${COMPLETED[*]}"
fi

# List missing signals
log_error "Missing signals:"
for platform in "${CLI_PLATFORMS[@]}"; do
    is_completed "cli-${platform}" || echo "  - cli-${platform}"
done
for browser in "${E2E_BROWSERS_ARR[@]}"; do
    is_completed "e2e-${browser}" || echo "  - e2e-${browser}"
done
# TODO: Re-enable when resolution/device tests are active
# for resolution in "${E2E_RESOLUTIONS[@]}"; do
#     is_completed "e2e-${resolution}" || echo "  - e2e-${resolution}"
# done
# for device in "${E2E_DEVICES[@]}"; do
#     is_completed "e2e-${device}" || echo "  - e2e-${device}"
# done
for platform in "${E2E_ELECTRON[@]}"; do
    is_completed "e2e-${platform}" || echo "  - e2e-${platform}"
done

exit 1
