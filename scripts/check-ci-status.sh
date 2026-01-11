#!/bin/bash
# Check GitHub Actions CI status after push
# Returns JSON for Stop hook: {"decision": "block", "reason": "..."} or allows stop

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Get repository info from git remote
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE_URL" ]; then
    # No remote, allow stop
    exit 0
fi

# Extract owner/repo from remote URL
if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
else
    # Not a GitHub repo, allow stop
    exit 0
fi

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [ -z "$BRANCH" ]; then
    exit 0
fi

# Check if we recently pushed (within last 5 minutes)
LAST_PUSH_FILE="/tmp/.claude-last-push-${OWNER}-${REPO}-${BRANCH}"
if [ ! -f "$LAST_PUSH_FILE" ]; then
    # No recent push tracked, allow stop
    exit 0
fi

LAST_PUSH_TIME=$(cat "$LAST_PUSH_FILE" 2>/dev/null || echo "0")
CURRENT_TIME=$(date +%s)
TIME_DIFF=$((CURRENT_TIME - LAST_PUSH_TIME))

# Only check CI if pushed within last 10 minutes
if [ "$TIME_DIFF" -gt 600 ]; then
    rm -f "$LAST_PUSH_FILE"
    exit 0
fi

# Check GitHub token
if [ -z "$GITHUB_TOKEN" ] && [ -z "$GH_TOKEN" ]; then
    # Try to get token from gh CLI
    GITHUB_TOKEN=$(gh auth token 2>/dev/null || echo "")
fi
TOKEN="${GITHUB_TOKEN:-$GH_TOKEN}"

if [ -z "$TOKEN" ]; then
    # No token available, allow stop
    exit 0
fi

# Get current commit SHA
COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "")
if [ -z "$COMMIT_SHA" ]; then
    exit 0
fi

# Wait a moment for CI to start (GitHub needs time to register the push)
sleep 3

# Get check runs for the commit
RESPONSE=$(curl -s -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    "https://api.github.com/repos/$OWNER/$REPO/commits/$COMMIT_SHA/check-runs" 2>/dev/null || echo "{}")

TOTAL_COUNT=$(echo "$RESPONSE" | jq -r '.total_count // 0' 2>/dev/null || echo "0")

# If no checks yet, might still be starting
if [ "$TOTAL_COUNT" = "0" ]; then
    # Check workflow runs instead
    WORKFLOW_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" \
        -H "Accept: application/vnd.github.v3+json" \
        "https://api.github.com/repos/$OWNER/$REPO/actions/runs?head_sha=$COMMIT_SHA&per_page=5" 2>/dev/null || echo "{}")

    WORKFLOW_COUNT=$(echo "$WORKFLOW_RESPONSE" | jq -r '.total_count // 0' 2>/dev/null || echo "0")

    if [ "$WORKFLOW_COUNT" = "0" ]; then
        # No workflows yet, CI might still be starting - wait and check again
        sleep 5
        WORKFLOW_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/$OWNER/$REPO/actions/runs?head_sha=$COMMIT_SHA&per_page=5" 2>/dev/null || echo "{}")
        WORKFLOW_COUNT=$(echo "$WORKFLOW_RESPONSE" | jq -r '.total_count // 0' 2>/dev/null || echo "0")
    fi

    if [ "$WORKFLOW_COUNT" = "0" ]; then
        # Still no workflows, allow stop
        rm -f "$LAST_PUSH_FILE"
        exit 0
    fi

    # Check workflow status
    IN_PROGRESS=$(echo "$WORKFLOW_RESPONSE" | jq -r '[.workflow_runs[] | select(.status == "in_progress" or .status == "queued")] | length' 2>/dev/null || echo "0")
    FAILED=$(echo "$WORKFLOW_RESPONSE" | jq -r '[.workflow_runs[] | select(.conclusion == "failure")] | length' 2>/dev/null || echo "0")

    if [ "$IN_PROGRESS" -gt 0 ]; then
        echo "⏳ CI is still running. Waiting for completion..."
        # Block and wait
        echo '{"decision": "block", "reason": "CI is still running. Please wait for CI to complete before stopping. You can check status with: gh run list --limit 3"}'
        exit 0
    fi

    if [ "$FAILED" -gt 0 ]; then
        # Get failure details
        FAILED_RUNS=$(echo "$WORKFLOW_RESPONSE" | jq -r '[.workflow_runs[] | select(.conclusion == "failure")] | .[0]' 2>/dev/null)
        RUN_ID=$(echo "$FAILED_RUNS" | jq -r '.id' 2>/dev/null)
        RUN_NAME=$(echo "$FAILED_RUNS" | jq -r '.name' 2>/dev/null)

        # Get job failures
        JOBS_RESPONSE=$(curl -s -H "Authorization: token $TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/$OWNER/$REPO/actions/runs/$RUN_ID/jobs" 2>/dev/null || echo "{}")

        FAILED_JOBS=$(echo "$JOBS_RESPONSE" | jq -r '[.jobs[] | select(.conclusion == "failure")] | map(.name) | join(", ")' 2>/dev/null || echo "unknown")

        echo "❌ CI FAILED: $RUN_NAME"
        echo "Failed jobs: $FAILED_JOBS"
        echo ""
        echo '{"decision": "block", "reason": "CI is failing! Please investigate and fix the issues. Run: gh run view '"$RUN_ID"' --log-failed to see error details. Failed jobs: '"$FAILED_JOBS"'"}'
        exit 0
    fi

    # All passed
    rm -f "$LAST_PUSH_FILE"
    exit 0
fi

# Parse check runs
IN_PROGRESS=$(echo "$RESPONSE" | jq -r '[.check_runs[] | select(.status == "in_progress" or .status == "queued")] | length' 2>/dev/null || echo "0")
FAILED=$(echo "$RESPONSE" | jq -r '[.check_runs[] | select(.conclusion == "failure")] | length' 2>/dev/null || echo "0")

if [ "$IN_PROGRESS" -gt 0 ]; then
    echo "⏳ CI checks still running..."
    echo '{"decision": "block", "reason": "CI checks are still running. Please wait for completion."}'
    exit 0
fi

if [ "$FAILED" -gt 0 ]; then
    FAILED_CHECKS=$(echo "$RESPONSE" | jq -r '[.check_runs[] | select(.conclusion == "failure")] | map(.name) | join(", ")' 2>/dev/null || echo "unknown")
    echo "❌ CI FAILED"
    echo "Failed checks: $FAILED_CHECKS"
    echo '{"decision": "block", "reason": "CI checks failed: '"$FAILED_CHECKS"'. Please investigate with: gh run list --limit 3 and fix the issues."}'
    exit 0
fi

# All checks passed
rm -f "$LAST_PUSH_FILE"
echo "✅ CI passed"
exit 0
