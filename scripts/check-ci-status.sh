#!/bin/bash
# Check GitHub Actions CI status after push
# Returns JSON for Stop hook: {"decision": "block", "reason": "..."} or allows stop
# Version: 1.3.0 - Added acknowledgment mechanism for unrelated failures

set -e

# Shared instructions for AI when CI fails
# Usage: printf "$AI_INSTRUCTIONS" "$RUN_ID" "$ACK_FILE" "$ACK_FILE"
AI_INSTRUCTIONS='
=== INSTRUCTIONS FOR AI ===
CI has failed. Investigate and take action:

1. INVESTIGATE: Run '\''gh run view %s --log-failed'\'' to see the error output

2. DETERMINE CAUSE:
   A) If failure is RELATED to your changes → FIX IT
      - Implement a proper solution (no workarounds)
      - Commit and push the fix

   B) If failure is UNRELATED to your changes (pre-existing/flaky test) → ACKNOWLEDGE IT
      - Create acknowledgment: echo "REASON" > %s
      - Example: echo "Pre-existing flaky test - unrelated to config changes" > %s
      - Then continue with your work

3. DO NOT use lint suppressions or test skips just to pass CI.

The acknowledgment file is temporary and cleaned up after CI passes or on next push.
==========================='

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Get repository info from git remote
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE_URL" ]; then
    exit 0
fi

# Extract owner/repo from remote URL
if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
else
    exit 0
fi

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ -z "$BRANCH" ]; then
    exit 0
fi
# Sanitize branch name (replace / with -)
BRANCH_SAFE="${BRANCH//\//-}"

# Check if we recently pushed
LAST_PUSH_FILE="/tmp/.claude-last-push-${OWNER}-${REPO}-${BRANCH_SAFE}"
if [ ! -f "$LAST_PUSH_FILE" ]; then
    exit 0
fi

# Parse push file: timestamp:commit_sha:status:session_id
PUSH_DATA=$(cat "$LAST_PUSH_FILE" 2>/dev/null || echo "0:::")
LAST_PUSH_TIME=$(echo "$PUSH_DATA" | cut -d: -f1)
PUSHED_SHA=$(echo "$PUSH_DATA" | cut -d: -f2)
NOTIFY_STATUS=$(echo "$PUSH_DATA" | cut -d: -f3)
PUSH_SESSION_ID=$(echo "$PUSH_DATA" | cut -d: -f4)

# Get current session ID (must match push session)
CURRENT_SESSION_ID="${CLAUDE_SESSION_ID:-$PPID}"

# Only check CI if push was made in THIS session
if [ -n "$PUSH_SESSION_ID" ] && [ "$PUSH_SESSION_ID" != "$CURRENT_SESSION_ID" ]; then
    # Push was made in a different session - not our concern
    exit 0
fi

CURRENT_TIME=$(date +%s)
TIME_DIFF=$((CURRENT_TIME - LAST_PUSH_TIME))

# Only check CI if pushed within last 10 minutes
if [ "$TIME_DIFF" -gt 600 ]; then
    rm -f "$LAST_PUSH_FILE"
    exit 0
fi

# If we already notified about this failure, don't block again
if [ "$NOTIFY_STATUS" = "notified" ]; then
    exit 0
fi

# Check GitHub token
if [ -z "$GITHUB_TOKEN" ] && [ -z "$GH_TOKEN" ]; then
    GITHUB_TOKEN=$(gh auth token 2>/dev/null || echo "")
fi
TOKEN="${GITHUB_TOKEN:-$GH_TOKEN}"

if [ -z "$TOKEN" ]; then
    exit 0
fi

# Use the pushed commit SHA (not current HEAD, which may have changed)
COMMIT_SHA="$PUSHED_SHA"
if [ -z "$COMMIT_SHA" ]; then
    COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "")
fi
if [ -z "$COMMIT_SHA" ]; then
    exit 0
fi

# Helper function to mark as notified (prevents repeated blocking)
mark_notified() {
    echo "${LAST_PUSH_TIME}:${PUSHED_SHA}:notified:${PUSH_SESSION_ID}" > "$LAST_PUSH_FILE"
}

# Get acknowledgment file path for a specific run
get_ack_file() {
    local run_id="$1"
    echo "/tmp/.claude-ci-ack-${OWNER}-${REPO}-${BRANCH_SAFE}-${run_id}"
}

# Check if failure is acknowledged
is_acknowledged() {
    local run_id="$1"
    local ack_file=$(get_ack_file "$run_id")
    if [ -f "$ack_file" ]; then
        local reason=$(cat "$ack_file" 2>/dev/null || echo "")
        if [ -n "$reason" ]; then
            echo "✓ CI failure acknowledged: $reason"
            return 0
        fi
    fi
    return 1
}

# Clean up old acknowledgment files (older than 1 hour)
cleanup_old_acks() {
    find /tmp -name ".claude-ci-ack-${OWNER}-${REPO}-*" -mmin +60 -delete 2>/dev/null || true
}

# Wait a moment for CI to start
sleep 3

# Get check runs for the commit
RESPONSE=$(curl -s -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/$OWNER/$REPO/commits/$COMMIT_SHA/check-runs" 2>/dev/null || echo "{}")

TOTAL_COUNT=$(echo "$RESPONSE" | jq -r '.total_count // 0' 2>/dev/null || echo "0")

# If no checks yet, check workflow runs
if [ "$TOTAL_COUNT" = "0" ]; then
    WORKFLOW_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/repos/$OWNER/$REPO/actions/runs?head_sha=$COMMIT_SHA&per_page=5" 2>/dev/null || echo "{}")

    WORKFLOW_COUNT=$(echo "$WORKFLOW_RESPONSE" | jq -r '.total_count // 0' 2>/dev/null || echo "0")

    if [ "$WORKFLOW_COUNT" = "0" ]; then
        sleep 5
        WORKFLOW_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/$OWNER/$REPO/actions/runs?head_sha=$COMMIT_SHA&per_page=5" 2>/dev/null || echo "{}")
        WORKFLOW_COUNT=$(echo "$WORKFLOW_RESPONSE" | jq -r '.total_count // 0' 2>/dev/null || echo "0")
    fi

    if [ "$WORKFLOW_COUNT" = "0" ]; then
        rm -f "$LAST_PUSH_FILE"
        exit 0
    fi

    # Check workflow status
    IN_PROGRESS=$(echo "$WORKFLOW_RESPONSE" | jq -r '[.workflow_runs[] | select(.status == "in_progress" or .status == "queued")] | length' 2>/dev/null || echo "0")
    FAILED=$(echo "$WORKFLOW_RESPONSE" | jq -r '[.workflow_runs[] | select(.conclusion == "failure")] | length' 2>/dev/null || echo "0")

    if [ "$IN_PROGRESS" -gt 0 ]; then
        echo '{"decision":"block","reason":"CI is still running. Please wait for CI to complete. Check status with: gh run list --limit 3"}'
        exit 0
    fi

    if [ "$FAILED" -gt 0 ]; then
        FAILED_RUNS=$(echo "$WORKFLOW_RESPONSE" | jq -r '[.workflow_runs[] | select(.conclusion == "failure")] | .[0]' 2>/dev/null)
        RUN_ID=$(echo "$FAILED_RUNS" | jq -r '.id' 2>/dev/null)

        # Check if this failure has been acknowledged
        if is_acknowledged "$RUN_ID"; then
            cleanup_old_acks
            rm -f "$LAST_PUSH_FILE"
            exit 0
        fi

        FAILED_JOBS=$(curl -s -H "Authorization: token $TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/$OWNER/$REPO/actions/runs/$RUN_ID/jobs" 2>/dev/null | \
            jq -r '[.jobs[] | select(.conclusion == "failure")] | map(.name) | join(", ")' 2>/dev/null || echo "unknown")

        mark_notified
        ACK_FILE=$(get_ack_file "$RUN_ID")
        INSTRUCTIONS=$(printf "$AI_INSTRUCTIONS" "$RUN_ID" "$ACK_FILE" "$ACK_FILE")
        echo "{\"decision\":\"block\",\"reason\":\"CI FAILED! Failed jobs: $FAILED_JOBS$INSTRUCTIONS\"}"
        exit 0
    fi

    rm -f "$LAST_PUSH_FILE"
    exit 0
fi

# Parse check runs
IN_PROGRESS=$(echo "$RESPONSE" | jq -r '[.check_runs[] | select(.status == "in_progress" or .status == "queued")] | length' 2>/dev/null || echo "0")
FAILED=$(echo "$RESPONSE" | jq -r '[.check_runs[] | select(.conclusion == "failure")] | length' 2>/dev/null || echo "0")

if [ "$IN_PROGRESS" -gt 0 ]; then
    echo '{"decision":"block","reason":"CI checks are still running. Please wait for completion."}'
    exit 0
fi

if [ "$FAILED" -gt 0 ]; then
    FAILED_CHECKS=$(echo "$RESPONSE" | jq -r '[.check_runs[] | select(.conclusion == "failure")] | map(.name) | join(", ")' 2>/dev/null || echo "unknown")
    # Get run ID for the failed checks
    CHECK_RUN_ID=$(gh run list --limit 1 --json databaseId --jq '.[0].databaseId' 2>/dev/null || echo "")

    # Check if this failure has been acknowledged
    if is_acknowledged "$CHECK_RUN_ID"; then
        cleanup_old_acks
        rm -f "$LAST_PUSH_FILE"
        exit 0
    fi

    mark_notified
    ACK_FILE=$(get_ack_file "$CHECK_RUN_ID")
    INSTRUCTIONS=$(printf "$AI_INSTRUCTIONS" "$CHECK_RUN_ID" "$ACK_FILE" "$ACK_FILE")
    echo "{\"decision\":\"block\",\"reason\":\"CI checks failed: $FAILED_CHECKS$INSTRUCTIONS\"}"
    exit 0
fi

# All checks passed
rm -f "$LAST_PUSH_FILE"
exit 0
