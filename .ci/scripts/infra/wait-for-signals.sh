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

# Ensure clean exit on cancellation (GitHub Actions sends SIGINT on force-cancel)
trap 'log_warn "Caught termination signal, exiting..."; exit 1' INT TERM

# Parse arguments
parse_args "$@"

TIMEOUT="${ARG_TIMEOUT:-7200}"
INTERVAL="${ARG_INTERVAL:-30}"

# Validate required environment variables
require_var GH_TOKEN
require_var GITHUB_REPOSITORY
require_var GITHUB_RUN_ID

# Run attempt for attempt-scoped artifact names (default: 1)
RUN_ATTEMPT="${GITHUB_RUN_ATTEMPT:-1}"
ATTEMPT_SUFFIX="-attempt-${RUN_ATTEMPT}"

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

log_step "Waiting for $EXPECTED_COUNT completion signals (attempt: ${RUN_ATTEMPT}, timeout: ${TIMEOUT}s)..."
log_info "CLI platforms: ${CLI_PLATFORMS[*]}"
log_info "E2E browsers: ${E2E_BROWSERS_ARR[*]}"
# TODO: Re-enable when resolution/device tests are active
# log_info "E2E resolutions: ${E2E_RESOLUTIONS[*]}"
# log_info "E2E devices: ${E2E_DEVICES[*]}"
log_info "E2E Electron: ${E2E_ELECTRON[*]}"

# Track completed signals and failed signals
declare -a COMPLETED=()
declare -a FAILED_SIGNALS=()

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

# Helper to check if signal indicates failure
is_signal_failed() {
    local signal="$1"
    for failed in "${FAILED_SIGNALS[@]:-}"; do
        [[ "$failed" == "$signal" ]] && return 0
    done
    return 1
}

# Check signal status by downloading and reading artifact content
check_signal_status() {
    local signal="$1"
    local artifact_name="$2"
    local temp_dir
    temp_dir=$(mktemp -d)

    # Download the artifact
    if gh run download "$GITHUB_RUN_ID" --name "$artifact_name" --dir "$temp_dir" 2>/dev/null; then
        # Read the status from complete.txt
        local status
        status=$(cat "$temp_dir/complete.txt" 2>/dev/null || echo "unknown")
        rm -rf "$temp_dir"

        # Check if status indicates failure
        if [[ "$status" == "failure" ]] || [[ "$status" == "cancelled" ]]; then
            if ! is_signal_failed "$signal"; then
                FAILED_SIGNALS+=("$signal")
                log_error "Signal $signal reported status: $status"
            fi
            return 1  # Signal indicates failure
        fi
        return 0  # Success
    fi

    rm -rf "$temp_dir"
    return 2  # Not found or download failed
}

# Try to find a signal artifact, falling back to previous attempts on rerun.
# When "Rerun Failed Jobs" bumps github.run_attempt to N, jobs that already
# succeeded in attempt N-1 are NOT rerun and will never produce attempt-N
# artifacts.  We accept a previous attempt's SUCCESS signal as valid, but
# ignore previous FAILURE signals (those jobs should be rerunning now).
#
# Arguments: $1 = signal name, $2 = artifact base name (without -attempt-N), $3 = artifacts list
try_signal() {
    local signal="$1"
    local artifact_base="$2"
    local artifacts="$3"

    is_completed "$signal" && return 0

    # 1. Try current attempt
    local artifact_name="${artifact_base}${ATTEMPT_SUFFIX}"
    if echo "$artifacts" | grep -q "^${artifact_name}$"; then
        mark_completed "$signal"
        check_signal_status "$signal" "$artifact_name" || true
        return 0
    fi

    # 2. Fallback to previous attempts (newest first)
    if [[ "$RUN_ATTEMPT" -gt 1 ]]; then
        local attempt
        for (( attempt = RUN_ATTEMPT - 1; attempt >= 1; attempt-- )); do
            local fallback_name="${artifact_base}-attempt-${attempt}"
            if echo "$artifacts" | grep -q "^${fallback_name}$"; then
                local ret=0
                check_signal_status "$signal" "$fallback_name" || ret=$?
                if [[ $ret -eq 0 ]]; then
                    # Previous attempt succeeded — job was not rerun, accept it
                    mark_completed "$signal"
                    return 0
                fi
                # ret == 1 (failure/cancelled): job should be rerunning now,
                #          wait for the current attempt's artifact instead.
                # ret == 2 (download error): try an even older attempt.
                [[ $ret -eq 1 ]] && return 1
            fi
        done
    fi

    return 1
}

# Fetch artifacts and check for completion signals
fetch_and_check_signals() {
    # Fetch current artifacts
    local artifacts
    artifacts=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts" --paginate --jq '.artifacts[].name' 2>/dev/null || echo "")

    # Check CLI platforms
    for platform in "${CLI_PLATFORMS[@]}"; do
        try_signal "cli-${platform}" "test-complete-cli-${platform}" "$artifacts"
    done

    # Check E2E browsers
    for browser in "${E2E_BROWSERS_ARR[@]}"; do
        try_signal "e2e-${browser}" "test-complete-e2e-${browser}" "$artifacts"
    done

    # TODO: Re-enable when resolution tests are active
    # for resolution in "${E2E_RESOLUTIONS[@]}"; do
    #     try_signal "e2e-${resolution}" "test-complete-e2e-${resolution}" "$artifacts"
    # done

    # TODO: Re-enable when device tests are active
    # for device in "${E2E_DEVICES[@]}"; do
    #     try_signal "e2e-${device}" "test-complete-e2e-${device}" "$artifacts"
    # done

    # Check E2E Electron platforms
    for platform in "${E2E_ELECTRON[@]}"; do
        try_signal "e2e-${platform}" "test-complete-e2e-${platform}" "$artifacts"
    done
}

# Check if any signals have failed
has_failures() {
    [[ ${#FAILED_SIGNALS[@]} -gt 0 ]]
}

# Condition: all signals received OR any failure detected
all_signals_received() {
    fetch_and_check_signals
    # Exit immediately on any failure - don't wait for remaining signals
    if has_failures; then
        return 0
    fi
    [[ ${#COMPLETED[@]} -ge $EXPECTED_COUNT ]]
}

# Progress callback
on_poll() {
    local elapsed="$1"
    local timeout="$2"
    log_debug "Waiting... (${elapsed}s / ${timeout}s) - Completed: ${#COMPLETED[@]}/${EXPECTED_COUNT}"
}

# Main wait loop using poll_with_watchdog
if poll_with_watchdog "$TIMEOUT" "$INTERVAL" all_signals_received on_poll; then
    # Check for failures (exits early on first failure detection)
    if has_failures; then
        log_error "${#FAILED_SIGNALS[@]} signal(s) reported failure: ${FAILED_SIGNALS[*]}"
        log_error "Exiting immediately — failed tests detected."
        exit 1
    fi
    log_info "All $EXPECTED_COUNT signals received successfully!"
    exit 0
fi

# Timeout reached
log_warn "Timeout reached after ${TIMEOUT}s"
log_warn "Completed: ${#COMPLETED[@]}/${EXPECTED_COUNT}"
if [[ ${#COMPLETED[@]} -gt 0 ]]; then
    log_info "Received signals: ${COMPLETED[*]}"
fi
if has_failures; then
    log_error "Failed signals: ${FAILED_SIGNALS[*]}"
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
