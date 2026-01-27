#!/bin/bash
# Check for Claude attribution in commits and PR description
#
# This script ensures commits don't contain Claude co-author attribution
# or AI-generated markers that should not be in production code.
#
# Usage:
#   GITHUB_TOKEN=xxx PR_NUMBER=123 ./check-claude-attribution.sh

set -euo pipefail

# Validate required environment variables
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "GITHUB_TOKEN is required"
    exit 1
fi

if [[ -z "${PR_NUMBER:-}" ]]; then
    echo "PR_NUMBER not set - skipping Claude attribution check (not a pull request)"
    exit 0
fi

REPO="${GITHUB_REPOSITORY:-rediacc/console}"
ISSUES=()

echo "Checking for Claude attribution in PR #${PR_NUMBER}..."

# Pattern to match Claude attribution (case-insensitive)
# Matches: Co-Authored-By: Claude, Generated with Claude, etc.
CLAUDE_PATTERN="(Co-Authored-By.*Claude|Generated with.*Claude|Claude Code|Claude Opus|Claude Sonnet|noreply@anthropic\.com)"

# Check PR description
echo "  Checking PR description..."
PR_BODY=$(gh api "repos/${REPO}/pulls/${PR_NUMBER}" --jq '.body // ""' 2>/dev/null || echo "")

if echo "$PR_BODY" | grep -qiE "$CLAUDE_PATTERN"; then
    MATCH=$(echo "$PR_BODY" | grep -iE "$CLAUDE_PATTERN" | head -1)
    ISSUES+=("PR description contains: \"${MATCH}\"")
fi

# Check commit messages
echo "  Checking commit messages..."
COMMITS=$(gh api "repos/${REPO}/pulls/${PR_NUMBER}/commits" --paginate --jq '.[].sha' 2>/dev/null || echo "")

for SHA in $COMMITS; do
    COMMIT_MSG=$(gh api "repos/${REPO}/commits/${SHA}" --jq '.commit.message' 2>/dev/null || echo "")

    if echo "$COMMIT_MSG" | grep -qiE "$CLAUDE_PATTERN"; then
        SHORT_SHA="${SHA:0:7}"
        MATCH=$(echo "$COMMIT_MSG" | grep -iE "$CLAUDE_PATTERN" | head -1)
        ISSUES+=("Commit ${SHORT_SHA} contains: \"${MATCH}\"")
    fi
done

# Check commit authors
echo "  Checking commit authors..."
for SHA in $COMMITS; do
    AUTHOR_NAME=$(gh api "repos/${REPO}/commits/${SHA}" --jq '.commit.author.name' 2>/dev/null || echo "")
    AUTHOR_EMAIL=$(gh api "repos/${REPO}/commits/${SHA}" --jq '.commit.author.email' 2>/dev/null || echo "")

    if echo "$AUTHOR_NAME $AUTHOR_EMAIL" | grep -qiE "(claude|anthropic)"; then
        SHORT_SHA="${SHA:0:7}"
        ISSUES+=("Commit ${SHORT_SHA} authored by: ${AUTHOR_NAME} <${AUTHOR_EMAIL}>")
    fi
done

if [[ ${#ISSUES[@]} -eq 0 ]]; then
    echo "No Claude attribution found - OK"
    exit 0
fi

# Found issues
echo ""
echo "============================================================"
echo "  Claude Attribution Detected"
echo "============================================================"
echo ""
echo "Found ${#ISSUES[@]} instance(s) of Claude attribution:"
echo ""
for issue in "${ISSUES[@]}"; do
    echo "  - ${issue}"
done
echo ""
echo "------------------------------------------------------------"
echo "Please remove Claude attribution before merging."
echo ""
echo "To fix commit messages, use interactive rebase:"
echo ""
echo "  git rebase -i HEAD~N  # where N is number of commits"
echo "  # Change 'pick' to 'reword' for commits to edit"
echo "  # Remove Co-Authored-By lines and save"
echo "  git push --force"
echo ""
echo "To fix PR description:"
echo ""
echo "  gh pr edit ${PR_NUMBER} --body \"\$(gh pr view ${PR_NUMBER} --json body -q .body | sed '/Claude/d')\""
echo ""
echo "Or edit directly on GitHub:"
echo "  https://github.com/${REPO}/pull/${PR_NUMBER}"
echo "------------------------------------------------------------"
exit 1
