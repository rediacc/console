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

# Record push timestamp
LAST_PUSH_FILE="/tmp/.claude-last-push-${OWNER}-${REPO}-${BRANCH_SAFE}"
date +%s > "$LAST_PUSH_FILE"

echo "📤 Push tracked. CI will be monitored."
exit 0
