#!/bin/bash
# Track when a git push happens so the Stop hook knows to check CI
# Called by PostToolUse hook after git push

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Get repository info
REMOTE_URL=$(git remote get-url origin 2>/dev/null || echo "")
if [ -z "$REMOTE_URL" ]; then
    exit 0
fi

# Extract owner/repo
if [[ "$REMOTE_URL" =~ github\.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
    OWNER="${BASH_REMATCH[1]}"
    REPO="${BASH_REMATCH[2]}"
else
    exit 0
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
# Sanitize branch name (replace / with -)
BRANCH_SAFE="${BRANCH//\//-}"
COMMIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "")

# Get session ID (use parent PID as session identifier if no explicit session ID)
SESSION_ID="${CLAUDE_SESSION_ID:-$PPID}"

# Clean up any existing acknowledgment files for this branch (new push invalidates old acks)
find /tmp -name ".claude-ci-ack-${OWNER}-${REPO}-${BRANCH_SAFE}-*" -delete 2>/dev/null || true

# Record push info (timestamp, commit SHA, status, and session ID)
LAST_PUSH_FILE="/tmp/.claude-last-push-${OWNER}-${REPO}-${BRANCH_SAFE}"
echo "$(date +%s):${COMMIT_SHA}:pending:${SESSION_ID}" > "$LAST_PUSH_FILE"

echo "📤 Push tracked. CI will be monitored."

# Check if PR exists for non-main branches
if [[ "$BRANCH" != "main" && "$BRANCH" != "master" && "$BRANCH" != "develop" ]]; then
    PR_EXISTS=$(gh pr list --head "$BRANCH" --json number --jq 'length' 2>/dev/null || echo "0")

    if [ "$PR_EXISTS" = "0" ]; then
        echo "📝 No PR exists for branch '$BRANCH'. Creating one..."

        # Get the last commit message for PR title
        COMMIT_MSG=$(git log -1 --format="%s" 2>/dev/null || echo "Update $BRANCH")

        # Create PR with auto-generated body
        PR_URL=$(gh pr create --title "$COMMIT_MSG" --body "$(cat <<EOF
## Summary
Auto-created PR for branch \`$BRANCH\`

## Changes
$(git log main..HEAD --oneline 2>/dev/null || git log origin/main..HEAD --oneline 2>/dev/null || echo "See commits")

---
*PR auto-created by Claude Code*
EOF
)" --head "$BRANCH" --base main 2>&1) && {
            echo "✅ PR created: $PR_URL"
        } || {
            echo "⚠️ Could not create PR automatically. Run: gh pr create"
        }
    fi
fi

exit 0
