#!/bin/bash
# Check GitHub Actions CI status after push
# Returns JSON for Stop hook: {"decision": "block", "reason": "..."} or allows stop
# Version: 1.2.0 - Added AI instructions for CI failures

set -e

# Shared instructions for AI when CI fails
# Usage: printf "$AI_INSTRUCTIONS" "$RUN_ID"
AI_INSTRUCTIONS='
=== INSTRUCTIONS FOR AI ===
You MUST fix CI failures before proceeding. Follow these steps:

1. INVESTIGATE: Run '\''gh run view %s --log-failed'\'' to see the actual error output
2. DIAGNOSE: Identify the root cause - do not guess or assume
3. FIX PROPERLY: Implement a proper long-term solution
   - Do NOT use workarounds, quick fixes, or '\''skip'\'' options
   - Do NOT add try/catch blocks just to silence errors
   - Do NOT disable tests or checks that are failing
   - Backward compatibility is NOT required - refactor freely if needed
4. VERIFY: Ensure your fix addresses the actual error message
5. COMMIT & PUSH: Push the fix and wait for CI to pass

If the failure is in infrastructure/external services, explain clearly why it cannot be fixed in code.
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

# Check if we recently pushed (within last 5 minutes)
LAST_PUSH_FILE="/tmp/.claude-last-push-${OWNER}-${REPO}-${BRANCH_SAFE}"
if [ ! -f "$LAST_PUSH_FILE" ]; then
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
    GITHUB_TOKEN=$(gh auth token 2>/dev/null || echo "")
fi
TOKEN="${GITHUB_TOKEN:-$GH_TOKEN}"

if [ -z "$TOKEN" ]; then
    exit 0
fi

# Get current commit SHA
COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "")
if [ -z "$COMMIT_SHA" ]; then
    exit 0
fi

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
        FAILED_JOBS=$(curl -s -H "Authorization: token $TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            "https://api.github.com/repos/$OWNER/$REPO/actions/runs/$RUN_ID/jobs" 2>/dev/null | \
            jq -r '[.jobs[] | select(.conclusion == "failure")] | map(.name) | join(", ")' 2>/dev/null || echo "unknown")

        INSTRUCTIONS=$(printf "$AI_INSTRUCTIONS" "$RUN_ID")
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

    INSTRUCTIONS=$(printf "$AI_INSTRUCTIONS" "$CHECK_RUN_ID")
    echo "{\"decision\":\"block\",\"reason\":\"CI checks failed: $FAILED_CHECKS$INSTRUCTIONS\"}"
    exit 0
fi

# All checks passed
rm -f "$LAST_PUSH_FILE"
exit 0
