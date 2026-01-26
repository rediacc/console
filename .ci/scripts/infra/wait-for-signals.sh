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

# Fetch artifacts and check for completion signals
fetch_and_check_signals() {
    # Fetch current artifacts
    local artifacts
    artifacts=$(gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts" --paginate --jq '.artifacts[].name' 2>/dev/null || echo "")

    # Check CLI platforms
    for platform in "${CLI_PLATFORMS[@]}"; do
        local artifact_name="test-complete-cli-${platform}"
        if echo "$artifacts" | grep -q "^${artifact_name}$"; then
            if ! is_completed "cli-${platform}"; then
                mark_completed "cli-${platform}"
                # Check signal status
                check_signal_status "cli-${platform}" "$artifact_name" || true
            fi
        fi
    done

    # Check E2E browsers
    for browser in "${E2E_BROWSERS_ARR[@]}"; do
        local artifact_name="test-complete-e2e-${browser}"
        if echo "$artifacts" | grep -q "^${artifact_name}$"; then
            if ! is_completed "e2e-${browser}"; then
                mark_completed "e2e-${browser}"
                # Check signal status
                check_signal_status "e2e-${browser}" "$artifact_name" || true
            fi
        fi
    done

    # TODO: Re-enable when resolution tests are active
    # for resolution in "${E2E_RESOLUTIONS[@]}"; do
    #     if echo "$artifacts" | grep -q "^test-complete-e2e-${resolution}$"; then
    #         mark_completed "e2e-${resolution}"
    #     fi
    # done

    # TODO: Re-enable when device tests are active
    # for device in "${E2E_DEVICES[@]}"; do
    #     if echo "$artifacts" | grep -q "^test-complete-e2e-${device}$"; then
    #         mark_completed "e2e-${device}"
    #     fi
    # done

    # Check E2E Electron platforms
    for platform in "${E2E_ELECTRON[@]}"; do
        local artifact_name="test-complete-e2e-${platform}"
        if echo "$artifacts" | grep -q "^${artifact_name}$"; then
            if ! is_completed "e2e-${platform}"; then
                mark_completed "e2e-${platform}"
                # Check signal status
                check_signal_status "e2e-${platform}" "$artifact_name" || true
            fi
        fi
    done
}

# Check if any signals have failed
has_failures() {
    [[ ${#FAILED_SIGNALS[@]} -gt 0 ]]
}

# Wait for failed signals to be updated to success (from retried jobs)
wait_for_retry_success() {
    local retry_timeout=$TIMEOUT  # Use same 2-hour timeout
    local start_time=$(date +%s)

    while [[ ${#FAILED_SIGNALS[@]} -gt 0 ]]; do
        local now=$(date +%s)
        local elapsed=$((now - start_time))

        if [[ $elapsed -ge $retry_timeout ]]; then
            log_error "Retry timeout reached after ${elapsed}s"
            return 1
        fi

        log_info "Checking failed signals for retry success... (${elapsed}s / ${retry_timeout}s)"

        # Re-check each failed signal
        local still_failed=()
        for signal in "${FAILED_SIGNALS[@]}"; do
            local artifact_name
            case "$signal" in
                cli-*) artifact_name="test-complete-${signal}" ;;
                e2e-*) artifact_name="test-complete-${signal}" ;;
                *) artifact_name="test-complete-${signal}" ;;
            esac

            # Re-download and check status
            local temp_dir=$(mktemp -d)
            if gh run download "$GITHUB_RUN_ID" --name "$artifact_name" --dir "$temp_dir" 2>/dev/null; then
                local status=$(cat "$temp_dir/complete.txt" 2>/dev/null || echo "unknown")
                if [[ "$status" == "success" ]]; then
                    log_info "Signal $signal now reports SUCCESS (retry succeeded)"
                else
                    still_failed+=("$signal")
                fi
            else
                still_failed+=("$signal")
            fi
            rm -rf "$temp_dir"
        done

        FAILED_SIGNALS=("${still_failed[@]}")

        if [[ ${#FAILED_SIGNALS[@]} -eq 0 ]]; then
            return 0
        fi

        log_info "Still waiting for ${#FAILED_SIGNALS[@]} signals: ${FAILED_SIGNALS[*]}"
        sleep "$INTERVAL"
    done

    return 0
}

# Condition: all signals received
all_signals_received() {
    fetch_and_check_signals
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
    # All signals received - check for failures
    if has_failures; then
        log_warn "All $EXPECTED_COUNT signals received, but ${#FAILED_SIGNALS[@]} reported failure!"
        log_warn "Failed signals: ${FAILED_SIGNALS[*]}"
        log_info "Keeping tunnel alive for retries. Re-polling failed signals..."

        # Continue polling failed signals until they succeed or timeout
        if wait_for_retry_success; then
            log_info "All retries succeeded!"
            exit 0
        else
            log_error "Retries did not succeed within timeout"
            exit 1
        fi
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
