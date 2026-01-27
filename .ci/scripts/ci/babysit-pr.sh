#!/bin/bash
# babysit-pr.sh - Monitor PR CI and auto-fix failures using Claude Code
#
# Features:
# - Zero-token monitoring loop (only invokes AI on failures)
# - Cancels pipeline on first failure (don't wait for full run)
# - Respects Rerun Watchdog flaky test retries before acting
# - Maintains AI session context between fix iterations
# - Enterprise-grade: no shortcuts, proper solutions only
#
# Usage:
#   .ci/scripts/ci/babysit-pr.sh
#
# Environment variables:
#   MAX_ITERATIONS   - Maximum auto-fix attempts (default: 10)
#   POLL_INTERVAL    - Seconds between CI status checks (default: 30)
#   MAX_RERUN_WAIT   - Max seconds to wait for Rerun Watchdog (default: 300)
#   SESSION_FILE     - File to persist session ID (default: /tmp/babysit-session-$$)

set -euo pipefail

# Configuration
MAX_ITERATIONS="${MAX_ITERATIONS:-10}"
POLL_INTERVAL="${POLL_INTERVAL:-30}"
MAX_RERUN_WAIT="${MAX_RERUN_WAIT:-300}"  # 5 min max wait for Rerun Watchdog
SESSION_FILE="${SESSION_FILE:-/tmp/babysit-session-$$}"
# Skip permission prompts - the AI is trusted for CI fixes
SKIP_PERMISSIONS="--dangerously-skip-permissions"

# Enterprise-grade prompt prefix
PROMPT_PREFIX="You are fixing CI failures for an enterprise software project.

IMPORTANT GUIDELINES:
- Do NOT use workarounds, hacks, or 'quick fix' solutions
- Identify and fix the ROOT CAUSE of the issue
- Ensure the fix is production-ready and maintainable
- If the issue requires architectural changes, implement them properly
- Do NOT disable tests, skip checks, or add ignore directives unless absolutely necessary
- If you previously attempted a fix that didn't work, analyze WHY and try a different approach

"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Get git repository root (works with worktrees)
get_git_root() {
    git rev-parse --show-toplevel 2>/dev/null || pwd
}

# Get PR number from current branch
get_pr_number() {
    gh pr view --json number -q '.number' 2>/dev/null || echo ""
}

# Get latest workflow run ID
get_latest_run_id() {
    gh run list --branch "$(git branch --show-current)" -L 1 --json databaseId -q '.[0].databaseId' 2>/dev/null || echo ""
}

# Get run status (in_progress, completed, queued, etc.)
get_run_status() {
    local run_id="$1"
    gh run view "$run_id" --json status -q '.status' 2>/dev/null || echo "unknown"
}

# Get run conclusion (success, failure, cancelled, etc.)
get_run_conclusion() {
    local run_id="$1"
    gh run view "$run_id" --json conclusion -q '.conclusion' 2>/dev/null || echo "unknown"
}

# Check if Rerun Watchdog is currently retrying
is_rerun_in_progress() {
    local run_id="$1"
    local rerun_status
    rerun_status=$(gh run view "$run_id" --json jobs -q '.jobs[] | select(.name | contains("Rerun")) | .status' 2>/dev/null || echo "")
    [[ "$rerun_status" == "in_progress" || "$rerun_status" == "queued" ]]
}

# Wait for Rerun Watchdog to complete (if running)
wait_for_rerun_watchdog() {
    local run_id="$1"
    local waited=0

    while is_rerun_in_progress "$run_id" && [[ $waited -lt $MAX_RERUN_WAIT ]]; do
        log_info "Rerun Watchdog is retrying flaky tests... waiting (${waited}s/${MAX_RERUN_WAIT}s)"
        sleep "$POLL_INTERVAL"
        waited=$((waited + POLL_INTERVAL))
    done

    if [[ $waited -ge $MAX_RERUN_WAIT ]]; then
        log_warn "Rerun Watchdog timeout - proceeding with fix"
    fi
}

# Cancel the current workflow run (only if still in progress)
cancel_pipeline() {
    local run_id="$1"
    local status
    status=$(get_run_status "$run_id")

    if [[ "$status" == "in_progress" || "$status" == "queued" ]]; then
        log_info "Cancelling pipeline run #$run_id..."
        gh run cancel "$run_id" 2>/dev/null || true
    else
        log_info "Pipeline run #$run_id already completed (status: $status)"
    fi
}

# Get failed job logs (truncated for context window)
get_failed_logs() {
    local run_id="$1"
    # Use || true because logs may not be available immediately after cancellation
    # Also wait a moment for logs to be flushed
    sleep 2
    gh run view "$run_id" --log-failed 2>&1 | tail -500 || echo "Failed to retrieve logs for run #$run_id"
}

# Run claude from git root directory
# Output is streamed to terminal AND captured for session ID extraction
run_claude() {
    local prompt="$1"
    local session_arg="$2"
    local output_file
    output_file=$(mktemp)

    # Run claude from git root so it has access to the full codebase
    # Use tee to show output in real-time while also capturing it
    (
        cd "$GIT_ROOT"
        if [[ -n "$session_arg" ]]; then
            claude -p "$prompt" --resume "$session_arg" --output-format stream-json $SKIP_PERMISSIONS 2>&1
        else
            claude -p "$prompt" --output-format stream-json $SKIP_PERMISSIONS 2>&1
        fi
    ) | tee "$output_file"

    # Extract final JSON result (last line with session_id)
    tail -1 "$output_file"
    rm -f "$output_file"
}

# Wait for a new CI run to start (different from the given run ID)
wait_for_new_run() {
    local old_run_id="$1"
    local max_wait=120  # 2 minutes max
    local waited=0

    log_info "Waiting for new CI run to start (current: #$old_run_id)..."

    while [[ $waited -lt $max_wait ]]; do
        local new_run_id
        new_run_id=$(get_latest_run_id)

        if [[ -n "$new_run_id" && "$new_run_id" != "$old_run_id" ]]; then
            log_success "New CI run started: #$new_run_id"
            return 0
        fi

        sleep 5
        waited=$((waited + 5))
    done

    log_warn "Timeout waiting for new CI run"
    return 1
}

# Wait for CI run to complete (polling, not --watch)
wait_for_ci_completion() {
    local run_id="$1"

    log_info "Waiting for run #$run_id to complete..."

    while true; do
        local status
        status=$(get_run_status "$run_id")

        case "$status" in
            completed)
                local conclusion
                conclusion=$(get_run_conclusion "$run_id")
                if [[ "$conclusion" == "success" ]]; then
                    return 0  # Success
                else
                    return 1  # Failed
                fi
                ;;
            in_progress|queued|waiting|pending)
                sleep "$POLL_INTERVAL"
                ;;
            *)
                log_warn "Unknown run status: $status"
                sleep "$POLL_INTERVAL"
                ;;
        esac
    done
}

# Check if there are uncommitted changes
has_uncommitted_changes() {
    ! git diff --quiet HEAD 2>/dev/null || ! git diff --cached --quiet 2>/dev/null
}

# Check if local branch is ahead of remote
has_unpushed_commits() {
    local ahead
    ahead=$(git rev-list --count @{upstream}..HEAD 2>/dev/null || echo "0")
    [[ "$ahead" -gt 0 ]]
}

# Main function
main() {
    # Detect git root first (works with worktrees)
    GIT_ROOT=$(get_git_root)

    local pr_number
    pr_number=$(get_pr_number)

    if [[ -z "$pr_number" ]]; then
        log_error "No PR found for current branch"
        echo "Make sure you're on a branch with an open PR."
        exit 1
    fi

    echo ""
    echo "=========================================="
    echo "  PR Babysitter - Monitoring PR #$pr_number"
    echo "=========================================="
    echo ""
    log_info "Git root: $GIT_ROOT"
    log_info "Max iterations: $MAX_ITERATIONS"
    log_info "Poll interval: ${POLL_INTERVAL}s"
    log_info "Max rerun wait: ${MAX_RERUN_WAIT}s"

    local iteration=0
    local session_id=""
    local last_run_id=""

    # Load existing session if available
    if [[ -f "$SESSION_FILE" ]]; then
        session_id=$(cat "$SESSION_FILE")
        log_info "Resuming session: ${session_id:0:20}..."
    fi

    while [[ $iteration -lt $MAX_ITERATIONS ]]; do
        echo ""
        echo "==========================================="
        echo "  Iteration $((iteration + 1)) of $MAX_ITERATIONS"
        echo "==========================================="

        # Step 1: Get current run and wait for it to complete
        local run_id
        run_id=$(get_latest_run_id)

        if [[ -z "$run_id" ]]; then
            log_error "Could not get run ID"
            sleep "$POLL_INTERVAL"
            continue
        fi

        # Skip if this is the same run we already processed
        if [[ "$run_id" == "$last_run_id" ]]; then
            log_info "Same run as before (#$run_id), waiting for new run..."
            if ! wait_for_new_run "$run_id"; then
                log_error "No new CI run started. Did you push changes?"
                exit 1
            fi
            run_id=$(get_latest_run_id)
        fi

        log_info "Monitoring run #$run_id..."
        last_run_id="$run_id"

        # Step 2: Wait for run to complete
        if wait_for_ci_completion "$run_id"; then
            echo ""
            echo "============================================"
            log_success "CI PASSED - PR #$pr_number is ready!"
            echo "============================================"
            rm -f "$SESSION_FILE"
            exit 0
        fi

        log_warn "Failure detected in run #$run_id"

        # Step 3: Wait for Rerun Watchdog if it's retrying
        wait_for_rerun_watchdog "$run_id"

        # Step 4: Check if issue was resolved by retry
        local final_conclusion
        final_conclusion=$(get_run_conclusion "$run_id")

        if [[ "$final_conclusion" == "success" ]]; then
            log_success "Rerun Watchdog fixed the issue!"
            continue
        fi

        # Step 5: Cancel pipeline if still running
        cancel_pipeline "$run_id"

        echo ""
        log_info "Invoking Claude Code to fix the failure..."
        echo ""

        log_info "Fetching failed job logs..."
        local failed_logs
        failed_logs=$(get_failed_logs "$run_id")

        if [[ -z "$failed_logs" ]]; then
            log_warn "No failed logs retrieved - using generic prompt"
            failed_logs="(Failed to retrieve logs - please investigate the CI failure)"
        else
            log_info "Retrieved ${#failed_logs} bytes of logs"
        fi

        local prompt="${PROMPT_PREFIX}CI has failed for PR #$pr_number. Here are the failed job logs:

\`\`\`
$failed_logs
\`\`\`

Analyze the failure, identify the root cause, and implement a proper fix.
After fixing, stage the changes and create a commit with a descriptive message."

        local result
        local claude_exit_code=0
        if [[ -n "$session_id" ]]; then
            log_info "Resuming previous session for context..."
            result=$(run_claude "$prompt" "$session_id") || claude_exit_code=$?
        else
            log_info "Starting new session..."
            result=$(run_claude "$prompt" "") || claude_exit_code=$?
        fi

        if [[ $claude_exit_code -ne 0 ]]; then
            log_warn "Claude exited with code $claude_exit_code"
        fi

        # Show Claude output for debugging
        if [[ -n "$result" ]]; then
            log_info "Claude response received (${#result} bytes)"
        else
            log_warn "No response from Claude - check if claude CLI is available"
        fi

        # Capture session ID for context persistence
        local new_session_id
        new_session_id=$(echo "$result" | jq -r '.session_id // empty' 2>/dev/null || echo "")
        if [[ -n "$new_session_id" ]]; then
            session_id="$new_session_id"
            echo "$session_id" > "$SESSION_FILE"
            log_info "Session saved for context persistence"
        fi

        # Step 6: Check if Claude made any changes
        if has_uncommitted_changes; then
            log_warn "Claude left uncommitted changes - committing them"
            (cd "$GIT_ROOT" && git add -A && git commit -m "fix(ci): auto-fix from babysit script")
        fi

        if ! has_unpushed_commits; then
            log_error "No changes to push - Claude didn't fix anything"
            log_info "You may need to fix this manually or provide more context"
            iteration=$((iteration + 1))
            continue
        fi

        # Step 7: Push changes
        log_info "Pushing changes..."
        if (cd "$GIT_ROOT" && git push); then
            log_success "Changes pushed successfully"
        else
            log_warn "Push failed - may need manual intervention"
        fi

        iteration=$((iteration + 1))
        log_info "Waiting for new CI run..."
        sleep 5
    done

    echo ""
    echo "============================================"
    log_error "MAX ITERATIONS REACHED ($MAX_ITERATIONS)"
    echo "  Manual intervention required for PR #$pr_number"
    echo "============================================"
    exit 1
}

main "$@"
